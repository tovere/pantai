#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""策略十三 · 启动加速回测：次日开盘买；破启动低止损 / 移动止损 / 超时。"""
import os
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed

import cache_data
import screen_launch_accel as sig

START = os.environ.get("START", "2025-01-01")
END = os.environ.get("END", "2026-08-12")
COST = float(os.environ.get("COST", "0.001"))
MAX_HOLD = int(os.environ.get("MAX_HOLD", "10"))
TRAIL = float(os.environ.get("TRAIL", "0.08"))  # 启动后峰值回撤8%
COOLDOWN = int(os.environ.get("COOLDOWN", "5"))


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
        # 边缘: 昨日未信号
        if sig.signal_at(code, name, rows, i - 1):
            i += 1
            continue
        buy_i = i + 1
        if buy_i >= len(rows):
            break
        entry = float(rows[buy_i][1])
        if entry <= 0:
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
            "launch_chg": rec["launch_chg"],
            "hold_days": rec["hold_days"],
            "chg": rec["chg"],
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
        f"  {label:<28} {len(xs):>4}笔  胜{sum(r>0 for r in rs)/len(rs)*100:5.1f}%  "
        f"均{statistics.mean(rs)*100:+6.2f}%  中{statistics.median(rs)*100:+6.2f}%  "
        f"均持{statistics.mean(t['held'] for t in xs):.1f}日"
    )


def main():
    uni = sig.universe()
    print(
        f"回测池 {len(uni)} | {START}~{END} | 启动加速 "
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

    # 剔除样本末截断
    clean = [
        t for t in trades
        if not (t["reason"] == "timeout" and t["held"] < MAX_HOLD)
    ]
    print(f"\n>> 策略十三·启动加速  信号{len(clean)}笔 (剔截断后)\n")
    if not clean:
        return
    bucket("整体", clean, 1)
    from collections import Counter
    print("\n[离场]")
    for k, n in Counter(t["reason"] for t in clean).most_common():
        bucket(k, [t for t in clean if t["reason"] == k], 10)
    print("\n[启动后整理天数]")
    for d in range(HOLD_MIN := sig.HOLD_MIN, sig.HOLD_MAX + 1):
        bucket(f"整理{d}天", [t for t in clean if t["hold_days"] == d], 15)
    print("\n[今日涨幅带]")
    for lo, hi, name in [(3, 5, "3-5%"), (5, 7, "5-7%"), (7, 8.5, "7-8.5%")]:
        bucket(name, [t for t in clean if lo <= t["chg"] < hi], 15)
    print("\n[启动日强度]")
    for lo, hi, name in [(7, 8, "启动7-8"), (8, 9.5, "启动8-9.5"), (9.5, 12, "启动≥9.5")]:
        bucket(name, [t for t in clean if lo <= t["launch_chg"] < hi], 15)

    # 安记专项: 历史是否曾触发
    print("\n[603696 样本期内信号]")
    for t in clean:
        if t["code"] == "603696":
            print(
                f"  {t['signal']} → {t['entry_date']}~{t['exit_date']} "
                f"持{t['held']} {t['ret']*100:+.2f}% {t['reason']} "
                f"今日{t['chg']}% 启动{t['launch_chg']}% 整理{t['hold_days']}天"
            )


if __name__ == "__main__":
    main()
