#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""回测: 周线向上 + 日线严格三买，持有到确认顶分型。"""
import os
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed

import screen_chan_wyckoff_3buy as sig

START = os.environ.get("START", "2025-07-01")
END = os.environ.get("END", "2026-06-26")
N_SLOTS = 8
COST = 0.001
STRICT = os.environ.get("STRICT_BUY", "1") != "0"
MAX_HOLD = 30
GAP_LIMIT = float(os.environ.get("GAP_LIMIT", "0.20"))  # 单日跳空超此比例=拆分/脏数据, 丢弃(主要保护ETF)
# 出场模式: fractal=确认顶分型卖(原版); trail=嫁接策略6(未启动时间止损+启动后移动止损)。
EXIT_MODE = os.environ.get("EXIT_MODE", "fractal")
LAUNCH_RET = float(os.environ.get("LAUNCH_RET", "0.05"))   # trail: 收盘涨幅达到即判定‘已启动’
LAUNCH_WAIT = int(os.environ.get("LAUNCH_WAIT", "5"))      # trail: 未启动时间止损
TRAIL_PCT = float(os.environ.get("TRAIL_PCT", "0.08"))     # trail: 启动后从峰值回撤离场


def _has_gap(O, C, a, b):
    for j in range(max(1, a), b + 1):
        if C[j - 1] > 0 and abs(O[j] / C[j - 1] - 1) > GAP_LIMIT:
            return True
    return False


def signal_at(code, name, rows, i):
    if i < 90 or i >= len(rows):
        return None
    D = [r[0] for r in rows[: i + 1]]
    O = [float(r[1]) for r in rows[: i + 1]]
    C = [float(r[2]) for r in rows[: i + 1]]
    H = [float(r[3]) for r in rows[: i + 1]]
    L = [float(r[4]) for r in rows[: i + 1]]
    V = [float(r[5]) for r in rows[: i + 1]]
    A = [float(r[6]) for r in rows[: i + 1]]
    if not (START <= D[-1] <= END) or A[-1] < sig.MIN_AMOUNT:
        return None
    weekly = sig.weekly_up_state(D, O, H, L, C, V, A)
    if not weekly or not weekly["up"]:
        return None
    ma = lambda p, k: sig.avg(C[k - p + 1 : k + 1])
    k = len(C) - 1
    if C[k] < ma(60, k) or ma(60, k) <= ma(60, k - 10):
        return None
    if C[k - 1] <= 0 or C[k] / C[k - 1] - 1 < -0.055:
        return None
    for sos in range(max(65, k - 12), k):
        box = sig.find_box_before_pullback(H, L, C, V, sos - 1)
        if not box:
            continue
        stage = sig.box_stage(L, box)
        if stage["runup"] > sig.MAX_RUNUP:
            continue
        if STRICT and stage["stage"] != 1:
            continue
        upper, mid = box["hi"], box["mid"]
        vbase = sig.avg(V[max(0, sos - 20) : sos])
        if not (C[sos] > upper * 1.015 and H[sos] > upper * 1.025 and V[sos] >= vbase * 1.25):
            continue
        if min(C[sos + 1 : k + 1] or [C[k]]) < mid:
            continue
        pull_days = k - sos
        if not (1 <= pull_days <= 8):
            continue
        pull_low = min(L[sos + 1 : k + 1])
        pull_low_idx = min(range(sos + 1, k + 1), key=lambda x: L[x])
        close_pos = (C[k] - L[k]) / (H[k] - L[k]) if H[k] > L[k] else 1
        if not (upper * 0.985 <= pull_low <= upper * 1.08):
            continue
        if not (C[k] >= upper * 0.995 and L[k] >= mid):
            continue
        if not (sig.avg(V[sos + 1 : k + 1]) <= V[sos] * 0.78 and close_pos >= 0.45):
            continue
        if C[k] / C[k - 3] - 1 >= 0.20:
            continue
        if STRICT:
            # 严格三买: 不能只是突破后横住，必须有清晰回踩段，低点贴近中枢上沿，
            # 且低点后出现重新转强确认。
            if pull_days < 2:
                continue
            if not (upper * 0.99 <= pull_low <= upper * 1.04):
                continue
            if pull_low_idx <= sos or pull_low_idx >= k:
                continue
            if min(C[sos + 1 : k + 1]) < upper * 0.985:
                continue
            if max(H[sos + 1 : k + 1]) > H[sos] * 1.03:
                continue
            rebound = C[k] > C[k - 1] and C[k] > O[k] and C[k] >= H[k - 1] * 0.995
            reclaimed = C[k] >= upper * 1.01 and close_pos >= 0.6
            if not (rebound and reclaimed):
                continue
        return {
            "date": D[k],
            "code": code,
            "name": name,
            "entry": C[k],
            "upper": upper,
            "buy_low": pull_low,
            "stage": stage["stage"],
            "runup": stage["runup"],
            "dist": (C[k] / upper - 1) * 100,
            "pull_days": pull_days,
            "vol_shrink": sig.avg(V[sos + 1 : k + 1]) / V[sos],
            "amt": A[k] / 1e8,
        }
    return None


def is_top_fractal(H, L, j):
    return H[j] > H[j - 1] and H[j] > H[j + 1] and L[j] > L[j - 1] and L[j] > L[j + 1]


