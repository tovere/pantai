#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""策略八 · 放量突破年线后缩量回踩年线。

定义:
  1) 老股: 至少有 280 根日线, 可稳定计算 MA250。
  2) 放量突破: 近 BREAK_LOOKBACK 日内, 收盘从年线下方上穿并站上 MA250,
     当日量能 >= 前 20 日均量 * BREAK_VOL_RATIO。
  3) 缩量回踩: 突破后第 PULL_MIN_DAYS~PULL_MAX_DAYS 日内, 当日低点贴近
     MA250, 收盘仍守住年线, 成交量低于前 5 日均量且明显低于突破日。
  4) 买入: 回踩确认日收盘。
  5) 卖出: 年线失守 / -6%硬止损 / 启动后移动止损 / 最长持有。
"""
import os
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed

import cache_data

START = os.environ.get("START", "2025-07-01")
END = os.environ.get("END", "2026-07-20")
COST = float(os.environ.get("COST", "0.001"))

MA_LONG = int(os.environ.get("MA_LONG", "250"))
MIN_BARS = int(os.environ.get("MIN_BARS", str(MA_LONG + 30)))
MIN_AMOUNT = float(os.environ.get("MIN_AMOUNT", "80000000"))

BREAK_LOOKBACK = int(os.environ.get("BREAK_LOOKBACK", "25"))
BREAK_VOL_RATIO = float(os.environ.get("BREAK_VOL_RATIO", "1.5"))
BREAK_CLOSE_ABOVE = float(os.environ.get("BREAK_CLOSE_ABOVE", "1.005"))
PRE_BELOW_DAYS = int(os.environ.get("PRE_BELOW_DAYS", "10"))

PULL_MIN_DAYS = int(os.environ.get("PULL_MIN_DAYS", "3"))
PULL_MAX_DAYS = int(os.environ.get("PULL_MAX_DAYS", "20"))
PULL_TOUCH_UPPER = float(os.environ.get("PULL_TOUCH_UPPER", "1.03"))
PULL_CLOSE_FLOOR = float(os.environ.get("PULL_CLOSE_FLOOR", "0.995"))
PULL_VOL_RATIO = float(os.environ.get("PULL_VOL_RATIO", "0.85"))
PULL_VS_BREAK = float(os.environ.get("PULL_VS_BREAK", "0.70"))

MAX_BREAK_RUNUP = float(os.environ.get("MAX_BREAK_RUNUP", "0.25"))
MAX_HOLD = int(os.environ.get("MAX_HOLD", "45"))
HARD_STOP_PCT = float(os.environ.get("HARD_STOP_PCT", "0.06"))
MA_STOP_FLOOR = float(os.environ.get("MA_STOP_FLOOR", "0.985"))
LAUNCH_RET = float(os.environ.get("LAUNCH_RET", "0.08"))
TRAIL_PCT = float(os.environ.get("TRAIL_PCT", "0.08"))
GAP_LIMIT = float(os.environ.get("GAP_LIMIT", "0.20"))


def ma(values, p):
    return [sum(values[i - p + 1:i + 1]) / p if i >= p - 1 else None for i in range(len(values))]


def _has_gap(open_, close, a, b):
    for j in range(max(1, a), b + 1):
        if close[j - 1] > 0 and abs(open_[j] / close[j - 1] - 1) > GAP_LIMIT:
            return True
    return False


def _breakout_at(C, V, A, M250, i):
    if i < MA_LONG or M250[i] is None or M250[i - 1] is None:
        return None
    prev_below = sum(C[k] < M250[k] for k in range(i - PRE_BELOW_DAYS, i) if M250[k])
    if prev_below < max(3, PRE_BELOW_DAYS // 2):
        return None
    vol20 = statistics.mean(V[i - 20:i]) if i >= 20 else 0
    if vol20 <= 0:
        return None
    crossed = C[i - 1] <= M250[i - 1] * 1.002 and C[i] >= M250[i] * BREAK_CLOSE_ABOVE
    if not crossed:
        return None
    vol_ratio = V[i] / vol20
    if vol_ratio < BREAK_VOL_RATIO or A[i] < MIN_AMOUNT:
        return None
    return {"idx": i, "vol": V[i], "vol_ratio": vol_ratio, "ma250": M250[i]}


def _find_breakout(C, H, V, A, M250, i):
    start = max(MA_LONG, i - BREAK_LOOKBACK)
    best = None
    for k in range(start, i - PULL_MIN_DAYS + 1):
        br = _breakout_at(C, V, A, M250, k)
        if not br:
            continue
        days = i - k
        if not (PULL_MIN_DAYS <= days <= PULL_MAX_DAYS):
            continue
        runup = max(H[k:i + 1]) / C[k] - 1
        if runup > MAX_BREAK_RUNUP:
            continue
        if min(C[k + 1:i]) < M250[k] * MA_STOP_FLOOR:
            continue
        best = br
    return best


def _is_pullback(C, L, V, M250, break_vol, i):
    if M250[i] is None:
        return False
    vol5 = statistics.mean(V[i - 5:i]) if i >= 5 else 0
    touch = L[i] <= M250[i] * PULL_TOUCH_UPPER and C[i] >= M250[i] * PULL_CLOSE_FLOOR
    shrink = vol5 > 0 and V[i] <= vol5 * PULL_VOL_RATIO and V[i] <= break_vol * PULL_VS_BREAK
    return touch and shrink


def signal_at(code, name, rows, i):
    D = [r[0] for r in rows[:i + 1]]
    O = [float(r[1]) for r in rows[:i + 1]]
    C = [float(r[2]) for r in rows[:i + 1]]
    H = [float(r[3]) for r in rows[:i + 1]]
    L = [float(r[4]) for r in rows[:i + 1]]
    V = [float(r[5]) for r in rows[:i + 1]]
    A = [float(r[6]) for r in rows[:i + 1]]
    if i < MIN_BARS or not (START <= D[-1] <= END) or A[-1] < MIN_AMOUNT:
        return None
    M250 = ma(C, MA_LONG)
    if M250[i] is None or M250[i - 10] is None:
        return None
    if M250[i] < M250[i - 10] * 0.99:
        return None
    br = _find_breakout(C, H, V, A, M250, i)
    if not br:
        return None
    if _has_gap(O, C, br["idx"] - 20, i):
        return None
    if not _is_pullback(C, L, V, M250, br["vol"], i):
        return None
    # 只记录该突破后的首次回踩确认, 避免同一段年线附近横盘被连续计数。
    first_possible = br["idx"] + PULL_MIN_DAYS
    for k in range(first_possible, i):
        if _is_pullback(C, L, V, M250, br["vol"], k):
            return None
    return {
        "date": D[i],
        "code": code,
        "name": name,
        "entry": C[i],
        "ma250": M250[i],
        "break_date": D[br["idx"]],
        "break_days": i - br["idx"],
        "break_vol_ratio": br["vol_ratio"],
        "pull_depth": L[i] / M250[i] - 1,
        "ma_slope10": M250[i] / M250[i - 10] - 1,
    }


def exit_trade(rows, i, rec):
    O = [float(r[1]) for r in rows]
    C = [float(r[2]) for r in rows]
    H = [float(r[3]) for r in rows]
    L = [float(r[4]) for r in rows]
    M250 = ma(C, MA_LONG)
    entry = rec["entry"]
    hard_stop = min(entry * (1 - HARD_STOP_PCT), rec["ma250"] * MA_STOP_FLOOR)
    end = min(len(rows) - 1, i + MAX_HOLD)
    launched = False
    peak = H[i]
    worst = 0.0
    for j in range(i + 1, end + 1):
        if C[j - 1] > 0 and abs(O[j] / C[j - 1] - 1) > GAP_LIMIT:
            return j, 0.0, "split", worst
        ma_stop = M250[j] * MA_STOP_FLOOR if M250[j] else hard_stop
        stop = max(hard_stop, ma_stop)
        if launched:
            stop = max(stop, peak * (1 - TRAIL_PCT))
        worst = min(worst, L[j] / entry - 1)
        if O[j] <= stop:
            return j, O[j], "stop_open" if not launched else "trail_open", worst
        if L[j] <= stop:
            return j, stop, "stop" if not launched else "trail", worst
        if C[j] / entry - 1 >= LAUNCH_RET:
            launched = True
        peak = max(peak, H[j])
    return end, C[end], "timeout", worst


def run_one(code, name, secid):
    rows = cache_data.daily_kline(secid)
    if not rows or len(rows) < MIN_BARS + 5:
        return []
    out = []
    for i in range(MIN_BARS, len(rows) - 3):
        rec = signal_at(code, name, rows, i)
        if not rec:
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


def _bucket_days(x):
    if x <= 5:
        return "回踩3-5天"
    if x <= 10:
        return "回踩6-10天"
    return "回踩11-20天"


def _bucket_slope(x):
    if x < 0:
        return "年线微降"
    if x < 0.01:
        return "年线走平"
    return "年线上行"


def _line(label, trades):
    rs = [t["ret"] for t in trades]
    maes = [t["mae"] for t in trades]
    return (
        f"  {label:<12} {len(trades):>4}笔  胜率 {sum(1 for r in rs if r > 0)/len(rs)*100:5.1f}%  "
        f"均值 {statistics.mean(rs)*100:+6.2f}%  中位 {statistics.median(rs)*100:+6.2f}%  "
        f"MAE {statistics.mean(maes)*100:+6.2f}%"
    )


def summarize(trades):
    print(f"\n>> 策略八·年线突破回踩验证 {START}~{END}  信号 {len(trades)} 笔\n")
    if not trades:
        return
    rs = [t["ret"] for t in trades]
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]
    maes = [t["mae"] for t in trades]
    print(
        f"整体  胜率 {len(wins)/len(rs)*100:5.1f}%  均值 {statistics.mean(rs)*100:+6.2f}%  "
        f"中位 {statistics.median(rs)*100:+6.2f}%  平均持有 {statistics.mean(t['held'] for t in trades):.1f}天"
    )
    print(
        f"      平均盈利 {(statistics.mean(wins) if wins else 0)*100:+.2f}% / "
        f"平均亏损 {(statistics.mean(losses) if losses else 0)*100:+.2f}%  "
        f"MAE {statistics.mean(maes)*100:+.2f}%  最好/最差 {max(rs)*100:+.1f}%/{min(rs)*100:+.1f}%"
    )
    by_reason = {}
    for t in trades:
        by_reason.setdefault(t["reason"], []).append(t["ret"])
    print("\n出场原因:")
    for reason, vals in sorted(by_reason.items(), key=lambda x: -len(x[1])):
        print(f"  {reason:<12} {len(vals):>4}笔  胜率 {sum(1 for v in vals if v > 0)/len(vals)*100:5.1f}%  均值 {statistics.mean(vals)*100:+6.2f}%")

    def group(keyfn, title, order):
        buckets = {}
        for t in trades:
            buckets.setdefault(keyfn(t), []).append(t)
        print(f"\n按{title}:")
        for key in order:
            if key in buckets:
                print(_line(key, buckets[key]))

    group(lambda t: _bucket_days(t["break_days"]), "突破后回踩天数", ["回踩3-5天", "回踩6-10天", "回踩11-20天"])
    group(lambda t: _bucket_slope(t["ma_slope10"]), "年线斜率", ["年线微降", "年线走平", "年线上行"])

    print("\n最近15笔:")
    for t in sorted(trades, key=lambda x: x["date"])[-15:]:
        print(
            f"{t['date']} {t['code']} {t['name'][:6]:<6} entry={t['entry']:.2f} "
            f"br={t['break_date']} d={t['break_days']:>2} volx={t['break_vol_ratio']:.1f} "
            f"exit={t['exit']} held={t['held']:>2} {t['reason']:<10} ret={t['ret']*100:+.1f}%"
        )


def main():
    U = cache_data.universe()
    print(f"标的池 {len(U)} 只，策略八·年线突破回踩验证中...", flush=True)
    trades, done, failed = [], 0, 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(run_one, c, n, s): c for c, n, s in U}
        for fut in as_completed(futs):
            done += 1
            try:
                trades.extend(fut.result())
            except Exception:
                failed += 1
            if done % 500 == 0:
                print(f"  {done}/{len(U)} 信号{len(trades)} 失败{failed}", flush=True)
    summarize(trades)


if __name__ == "__main__":
    main()
