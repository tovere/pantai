#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""策略十一分层诊断: 找能抬胜率/均值的过滤。"""
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed

import cache_data
import vdb_pullback as sig
from backtest_vdb_pullback import COST, END, START, exit_trade


def run_one(item):
    code, name, secid = item
    rows = cache_data.daily_kline(secid) or []
    if len(rows) < 110:
        return []
    out = []
    for i in range(90, len(rows) - 3):
        if not (START <= rows[i][0] <= END):
            continue
        rec = sig.signal_at(code, name, rows, i)
        if not rec:
            continue
        j, sell, reason, mae = exit_trade(rows, i, rec)
        if reason == "split":
            continue
        o = float(rows[i][1])
        c = float(rows[i][2])
        h_prev = float(rows[i - 1][3])
        rec.update({
            "ret": sell / rec["entry"] - 1 - COST,
            "reason": reason,
            "held": j - i,
            "mae": mae,
            "yang": int(c > o),
            "reclaim": int(c > h_prev),
            "touch": int(rec["buy_low"] <= rec["vdb_low"] * 1.02),
        })
        out.append(rec)
    return out


def bucket(label, xs):
    if not xs:
        print(f"  {label}: 0")
        return
    rs = [t["ret"] for t in xs]
    print(
        f"  {label}: {len(rs):5d} 胜{sum(r > 0 for r in rs) / len(rs) * 100:5.1f}% "
        f"均{statistics.mean(rs) * 100:+6.2f}% 中{statistics.median(rs) * 100:+6.2f}% "
        f"MAE{statistics.mean(t['mae'] for t in xs) * 100:+5.2f}%"
    )


def main():
    uni = cache_data.universe()
    trades = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = [pool.submit(run_one, it) for it in uni]
        for n, fut in enumerate(as_completed(futs), 1):
            try:
                trades.extend(fut.result())
            except Exception:
                pass
            if n % 500 == 0 or n == len(futs):
                print(f"  {n}/{len(futs)} trades={len(trades)}", flush=True)

    print(f"\n样本 {len(trades)}")
    bucket("ALL", trades)

    print("\n== dist_vdb ==")
    for lo, hi, name in [(0, 4, "≤4%"), (4, 8, "4-8"), (8, 12, "8-12"), (12, 99, ">12")]:
        bucket(name, [t for t in trades if lo <= t["dist_vdb"] < hi])

    print("\n== vol_shrink ==")
    for lo, hi, name in [(0, 0.45, "≤0.45"), (0.45, 0.55, "0.45-0.55"), (0.55, 0.70, "0.55-0.70")]:
        if lo == 0:
            bucket(name, [t for t in trades if t["vol_shrink"] <= hi])
        else:
            bucket(name, [t for t in trades if lo < t["vol_shrink"] <= hi])

    print("\n== pull_days ==")
    for d in range(2, 9):
        bucket(f"{d}天", [t for t in trades if t["pull_days"] == d])

    print("\n== 入场形态 ==")
    bucket("阳线", [t for t in trades if t["yang"]])
    bucket("阴线", [t for t in trades if not t["yang"]])
    bucket("收盘破昨高", [t for t in trades if t["reclaim"]])
    bucket("未破昨高", [t for t in trades if not t["reclaim"]])
    bucket("回踩贴近VDB低(≤2%)", [t for t in trades if t["touch"]])
    bucket("回踩未贴VDB低", [t for t in trades if not t["touch"]])

    print("\n== 背景 ==")
    bucket("ret20≤-8", [t for t in trades if t["ret20"] <= -8])
    bucket("ret20 -8~0", [t for t in trades if -8 < t["ret20"] <= 0])
    bucket("ret20 0~10", [t for t in trades if 0 < t["ret20"] <= 10])
    bucket("ret20>10", [t for t in trades if t["ret20"] > 10])
    bucket("bias60≤-5", [t for t in trades if t["bias60"] <= -5])
    bucket("bias60 -5~5", [t for t in trades if -5 < t["bias60"] <= 5])
    bucket("bias60>5", [t for t in trades if t["bias60"] > 5])

    print("\n== 额 ==")
    for lo, hi, name in [(0, 1.5, "<1.5亿"), (1.5, 5, "1.5-5"), (5, 20, "5-20"), (20, 999, ">20")]:
        bucket(name, [t for t in trades if lo <= t["amt"] < hi])

    print("\n== 组合候选 ==")
    combos = [
        ("贴低≤8 + 缩≤0.55 + 阳 + 破昨高",
         lambda t: t["dist_vdb"] <= 8 and t["vol_shrink"] <= 0.55 and t["yang"] and t["reclaim"]),
        ("贴低≤8 + 缩≤0.55 + 破昨高 + 贴测VDB",
         lambda t: t["dist_vdb"] <= 8 and t["vol_shrink"] <= 0.55 and t["reclaim"] and t["touch"]),
        ("贴低≤6 + 缩≤0.55 + 破昨高 + pull2-4 + 阳",
         lambda t: t["dist_vdb"] <= 6 and t["vol_shrink"] <= 0.55 and t["reclaim"]
         and 2 <= t["pull_days"] <= 4 and t["yang"]),
        ("贴低≤8 + 缩≤0.5 + 破昨高 + amt≥1.5 + chain0",
         lambda t: t["dist_vdb"] <= 8 and t["vol_shrink"] <= 0.5 and t["reclaim"]
         and t["amt"] >= 1.5 and t.get("chain", 0) == 0),
        ("ret20>0 + 贴低≤8 + 破昨高 + 缩≤0.55",
         lambda t: t["ret20"] > 0 and t["dist_vdb"] <= 8 and t["reclaim"] and t["vol_shrink"] <= 0.55),
        ("bias60>0 + 贴低≤8 + 破昨高 + 缩≤0.55 + pull2-5",
         lambda t: t["bias60"] > 0 and t["dist_vdb"] <= 8 and t["reclaim"]
         and t["vol_shrink"] <= 0.55 and 2 <= t["pull_days"] <= 5),
        ("严格: ≤6 + ≤0.5 + 阳破昨高 + 贴测 + chain0 + amt≥2",
         lambda t: t["dist_vdb"] <= 6 and t["vol_shrink"] <= 0.5 and t["yang"] and t["reclaim"]
         and t["touch"] and t.get("chain", 0) == 0 and t["amt"] >= 2),
    ]
    for name, pred in combos:
        bucket(name, [t for t in trades if pred(t)])


if __name__ == "__main__":
    main()
