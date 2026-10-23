#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""情绪周期回测：A 状态过滤器（策略2+3）+ B 可执行打板（首板/二板回踩）。

硬约束（沿用策略一教训）：
  - 信号日收盘封死涨停 → 买不进，丢弃
  - 一字涨停不作为打板标的（无价格发现）
  - 买点是回踩日收盘，不是封板价
  - 不按事后收益排序选仓（无未来函数）
"""
from __future__ import annotations

import os
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cache_data
from strategy_sentiment_cycle import cycle

START = os.environ.get("START", "2025-07-01")
END = os.environ.get("END", "2026-08-21")
COST = float(os.environ.get("COST", "0.001"))
MIN_AMT = float(os.environ.get("MIN_AMOUNT", "50000000"))
HARD_STOP = float(os.environ.get("HARD_STOP", "0.05"))
B_MAX_HOLD = int(os.environ.get("B_MAX_HOLD", "3"))
N_SLOTS = int(os.environ.get("N_SLOTS", "8"))
PULL_BUF = float(os.environ.get("PULL_BUF", "0.97"))  # 回踩不得深破板日低点


def _in_win(d):
    return START <= d <= END


def _buyable_close(code, prev, close):
    return not cycle.is_limit_up(code, prev, close)


def s2_trades(s):
    """策略2：新突破站上 MA5（B 容忍）+ MA60 上行，破 MA5 或 -5% 离场。"""
    C, O, L, dates = s["C"], s["O"], s["L"], s["dates"]
    n = len(dates)
    if n < 72:
        return []
    code = s["code"]
    ma5 = [sum(C[k - 4 : k + 1]) / 5 if k >= 4 else None for k in range(n)]
    above = [ma5[k] is not None and C[k] >= ma5[k] for k in range(n)]
    hold = lambda k: above[k] or (k > 0 and above[k - 1])
    out = []
    i = 70
    while i < n - 1:
        stretch = 0
        k = i
        while k >= 5 and hold(k):
            stretch += 1
            k -= 1
        ma60 = sum(C[i - 59 : i + 1]) / 60
        ma60p = sum(C[i - 69 : i - 9]) / 60  # i>=70 → i-69>=1，避免负索引切片
        up = C[i] >= ma60 and ma60 > ma60p
        chg = C[i] / C[i - 1] - 1 if C[i - 1] else 0
        if (
            above[i] and stretch == 3 and up and chg >= -0.05
            and _buyable_close(code, C[i - 1], C[i])
            and _in_win(dates[i])
        ):
            buy = C[i]
            stop = buy * (1 - HARD_STOP)
            j, sell = i + 1, None
            while j < n:
                if O[j] <= stop:
                    sell = O[j]
                    break
                if L[j] <= stop:
                    sell = stop
                    break
                if not hold(j):
                    sell = C[j]
                    break
                j += 1
            if sell is None:
                sell = C[n - 1]
                j = n - 1
            rec = _trade(s, "S2", i, j, buy, sell)
            if rec:
                out.append(rec)
            i = j + 1
        else:
            i += 1
    return out


def s3_trades(s):
    """策略3：回踩 MA20 缩量低吸，破 MA20 或 -5% 离场。"""
    C, O, L, dates = s["C"], s["O"], s["L"], s["dates"]
    n = len(dates)
    if n < 72:
        return []
    vol = s["V"]
    code = s["code"]
    ma20 = [sum(C[k - 19 : k + 1]) / 20 if k >= 19 else None for k in range(n)]
    ma60 = [sum(C[k - 59 : k + 1]) / 60 if k >= 59 else None for k in range(n)]
    out = []
    i = 70
    while i < n - 1:
        m20, m60 = ma20[i], ma60[i]
        m60p = ma60[i - 10]
        if m20 is None or m60 is None or m60p is None:
            i += 1
            continue
        uptrend = C[i] > m20 > m60 and m60 > m60p
        pulled = max(C[i - 9 : i + 1]) >= m20 * 1.05
        touch = L[i] <= m20 * 1.02 and C[i] >= m20
        shrink = vol[i] < sum(vol[i - 5 : i]) / 5 if sum(vol[i - 5 : i]) > 0 else False
        chg = C[i] / C[i - 1] - 1 if C[i - 1] else 0
        if (
            uptrend and pulled and touch and shrink and chg >= -0.05
            and _buyable_close(code, C[i - 1], C[i])
            and _in_win(dates[i])
        ):
            buy = C[i]
            stop = buy * (1 - HARD_STOP)
            j, sell = i + 1, None
            while j < n:
                if O[j] <= stop:
                    sell = O[j]
                    break
                if L[j] <= stop:
                    sell = stop
                    break
                if ma20[j] is not None and C[j] < ma20[j]:
                    sell = C[j]
                    break
                j += 1
            if sell is None:
                sell = C[n - 1]
                j = n - 1
            rec = _trade(s, "S3", i, j, buy, sell)
            if rec:
                out.append(rec)
            i = j + 1
        else:
            i += 1
    return out


def _trade(s, src, i, j, buy, sell):
    if buy <= 0 or sell <= 0:
        return None
    return {
        "code": s["code"],
        "name": s["name"],
        "src": src,
        "entry": s["dates"][i],
        "exit": s["dates"][j],
        "ret": sell / buy - 1 - COST,
        "held": j - i,
    }


def b_pullback_trades(s, height, src):
    """昨日连板=height 且非一字 → 今日未封死、回踩不破板日低点、收盘承接。"""
    C, O, H, L, A = s["C"], s["O"], s["H"], s["L"], s["A"]
    dates, lu, yizi, streak = s["dates"], s["lu"], s["yizi"], s["streak"]
    n = len(dates)
    code = s["code"]
    out = []
    i = 2
    while i < n - 1:
        if not _in_win(dates[i]):
            i += 1
            continue
        if streak[i - 1] != height or not lu[i - 1] or yizi[i - 1]:
            i += 1
            continue
        if A[i - 1] < MIN_AMT:
            i += 1
            continue
        if not _buyable_close(code, C[i - 1], C[i]):
            i += 1
            continue
        # 开盘已涨停也买不进（即使收盘打开）
        if cycle.is_limit_up(code, C[i - 1], O[i]):
            i += 1
            continue
        board_low = L[i - 1]
        if board_low <= 0 or L[i] < board_low * PULL_BUF:
            i += 1
            continue
        yang = C[i] >= O[i]
        hold_up = C[i] >= C[i - 1] * 0.97
        close_pos = (C[i] - L[i]) / (H[i] - L[i]) if H[i] > L[i] else 0.5
        if not ((yang and hold_up) or close_pos >= 0.55):
            i += 1
            continue
        buy = C[i]
        stop = min(buy * (1 - HARD_STOP), board_low * 0.99)
        j, sell, reason = i + 1, None, "timeout"
        end = min(n - 1, i + B_MAX_HOLD)
        while j <= end:
            if O[j] <= stop:
                sell, reason = O[j], "stop_open"
                break
            if L[j] <= stop:
                sell, reason = stop, "stop"
                break
            if C[j] < board_low:
                sell, reason = C[j], "break"
                break
            j += 1
        if sell is None:
            j = end
            sell = C[j]
        rec = _trade(s, src, i, j, buy, sell)
        if rec:
            rec["reason"] = reason
            rec["height"] = height
            rec["board_date"] = dates[i - 1]
            out.append(rec)
        i = j + 1
    return out


def b3_premium_trades(s):
    """对照：昨日涨停（非一字）→ 今日开盘买、收盘卖。测可执行的「昨日涨停溢价」。"""
    C, O, dates, lu, yizi = s["C"], s["O"], s["dates"], s["lu"], s["yizi"]
    n = len(dates)
    code = s["code"]
    out = []
    for i in range(1, n - 1):
        if not _in_win(dates[i]):
            continue
        if not lu[i] or yizi[i]:
            continue
        buy_i = i + 1
        if buy_i >= n:
            break
        if cycle.is_limit_up(code, C[i], O[buy_i]):
            continue  # 次日一字开盘买不进
        buy, sell = O[buy_i], C[buy_i]
        rec = _trade(s, "B3", buy_i, buy_i, buy, sell)
        if not rec:
            continue
        rec["board_date"] = dates[i]
        rec["held"] = 1
        out.append(rec)
    return out


def tag_phase(trades, pmap):
    for t in trades:
        t["phase"] = pmap.get(t["entry"], "")
        t["phase_cn"] = cycle.PHASE_CN.get(t["phase"], "?")
    return trades


def stats(xs, min_n=15):
    if len(xs) < min_n:
        return None
    rs = [t["ret"] for t in xs]
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]
    avg_w = statistics.mean(wins) if wins else 0.0
    avg_l = statistics.mean(losses) if losses else 0.0
    pl = (avg_w / abs(avg_l)) if avg_l else float("inf")
    held = statistics.mean(t.get("held", 0) for t in xs)
    return {
        "n": len(xs),
        "wr": len(wins) / len(xs),
        "avg": statistics.mean(rs),
        "med": statistics.median(rs),
        "pl": pl,
        "held": held,
        "best": max(rs),
        "worst": min(rs),
    }


def pr(label, s):
    if not s:
        print(f"  {label:<22} 样本不足")
        return
    print(
        f"  {label:<22} {s['n']:>5}笔  胜{s['wr']*100:5.1f}%  "
        f"均{s['avg']*100:+6.2f}%  中{s['med']*100:+6.2f}%  "
        f"盈亏比{s['pl']:.2f}  持{s['held']:.1f}日  "
        f"最好{s['best']*100:+.0f}% 最差{s['worst']*100:+.0f}%"
    )


def by_phase(trades):
    print("  按入场日阶段：")
    for ph in cycle.PHASES:
        pr(cycle.PHASE_CN[ph], stats([t for t in trades if t.get("phase") == ph], min_n=10))


def simulate(trades, n_slots=N_SLOTS):
    """等权 N 仓，同股不重复；同日信号按代码序取，不按收益排。"""
    if not trades:
        return None, None
    by = defaultdict(list)
    for t in trades:
        by[t["entry"]].append(t)
    for d in by:
        by[d].sort(key=lambda t: t["code"])
    days = sorted(set(t["entry"] for t in trades) | set(t["exit"] for t in trades))
    cash, pos, curve = 1.0, [], []

    def _close_due(dt):
        nonlocal cash, pos
        keep = []
        for p in pos:
            if p["exit"] == dt:
                cash += p["cap"] * (1 + p["ret"])
            else:
                keep.append(p)
        pos = keep

    for dt in days:
        _close_due(dt)  # 隔夜仓到期
        held = {p["code"] for p in pos}
        eq = cash + sum(p["cap"] for p in pos)
        for t in by.get(dt, []):
            if len(pos) >= n_slots or cash <= 1e-9:
                break
            if t["code"] in held:
                continue
            commit = min(eq / n_slots, cash)
            cash -= commit
            pos.append({"code": t["code"], "exit": t["exit"], "cap": commit, "ret": t["ret"]})
            held.add(t["code"])
        _close_due(dt)  # 当日开当日平（B3 溢价）
        curve.append(cash + sum(p["cap"] for p in pos))
    if not curve:
        return None, None
    peak, mdd = curve[0], 0.0
    for v in curve:
        peak = max(peak, v)
        mdd = max(mdd, (peak - v) / peak if peak else 0)
    return curve[-1] - 1, mdd


def pr_sim(label, trades):
    ret, mdd = simulate(trades)
    if ret is None:
        print(f"  {label:<22} 无交易")
        return
    print(f"  {label:<22} {N_SLOTS}仓  收益{ret*100:+.1f}%  回撤{mdd*100:.1f}%  笔数{len(trades)}")


def main():
    os.environ.setdefault("CACHE_ONLY", "1")
    print(f"情绪周期回测 {START}~{END}  主板缓存  成本{COST*100:.2f}%", flush=True)
    print("载入日线…", flush=True)
    stocks = cycle.load_stocks()
    print(f"有效 {len(stocks)} 只，汇总日历…", flush=True)
    days = cycle.aggregate(stocks)
    cycle.save_calendar(days, len(stocks))
    pmap = cycle.phase_map(days)
    cnt = Counter(m["phase_cn"] for m in days if _in_win(m["date"]))
    print(f"日历 {len(days)} 日  窗口内阶段天数 {dict(cnt)}")
    if days:
        last = days[-1]
        print(f"最新 {last['date']} {last['phase_cn']} 热度{last['heat']} "
              f"涨停{last['lu']} 最高{last['max_height']}板 溢价{last['premium']*100:+.2f}%")
        print(f"建议：{cycle.advice(last['phase'])}")

    print("\n===== 日历（窗口内末 20 日）=====")
    print("日期        阶段  热度  涨停 跌停 高板 高位n  晋级%  炸板%  溢价%")
    win_days = [m for m in days if _in_win(m["date"])]
    for m in win_days[-20:]:
        print(
            f"{m['date']}  {m['phase_cn']:<2} {m['heat']:5.1f} "
            f"{m['lu']:4d} {m['ld']:4d} {m['max_height']:3d} {m.get('high_n',0):4d}  "
            f"{m['promo']*100:5.1f} {m['break_rate']*100:5.1f} {m['premium']*100:+6.2f}"
        )

    print("\n生成 A/B 交易…", flush=True)
    a_all, b1, b2, b3 = [], [], [], []
    for s in stocks:
        a_all.extend(s2_trades(s))
        a_all.extend(s3_trades(s))
        b1.extend(b_pullback_trades(s, 1, "B1"))
        b2.extend(b_pullback_trades(s, 2, "B2"))
        b3.extend(b3_premium_trades(s))
    tag_phase(a_all, pmap)
    tag_phase(b1, pmap)
    tag_phase(b2, pmap)
    tag_phase(b3, pmap)
    s2 = [t for t in a_all if t["src"] == "S2"]
    s3 = [t for t in a_all if t["src"] == "S3"]
    a_gate = [t for t in a_all if t.get("phase") in cycle.A_TRADE_PHASES]
    a_hyp = [t for t in a_all if t.get("phase") in cycle.A_HYPOTHESIS_PHASES]
    a_skip_hot = [t for t in a_all if t.get("phase") != "climax"]
    a_skip_climax_ebb = [t for t in a_all if t.get("phase") not in ("climax", "ebb")]
    a_ebb = [t for t in a_all if t.get("phase") == "ebb"]
    b1_gate = [t for t in b1 if t.get("phase") in cycle.B1_PHASES]
    b2_gate = [t for t in b2 if t.get("phase") in cycle.B2_PHASES]
    b3_gate = [t for t in b3 if t.get("phase") in cycle.B3_PHASES]
    b3_ferm = [t for t in b3 if t.get("phase") == "ferment"]

    print("\n===== A. 状态过滤器（策略2+3，信号日收盘买）=====")
    pr("S2 全时段", stats(s2))
    pr("S3 全时段", stats(s3))
    pr("S2+S3 全时段", stats(a_all))
    by_phase(a_all)
    pr("只做发酵+高潮(默认A)", stats(a_gate))
    pr("教科书·只做修复+发酵", stats(a_hyp))
    pr("避开高潮", stats(a_skip_hot))
    pr("避开高潮+退潮", stats(a_skip_climax_ebb))
    pr("只做退潮", stats(a_ebb))
    print(f"  {N_SLOTS} 仓资金曲线：")
    pr_sim("全时段", a_all)
    pr_sim("只做发酵+高潮", a_gate)
    pr_sim("教科书·修复+发酵", a_hyp)
    pr_sim("避开高潮", a_skip_hot)
    pr_sim("避开高潮+退潮", a_skip_climax_ebb)
    pr_sim("只做退潮", a_ebb)

    print("\n===== B. 独立打板（回踩收盘买，不追封板）=====")
    print("B1 首板回踩")
    pr("全时段", stats(b1))
    by_phase(b1)
    pr("只做冰点+修复", stats(b1_gate, min_n=10))
    pr_sim("B1 全时段", b1)
    pr_sim("B1 冰点+修复", b1_gate)

    print("B2 二板回踩")
    pr("全时段", stats(b2, min_n=10))
    by_phase(b2)
    pr("只做修复+发酵", stats(b2_gate, min_n=10))
    pr_sim("B2 全时段", b2)
    pr_sim("B2 修复+发酵", b2_gate)

    print("B3 对照·昨日涨停次日开盘买收盘卖（可执行溢价）")
    pr("全时段", stats(b3))
    by_phase(b3)
    pr("只做发酵+高潮", stats(b3_gate))
    pr("只做发酵", stats(b3_ferm))
    pr_sim("B3 全时段", b3)
    pr_sim("B3 发酵+高潮", b3_gate)
    pr_sim("B3 只做发酵", b3_ferm)

    print("\n说明：主板口径，缺创业板/科创。"
          "A 的教科书过滤(修复+发酵)已被回测推翻；B1/B2 可执行回踩为负。")


if __name__ == "__main__":
    main()
