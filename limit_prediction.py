"""Walk-forward limit continuation baseline, using local main-board daily cache."""
import json
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from strategy_sentiment_cycle import cycle

ROOT = Path(__file__).resolve().parent
LOCK = threading.Lock()
STATUS = {"running": False, "error": None}
OUT = ROOT / "data_cache" / "limit_prediction.json"


def build():
    stocks = []
    for path in sorted((ROOT / "data_cache" / "daily").glob("*.json")):
        code = path.stem.split(".")[-1]
        if not code.startswith(("000", "001", "002", "003", "600", "601", "603", "605")):
            continue
        try:
            payload = json.loads(path.read_text())
            rows = [row.split(",") if isinstance(row, str) else row for row in payload.get("klines", [])]
            stock = cycle.parse_stock(code, code, rows)
            if stock:
                stocks.append(stock)
        except (ValueError, KeyError, TypeError):
            continue
    raw = ROOT / "data_cache" / "limit_raw" / "daily.parquet"
    if raw.exists():
        try:
            import duckdb
        except ImportError:
            raise ValueError("读取未复权数据需要 duckdb，请使用已安装研究依赖的Python环境") from None
        conn = duckdb.connect()
        groups = defaultdict(list)
        query = """SELECT split_part(thscode,'.',1), strftime(to_timestamp(date_ms/1000) AT TIME ZONE 'Asia/Shanghai','%Y-%m-%d'),
                   open_price,close_price,high_price,low_price,volume,turnover
                   FROM read_parquet(?) WHERE date_ms >= epoch_ms(DATE '2024-01-01') ORDER BY thscode,date_ms"""
        for code, *row in conn.execute(query, [str(raw)]).fetchall():
            if code.startswith(("000","001","002","003","600","601","603","605")):
                groups[code].append(row)
        stocks = [record for code, rows in groups.items() if (record := cycle.parse_stock(code, code, rows))]
    days = cycle.aggregate(stocks)
    calendar = [day["date"] for day in days]
    if not calendar:
        raise ValueError("本地日线覆盖不足，无法构建有效交易日历")
    # A snapshot refresh can append today to old history. Never treat a
    # multi-week gap as the next trading session.
    from datetime import date as date_type
    records = defaultdict(list)
    for stock in stocks:
        index = {date: i for i, date in enumerate(stock["dates"])}
        for j, day in enumerate(calendar):
            i = index.get(day)
            if i is None or i < 1 or (j > 0 and stock["dates"][i-1] != calendar[j-1]) or not (stock["lu"][i] or stock["brk"][i]):
                continue
            next_day = calendar[j + 1] if j + 1 < len(calendar) else None
            ni = index.get(next_day)
            now_local = datetime.now(timezone(timedelta(hours=8)))
            # An unfinished session must not close the previous day's outcome.
            if next_day == now_local.strftime("%Y-%m-%d") and now_local.hour < 16:
                ni = None
            if next_day and (date_type.fromisoformat(next_day) - date_type.fromisoformat(day)).days > 10:
                ni = None
            records[day].append({
                "kind": "sealed" if stock["lu"][i] else "broken", "code": stock["code"], "height": stock["streak"][i],
                "onePrice": bool(stock["yizi"][i]), "close": stock["C"][i],
                "volumeRatio": stock["V"][i] / max(1, sum(stock["V"][max(0, i-5):i]) / min(i, 5)),
                "nextDate": next_day,
                "decent": stock["H"][ni] >= stock["C"][i]*1.02 if ni is not None else None,
                "redClose": stock["C"][ni] > stock["C"][i] if ni is not None else None,
                "gapDown": stock["O"][ni] <= stock["C"][i]*.97 if ni is not None else None,
                "negative": stock["C"][ni] <= stock["C"][i]*.95 if ni is not None else None,
                "nextReturn": (stock["C"][ni]/stock["C"][i]-1)*100 if ni is not None else None,
                "continued": bool(stock["lu"][ni]) if ni is not None else None,
                "touched": bool(stock["H"][ni] >= cycle.limit_px(stock["C"][i], .1) - .01) if ni is not None else None,
                "openPremium": round((stock["O"][ni] / stock["C"][i] - 1) * 100, 2) if ni is not None else None,
                "openBuyable": not cycle.is_limit_up(stock["code"], stock["C"][i], stock["O"][ni]) if ni is not None else None,
            })
    from limit_context import estimate, compare, grouped
    markets = {m["date"]: m for m in days}
    history, predictions = [], []
    for day in calendar:
        # Only labels observable by today's close enter training.
        eligible = [r for r in history if r["nextDate"] and r["nextDate"] <= day and r["continued"] is not None and r["kind"] == "sealed"]
        eligible = eligible[-20000:]
        base = sum(r["continued"] for r in eligible) / len(eligible) if eligible else None
        groups = defaultdict(list)
        for observed in eligible:
            groups[(min(observed["height"], 4), observed["onePrice"])].append(observed)
        for row in records[day]:
            peers = groups[(min(row["height"], 4), row["onePrice"])]
            n = len(peers)
            probability = (sum(r["continued"] for r in peers) + 30 * base) / (n + 30) if base is not None and n >= 50 else None
            predictions.append({**row, "date": day, "probability": round(probability * 100, 1) if probability is not None else None,
                                "samples": n, "baseline": round(base * 100, 1) if base is not None else None})
        context_groups = grouped(eligible, markets)
        for row in predictions[-len(records[day]):] if records[day] else []:
            value, count = estimate(row, markets[day], eligible, markets, row["probability"]/100 if row["probability"] is not None else None, context_groups)
            row.update(contextProbability=value, contextSamples=count)
        history.extend([{**r, "date": day} for r in records[day]])
    scored = [r for r in predictions if r["probability"] is not None and r["continued"] is not None and r["kind"] == "sealed"]
    bins = []
    for low in range(0, 100, 10):
        group = [r for r in scored if low <= r["probability"] < low + 10]
        if group:
            bins.append({"range": f"{low}–{low+10}%", "samples": len(group),
                         "predicted": round(sum(r["probability"] for r in group)/len(group),1),
                         "actual": round(sum(r["continued"] for r in group)/len(group)*100,1)})
    outcomes = []
    for kind in ("sealed", "broken"):
        sample = [r for r in predictions if r["kind"] == kind and r["continued"] is not None]
        for height in (None, 1, 2, 3):
            subset = sample if height is None else [r for r in sample if r["height"] == height]
            if not subset:
                continue
            outcomes.append({"kind": kind, "group": "全部" if height is None else str(height)+"板",
                             "samples": len(subset), "start": min(r["date"] for r in subset),
                             "end": max(r["date"] for r in subset),
                             **{key: round(sum(r[key] for r in subset)/len(subset)*100,2)
                                for key in ("continued","touched","decent","redClose","gapDown","negative")},
                             "avgNextReturn": round(sum(r["nextReturn"] for r in subset)/len(subset),2)})
    latest = calendar[-1]
    result = {"date": latest, "generatedAt": datetime.now(timezone(timedelta(hours=8))).isoformat(),
              "comparison": compare(predictions), "priceBasis": "none" if raw.exists() else "forward", "version": "daily-baseline-v2", "market": days[-1],
              "items": sorted([r for r in predictions if r["date"] == latest], key=lambda r: -(r["probability"] or -1)),
              "outcomes": outcomes, "outcomeDefinition": "体面率=次日最高价≥信号日收盘价×1.02；红盘率=次日收盘高于信号收盘；低开=≤-3%；负反馈=收盘≤-5%；价格机会非成交收益", "calibration": bins, "history": predictions[-500:],
              "warnings": ["本地前复权日线推算涨停，非交易所精确涨停价；历史ST和上市状态未完整还原。",
                           "当前为主板日线基线，未接入封单、封板时间与历史板块归属；不代表完整连板模型。",
                           "openBuyable仅表示开盘未封涨停，不能证明实际成交。"],
              "brier": round(sum((r["probability"]/100-r["continued"])**2 for r in scored)/len(scored),4) if scored else None}
    if raw.exists():
        result["warnings"][0] = "未复权日线推算涨停；历史ST、除权日参考价与新股状态未完整还原，不是交易所精确涨停名单。"
    from limit_pool import enrich, DIR
    pool_path = DIR / (latest + ".json")
    if pool_path.exists():
        pool = json.loads(pool_path.read_text())
        eligible = [r for r in history if r.get("nextDate") and r["nextDate"] <= latest and r["continued"] is not None and r["kind"] == "sealed"][-20000:]
        base = sum(r["continued"] for r in eligible)/len(eligible) if eligible else None
        current = []
        from paper_quality import market as observed_market
        try:
            current_market = observed_market(latest)
        except ValueError:
            current_market = {"phase_cn":"未确认","max_height":max((i.get("continue_day_cnt") or 1 for i in pool["items"]),default=0),"phase":None}
        result["market"] = current_market
        for item in pool["items"]:
            code = str(item.get("ticker", ""))
            if not code.startswith(("000","001","002","003","600","601","603","605")) or item.get("is_st"):
                continue
            height = item.get("continue_day_cnt") or 1
            # Pool does not specify one-price status: do not guess it.
            peers = [r for r in eligible if min(r["height"],4) == min(height,4)]
            n = len(peers)
            probability = (sum(r["continued"] for r in peers)+30*base)/(n+30) if n>=50 and base is not None else None
            context_probability, context_samples = None, 0
            current.append({"contextProbability":context_probability, "contextSamples":context_samples, "phase": current_market["phase_cn"], "spaceHeight":current_market["max_height"], "code":code, "name":item.get("name"), "height":height,
                            "close":item.get("last_price"), "date":latest,
                            "probability":round(probability*100,1) if probability is not None else None,
                            "samples":n, "baseline":round(base*100,1) if base is not None else None,
                            "source":"真实涨停池", "groupNote":"同连板高度历史组；未区分一字板"})
        result["items"] = sorted(current,key=lambda row: -(row["probability"] or 0))
        result["candidateSource"] = "同花顺真实涨停池"
        result["warnings"].append("当前概率按连板高度分组，同组同概率；封单和题材未进入模型，非个股独立概率。")
    else:
        result["items"] = []
        result["warnings"].append("缺少同日真实涨停池，暂停输出候选，避免历史缺口误判。")
    result = enrich(result, latest)
    from limit_sectors import aggregate
    result["sectors"] = aggregate(latest)
    result["intraday"] = latest == datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d") and datetime.now(timezone(timedelta(hours=8))).hour < 16
    if result["intraday"]:
        result["warnings"].append("当前是盘中快照，仅供预览，不是收盘预测。")
    result["stale"] = latest != datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
    archive = OUT.parent / "limit_predictions" / latest
    archive.mkdir(parents=True, exist_ok=True)
    # Each run is immutable; outcomes belong to separate reconstruction output.
    snapshot = {**result, "history": [], "mode": "forward" if not result["stale"] and datetime.now(timezone(timedelta(hours=8))).hour >= 16 else "reconstruction"}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    with (archive / (stamp + ".json")).open("x") as handle:
        json.dump(snapshot, handle, ensure_ascii=False)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    temp = OUT.with_suffix(".tmp")
    temp.write_text(json.dumps(result, ensure_ascii=False))
    temp.replace(OUT)
    return result


