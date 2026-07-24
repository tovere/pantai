#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""策略九 · 八策蒸馏版。

蒸馏原则:
  - 策略1/4/8 不作为独立入场, 只吸收教训: 排买不到的板、排纯新高彩票、排年线假突破。
  - 策略2/3 只作为可选扩展, 默认关闭; 广撒网单笔为正但组合噪音偏大。
  - 策略5/6 提供更高质量的结构确认: 三买/LPS + 压缩蓄势。
  - 策略7 提供少量反转补位: Spring 二买 + 强底背驰。
  - 所有信号进入同一个组合池, 同股不重复持仓, 统一硬止损/移动止损。
"""
import os
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed

import cache_data
import screen_chan_wyckoff_3buy as chan
import screen_spring_2buy as sp
import screen_squeeze_launch as sq

START = os.environ.get("START", "2025-07-01")
END = os.environ.get("END", "2026-07-20")
COST = float(os.environ.get("COST", "0.001"))
N_SLOTS = int(os.environ.get("N_SLOTS", "8"))
MIN_AMOUNT = float(os.environ.get("MIN_AMOUNT", "50000000"))
ENABLE_PULLBACK = os.environ.get("ENABLE_PULLBACK", "0") != "0"
ENABLE_BREAK = os.environ.get("ENABLE_BREAK", "0") != "0"
ENABLE_3BUY = os.environ.get("ENABLE_3BUY", "1") != "0"
ENABLE_COIL = os.environ.get("ENABLE_COIL", "1") != "0"
ENABLE_SPRING = os.environ.get("ENABLE_SPRING", "1") != "0"
MAX_HOLD = int(os.environ.get("MAX_HOLD", "45"))
LAUNCH_WAIT = int(os.environ.get("LAUNCH_WAIT", "5"))
LAUNCH_RET = float(os.environ.get("LAUNCH_RET", "0.06"))
TRAIL_PCT = float(os.environ.get("TRAIL_PCT", "0.08"))
HARD_STOP_PCT = float(os.environ.get("HARD_STOP_PCT", "0.05"))
GAP_LIMIT = float(os.environ.get("GAP_LIMIT", "0.20"))


def avg(xs):
    return sum(xs) / len(xs) if xs else 0


def ma(values, p):
    return [avg(values[i - p + 1:i + 1]) if i >= p - 1 else None for i in range(len(values))]


def _has_gap(O, C, a, b):
    for j in range(max(1, a), b + 1):
        if C[j - 1] > 0 and abs(O[j] / C[j - 1] - 1) > GAP_LIMIT:
            return True
    return False


def _weekly_up(D, O, H, L, C, V, A):
    wk = chan.weekly_up_state(D, O, H, L, C, V, A)
    return bool(wk and wk["up"])


def _weekly_loose(D, O, H, L, C, V, A):
    W = chan.weekly_bars(D, O, H, L, C, V, A)
    if len(W) < 12:
        return False
    WC = [w["close"] for w in W]
    WL = [w["low"] for w in W]
    i = len(W) - 1
    ma10 = avg(WC[i - 9:i + 1])
    ma10p = avg(WC[i - 12:i - 2])
    return ma10 > ma10p and WL[i] >= min(WL[max(0, i - 8):i]) * 0.95


def _quality_base(C, V, A, m20, m60, i):
    trend = C[i] >= m20[i] >= m60[i] and m60[i] > m60[i - 10]
    liquid = A[i] >= MIN_AMOUNT
    not_extended = C[i] / m60[i] - 1 <= 0.45
    return trend and liquid and not_extended


def signal_s2_breakout(code, D, O, C, H, L, V, A, m5, m20, m60, i):
    if i < 63 or not _quality_base(C, V, A, m20, m60, i):
        return None
    above = [x is not None and c >= x for c, x in zip(C, m5)]
    hold5 = lambda k: above[k] or (k > 0 and above[k - 1])
    s, k = 0, i
    while k >= 5 and hold5(k):
        s += 1
        k -= 1
    lim = 0.10
    chg = C[i] / C[i - 1] - 1
    if not (above[i] and s == 3 and -0.05 <= chg < lim - 0.005):
        return None
    bias5 = C[i] / m5[i] - 1
    if bias5 > 0.06:
        return None
    return {
        "kind": "break_ma5",
        "entry": C[i],
        "stop": min(C[i] * (1 - HARD_STOP_PCT), m20[i] * 0.985),
        "score": 70 + max(0, int((0.06 - bias5) * 100)),
    }


def signal_s3_pullback(D, O, C, H, L, V, A, m20, m60, i):
    if i < 63 or not _quality_base(C, V, A, m20, m60, i):
        return None
    pulled = max(C[i - 9:i + 1]) >= m20[i] * 1.05
    touch = L[i] <= m20[i] * 1.02 and C[i] >= m20[i]
    shrink = V[i] < avg(V[i - 5:i])
    chg = C[i] / C[i - 1] - 1
    if not (pulled and touch and shrink and -0.05 <= chg < 0.095):
        return None
    return {
        "kind": "pull_ma20",
        "entry": C[i],
        "stop": min(C[i] * (1 - HARD_STOP_PCT), m20[i] * 0.985),
        "score": 76 + max(0, int((m20[i] * 1.02 / max(L[i], 0.01) - 1) * 100)),
    }


def signal_s5_3buy(D, O, C, H, L, V, A, i):
    if i < 80 or A[i] < MIN_AMOUNT:
        return None
    for sos in range(max(65, i - 12), i):
        box = chan.find_box_before_pullback(H, L, C, V, sos - 1)
        if not box:
            continue
        stage = chan.box_stage(L, box)
        if stage["stage"] != 1 or stage["runup"] > 0.60:
            continue
        upper, mid = box["hi"], box["mid"]
        vbase = avg(V[max(0, sos - 20):sos])
        if not (C[sos] > upper * 1.015 and H[sos] > upper * 1.025 and V[sos] >= vbase * 1.25):
            continue
        if min(C[sos + 1:i + 1] or [C[i]]) < mid:
            continue
        pull_days = i - sos
        pull_low = min(L[sos + 1:i + 1])
        pull_low_idx = min(range(sos + 1, i + 1), key=lambda x: L[x])
        close_pos = (C[i] - L[i]) / (H[i] - L[i]) if H[i] > L[i] else 1
        if not (2 <= pull_days <= 8 and upper * 0.99 <= pull_low <= upper * 1.04):
            continue
        if pull_low_idx <= sos or pull_low_idx >= i:
            continue
        if min(C[sos + 1:i + 1]) < upper * 0.985 or max(H[sos + 1:i + 1]) > H[sos] * 1.03:
            continue
        rebound = C[i] > C[i - 1] and C[i] > O[i] and C[i] >= H[i - 1] * 0.995
        reclaimed = C[i] >= upper * 1.01 and close_pos >= 0.6
        shrink = avg(V[sos + 1:i + 1]) <= V[sos] * 0.78
        if rebound and reclaimed and shrink:
            if not _weekly_up(D[:i + 1], O[:i + 1], H[:i + 1], L[:i + 1], C[:i + 1], V[:i + 1], A[:i + 1]):
                return None
            return {"kind": "chan_3buy", "entry": C[i], "stop": min(pull_low * 0.99, upper * 0.985), "score": 88}
    return None


def signal_s6_coil(D, O, C, H, L, V, A, i):
    if i < 90 or A[i] < MIN_AMOUNT:
        return None
    cs = sq.coil_state(O[:i + 1], H[:i + 1], L[:i + 1], C[:i + 1], V[:i + 1], i)
    if not cs:
        return None
    prev = sq.coil_state(O[:i], H[:i], L[:i], C[:i], V[:i], i - 1)
    if prev:
        return None
    if not _weekly_up(D[:i + 1], O[:i + 1], H[:i + 1], L[:i + 1], C[:i + 1], V[:i + 1], A[:i + 1]):
        return None
    return {"kind": "coil_launch", "entry": C[i], "stop": cs["coil_low"] * 0.99, "score": 82 + cs["score"]}


def signal_s7_spring(D, O, C, H, L, V, A, dif, i):
    if i < 90 or A[i] < MIN_AMOUNT:
        return None
    sig = sp.spring_signal(O[:i + 1], H[:i + 1], L[:i + 1], C[:i + 1], V[:i + 1], dif[:i + 1], i)
    if not sig:
        return None
    if not _weekly_loose(D[:i + 1], O[:i + 1], H[:i + 1], L[:i + 1], C[:i + 1], V[:i + 1], A[:i + 1]):
        return None
    return {"kind": "spring_2buy", "entry": C[i], "stop": sig["spring_low"] * 0.99, "score": 92}


def best_signal(code, name, ctx, i):
    D, O, C, H, L, V, A = ctx["D"], ctx["O"], ctx["C"], ctx["H"], ctx["L"], ctx["V"], ctx["A"]
    if i < 90 or not (START <= D[i] <= END) or _has_gap(O, C, i - 70, i):
        return None
    m5, m20, m60 = ctx["m5"], ctx["m20"], ctx["m60"]
    sigs = [
        signal_s2_breakout(code, D, O, C, H, L, V, A, m5, m20, m60, i) if ENABLE_BREAK else None,
        signal_s3_pullback(D, O, C, H, L, V, A, m20, m60, i) if ENABLE_PULLBACK else None,
        signal_s5_3buy(D, O, C, H, L, V, A, i) if ENABLE_3BUY else None,
        signal_s6_coil(D, O, C, H, L, V, A, i) if ENABLE_COIL else None,
        signal_s7_spring(D, O, C, H, L, V, A, ctx["dif"], i) if ENABLE_SPRING else None,
    ]
    sigs = [s for s in sigs if s]
    if not sigs:
        return None
    sig = max(sigs, key=lambda x: x["score"])
    sig.update({"code": code, "name": name, "date": D[i]})
    return sig


def exit_trade(rows, i, rec):
    O = [float(r[1]) for r in rows]
    C = [float(r[2]) for r in rows]
    H = [float(r[3]) for r in rows]
    L = [float(r[4]) for r in rows]
    m5, m20 = ma(C, 5), ma(C, 20)
    entry = rec["entry"]
    hard_stop = min(entry * (1 - HARD_STOP_PCT), rec["stop"])
    end = min(len(rows) - 1, i + MAX_HOLD)
    launched, peak, worst = False, H[i], 0.0
    for j in range(i + 1, end + 1):
        if C[j - 1] > 0 and abs(O[j] / C[j - 1] - 1) > GAP_LIMIT:
            return j, 0.0, "split", worst
        stop = hard_stop
        if rec["kind"] == "break_ma5" and m5[j] is not None and C[j] < m5[j] and C[j - 1] < m5[j - 1]:
            return j, C[j], "ma5_break", min(worst, L[j] / entry - 1)
        if rec["kind"] in ("pull_ma20", "chan_3buy") and m20[j] is not None and C[j] < m20[j]:
            return j, C[j], "ma20_break", min(worst, L[j] / entry - 1)
        if launched:
            stop = max(stop, peak * (1 - TRAIL_PCT))
        worst = min(worst, L[j] / entry - 1)
        if O[j] <= stop:
            return j, O[j], "stop_open" if not launched else "trail_open", worst
        if L[j] <= stop:
            return j, stop, "stop" if not launched else "trail", worst
        if rec["kind"] in ("coil_launch", "spring_2buy") and not launched and (j - i) >= LAUNCH_WAIT:
            return j, C[j], "no_launch", worst
        if C[j] / entry - 1 >= LAUNCH_RET:
            launched = True
        peak = max(peak, H[j])
    return end, C[end], "timeout", worst


def run_one(code, name, secid):
    rows = cache_data.daily_kline(secid)
    if not rows or len(rows) < 110:
        return []
    ctx = {
        "D": [r[0] for r in rows],
        "O": [float(r[1]) for r in rows],
        "C": [float(r[2]) for r in rows],
        "H": [float(r[3]) for r in rows],
        "L": [float(r[4]) for r in rows],
        "V": [float(r[5]) for r in rows],
        "A": [float(r[6]) for r in rows],
    }
    ctx["m5"], ctx["m20"], ctx["m60"] = ma(ctx["C"], 5), ma(ctx["C"], 20), ma(ctx["C"], 60)
    ctx["dif"] = sp.macd_dif(ctx["C"])
    out = []
    i = 90
    while i < len(rows) - 3:
        rec = best_signal(code, name, ctx, i)
        if not rec:
            i += 1
            continue
        j, sell, reason, mae = exit_trade(rows, i, rec)
        if reason != "split":
            rec["exit"] = rows[j][0]
            rec["reason"] = reason
            rec["held"] = j - i
            rec["ret"] = sell / rec["entry"] - 1 - COST
            rec["mae"] = mae
            out.append(rec)
        i = j + 1
    return out


def simulate(trades, slots):
    by = {}
    for t in sorted(trades, key=lambda x: (-x["score"], x["code"])):
        by.setdefault(t["date"], []).append(t)
    days = sorted(set([t["date"] for t in trades] + [t["exit"] for t in trades]))
    cash, pos, curve = 1.0, [], []
    for dt in days:
        keep = []
        for p in pos:
            if p["exit"] == dt:
                cash += p["cap"] * (1 + p["ret"])
            else:
                keep.append(p)
        pos = keep
        held = {p["code"] for p in pos}
        eq = cash + sum(p["cap"] for p in pos)
        for t in by.get(dt, []):
            if len(pos) >= slots or cash <= 1e-9 or t["code"] in held:
                continue
            cap = min(eq / slots, cash)
            cash -= cap
            pos.append({"code": t["code"], "exit": t["exit"], "cap": cap, "ret": t["ret"]})
            held.add(t["code"])
        curve.append(cash + sum(p["cap"] for p in pos))
    peak, mdd = curve[0], 0.0
    for v in curve:
        peak = max(peak, v)
        mdd = max(mdd, (peak - v) / peak)
    return curve[-1] - 1, mdd


def _line(label, ts):
    rs = [t["ret"] for t in ts]
    return (
        f"  {label:<13} {len(ts):>5}笔  胜率 {sum(1 for r in rs if r > 0)/len(rs)*100:5.1f}%  "
        f"均值 {statistics.mean(rs)*100:+6.2f}%  中位 {statistics.median(rs)*100:+6.2f}%"
    )


def summarize(trades):
    print(f"\n>> 策略九·八策蒸馏版 {START}~{END}  交易 {len(trades)} 笔\n")
    if not trades:
        return
    print(_line("整体", trades))
    print(f"  平均持有 {statistics.mean(t['held'] for t in trades):.1f}天  MAE {statistics.mean(t['mae'] for t in trades)*100:+.2f}%")
    print(f"  最好/最差 {max(t['ret'] for t in trades)*100:+.1f}%/{min(t['ret'] for t in trades)*100:+.1f}%")
    by_kind = {}
    for t in trades:
        by_kind.setdefault(t["kind"], []).append(t)
    print("\n按入口:")
    for k, vals in sorted(by_kind.items(), key=lambda x: -len(x[1])):
        print(_line(k, vals))
    by_reason = {}
    for t in trades:
        by_reason.setdefault(t["reason"], []).append(t)
    print("\n按出场:")
    for k, vals in sorted(by_reason.items(), key=lambda x: -len(x[1])):
        print(_line(k, vals))
    print("\n资金曲线:")
    for n in (5, 8, 10):
        tot, mdd = simulate(trades, n)
        print(f"  {n}仓等权: 总收益 {tot*100:+6.1f}%  最大回撤 {mdd*100:5.1f}%")
    print("\n最近15笔:")
    for t in sorted(trades, key=lambda x: x["date"])[-15:]:
        print(f"{t['date']} {t['code']} {t['name'][:6]:<6} {t['kind']:<12} entry={t['entry']:.2f} exit={t['exit']} {t['reason']:<10} ret={t['ret']*100:+.1f}%")


def main():
    U = cache_data.universe()
    print(f"标的池 {len(U)} 只，策略九·八策蒸馏版回测中...", flush=True)
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
                print(f"  {done}/{len(U)} 交易{len(trades)} 失败{failed}", flush=True)
    summarize(trades)


if __name__ == "__main__":
    main()
