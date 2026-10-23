#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把情绪阶段接到盯盘台策略 5/10/11/12 上，看过滤后胜率升还是降。

策略2/3 不在这里。5/10 优先用已落盘的交易 JSON（盯盘过滤），11/12 和 5·ETF 现场跑。
"""
from __future__ import annotations

import json
import os
import statistics
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("CACHE_ONLY", "1")

import cache_data
from strategy_sentiment_cycle import cycle

START = os.environ.get("START", "2025-07-01")
END = os.environ.get("END", "2026-08-21")
WORKERS = int(os.environ.get("WORKERS", "12"))
CACHE = cache_data.CACHE_DIR

GATES = [
    ("全时段", None),
    ("发酵+高潮", frozenset({"ferment", "climax"})),
    ("教科书·修复+发酵", frozenset({"repair", "ferment"})),
    ("避开高潮", "skip_climax"),
    ("避开退潮", "skip_ebb"),
    ("只关冰点修复", "skip_ice_repair"),
    ("只做退潮", frozenset({"ebb"})),
]


def _in_win(d):
    return d and START <= d <= END


def load_pmap():
    days = cycle.load_calendar()
    if not days:
        days, _ = cycle.build_calendar(reuse=False)
    return {m["date"]: m["phase"] for m in days}, days


def wr_avg(xs):
    if len(xs) < 8:
        return None
    rs = [t["ret"] for t in xs]
    wins = sum(1 for r in rs if r > 0)
    return {
        "n": len(xs),
        "wr": wins / len(xs),
        "avg": statistics.mean(rs),
        "med": statistics.median(rs),
    }


def apply_gate(trades, gate):
    if gate is None:
        return trades
    if gate == "skip_climax":
        return [t for t in trades if t.get("phase") != "climax"]
    if gate == "skip_ebb":
        return [t for t in trades if t.get("phase") != "ebb"]
    if gate == "skip_ice_repair":
        return [t for t in trades if t.get("phase") not in ("ice", "repair")]
    return [t for t in trades if t.get("phase") in gate]


def tag(trades, pmap, date_key="date"):
    out = []
    for t in trades:
        d = t.get(date_key) or t.get("signal") or t.get("entry_date")
        if not _in_win(d):
            continue
        ph = pmap.get(d)
        if not ph:
            continue
        t = dict(t)
        t["phase"] = ph
        t["phase_cn"] = cycle.PHASE_CN[ph]
        out.append(t)
    return out


def report(title, trades):
    base = wr_avg(trades)
    print(f"\n===== {title}  n={len(trades)} =====")
    if not base:
        print("  样本不足")
        return None
    print(
        f"  {'过滤':<18} {'笔数':>6} {'胜率':>7} {'Δ胜率':>7} {'均值':>8} {'Δ均值':>8}"
    )
    rows = []
    for label, gate in GATES:
        s = wr_avg(apply_gate(trades, gate))
        if not s:
            print(f"  {label:<18} 样本不足")
            continue
        dwr = (s["wr"] - base["wr"]) * 100
        davg = (s["avg"] - base["avg"]) * 100
        mark = ""
        if label != "全时段":
            if dwr >= 1.0 and s["avg"] >= base["avg"]:
                mark = " ↑"
            elif dwr <= -1.0 or s["avg"] < base["avg"] - 0.001:
                mark = " ↓"
        print(
            f"  {label:<18} {s['n']:>6} {s['wr']*100:6.1f}% {dwr:+6.1f}pp "
            f"{s['avg']*100:+7.2f}% {davg:+7.2f}pp{mark}"
        )
        rows.append((label, s, dwr, davg))
    print("  按入场日阶段：")
    for ph in cycle.PHASES:
        bucket = [t for t in trades if t.get("phase") == ph]
        s = wr_avg(bucket)
        if not s:
            print(f"    {cycle.PHASE_CN[ph]}  样本不足 ({len(bucket)})")
            continue
        print(
            f"    {cycle.PHASE_CN[ph]}  {s['n']:>5}笔  胜{s['wr']*100:5.1f}%  "
            f"均{s['avg']*100:+6.2f}%  中{s['med']*100:+6.2f}%"
        )
    return base, rows


def s5_loose_ok(t):
    if int(t.get("stage", 1)) != 1:
        return False
    if float(t.get("dist", 99)) > 5:
        return False
    if float(t.get("vol_shrink", 9)) > 0.50:
        return False
    if int(t.get("pull_days", 0)) < 2:
        return False
    buy_low = float(t.get("buy_low") or 0)
    if buy_low <= 0:
        return False
    risk = (float(t["entry"]) / buy_low - 1) * 100
    return risk <= 4


def s5_strict_ok(t):
    if float(t.get("dist", 99)) > 6:
        return False
    if float(t.get("vol_shrink", 9)) > 0.60:
        return False
    buy_low = float(t.get("buy_low") or 0)
    if buy_low <= 0:
        return False
    risk = (float(t["entry"]) / buy_low - 1) * 100
    return risk <= 5


def s10_dash_ok(t):
    if int(t.get("type", 0)) != 3 or int(t.get("stage", 0)) != 1:
        return False
    if int(t.get("lag", 99)) > 2:
        return False
    stop = t.get("stop_ref") or t.get("zg")
    entry = t.get("entry")
    if not stop or not entry:
        return False
    risk = (float(entry) / float(stop) - 1) * 100
    return risk <= 12


def load_json(name):
    path = CACHE / name
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def collect(uni, run_one, label):
    out, done = [], 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(run_one, *it): it[0] for it in uni}
        for fut in as_completed(futs):
            done += 1
            try:
                out.extend(fut.result() or [])
            except Exception:
                pass
            if done % 800 == 0:
                print(f"  {label} {done}/{len(uni)} 交易{len(out)}", flush=True)
    return out


def s12_tier_ok(rows, i, rec, tier):
    net = rec["net"]
    c1 = float(rows[i][2])
    prev20 = float(rows[i - 20][2]) if i >= 20 else 0.0
    ret20 = (c1 / prev20 - 1) * 100 if prev20 else 0.0
    amt = float(rows[i][6]) / 1e8 if len(rows[i]) > 6 else 0.0
    if tier == 2:
        return net <= 8 and ret20 < 0 and 0.3 <= amt < 1.2
    if tier == 3:
        return net <= 8 and ret20 < 5 and 0.3 <= amt < 1.0
    return True


def main():
    print(f"情绪叠加 5/10/11/12  {START}~{END}", flush=True)
    pmap, days = load_pmap()
    print(f"日历 {len(days)} 日 最新 {days[-1]['date'] if days else '-'}", flush=True)

    # ---- 5 / 10：落盘交易 + 盯盘过滤 ----
    s5_loose = tag([t for t in load_json("s5_stock_loose_trades.json") if s5_loose_ok(t)], pmap)
    s5_strict = tag([t for t in load_json("s5_stock_strict_trades.json") if s5_strict_ok(t)], pmap)
    s10 = tag([t for t in load_json("s10_stock_grade_trades.json") if s10_dash_ok(t)], pmap)
    report("策略5 个股宽松·盯盘口径（JSON，约到2026-06）", s5_loose)
    report("策略5 个股严格·盯盘口径（JSON，约到2026-06）", s5_strict)
    report("策略10 个股三买·盯盘口径（JSON，约到2026-06）", s10)

    # ---- 5 ETF 宽松：现场 ----
    print("\n现场跑 策略5 ETF宽松…", flush=True)
    import backtest_chan_wyckoff_3buy as s5bt
    s5bt.STRICT = False
    s5bt.EXIT_MODE = "trail"
    s5bt.START = START
    s5bt.END = END
    s5_etf = tag(collect(cache_data.etf_universe(), s5bt.run_one, "s5etf"), pmap)
    report("策略5 ETF宽松·移动止损", s5_etf)

    # ---- 11 宽松盯盘口径 ----
    print("\n现场跑 策略11 VDB宽松…", flush=True)
    import vdb_pullback as vdb
    import backtest_vdb_pullback as s11bt
    vdb.MIN_MKTCAP = 20e9
    vdb.SHRINK = 0.50
    vdb.LOOSE_DIST = 6.0
    vdb.MIN_RET20 = 0.0
    vdb.EXCLUDE_REVERSAL = True
    vdb.STRICT_BUY = False
    s11bt.START = START
    s11bt.END = END
    s11 = tag(collect(cache_data.universe(), s11bt.run_one, "s11"), pmap)
    report("策略11 VDB宽松·盯盘口径", s11)

    # ---- 12：一趟扫出 2档 / 3档 ----
    print("\n现场跑 策略12 连小阳 2/3档…", flush=True)
    import backtest_csi2000_small_yang as s12bt
    s12bt.START = START
    s12bt.END = END

    def s12_run(item):
        code, name, secid = item
        rows = cache_data.daily_kline(secid)
        if not rows or len(rows) < s12bt.sy.WINDOW + 22:
            return [], []
        t2, t3 = [], []
        next_ok = s12bt.sy.WINDOW
        i = s12bt.sy.WINDOW
        n = len(rows)
        while i < n - 2:
            if i < next_ok:
                i += 1
                continue
            rec = s12bt.is_new_signal(rows, i)
            if not rec:
                i += 1
                continue
            buy_i = i + 1
            entry = float(rows[buy_i][1])
            if entry <= 0:
                i += 1
                continue
            sell_i, sell_px, reason = s12bt.exit_trade(rows, buy_i, rec)
            trade = {
                "code": code,
                "date": rec["date"],
                "ret": sell_px / entry - 1 - s12bt.COST,
                "held": sell_i - buy_i + 1,
                "reason": reason,
            }
            if s12_tier_ok(rows, i, rec, 2):
                t2.append(trade)
            if s12_tier_ok(rows, i, rec, 3):
                t3.append(trade)
            next_ok = sell_i + 1 + s12bt.COOLDOWN
            i = buy_i + 1
        return t2, t3

    t2_all, t3_all, done = [], [], 0
    uni = cache_data.universe()
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = [ex.submit(s12_run, it) for it in uni]
        for fut in as_completed(futs):
            done += 1
            try:
                a, b = fut.result()
                t2_all.extend(a)
                t3_all.extend(b)
            except Exception:
                pass
            if done % 800 == 0:
                print(f"  s12 {done}/{len(uni)} t2={len(t2_all)} t3={len(t3_all)}", flush=True)
    report("策略12 连小阳·2档（未涨透）", tag(t2_all, pmap))
    report("策略12 连小阳·3档（温和未透）", tag(t3_all, pmap))

    print("\n读法：Δ胜率/Δ均值相对该策略自己的全时段。"
          "↑=胜率至少+1pp且均值没变差；↓=胜率掉1pp或均值变差。"
          "5/10 的 JSON 只到 2026-06，11/12/5ETF 到缓存最新日。")


if __name__ == "__main__":
    main()
