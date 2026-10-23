#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""策略十四 · 底部放量第一根大阳回测：信号日收盘确认 → 次日开盘买。

离场: 破止损(信号低/底盘低×0.99) / 峰值回撤 TRAIL / 超时 MAX_HOLD。
"""
import os
import statistics
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

import cache_data
import screen_bottom_vol_yang as sig

START = os.environ.get("START", "2025-01-01")
END = os.environ.get("END", "2026-08-25")
COST = float(os.environ.get("COST", "0.001"))
MAX_HOLD = int(os.environ.get("MAX_HOLD", "10"))
TRAIL = float(os.environ.get("TRAIL", "0.08"))
COOLDOWN = int(os.environ.get("COOLDOWN", "5"))
# 跳空过大不追（相对信号收盘）
GAP_LIMIT = float(os.environ.get("GAP_LIMIT", "0.07"))


def exit_trade(rows, buy_i, stop0):
    O = [float(r[1]) for r in rows]
    C = [float(r[2]) for r in rows]
    H = [float(r[3]) for r in rows]
    L = [float(r[4]) for r in rows]
    end = min(len(rows) - 1, buy_i + MAX_HOLD)
    peak = H[buy_i]
    stop = stop0
    for j in range(buy_i, end + 1):
        peak = max(peak, H[j])
        trail_stop = peak * (1 - TRAIL)
        stop = max(stop0, trail_stop) if peak > O[buy_i] * 1.03 else stop0
        if O[j] <= stop:
            return j, O[j], ("trail_open" if stop > stop0 else "stop_open")
        if L[j] <= stop:
            return j, stop, ("trail" if stop > stop0 else "stop")
    return end, C[end], "timeout"


def run_one(item):
    code, name, secid = item
    rows = cache_data.daily_kline(secid)
    if not rows or len(rows) < 80:
        return []
    out = []
    next_ok = 70
    i = 70
    while i < len(rows) - 2:
        if i < next_ok:
            i += 1
            continue
        if not (START <= rows[i][0] <= END):
            i += 1
            continue
        rec = sig.signal_at(code, name, rows, i)
        if not rec:
            i += 1
            continue
        buy_i = i + 1
        if buy_i >= len(rows):
            break
        entry = float(rows[buy_i][1])
        sig_close = float(rows[i][2])
        if entry <= 0 or sig_close <= 0:
            i += 1
            continue
        if entry / sig_close - 1 > GAP_LIMIT:
            i += 1
            continue
        sell_i, sell_px, reason = exit_trade(rows, buy_i, rec["stop"])
        held = sell_i - buy_i + 1
        if reason == "timeout" and held < MAX_HOLD and rows[sell_i][0] >= END:
            break
        ret = sell_px / entry - 1 - COST
        out.append({
            "code": code,
            "name": name,
            "signal": rec["date"],
            "entry_date": rows[buy_i][0],
            "exit_date": rows[sell_i][0],
            "ret": ret,
            "reason": reason,
            "held": held,
            "chg": rec["chg"],
            "vol_ratio": rec["vol_ratio"],
            "ret20": rec["ret20"],
            "pos60": rec["pos60"],
        })
        next_ok = sell_i + 1 + COOLDOWN
        i = buy_i + 1
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
        f"回测池 {len(uni)} | {START}~{END} | 底部放量第一根大阳 "
        f"TRAIL={TRAIL} MAX_HOLD={MAX_HOLD}",
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
    print(f"\n>> 策略十四·底部放量第一根大阳  信号{len(clean)}笔 (剔截断后)\n")
    if not clean:
        return
    bucket("整体", clean, 1)
    print("\n[离场]")
    for k, n in Counter(t["reason"] for t in clean).most_common():
        bucket(k, [t for t in clean if t["reason"] == k], 10)
    print("\n[今日涨幅带]")
    for lo, hi, name in [(7, 9, "7-9%"), (9, 11, "9-11%"), (11, 15, "11-15%"), (15, 21, "≥15%")]:
        bucket(name, [t for t in clean if lo <= t["chg"] < hi], 15)
    print("\n[量比]")
    for lo, hi, name in [(2, 3, "2-3x"), (3, 5, "3-5x"), (5, 99, "≥5x")]:
        bucket(name, [t for t in clean if lo <= t["vol_ratio"] < hi], 15)
    print("\n[大阳前20日]")
    for lo, hi, name in [(-99, -15, "≤-15%"), (-15, -5, "-15~-5%"), (-5, 5, "-5~+5%")]:
        bucket(name, [t for t in clean if lo <= t["ret20"] < hi], 15)

    print("\n[300839 样本期内信号]")
    for t in clean:
        if t["code"] == "300839":
            print(
                f"  {t['signal']} → {t['entry_date']}~{t['exit_date']} "
                f"持{t['held']} {t['ret'] * 100:+.2f}% {t['reason']} "
                f"今日{t['chg']}% 量比{t['vol_ratio']}x"
            )


if __name__ == "__main__":
    main()
