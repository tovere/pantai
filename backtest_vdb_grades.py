#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""策略十一 A/B/C 评级分层回测。"""
import os
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed

import cache_data
import vdb_pullback as sig
import watch_grade
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
        bars = rows[max(0, i - 59):i + 1]
        g = watch_grade.grade("vdb_pullback", rec, bars)
        out.append({
            "ret": sell / rec["entry"] - 1 - COST,
            "grade": g["grade"],
            "reason": reason,
            "mae": mae,
            "held": j - i,
        })
    return out


def bucket(label, xs):
    if not xs:
        print(f"  {label}: 0笔")
        return
    rs = [t["ret"] for t in xs]
    print(
        f"  {label}: {len(rs):5d}笔  胜率{sum(r > 0 for r in rs) / len(rs) * 100:5.1f}%  "
        f"均值{statistics.mean(rs) * 100:+6.2f}%  中位{statistics.median(rs) * 100:+6.2f}%  "
        f"MAE{statistics.mean(t['mae'] for t in xs) * 100:+5.2f}%"
    )


def main():
    mode = "严格" if sig.STRICT_BUY else "宽松"
    stop = os.environ.get("STOP_MODE", "close")
    uni = cache_data.universe()
    print(f"策略十一·{mode}·止损{stop}  评级分层 {START}~{END}...", flush=True)
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
    print(f"\n总体 {len(trades)}笔")
    bucket("ALL", trades)
    for g in "ABCD":
        bucket(g, [t for t in trades if t["grade"] == g])


if __name__ == "__main__":
    main()
