#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""三重共振回测: 周线向上 + 日线三买(选池) × 30f三买(择时)。

- 观察池: 某票在过去 POOL_DAYS 个交易日内触发过**日线三买**(日线版 check 已含
  周线向上过滤), 则视为"在有效三买结构里", 进池 POOL_DAYS 天。
- 择时: 只在池内的票上, 当 **30f三买** 出现时进场(入场那根30分bar)。
- 出场: 复用 30f 版口径(硬止损贴上沿 + 启动后移动止损)。
- 不吃未来: 日线信号按 as-of 日线切片; 池判定只看信号bar日期**之前**的日线。

⚠️ 30分数据仅约40交易日, 且共振本就稀有, 样本会很小, 只作方向性参考。
单线程(日线 check 用模块级 TODAY, 避免多线程竞态)。
"""
import bisect
import os
import statistics

import cache_data
import screen_chan_wyckoff_3buy as dstk
import screen_chan_wyckoff_3buy_30f as m30
import backtest_chan_wyckoff_3buy_30f as bt30

KLT = 30
POOL_DAYS = int(os.environ.get("POOL_DAYS", "5"))         # 日线三买观察池有效交易日
ETF_ONLY = os.environ.get("ETF_ONLY", "0") != "0"
ENTRY_MAX_EXT = float(os.environ.get("ENTRY_MAX_EXT", "0"))

# 日线选池用宽松(候选结构), 30f择时用严格(可 env 调)
dstk.STRICT_BUY = os.environ.get("DAILY_STRICT", "0") != "0"
m30.STRICT_BUY = os.environ.get("STRICT_BUY", "1") != "0"
m30.ENTRY_MAX_EXT = ENTRY_MAX_EXT


def universe():
    return cache_data.etf_universe() if ETF_ONLY else cache_data.universe()


def daily_signal_dates(code, name, drows, ddates, start_idx):
    """该票 start_idx 起, 各日线bar as-of 是否日线三买 -> 命中日期集合。"""
    out = set()
    for di in range(max(80, start_idx), len(ddates)):
        dstk.TODAY = ddates[di]
        try:
            if dstk.check(code, name, drows[: di + 1]):
                out.add(ddates[di])
        except Exception:
            pass
    return out


def run_one(code, name, secid):
    mrows = cache_data.min_kline(secid, KLT)
    if not mrows or len(mrows) < 90:
        return []
    drows = cache_data.daily_kline(secid)
    if not drows or len(drows) < 80:
        return []
    ddates = [r[0] for r in drows]
    m_start = mrows[0][0][:10]
    # 日线信号只从 30f 起点前 POOL_DAYS+3 天算起, 省算力
    s_idx = max(0, bisect.bisect_left(ddates, m_start) - POOL_DAYS - 3)
    dsig = daily_signal_dates(code, name, drows, ddates, s_idx)
    if not dsig:
        return []  # 整段无日线三买 -> 不可能共振

    trades = []
    i = 80
    n = len(mrows)
    while i < n - 1:
        day = mrows[i][0][:10]
        k = bisect.bisect_left(ddates, day) - 1  # 最后一根 < day 的日线
        if k < 0:
            i += 1
            continue
        pool = {ddates[j] for j in range(max(0, k - POOL_DAYS + 1), k + 1)}
        if not (pool & dsig):
            i += 1
            continue  # 不在日线三买观察池
        dt = bt30.daily_trend_asof(drows, day)
        if dt is None:
            i += 1
            continue
        item = m30.check(code, name, mrows[: i + 1], dt)
        if not item:
            i += 1
            continue
        entry = float(mrows[i][2])
        rec = {"entry": entry, "buy_low": item["buy_low"], "upper": item["upper"]}
        j, sell, reason, mae = bt30.exit_trade(mrows, i, rec)
        ret = sell / entry - 1 - bt30.COST
        trades.append({
            "code": code, "name": name, "time": mrows[i][0], "entry": entry,
            "exit": mrows[j][0], "held": j - i, "reason": reason, "ret": ret, "mae": mae,
        })
        i = j + 1
    return trades


def main():
    uni = universe()
    pool = "ETF" if ETF_ONLY else "个股"
    print(f"{pool}池 {len(uni)} 只, 三重共振回测 "
          f"(日线三买{'严格' if dstk.STRICT_BUY else '宽松'}选池 POOL_DAYS={POOL_DAYS} × "
          f"30f三买{'严格' if m30.STRICT_BUY else '宽松'}择时 ENTRY_EXT={ENTRY_MAX_EXT})...", flush=True)
    trades, done = [], 0
    for c, n, s in uni:
        done += 1
        try:
            trades.extend(run_one(c, n, s))
        except Exception:
            pass
        if done % 500 == 0:
            print(f"  {done}/{len(uni)} 累计信号 {len(trades)}", flush=True)

    if not trades:
        print("\n无共振信号(40天样本+严格共振, 空是正常的)")
        return
    rs = [t["ret"] for t in trades]
    win = sum(1 for v in rs if v > 0)
    print(f"\n整体: {len(trades)} 笔  胜率 {win/len(trades)*100:.1f}%  "
          f"均值 {statistics.mean(rs)*100:+.2f}%  中位 {statistics.median(rs)*100:+.2f}%  "
          f"平均持有 {statistics.mean(t['held'] for t in trades):.1f}根  "
          f"平均MAE {statistics.mean(t['mae'] for t in trades)*100:.2f}%  "
          f"最好/最差 {max(rs)*100:+.1f}%/{min(rs)*100:+.1f}%")
    from collections import defaultdict
    by = defaultdict(list)
    for t in trades:
        by[t["reason"]].append(t["ret"])
    print("出场原因:")
    for r, vs in sorted(by.items(), key=lambda x: -len(x[1])):
        w = sum(1 for v in vs if v > 0)
        print(f"  {r:<12} {len(vs):>3}笔  胜率 {w/len(vs)*100:5.1f}%  均值 {statistics.mean(vs)*100:+6.2f}%")
    print("\n全部信号:")
    for t in sorted(trades, key=lambda x: x["time"]):
        print(f"  {t['time']} {t['code']} {t['name'][:6]:<6} entry={t['entry']:.2f} "
              f"exit={t['exit'][5:]} held={t['held']:>2} {t['reason']:<11} ret={t['ret']*100:+.1f}%")


if __name__ == "__main__":
    main()
