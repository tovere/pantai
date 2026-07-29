#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""策略七验证: 威科夫 Spring + 缠论二买(底背驰) —— 底部转折买点。

止损贴 Spring 低点下方(极紧); 启动后移动止损让利润奔跑; 拆分过滤。
"""
import os
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed

import cache_data
import screen_chan_wyckoff_3buy as chan
import screen_spring_2buy as sp

START = os.environ.get("START", "2025-07-01")
END = os.environ.get("END", "2026-06-26")
COST = 0.001
MAX_HOLD = int(os.environ.get("MAX_HOLD", "40"))
TRAIL_PCT = float(os.environ.get("TRAIL_PCT", "0.10"))     # 底部转折给多一点波动空间
LAUNCH_RET = float(os.environ.get("LAUNCH_RET", "0.05"))
LAUNCH_WAIT = int(os.environ.get("LAUNCH_WAIT", "4"))      # 洗盘后不启动就早撤(实测比8好)
GAP_LIMIT = float(os.environ.get("GAP_LIMIT", "0.20"))
INCLUDE_ETF = os.environ.get("INCLUDE_ETF", "0") != "0"
ETF_ONLY = os.environ.get("ETF_ONLY", "0") != "0"  # 纯ETF池(优先于INCLUDE_ETF)


def _has_gap(O, C, a, b):
    for j in range(max(1, a), b + 1):
        if C[j - 1] > 0 and abs(O[j] / C[j - 1] - 1) > GAP_LIMIT:
            return True
    return False


def signal_at(code, name, rows, i):
    if i < 75 or i >= len(rows):
        return None
    D = [r[0] for r in rows[: i + 1]]
    O = [float(r[1]) for r in rows[: i + 1]]
    C = [float(r[2]) for r in rows[: i + 1]]
    H = [float(r[3]) for r in rows[: i + 1]]
    L = [float(r[4]) for r in rows[: i + 1]]
    V = [float(r[5]) for r in rows[: i + 1]]
    A = [float(r[6]) for r in rows[: i + 1]]
    if not (START <= D[-1] <= END) or A[-1] < sp.MIN_AMOUNT:
        return None
    if not sp.weekly_ok(D, O, H, L, C, V, A):
        return None
    dif = sp.macd_dif(C)
    sig = sp.spring_signal(O, H, L, C, V, dif, i)
    if not sig:
        return None
    return {
        "date": D[i],
        "code": code,
        "name": name,
        "entry": C[i],
        "spring_low": sig["spring_low"],
        "div": sig["div"],
        "up_from_spring": sig["up_from_spring"],
        "div_pct": sig["div"] / C[i] * 100,
        "amt": A[i] / 1e8,
    }


def exit_trade(rows, i, rec):
    O = [float(r[1]) for r in rows]
    C = [float(r[2]) for r in rows]
    H = [float(r[3]) for r in rows]
    L = [float(r[4]) for r in rows]
    entry = rec["entry"]
    hard_stop = rec["spring_low"] * 0.99
    end = min(len(rows) - 1, i + MAX_HOLD)
    launched = False
    peak = H[i]
    worst = 0.0
    for j in range(i + 1, end + 1):
        if C[j - 1] > 0 and abs(O[j] / C[j - 1] - 1) > GAP_LIMIT:
            return j, 0.0, "split", worst
        stop = max(hard_stop, peak * (1 - TRAIL_PCT)) if launched else hard_stop
        worst = min(worst, L[j] / entry - 1)
        if O[j] <= stop:
            return j, O[j], ("trail_open" if launched else "stop_open"), worst
        if L[j] <= stop:
            return j, stop, ("trail" if launched else "stop"), worst
        if not launched and (j - i) >= LAUNCH_WAIT:
            return j, C[j], "no_launch", worst
        if not launched and C[j] / entry - 1 >= LAUNCH_RET:
            launched = True
        peak = max(peak, H[j])
    return end, C[end], "timeout", worst


def run_one(code, name, secid, rows=None):
    rows = rows if rows is not None else cache_data.daily_kline(secid)
    if not rows or len(rows) < 110:
        return []
    O = [float(r[1]) for r in rows]
    C = [float(r[2]) for r in rows]
    out = []
    for i in range(75, len(rows) - 3):
        rec = signal_at(code, name, rows, i)
        if not rec:
            continue
        if _has_gap(O, C, i - 70, i):
            continue
        j, sell, reason, mae = exit_trade(rows, i, rec)
        if reason == "split":
            continue
        rec["exit"] = rows[j][0]
        rec["reason"] = reason
        rec["held"] = j - i
        rec["ret"] = sell / rec["entry"] - 1 - COST
        rec["mae"] = mae
        out.append(rec)
    return out


def summarize(trades):
    print(f"\n>> 策略七验证 {START}~{END}  信号 {len(trades)} 笔  (Spring+二买+底背驰, 移动止损)\n")
    if not trades:
        return
    rs = [t["ret"] for t in trades]
    maes = [t["mae"] for t in trades]
    print(
        f"整体  胜率 {sum(1 for v in rs if v > 0)/len(rs)*100:5.1f}%  "
        f"均值 {statistics.mean(rs)*100:+6.2f}%  中位 {statistics.median(rs)*100:+6.2f}%  "
        f"平均持有 {statistics.mean(t['held'] for t in trades):.1f}天  MAE {statistics.mean(maes)*100:+6.2f}%  "
        f"最好/最差 {max(rs)*100:+.1f}%/{min(rs)*100:+.1f}%"
    )
    by_reason = {}
    for t in trades:
        by_reason.setdefault(t["reason"], []).append(t["ret"])
    print("\n出场原因:")
    for reason, vals in sorted(by_reason.items(), key=lambda x: -len(x[1])):
        print(f"  {reason:<12} {len(vals):>4}笔  胜率 {sum(1 for v in vals if v>0)/len(vals)*100:5.1f}%  均值 {statistics.mean(vals)*100:+6.2f}%")
    sample = sorted(trades, key=lambda x: x["date"])[-15:]
    print("\n最近15笔信号:")
    for t in sample:
        print(
            f"{t['date']} {t['code']} {t['name'][:6]:<6} entry={t['entry']:.2f} "
            f"exit={t['exit']} held={t['held']:>2} {t['reason']:<11} ret={t['ret']*100:+.1f}%"
        )


def main():
    if ETF_ONLY:
        U = cache_data.etf_universe()
    elif INCLUDE_ETF:
        U = cache_data.universe() + cache_data.etf_universe()
    else:
        U = cache_data.universe()
    _tag = " (纯ETF)" if ETF_ONLY else (" + ETF" if INCLUDE_ETF else "")
    print(f"标的池 {len(U)} 只{_tag}，策略七(Spring/二买+背驰)验证中...", flush=True)
    trades, done = [], 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(run_one, c, n, s): c for c, n, s in U}
        for fut in as_completed(futs):
            done += 1
            try:
                trades.extend(fut.result())
            except Exception:
                pass
            if done % 500 == 0:
                print(f"  {done}/{len(U)} 信号{len(trades)}", flush=True)
    summarize(trades)


if __name__ == "__main__":
    main()
