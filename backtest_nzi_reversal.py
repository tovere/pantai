#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""策略八 N字反包 回测。出场借策略六: 回踩低硬止损 → 未续涨时间止损 → 续涨后移动止损。"""
import os
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed

import cache_data
import screen_chan_wyckoff_3buy as chan
import screen_nzi_reversal as nz

START = os.environ.get("START", "2025-07-01")
END = os.environ.get("END", "2026-06-26")
COST = 0.001
MAX_HOLD = int(os.environ.get("MAX_HOLD", "30"))
FAST_DAYS = int(os.environ.get("FAST_DAYS", "6"))
ACCEL_RET = float(os.environ.get("ACCEL_RET", "0.12"))
REQUIRE_WEEKLY_UP = os.environ.get("REQUIRE_WEEKLY_UP", "1") != "0"
LAUNCH_RET = float(os.environ.get("LAUNCH_RET", "0.05"))
LAUNCH_WAIT = int(os.environ.get("LAUNCH_WAIT", "5"))
TRAIL_PCT = float(os.environ.get("TRAIL_PCT", "0.08"))
GAP_LIMIT = float(os.environ.get("GAP_LIMIT", "0.20"))


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
    if not (START <= D[-1] <= END) or A[-1] < nz.MIN_AMOUNT:
        return None
    if REQUIRE_WEEKLY_UP:
        w = chan.weekly_up_state(D, O, H, L, C, V, A)
        if not w or not w["up"]:
            return None
    sig = nz.nzi_signal(O, H, L, C, V, i)
    if not sig:
        return None
    # 去重: 昨日若已是反包信号则不重复记(避免连续两日同一反包计两次)
    if nz.nzi_signal(O[:-1], H[:-1], L[:-1], C[:-1], V[:-1], i - 1):
        return None
    return {
        "date": D[i], "code": code, "name": name, "entry": C[i],
        "pull_low": sig["pull_low"], "pull_days": sig["pull_days"],
        "shrink": sig["shrink"], "runup": sig["runup"],
    }


def exit_trade(rows, i, rec):
    O = [float(r[1]) for r in rows]
    C = [float(r[2]) for r in rows]
    H = [float(r[3]) for r in rows]
    L = [float(r[4]) for r in rows]
    entry = rec["entry"]
    hard_stop = rec["pull_low"] * 0.99
    end = min(len(rows) - 1, i + MAX_HOLD)
    launched, peak, worst = False, H[i], 0.0
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


def run_one(code, name, secid):
    rows = cache_data.daily_kline(secid)
    if not rows or len(rows) < 100:
        return []
    O = [float(r[1]) for r in rows]
    C = [float(r[2]) for r in rows]
    out = []
    for i in range(78, len(rows) - 3):
        rec = signal_at(code, name, rows, i)
        if not rec:
            continue
        if _has_gap(O, C, i - 60, i):
            continue
        j, sell, reason, mae = exit_trade(rows, i, rec)
        if reason == "split":
            continue
        fwd_end = min(len(rows) - 1, i + FAST_DAYS)
        k_end = i
        for k in range(i + 1, fwd_end + 1):
            if C[k - 1] > 0 and abs(O[k] / C[k - 1] - 1) > GAP_LIMIT:
                break
            k_end = k
        fwd_max = max((C[k] / rec["entry"] - 1 for k in range(i + 1, k_end + 1)), default=0.0)
        rec["accel"] = 1 if fwd_max >= ACCEL_RET else 0
        rec["exit"] = rows[j][0]
        rec["reason"] = reason
        rec["held"] = j - i
        rec["ret"] = sell / rec["entry"] - 1 - COST
        rec["mae"] = mae
        out.append(rec)
    return out


def _bucket_runup(x):
    if x < 0.25:
        return "前涨<25%"
    if x < 0.50:
        return "前涨25-50%"
    return "前涨>=50%"


def _line(name, ts):
    rs = [t["ret"] for t in ts]
    maes = [t["mae"] for t in ts]
    return (
        f"  {name:<12} {len(ts):>4}笔  胜率 {sum(1 for v in rs if v>0)/len(rs)*100:5.1f}%  "
        f"均值 {statistics.mean(rs)*100:+6.2f}%  中位 {statistics.median(rs)*100:+6.2f}%  "
        f"MAE {statistics.mean(maes)*100:+6.2f}%"
    )


def summarize(trades):
    print(f"\n>> 策略八(N字反包)验证 {START}~{END}  信号 {len(trades)} 笔\n")
    if not trades:
        return
    rs = [t["ret"] for t in trades]
    maes = [t["mae"] for t in trades]
    print(
        f"整体  胜率 {sum(1 for v in rs if v>0)/len(rs)*100:5.1f}%  "
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

    def group(keyfn, title, order=None):
        g = {}
        for t in trades:
            g.setdefault(keyfn(t), []).append(t)
        print(f"\n按{title}:")
        for k in (order or sorted(g.keys())):
            if k in g:
                _line_out = _line(str(k), g[k])
                print(_line_out)

    group(lambda t: f"回调{t['pull_days']}天", "回调天数")
    group(lambda t: _bucket_runup(t["runup"]), "前期涨幅档", ["前涨<25%", "前涨25-50%", "前涨>=50%"])

    sample = sorted(trades, key=lambda x: x["date"])[-15:]
    print("\n最近15笔:")
    for t in sample:
        print(
            f"{t['date']} {t['code']} {t['name'][:6]:<6} entry={t['entry']:.2f} "
            f"exit={t['exit']} held={t['held']:>2} {t['reason']:<11} ret={t['ret']*100:+.1f}%"
        )


def main():
    U = cache_data.universe()
    print(f"标的池 {len(U)} 只，策略八(N字反包)验证中...", flush=True)
    trades, done = [], 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(run_one, c, n, s): c for c, n, s in U}
        for fut in as_completed(futs):
            done += 1
            trades.extend(fut.result())
            if done % 500 == 0:
                print(f"  {done}/{len(U)} 信号{len(trades)}", flush=True)
    summarize(trades)


if __name__ == "__main__":
    main()
