#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
策略四：新高股回踩缩量低吸回测。

数据直接使用项目的 data_cache（cache_data.daily_kline，默认 2025 起）。
买入：信号日收盘价。
卖出：跌破保护位（昨日阳线低点）或 -5% 硬止损，先到先平；未触发则按缓存末日收盘强制了结。
"""
import os
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from cache_data import daily_kline, universe

SIGNAL_START = "2025-07-01"
SIGNAL_END = "2026-06-29"
COST = 0.001
N_SLOTS = 5
MAX_WORKERS = 12


def parse_rows(rows):
    dates = [r[0] for r in rows]
    opens = [float(r[1]) for r in rows]
    closes = [float(r[2]) for r in rows]
    highs = [float(r[3]) for r in rows]
    lows = [float(r[4]) for r in rows]
    vols = [float(r[5]) for r in rows]
    return dates, opens, closes, highs, lows, vols


def is_new_high_day(highs, idx):
    return highs[idx] == max(highs[: idx + 1])


def signal_at(dates, opens, closes, highs, lows, vols, i):
    if i < 12:
        return None

    prev_high = max(highs[:i])
    high_idx = max(k for k in range(i) if highs[k] == prev_high)

    if high_idx < i - 2:
        return None
    if sum(1 for k in range(max(0, i - 10), i) if is_new_high_day(highs, k)) > 2:
        return None
    if high_idx < 5 or vols[high_idx] <= sum(vols[high_idx - 5 : high_idx]) / 5:
        return None

    if closes[i - 1] <= opens[i - 1]:
        return None
    protect = lows[i - 1]

    chg = closes[i] / closes[i - 1] - 1
    base_vol = sum(vols[i - 6 : i - 1]) / 5
    if vols[i] >= vols[i - 1] or vols[i] < base_vol * 0.4:
        return None
    if closes[i] < protect or chg > 0.05 or chg < -0.05:
        return None

    intraday_range = highs[i] - lows[i]
    if intraday_range > 0 and closes[i] < lows[i] + intraday_range * 0.5:
        return None

    for k in range(i - 9, i + 1):
        if closes[k] / closes[k - 1] - 1 <= -0.06:
            return None
    if closes[i] / closes[i - 3] - 1 >= 0.30:
        return None

    return {
        "entry": dates[i],
        "buy": closes[i],
        "protect": protect,
        "new_high_days_ago": i - high_idx,
        "shrink": vols[i] / vols[i - 1] if vols[i - 1] else 0,
        "to_protect": closes[i] / protect - 1,
    }


def run_one(code, name, rows):
    if not rows or len(rows) < 30:
        return []

    dates, opens, closes, highs, lows, vols = parse_rows(rows)
    trades = []
    i = 12
    n = len(rows)

    while i < n - 1:
        sig = signal_at(dates, opens, closes, highs, lows, vols, i)
        if not sig or not (SIGNAL_START <= dates[i] <= SIGNAL_END):
            i += 1
            continue

        buy = sig["buy"]
        stop = max(sig["protect"], buy * 0.95)
        j = i + 1
        sell = None
        closed = True

        while j < n:
            if opens[j] <= stop:
                sell = opens[j]
                break
            if lows[j] <= stop:
                sell = stop
                break
            j += 1

        if sell is None:
            sell = closes[-1]
            j = n - 1
            closed = False

        trades.append(
            {
                "code": code,
                "name": name,
                "entry": dates[i],
                "exit": dates[j],
                "ret": sell / buy - 1 - COST,
                "held": j - i,
                "closed": closed,
                "buy": buy,
                "sell": sell,
                "protect": sig["protect"],
                "new_high_days_ago": sig["new_high_days_ago"],
                "to_protect": sig["to_protect"],
            }
        )
        i = j + 1

    return trades


def simulate(trades):
    if not trades:
        return 0, 0

    by_entry = {}
    for trade in trades:
        by_entry.setdefault(trade["entry"], []).append(trade)

    days = sorted({t["entry"] for t in trades} | {t["exit"] for t in trades})
    cash = 1.0
    positions = []
    curve = []

    for day in days:
        keep = []
        for pos in positions:
            if pos["exit"] == day:
                cash += pos["cap"] * (1 + pos["ret"])
            else:
                keep.append(pos)
        positions = keep

        held_codes = {p["code"] for p in positions}
        equity = cash + sum(p["cap"] for p in positions)
        for trade in sorted(by_entry.get(day, []), key=lambda t: t["to_protect"]):
            if len(positions) >= N_SLOTS or cash <= 1e-9:
                break
            if trade["code"] in held_codes:
                continue
            commit = min(equity / N_SLOTS, cash)
            cash -= commit
            positions.append(
                {
                    "code": trade["code"],
                    "exit": trade["exit"],
                    "cap": commit,
                    "ret": trade["ret"],
                }
            )
            held_codes.add(trade["code"])

        curve.append(cash + sum(p["cap"] for p in positions))

    peak = curve[0]
    max_drawdown = 0
    for value in curve:
        peak = max(peak, value)
        max_drawdown = max(max_drawdown, (peak - value) / peak)
    return curve[-1] - 1, max_drawdown


def print_stats(trades):
    if not trades:
        print("\n>> 无交易")
        return

    rets = [t["ret"] for t in trades]
    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r <= 0]
    avg_win = statistics.mean(wins) if wins else 0
    avg_loss = statistics.mean(losses) if losses else 0
    open_n = sum(1 for t in trades if not t["closed"])

    print(f"\n>> 策略四回测 {SIGNAL_START}~{SIGNAL_END}  成本往返{COST*100:.2f}%")
    print(f">> 交易总数 {len(trades)} 笔（其中未触发止损强制了结 {open_n} 笔）\n")
    print(f"  胜率        {len(wins)/len(rets)*100:.1f}%")
    print(f"  单笔均收益   {statistics.mean(rets)*100:+.2f}%")
    print(f"  中位数      {statistics.median(rets)*100:+.2f}%")
    print(f"  平均盈利    {avg_win*100:+.2f}%   平均亏损 {avg_loss*100:+.2f}%")
    print(f"  盈亏比      {avg_win/abs(avg_loss):.2f}" if avg_loss else "  盈亏比 inf")
    print(f"  平均持有    {statistics.mean(t['held'] for t in trades):.1f} 个交易日")
    print(f"  最好/最差   {max(rets)*100:+.0f}% / {min(rets)*100:+.0f}%")

    print("\n  分月:")
    by_month = {}
    for trade in trades:
        by_month.setdefault(trade["entry"][:7], []).append(trade["ret"])
    for month in sorted(by_month):
        rs = by_month[month]
        win_rate = sum(1 for r in rs if r > 0) / len(rs) * 100
        print(f"   {month}: {len(rs):>4}笔 胜率{win_rate:4.1f}% 均{statistics.mean(rs)*100:+5.2f}%")

    print("\n  收益分布:")
    buckets = [
        ("亏损>10%", lambda r: r <= -0.10),
        ("亏5~10%", lambda r: -0.10 < r <= -0.05),
        ("亏0~5%", lambda r: -0.05 < r <= 0),
        ("赚0~5%", lambda r: 0 < r <= 0.05),
        ("赚5~15%", lambda r: 0.05 < r <= 0.15),
        ("赚>15%", lambda r: r > 0.15),
    ]
    for name, fn in buckets:
        count = sum(1 for r in rets if fn(r))
        print(f"   {name:<8}: {count:>5} 笔 ({count/len(rets)*100:4.1f}%)")

    total, max_drawdown = simulate(trades)
    print(f"\n  资金曲线({N_SLOTS}仓位等权): 总收益 {total*100:+.1f}%   最大回撤 {max_drawdown*100:.1f}%")


def main():
    items = universe()
    print(f"缓存股票池 {len(items)} 只，策略四回测中...")

    all_trades = []
    done = 0
    failed = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(daily_kline, secid): (code, name) for code, name, secid in items}
        for future in as_completed(futures):
            done += 1
            code, name = futures[future]
            try:
                rows = future.result()
                if rows:
                    all_trades.extend(run_one(code, name, rows))
                else:
                    failed += 1
            except Exception:
                failed += 1
            if done % 1000 == 0:
                print(f"  {done}/{len(items)} 交易{len(all_trades)} 失败{failed}")

    all_trades.sort(key=lambda t: (t["entry"], t["to_protect"], t["code"]))
    print_stats(all_trades)


if __name__ == "__main__":
    main()