def exit_trade(rows, i, rec):
    O = [float(r[1]) for r in rows]
    C = [float(r[2]) for r in rows]
    H = [float(r[3]) for r in rows]
    L = [float(r[4]) for r in rows]
    entry = rec["entry"]
    base_stop = min(rec["buy_low"], rec["upper"] * 0.985)
    end = min(len(rows) - 1, i + MAX_HOLD)
    worst = 0.0
    launched = False
    peak = H[i]
    for j in range(i + 1, end + 1):
        # 异常跳空(拆分/脏数据): 丢弃该样本。
        if C[j - 1] > 0 and abs(O[j] / C[j - 1] - 1) > GAP_LIMIT:
            return j, 0.0, "split", worst
        # trail 模式启动后, 止损上移到峰值回撤位。
        stop = max(base_stop, peak * (1 - TRAIL_PCT)) if (EXIT_MODE == "trail" and launched) else base_stop
        worst = min(worst, L[j] / entry - 1)
        if O[j] <= stop:
            return j, O[j], ("trail_open" if (EXIT_MODE == "trail" and launched) else "stop_open"), worst
        if L[j] <= stop:
            return j, stop, ("trail" if (EXIT_MODE == "trail" and launched) else "stop"), worst
        if EXIT_MODE == "fractal":
            # 第 j 根收盘后才能确认 j-1 是顶分型，所以按第 j 根收盘价卖。
            if j >= i + 2 and is_top_fractal(H, L, j - 1):
                return j, C[j], "top_fractal", worst
        else:  # trail
            if not launched and (j - i) >= LAUNCH_WAIT:
                return j, C[j], "no_launch", worst
            if not launched and C[j] / entry - 1 >= LAUNCH_RET:
                launched = True
        peak = max(peak, H[j])
    return end, C[end], "timeout", worst


def run_one(code, name, secid, rows=None):
    rows = rows if rows is not None else sig.kline(secid)
    if not rows or len(rows) < 110:
        return []
    O = [float(r[1]) for r in rows]
    C = [float(r[2]) for r in rows]
    out = []
    for i in range(90, len(rows) - 3):
        rec = signal_at(code, name, rows, i)
        if not rec:
            continue
        if _has_gap(O, C, i - 70, i):   # 入场前窗口有拆分 → 均线污染, 丢弃
            continue
        j, sell, reason, mae = exit_trade(rows, i, rec)
        if reason == "split":           # 持有期内拆分 → 丢弃
            continue
        rec["exit"] = rows[j][0]
        rec["sell"] = sell
        rec["reason"] = reason
        rec["held"] = j - i
        rec["ret"] = sell / rec["entry"] - 1 - COST
        rec["mae"] = mae
        out.append(rec)
    return out


def summarize(trades):
    label = "严格三买" if STRICT else "SOS后LPS/类三买"
    exit_label = "移动止损" if EXIT_MODE == "trail" else "确认顶分型卖"
    print(f"\n>> 回测 {START}~{END} 信号 {len(trades)} 笔，周线向上 + 日线{label} + {exit_label}\n")
    if not trades:
        return
    rs = [t["ret"] for t in trades]
    maes = [t["mae"] for t in trades]
    wins = [r for r in rs if r > 0]
    print(f"胜率 {len(wins)/len(rs)*100:5.1f}%  均值 {statistics.mean(rs)*100:+6.2f}%  中位 {statistics.median(rs)*100:+6.2f}%")
    print(f"平均持有 {statistics.mean(t['held'] for t in trades):.1f}天  平均MAE {statistics.mean(maes)*100:+6.2f}%  最好/最差 {max(rs)*100:+.1f}%/{min(rs)*100:+.1f}%")
    by_reason = {}
    for t in trades:
        by_reason.setdefault(t["reason"], []).append(t["ret"])
    print("\n出场原因:")
    for reason, vals in sorted(by_reason.items(), key=lambda x: -len(x[1])):
        print(f"  {reason:<12} {len(vals):>4}笔  胜率 {sum(1 for v in vals if v>0)/len(vals)*100:5.1f}%  均值 {statistics.mean(vals)*100:+6.2f}%")
    by_stage = {}
    for t in trades:
        by_stage.setdefault(t.get("stage", 0), []).append(t)
    print("\n按中枢序号(前期涨幅档, 验证第一个中枢是否更优):")
    for s, ts in sorted(by_stage.items()):
        vals = [t["ret"] for t in ts]
        maes = [t["mae"] for t in ts]
        print(
            f"  第{s}个中枢  {len(vals):>4}笔  胜率 {sum(1 for v in vals if v>0)/len(vals)*100:5.1f}%  "
            f"均值 {statistics.mean(vals)*100:+6.2f}%  中位 {statistics.median(vals)*100:+6.2f}%  "
            f"MAE {statistics.mean(maes)*100:+6.2f}%"
        )
    sample = sorted(trades, key=lambda x: x["date"])[-20:]
    print("\n最近20笔信号:")
    for t in sample:
        print(
            f"{t['date']} {t['code']} {t['name'][:6]:<6} entry={t['entry']:.2f} "
            f"exit={t['exit']} held={t['held']:>2} {t['reason']:<11} ret={t['ret']*100:+.1f}%"
        )


def main():
    if os.environ.get("ETF_ONLY", "0") != "0":
        import cache_data
        U = cache_data.etf_universe()
    else:
        U = sig.universe()
        if os.environ.get("INCLUDE_ETF", "0") != "0":
            import cache_data
            U = U + cache_data.etf_universe()
    print(f"标的池 {len(U)} 只，回测中(出场={EXIT_MODE})...", flush=True)
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
