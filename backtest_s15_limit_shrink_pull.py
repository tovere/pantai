#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""策略十五回测：信号日尾盘买。

离场: 破昨低立刻走 / 放量下跌走 / 红盘收盘走 / 缩量下跌再格局 / 超时。
"""
import os
import statistics
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

import cache_data
import screen_s15_limit_shrink_pull as sig

START = os.environ.get("START", "2025-01-01")
END = os.environ.get("END", "2026-08-25")
COST = float(os.environ.get("COST", "0.001"))
COOLDOWN = int(os.environ.get("COOLDOWN", "3"))
MAX_HOLD = int(os.environ.get("S15_MAX_HOLD", str(sig.MAX_HOLD)))


def run_one(item):
    code, name, secid = item
    rows = cache_data.daily_kline(secid)
    if not rows or len(rows) < 40:
        return []
    out = []
    next_ok = 70
    i = 70
    while i < len(rows) - 1:
        if i < next_ok:
            i += 1
            continue
        if not (START <= rows[i][0] <= END):
            i += 1
            continue
        rec = sig.signal_at(code, name, rows, i, up_mode="off")
        if not rec:
            i += 1
            continue
        entry = float(rows[i][2])
        if entry <= 0:
            i += 1
            continue
        sell_i, sell_px, reason = sig.exit_from(rows, i, rec["stop"], MAX_HOLD)
        held = sell_i - i
        if reason == "timeout" and held < MAX_HOLD and rows[sell_i][0] >= END:
            break
        ret = sell_px / entry - 1 - COST
        out.append({
            "code": code,
            "name": name,
            "signal": rec["date"],
            "exit_date": rows[sell_i][0],
            "ret": ret,
            "reason": reason,
            "held": held,
            "chg": rec["chg"],
            "prev_chg": rec["prev_chg"],
            "vol_shrink": rec["vol_shrink"],
            "limit": rec["limit"],
            "amt": rec["amt"],
            "ma60_up": rec.get("ma60_up", 0),
            "weekly_up": rec.get("weekly_up", 0),
        })
        next_ok = sell_i + 1 + COOLDOWN
        i += 1
    return out


def bucket(label, xs, min_n=20):
    if len(xs) < min_n:
        print(f"  {label:<28} {len(xs):>4}笔 (少)")
        return
    rs = [t["ret"] for t in xs]
    print(
        f"  {label:<28} {len(xs):>4}笔  胜{sum(r > 0 for r in rs) / len(rs) * 100:5.1f}%  "
        f"均{statistics.mean(rs) * 100:+6.2f}%  中{statistics.median(rs) * 100:+6.2f}%  "
        f"均持{statistics.mean(t['held'] for t in xs):.1f}日"
    )


def main():
    uni = sig.universe()
    print(
        f"回测池 {len(uni)} 主板 | {START}~{END} | 十五·昨大涨今缩量回踩 "
        f"上涨对比 MAX_HOLD={MAX_HOLD}",
        flush=True,
    )
    os.environ.setdefault("CACHE_ONLY", "1")
    trades = []
    with ThreadPoolExecutor(max_workers=12) as ex:
        futs = [ex.submit(run_one, it) for it in uni]
        for n, fut in enumerate(as_completed(futs), 1):
            try:
                trades.extend(fut.result() or [])
            except Exception:
                pass
            if n % 500 == 0 or n == len(futs):
                print(f"  {n}/{len(futs)} trades={len(trades)}", flush=True)

    clean = [
        t for t in trades
        if not (t["reason"] == "timeout" and t["held"] < MAX_HOLD)
    ]
    print(f"\n>> 策略十五·昨大涨今缩量回踩  无趋势过滤 {len(clean)}笔 (剔截断后)\n")
    if not clean:
        return
    bucket("原策略(无上涨背景)", clean, 1)
    ma60 = [t for t in clean if t.get("ma60_up")]
    weekly = [t for t in clean if t.get("weekly_up")]
    both = [t for t in clean if t.get("ma60_up") and t.get("weekly_up")]
    print("\n[补上涨背景]")
    bucket("MA60向上", ma60, 1)
    bucket("周线向上", weekly, 1)
    bucket("MA60+周线", both, 1)
    dump = os.path.join("data_cache", "s15_trades.json")
    try:
        import json
        with open(dump, "w", encoding="utf-8") as f:
            json.dump(clean, f, ensure_ascii=False)
        print(f"\n[dump] {dump}  {len(clean)}笔", flush=True)
    except OSError:
        pass
    print("\n[ABC · 无上涨背景]")
    import watch_grade
    for t in clean:
        t["grade"] = watch_grade.grade_limit_shrink_pull({
            "prev_chg": t["prev_chg"], "chg": t["chg"],
            "vol_shrink": t["vol_shrink"], "limit": t["limit"],
            "amt": t.get("amt"),
        }, [])["grade"]
    for g in "ABC":
        bucket(g, [t for t in clean if t["grade"] == g], 1)
    print("\n[ABC · MA60向上]")
    for t in ma60:
        if "grade" not in t:
            t["grade"] = watch_grade.grade_limit_shrink_pull({
                "prev_chg": t["prev_chg"], "chg": t["chg"],
                "vol_shrink": t["vol_shrink"], "limit": t["limit"],
                "amt": t.get("amt"),
            }, [])["grade"]
    for g in "ABC":
        bucket("MA60 " + g, [t for t in ma60 if t["grade"] == g], 1)
    print("\n[更严对照 · MA60] 昨≥7% 缩≤0.75x 额≥0.5亿")
    tighter = [
        t for t in ma60
        if t["prev_chg"] >= 7 and t["vol_shrink"] <= 0.75 and t.get("amt", 0) >= 0.5
    ]
    bucket("更严整体", tighter, 1)
    for g in "ABC":
        bucket("更严" + g, [t for t in tighter if t["grade"] == g], 1)
    print("\n[离场 · MA60]")
    for k, _ in Counter(t["reason"] for t in ma60).most_common():
        bucket(k, [t for t in ma60 if t["reason"] == k], 10)
    print("\n[昨涨幅 · MA60]")
    for lo, hi, name in [(6, 7, "6-7%"), (7, 9.9, "7-9.9%"), (9.9, 99, "涨停≥9.9%")]:
        bucket(name, [t for t in ma60 if lo <= t["prev_chg"] < hi], 15)
    print("\n[今日回踩 · MA60]")
    for lo, hi, name in [(-3, -1.5, "-3~-1.5%"), (-1.5, 0, "-1.5~0%")]:
        bucket(name, [t for t in ma60 if lo <= t["chg"] < hi], 15)
    print("\n[缩量 · MA60]")
    for lo, hi, name in [(0, 0.5, "<0.5x"), (0.5, 0.7, "0.5-0.7x"), (0.7, 0.80, "0.7-0.8x")]:
        bucket(name, [t for t in ma60 if lo <= t["vol_shrink"] < hi], 15)


if __name__ == "__main__":
    main()
