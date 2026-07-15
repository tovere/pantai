#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""盯盘数据编排: 跑策略变体 -> 挂评级 -> 附K线/止损位 -> watch_data.json。

支持单策略独立跑(带进度回调)与历史快照, 供 watch_server.py 的异步任务调用。
    python3 watch_export.py                 # 全部变体, 用现有缓存
    REFRESH=1 python3 watch_export.py       # 先刷全市场再跑
每个变体以子进程运行(env 常量隔离), 经 WATCH_JSON_OUT 落 JSON 回收。
"""
import json
import os
import random
import re
import subprocess
import tempfile
import time
from collections import Counter
from datetime import datetime, timedelta

import cache_data
import watch_grade

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_PATH = os.path.join(HERE, "watch_data.json")
HIST_DIR = os.path.join(HERE, "data_cache", "watch_history")


def now_bj():
    """北京时间(UTC+8), 不依赖本机时区(服务器可能在美西)。"""
    return datetime.utcnow() + timedelta(hours=8)

# key -> (脚本, 标题, 额外env)
VARIANTS = {
    "s5_stock_loose":  ("screen_chan_wyckoff_3buy.py", "策略五·个股·宽松候选", {"STRICT_BUY": "0"}),
    "s5_stock_strict": ("screen_chan_wyckoff_3buy.py", "策略五·个股·严格(下单级别)", {"STRICT_BUY": "1"}),
    "s5_etf_loose":    ("screen_chan_wyckoff_3buy.py", "策略五·ETF·宽松", {"ETF_ONLY": "1", "STRICT_BUY": "0"}),
    "s5_etf_strict":   ("screen_chan_wyckoff_3buy.py", "策略五·ETF·严格(狙击)", {"ETF_ONLY": "1", "STRICT_BUY": "1"}),
    "s6_stock":        ("screen_squeeze_launch.py",    "策略六·个股·压缩蓄势", {}),
    "s6_etf":          ("screen_squeeze_launch.py",    "策略六·ETF·压缩蓄势", {"ETF_ONLY": "1"}),
    "s7_stock":        ("screen_spring_2buy.py",       "策略七·个股·Spring二买背驰", {}),
    "s8_stock":        ("screen_nzi_reversal.py",      "策略八·个股·N字反包", {}),
}
VKEYS = list(VARIANTS.keys())


def _secid(code, is_etf):
    if is_etf:
        return ("1." if code.startswith("5") else "0.") + code
    return ("1." if code.startswith("6") else "0.") + code


def _bars_for(secid, n=60):
    rows = cache_data.daily_kline(secid)
    if not rows:
        return []
    out = []
    for r in rows[-n:]:
        try:
            out.append([r[0], float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])])
        except (ValueError, IndexError):
            continue
    return out


def _levels(strategy, hit):
    if strategy == "chan_wyckoff_3buy":
        box = hit.get("box", "")
        up = None
        if "-" in box:
            try:
                up = float(box.split("-")[1])
            except ValueError:
                up = None
        return {"中枢上沿": up, "三买低(止损)": hit.get("buy_low")}
    if strategy == "squeeze_launch":
        coil = hit.get("coil", "")
        lo = hi = None
        if "-" in coil:
            try:
                lo, hi = (float(x) for x in coil.split("-"))
            except ValueError:
                lo = hi = None
        return {"蓄势上沿": hi, "蓄势下沿": lo, "止损": hit.get("stop")}
    if strategy == "spring_2buy":
        return {"区间下沿": hit.get("range_low"), "Spring低": hit.get("spring_low"),
                "止损": hit.get("stop")}
    if strategy == "nzi_reversal":
        return {"前高": hit.get("peak"), "回踩低": hit.get("pull_low"),
                "止损": hit.get("stop")}
    return {}


def _ensure_screen_date():
    # 始终对齐到缓存最新交易日。长驻 server 进程里 SCREEN_DATE 会残留旧值(如昨天),
    # 缓存进入新一天后若不更新, 筛选器的 D[i]!=TODAY 会把全部票挡掉 -> 全0。
    ref = cache_data.daily_kline("0.000001")
    if ref:
        os.environ["SCREEN_DATE"] = ref[-1][0]


def enrich_section(key, raw):
    """把子进程回收的原始 hits 挂上评级/K线/止损位, 组成一个 section。"""
    script, title, _ = VARIANTS[key]
    strategy = raw.get("strategy", "")
    is_etf = raw.get("is_etf", False)
    latest = ""
    hits = []
    for hit in raw.get("hits", []):
        secid = _secid(hit["code"], is_etf)
        bars = _bars_for(secid)
        if bars:
            latest = max(latest, bars[-1][0])
        g = watch_grade.grade(strategy, hit, bars)
        hit.update({
            "secid": secid,
            "grade": g["grade"],
            "gradeScore": g["score"],
            "gradeNote": g["note"],
            "flags": g["flags"],
            "levels": _levels(strategy, hit),
            "bars": bars,
        })
        hits.append(hit)
    rank = {"A": 0, "B": 1, "C": 2, "D": 3}
    hits.sort(key=lambda h: rank.get(h["grade"], 9))
    return {
        "key": key, "strategy": strategy, "title": title,
        "is_etf": is_etf, "count": len(hits), "hits": hits,
        "error": raw.get("error"), "latest": latest,
        "updatedAt": now_bj().strftime("%Y-%m-%d %H:%M"),
    }


def run_variant_live(key, progress_cb=None):
    """单变体: 子进程流式解析进度 -> 回收 JSON -> enrich。progress_cb(done, total)。"""
    _ensure_screen_date()
    script, title, env_extra = VARIANTS[key]
    env = dict(os.environ)
    env.update(env_extra)
    env["CACHE_ONLY"] = "1"  # 筛选只读缓存, 不逐只现拉(缺数据的票跳过, 由全量重拉补)
    fd, path = tempfile.mkstemp(suffix=".json", prefix="watch_")
    os.close(fd)
    env["WATCH_JSON_OUT"] = path
    try:
        proc = subprocess.Popen(
            ["python3", os.path.join(HERE, script)], env=env, cwd=HERE,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
        )
        for line in proc.stdout:
            m = re.search(r"(\d+)/(\d+)", line)
            if m and progress_cb:
                progress_cb(int(m.group(1)), int(m.group(2)))
        proc.wait(timeout=600)
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:
        raw = {"strategy": "", "hits": [], "error": str(e)}
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    return enrich_section(key, raw)


# ---------- 聚合 / 落盘 / 历史 ----------

def empty_payload():
    now = now_bj()
    return {
        "generatedAt": now.strftime("%Y-%m-%d %H:%M"),
        "screenDate": os.environ.get("SCREEN_DATE", ""),
        "latestBar": "",
        "closed": False,
        "summary": {"total": 0, "gradeA": 0, "gradeB": 0},
        "sections": [{"key": k, "strategy": "", "title": VARIANTS[k][1],
                      "is_etf": "etf" in k, "count": 0, "hits": [], "error": None}
                     for k in VKEYS],
    }


def load_payload():
    if os.path.exists(OUT_PATH):
        try:
            with open(OUT_PATH, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            pass
    return empty_payload()


def _resummarize(payload):
    ga = gb = total = 0
    latest = payload.get("latestBar", "")
    for sec in payload["sections"]:
        for h in sec["hits"]:
            total += 1
            if h["grade"] == "A":
                ga += 1
            elif h["grade"] == "B":
                gb += 1
        if sec.get("latest"):
            latest = max(latest, sec["latest"])
    # 0命中时各 section 无 latest, 用参考票的最新交易日兜底, 避免顶部日期显示旧值
    sd = os.environ.get("SCREEN_DATE", "")
    if sd:
        latest = max(latest, sd)
    now = now_bj()
    payload["summary"] = {"total": total, "gradeA": ga, "gradeB": gb}
    payload["latestBar"] = latest
    payload["generatedAt"] = now.strftime("%Y-%m-%d %H:%M")
    payload["closed"] = bool(latest == now.strftime("%Y-%m-%d") and now.hour >= 15)
    payload["screenDate"] = os.environ.get("SCREEN_DATE", latest)
    return payload


def save_payload(payload):
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)


def merge_section(section):
    """把单个 section 写回聚合结果并重算汇总 + 快照历史。"""
    payload = load_payload()
    bykey = {s["key"]: i for i, s in enumerate(payload["sections"])}
    if section["key"] in bykey:
        payload["sections"][bykey[section["key"]]] = section
    else:
        payload["sections"].append(section)
    _resummarize(payload)
    save_payload(payload)
    snapshot_history(payload)
    return payload


def snapshot_history(payload):
    """按交易日存一份精简快照(不含K线), 最新覆盖当日。"""
    date = payload.get("latestBar") or payload.get("screenDate")
    if not date:
        return
    os.makedirs(HIST_DIR, exist_ok=True)
    slim = {
        "date": date,
        "generatedAt": payload["generatedAt"],
        "closed": payload["closed"],
        "summary": payload["summary"],
        "sections": [{
            "key": s["key"], "title": s["title"], "count": s["count"],
            "hits": [{k: h.get(k) for k in
                      ("code", "name", "grade", "close", "chg", "gradeNote",
                       "dist", "stage", "pull_days", "runup", "amt", "flags")}
                     for h in s["hits"]],
        } for s in payload["sections"]],
    }
    with open(os.path.join(HIST_DIR, f"{date}.json"), "w", encoding="utf-8") as f:
        json.dump(slim, f, ensure_ascii=False)


def list_history():
    if not os.path.isdir(HIST_DIR):
        return []
    out = []
    for fn in os.listdir(HIST_DIR):
        if not fn.endswith(".json"):
            continue
        try:
            with open(os.path.join(HIST_DIR, fn), encoding="utf-8") as f:
                d = json.load(f)
            out.append({"date": d["date"], "generatedAt": d.get("generatedAt", ""),
                        "closed": d.get("closed", False), "summary": d.get("summary", {})})
        except (OSError, json.JSONDecodeError):
            continue
    out.sort(key=lambda x: x["date"], reverse=True)
    return out


def get_history(date):
    path = os.path.join(HIST_DIR, f"{date}.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


INDICES = [
    ("上证指数", "1.000001"),
    ("深证成指", "0.399001"),
    ("创业板指", "0.399006"),
    ("沪深300", "1.000300"),
    ("科创50", "1.000688"),
    ("北证50", "0.899050"),
]


def _day_chg(bars):
    """当日涨跌%: 最新收 vs 上一交易日收。分钟线按日期分段找上一日收盘。"""
    last = bars[-1]
    if len(bars) < 2:
        return 0.0
    if len(last[0]) > 10:  # 分钟线, 时间含 HH:MM
        day = last[0][:10]
        for r in reversed(bars):
            if r[0][:10] != day:
                return round((last[2] / r[2] - 1) * 100, 2) if r[2] else 0.0
        return round((last[2] / bars[0][1] - 1) * 100, 2) if bars[0][1] else 0.0
    prev = bars[-2]
    return round((last[2] / prev[2] - 1) * 100, 2) if prev[2] else 0.0


def market_indices(klt=101, n=None):
    """主要大盘指数K线(现拉最新)。klt=101 日线 / 30 / 5 分钟。涨跌恒为当日涨跌。"""
    out = []
    for name, secid in INDICES:
        try:
            if int(klt) == 101:
                rows = cache_data.daily_kline(secid, force=True)
                nn = n or 120
            else:
                rows = cache_data.min_kline(secid, klt=int(klt), force=True)
                nn = n or 240
        except Exception:
            rows = None
        if not rows:
            continue
        bars = []
        for r in rows[-nn:]:
            try:
                bars.append([r[0], float(r[1]), float(r[2]), float(r[3]),
                             float(r[4]), float(r[5])])
            except (ValueError, IndexError):
                continue
        if not bars:
            continue
        out.append({"name": name, "secid": secid, "bars": bars, "klt": int(klt),
                    "close": round(bars[-1][2], 2), "chg": _day_chg(bars),
                    "date": bars[-1][0]})
    return out


def cache_status(sample=400):
    """读磁盘真实缓存状态: 数量 / 最新交易日 / 覆盖率 / 最后拉取时间(mtime, 含命令行拉的) / 日期分布。"""
    ddir = str(cache_data.DAILY_DIR)
    if not os.path.isdir(ddir):
        return {"dailyCount": 0, "latestDay": "", "coveragePct": 0,
                "sampleSize": 0, "lastFetched": "-", "agoMinutes": 0, "breakdown": []}
    entries = [e for e in os.scandir(ddir) if e.name.endswith(".json")]
    count = len(entries)
    last_mtime = max((e.stat().st_mtime for e in entries), default=0)
    names = sorted(e.name for e in entries)
    # 固定种子抽样 -> 每次同一批, 覆盖率/分布不抖动
    samp = random.Random(42).sample(names, min(sample, count)) if count else []
    dist = Counter()
    for n in samp:
        try:
            with open(os.path.join(ddir, n), encoding="utf-8") as f:
                d = json.load(f)
            dist[d["klines"][-1].split(",")[0]] += 1
        except Exception:
            dist["读取失败"] += 1
    dates = [k for k in dist if k[:2] == "20"]
    # "最新交易日"取占比最多的日期(众数), 而非 max —— 抗个别超前/滞后的脏数据
    # (盘前快照可能给个别票写出次日 bar, 用 max 会把覆盖率误算成 0)
    latest = max(dates, key=lambda d: dist[d], default="")
    latest_n = dist.get(latest, 0)
    cov = round(latest_n * 100 / len(samp)) if samp else 0
    # 非最新日全部折叠成一个"其它"桶(多为停牌/退市), 不再列零散旧日期
    others = len(samp) - latest_n
    bj = (datetime.utcfromtimestamp(last_mtime) + timedelta(hours=8)) if last_mtime else None
    ago = int((time.time() - last_mtime) / 60) if last_mtime else 0
    # ETF 缓存数
    etf_n = 0
    if os.path.exists(str(cache_data.ETF_UNIVERSE_PATH)):
        try:
            with open(str(cache_data.ETF_UNIVERSE_PATH), encoding="utf-8") as f:
                etf_n = len(json.load(f).get("items", []))
        except Exception:
            etf_n = 0
    return {
        "dailyCount": count,
        "etfCount": etf_n,
        "latestDay": latest,
        "coveragePct": cov,
        "sampleSize": len(samp),
        "lastFetched": bj.strftime("%Y-%m-%d %H:%M") if bj else "-",
        "agoMinutes": ago,
        "breakdown": (
            ([{"date": latest, "n": latest_n, "latest": True}] if latest else [])
            + ([{"date": "其它(停牌/退市)", "n": others, "latest": False}] if others else [])
        ),
    }


def build(progress_cb=None):
    """全部变体顺序跑(初始化/全量重跑)。progress_cb(key, done, total)。"""
    if os.environ.get("REFRESH", "0") != "0":
        os.environ["BYPASS_CACHE"] = "1"
        cache_data.warmup(max_workers=24)
        os.environ.pop("BYPASS_CACHE", None)
    _ensure_screen_date()
    payload = load_payload()
    bykey = {s["key"]: i for i, s in enumerate(payload["sections"])}
    for key in VKEYS:
        cb = (lambda d, t, k=key: progress_cb(k, d, t)) if progress_cb else None
        section = run_variant_live(key, cb)
        payload["sections"][bykey[key]] = section
    _resummarize(payload)
    save_payload(payload)
    snapshot_history(payload)
    return payload


def main():
    payload = build()
    s = payload["summary"]
    print(f"[watch_export] {payload['generatedAt']} 数据日={payload['latestBar']} "
          f"收盘={payload['closed']} 命中={s['total']} A={s['gradeA']} B={s['gradeB']}")
    print(f"[watch_export] -> {OUT_PATH}")


if __name__ == "__main__":
    main()