def load():
    from limit_pool import DIR
    from limit_sectors import aggregate
    today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
    path = DIR / (today + ".json")
    live = {"poolDate": today, "poolItems": json.loads(path.read_text())["items"], "currentSectors": aggregate(today)} if path.exists() else {}
    broken_path = DIR / (today + "-broken.json")
    broken = json.loads(broken_path.read_text()) if broken_path.exists() else None
    if broken:
        live.update(brokenItems=broken["items"], brokenCapturedAt=broken["capturedAt"], brokenDate=broken["date"])
    if path.exists():
        live["poolCapturedAt"] = json.loads(path.read_text()).get("capturedAt")
    return {**json.loads(OUT.read_text()), "status": dict(STATUS), **live} if OUT.exists() else {"items": [], "warnings": ["尚未生成，请先运行分析"], "calibration": [], "history": []}


def run():
    if not LOCK.acquire(False):
        return
    STATUS.update(running=True, error=None)
    try:
        from limit_pool import fetch
        import cache_data
        today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
        try:
            snapshot = cache_data.snapshot_update()
            if snapshot.get("blocked") or snapshot.get("trade_date") != today:
                STATUS["error"] = "行情未刷新到今天，上方候选仍使用上次日线日期"
        except Exception:
            STATUS["error"] = "行情刷新失败，上方候选仍使用上次日线日期"
        try:
            fetch(today)
            from limit_sectors import capture
            capture()
        except Exception:
            STATUS["error"] = "涨停池获取失败，保留本地数据；封单与题材可能缺失"
        try:
            fetch(today, broken=True)
        except Exception:
            STATUS["error"] = "炸板池获取失败，保留上次快照，请检查采集时间"
        build()
    except Exception as exc:
        STATUS["error"] = str(exc) if isinstance(exc, ValueError) else "本地连板分析失败"
    finally:
        STATUS["running"] = False
        LOCK.release()


def daily_loop():
    done = ""
    last_attempt = None
    while True:
        stamp = datetime.now(timezone(timedelta(hours=8)))
        day = stamp.strftime("%Y-%m-%d")
        clock = stamp.strftime("%H:%M")
        intraday = "09:30" <= clock < "11:30" or "13:00" <= clock < "15:00"
        if stamp.weekday() < 5 and not STATUS["running"]:
            if intraday and (last_attempt is None or time.monotonic()-last_attempt >= 300):
                last_attempt = time.monotonic()
                run()
            elif stamp.hour >= 16 and done != day:
                run()
                if not STATUS["error"]:
                    done = day
                else:
                    # Bound retry frequency when the provider is unavailable.
                    time.sleep(240)
        time.sleep(60)


if __name__ == "__main__":
    import sys
    if "--refresh" in sys.argv:
        run()
        raise SystemExit(0)
    result = build()
    print(json.dumps({k: result.get(k) for k in ("date", "brier", "calibration")}, ensure_ascii=False))
