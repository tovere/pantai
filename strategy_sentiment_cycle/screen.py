#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""每日情绪周期：打印阶段日历 + 今日可执行 B 候选（首板/二板回踩，不追封板）。

  CACHE_ONLY=1 python3 strategy_sentiment_cycle/screen.py
  SCREEN_DATE=2026-08-21 python3 strategy_sentiment_cycle/screen.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from strategy_sentiment_cycle import cycle
from strategy_sentiment_cycle import backtest as bt

TODAY = os.environ.get("SCREEN_DATE", date.today().isoformat())
MIN_AMT = float(os.environ.get("MIN_AMOUNT", "50000000"))


def _last_idx(s, day):
    dates = s["dates"]
    if not dates:
        return None
    if dates[-1] == day:
        return len(dates) - 1
    # 允许缓存停在 day 之前：找不到当日则无信号
    try:
        return dates.index(day)
    except ValueError:
        return None


def _candidate(s, i, height, kind):
    """复用回测入场条件，只检查当日是否命中（不模拟卖出）。"""
    C, O, H, L, A = s["C"], s["O"], s["H"], s["L"], s["A"]
    lu, yizi, streak = s["lu"], s["yizi"], s["streak"]
    code = s["code"]
    if i < 2:
        return None
    if streak[i - 1] != height or not lu[i - 1] or yizi[i - 1]:
        return None
    if A[i - 1] < MIN_AMT:
        return None
    if not bt._buyable_close(code, C[i - 1], C[i]):
        return None
    if cycle.is_limit_up(code, C[i - 1], O[i]):
        return None
    board_low = L[i - 1]
    if board_low <= 0 or L[i] < board_low * bt.PULL_BUF:
        return None
    yang = C[i] >= O[i]
    hold_up = C[i] >= C[i - 1] * 0.97
    close_pos = (C[i] - L[i]) / (H[i] - L[i]) if H[i] > L[i] else 0.5
    if not ((yang and hold_up) or close_pos >= 0.55):
        return None
    chg = (C[i] / C[i - 1] - 1) * 100 if C[i - 1] else 0
    stop = min(C[i] * (1 - bt.HARD_STOP), board_low * 0.99)
    return {
        "code": code,
        "name": s["name"],
        "kind": kind,
        "height": height,
        "board_date": s["dates"][i - 1],
        "close": C[i],
        "chg": chg,
        "board_low": board_low,
        "stop": stop,
        "amt": A[i] / 1e8,
        "yizi": False,
    }


def main():
    os.environ.setdefault("CACHE_ONLY", "1")
    print("载入日线并构建情绪日历…", flush=True)
    stocks = cycle.load_stocks()
    days = cycle.aggregate(stocks)
    cycle.save_calendar(days, len(stocks))
    if not days:
        print("日历为空（缓存不足）")
        return

    asof = days[-1]["date"]
    target = TODAY if TODAY <= asof else asof
    today_m = next((m for m in days if m["date"] == target), days[-1])
    phase = today_m["phase"]

    print(f"\n>>> {target}  主板情绪 {today_m['phase_cn']}  热度{today_m['heat']}")
    print(
        f"    涨停{today_m['lu']} 跌停{today_m['ld']} 最高{today_m['max_height']}板"
        f"({today_m['leader']} {today_m['leader_name']})  "
        f"1/2/3/4+ = {today_m['h1']}/{today_m['h2']}/{today_m['h3']}/{today_m['h4p']}"
    )
    print(
        f"    晋级{today_m['promo']*100:.1f}%  炸板{today_m['break_rate']*100:.1f}%  "
        f"昨日涨停竞价溢价{today_m['premium']*100:+.2f}%  上涨家占比{today_m['breadth']*100:.1f}%"
    )
    print(f"    {cycle.advice(phase)}")
    if TODAY > asof:
        print(f"    注意：缓存最新日是 {asof}，不是 {TODAY}")

    print("\n近 15 日：")
    print("日期        阶段  热度  涨停 高板  晋级%  炸板%  溢价%")
    for m in days[-15:]:
        mark = " <<<" if m["date"] == target else ""
        print(
            f"{m['date']}  {m['phase_cn']:<2} {m['heat']:5.1f} "
            f"{m['lu']:4d} {m['max_height']:3d}  {m['promo']*100:5.1f} "
            f"{m['break_rate']*100:5.1f} {m['premium']*100:+6.2f}{mark}"
        )

    if phase in cycle.A_PAUSE_PHASES:
        a_label = "关（冰点/修复）"
    elif phase == "ebb":
        a_label = "降权（退潮）"
    else:
        a_label = "开"
    b1_ok = phase in cycle.B1_PHASES
    b2_ok = phase in cycle.B2_PHASES
    print(f"\nA 过滤器（策略2/3）：{a_label}")
    print(f"B1 首板回踩：{'阶段匹配' if b1_ok else '阶段不匹配'}（回测为负，只观察）")
    print(f"B2 二板回踩：{'阶段匹配' if b2_ok else '阶段不匹配'}（回测为负，只观察）")

    hits = []
    for s in stocks:
        i = _last_idx(s, target)
        if i is None:
            continue
        h1 = _candidate(s, i, 1, "B1首板回踩")
        h2 = _candidate(s, i, 2, "B2二板回踩")
        if h1:
            h1["allowed"] = b1_ok
            hits.append(h1)
        if h2:
            h2["allowed"] = b2_ok
            hits.append(h2)
    hits.sort(key=lambda x: (-x["height"], -x["amt"]))

    shown = [h for h in hits if h["allowed"]]
    parked = [h for h in hits if not h["allowed"]]
    print(f"\n>>> 今日可执行 B 候选 {len(shown)} 只（形态命中但阶段关闭 {len(parked)}）\n")
    print("类型        代码    名称        现价   今日%  板日低  止损   额(亿)  板日")
    for h in shown[:40]:
        print(
            f"{h['kind']:<10} {h['code']}  {h['name'][:6]:<7} {h['close']:>7.2f} "
            f"{h['chg']:>+6.2f} {h['board_low']:>7.2f} {h['stop']:>7.2f} "
            f"{h['amt']:>6.1f}  {h['board_date']}"
        )
    if not shown:
        print("  （无）")
    if parked:
        print(f"\n阶段关闭、仅供观察 {len(parked)} 只： "
              + ", ".join(f"{x['code']}{x['name'][:4]}" for x in parked[:12]))

    dump = os.environ.get("WATCH_JSON_OUT")
    if dump:
        with open(dump, "w", encoding="utf-8") as f:
            json.dump({
                "strategy": "sentiment_cycle",
                "variant": "stock",
                "is_etf": False,
                "date": target,
                "phase": phase,
                "phase_cn": today_m["phase_cn"],
                "heat": today_m["heat"],
                "advice": cycle.advice(phase),
                "metrics": {k: today_m[k] for k in
                            ("lu", "ld", "max_height", "promo", "break_rate", "premium", "breadth")},
                "hits": shown,
            }, f, ensure_ascii=False)


if __name__ == "__main__":
    main()
