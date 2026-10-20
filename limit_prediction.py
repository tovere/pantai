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
    records = defaultdict(list)
    for stock in stocks:
        index = {date: i for i, date in enumerate(stock["dates"])}
        for j, day in enumerate(calendar):
            i = index.get(day)
            if i is None or i < 1 or (j > 0 and stock["dates"][i-1] != calendar[j-1]) or not stock["lu"][i]:
                continue
            next_day = calendar[j + 1] if j + 1 < len(calendar) else None
            ni = index.get(next_day)
            records[day].append({
                "code": stock["code"], "height": stock["streak"][i],
                "onePrice": bool(stock["yizi"][i]), "close": stock["C"][i],
                "volumeRatio": stock["V"][i] / max(1, sum(stock["V"][max(0, i-5):i]) / min(i, 5)),
                "nextDate": next_day,
                "continued": bool(stock["lu"][ni]) if ni is not None else None,
                "touched": bool(stock["H"][ni] >= cycle.limit_px(stock["C"][i], .1) - .01) if ni is not None else None,
                "openPremium": round((stock["O"][ni] / stock["C"][i] - 1) * 100, 2) if ni is not None else None,
                "openBuyable": not cycle.is_limit_up(stock["code"], stock["C"][i], stock["O"][ni]) if ni is not None else None,
            })
    history, predictions = [], []
    for day in calendar:
        # Only labels observable by today's close enter training.
        eligible = [r for r in history if r["nextDate"] and r["nextDate"] <= day and r["continued"] is not None]
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
        history.extend(records[day])
    scored = [r for r in predictions if r["probability"] is not None and r["continued"] is not None]
    bins = []
    for low in range(0, 100, 10):
        group = [r for r in scored if low <= r["probability"] < low + 10]
        if group:
            bins.append({"range": f"{low}–{low+10}%", "samples": len(group),
                         "predicted": round(sum(r["probability"] for r in group)/len(group),1),
                         "actual": round(sum(r["continued"] for r in group)/len(group)*100,1)})
    latest = calendar[-1]
    result = {"date": latest, "generatedAt": datetime.now(timezone(timedelta(hours=8))).isoformat(),
              "priceBasis": "none" if raw.exists() else "forward", "version": "daily-baseline-v2", "market": days[-1],
              "items": sorted([r for r in predictions if r["date"] == latest], key=lambda r: -(r["probability"] or -1)),
              "calibration": bins, "history": predictions[-500:],
              "warnings": ["本地前复权日线推算涨停，非交易所精确涨停价；历史ST和上市状态未完整还原。",
                           "当前为主板日线基线，未接入封单、封板时间与历史板块归属；不代表完整连板模型。",
                           "openBuyable仅表示开盘未封涨停，不能证明实际成交。"],
              "brier": round(sum((r["probability"]/100-r["continued"])**2 for r in scored)/len(scored),4) if scored else None}
    if raw.exists():
        result["warnings"][0] = "未复权日线推算涨停；历史ST、除权日参考价与新股状态未完整还原，不是交易所精确涨停名单。"
    from limit_pool import enrich
    result = enrich(result, latest)
    from limit_sectors import aggregate
    result["sectors"] = aggregate(latest)
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
    return {**json.loads(OUT.read_text()), "status": dict(STATUS), **live} if OUT.exists() else {"items": [], "warnings": ["尚未生成，请先运行分析"], "calibration": [], "history": []}


def run():
    if not LOCK.acquire(False):
        return
    STATUS.update(running=True, error=None)
    try:
        from limit_pool import fetch
        today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
        try:
            fetch(today)
            from limit_sectors import capture
            capture()
        except Exception:
            STATUS["error"] = "涨停池获取失败，保留本地数据；封单与题材可能缺失"
        build()
    except Exception as exc:
        STATUS["error"] = str(exc) if isinstance(exc, ValueError) else "本地连板分析失败"
    finally:
        STATUS["running"] = False
        LOCK.release()


def daily_loop():
    done = ""
    while True:
        stamp = datetime.now(timezone(timedelta(hours=8)))
        day = stamp.strftime("%Y-%m-%d")
        if stamp.weekday() < 5 and stamp.hour >= 16 and done != day:
            run()
            done = day
        time.sleep(60)


if __name__ == "__main__":
    result = build()
    print(json.dumps({k: result.get(k) for k in ("date", "brier", "calibration")}, ensure_ascii=False))
