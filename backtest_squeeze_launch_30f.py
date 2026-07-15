#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""30 分钟级别 策略六(C段加速前临界点 / 压缩蓄势)回测。

口径同日线版 backtest_squeeze_launch.py 的出场思路, 但在 30 分序列上跑:
  - 信号: 复用 screen_squeeze_launch_30f.check(判某根30分bar是否压缩临界点);
  - 大级别过滤: 日线趋势按**信号那根bar的日期之前已收盘的日线**切片(不吃未来),
    抄 30f 模板(backtest_chan_wyckoff_3buy_30f)的 daily_trend_asof;
  - 出场(策略六口径): 收敛下沿硬止损 → 未启动时间止损 → 启动后从峰值回撤的移动止损,
    MAX_HOLD 根 30分bar 封顶;
  - 胜率 = ret>0 的笔数占比。

⚠️ 30 分数据仅约 40 交易日(~320 根), 样本小, 结果只作方向性参考。
持有/等待都按 30分bar 计(8根=1个交易日)。
"""
import os
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed

import cache_data
import screen_chan_wyckoff_3buy as d
import screen_squeeze_launch_30f as s30

KLT = 30
COST = 0.001
MAX_HOLD = int(os.environ.get("MAX_HOLD", "40"))       # 30分bar(~5交易日)
LAUNCH_WAIT = int(os.environ.get("LAUNCH_WAIT", "8"))  # 未启动时间止损(~1日)
LAUNCH_RET = float(os.environ.get("LAUNCH_RET", "0.04"))
TRAIL_PCT = float(os.environ.get("TRAIL_PCT", "0.05"))
GAP_LIMIT = float(os.environ.get("GAP_LIMIT", "0.20"))  # 异常跳空(拆分/脏数据)阈值
ETF_ONLY = os.environ.get("ETF_ONLY", "0") != "0"
STRICT = os.environ.get("STRICT_BUY", "1") != "0"


def universe():
    return cache_data.etf_universe() if ETF_ONLY else cache_data.universe()


def daily_trend_asof(drows, day):
    """信号日 day(YYYY-MM-DD)之前已收盘的日线, 判日线趋势+流动性。不吃未来。"""
    sub = [r for r in drows if r[0] < day]
    if len(sub) < 60:
        return None
    C = [float(r[2]) for r in sub]
    A = [float(r[6]) for r in sub]
    i = len(C) - 1
    if A[i] < s30.MIN_AMOUNT:
        return None
    ma = lambda p, k: d.avg(C[k - p + 1 : k + 1])
    up = (C[i] >= ma(20, i) and ma(20, i) > ma(20, i - 5) and ma(20, i) >= ma(60, i))
    return {"up": up, "damt": A[i]}


def exit_trade(rows, i, rec):
    """策略六出场: 收敛下沿硬止损 → 未启动时间止损 → 启动后从峰值回撤的移动止损。

    - 启动前: 止损固定在收敛区下沿(coil_low*0.99)。埋伏 LAUNCH_WAIT 根仍没启动
      (收盘涨幅 < LAUNCH_RET) 就按收盘撤出, 把仓位让给真启动的票。
    - 启动后: 止损上移为 peak*(1-TRAIL_PCT), 给加速腿让出波动空间。
    """
    O = [float(r[1]) for r in rows]
    C = [float(r[2]) for r in rows]
    H = [float(r[3]) for r in rows]
    L = [float(r[4]) for r in rows]
    entry = rec["entry"]
    hard_stop = rec["coil_low"] * 0.99
    end = min(len(rows) - 1, i + MAX_HOLD)
    launched = False
    peak = H[i]
    worst = 0.0
    for j in range(i + 1, end + 1):
        # 异常跳空(拆分/脏数据): 后续价格与入场不同量纲, 丢弃该样本。
        if C[j - 1] > 0 and abs(O[j] / C[j - 1] - 1) > GAP_LIMIT:
            return j, 0.0, "split", worst
        stop = max(hard_stop, peak * (1 - TRAIL_PCT)) if launched else hard_stop
        worst = min(worst, L[j] / entry - 1)
        if O[j] <= stop:
            return j, O[j], ("trail_open" if launched else "stop_open"), worst
        if L[j] <= stop:
            return j, stop, ("trail" if launched else "stop"), worst
        if not launched and LAUNCH_WAIT > 0 and (j - i) >= LAUNCH_WAIT:
            return j, C[j], "no_launch", worst
        if not launched and C[j] / entry - 1 >= LAUNCH_RET:
            launched = True
        peak = max(peak, H[j])
    return end, C[end], "timeout", worst


def run_one(code, name, secid):
    rows = cache_data.min_kline(secid, KLT)
    if not rows or len(rows) < 100:
        return []
    drows = cache_data.daily_kline(secid)
    if not drows:
        return []
    trades = []
    i = 80
    n = len(rows)
    while i < n - 1:
        day = rows[i][0][:10]
        dt = daily_trend_asof(drows, day)
        if dt is None:
            i += 1
            continue
        item = s30.check(code, name, rows[: i + 1], dt)
        if not item:
            i += 1
            continue
        entry = float(rows[i][2])
        rec = {"entry": entry, "coil_low": item["coil_low"]}
        j, sell, reason, mae = exit_trade(rows, i, rec)
        if reason == "split":       # 持有期内拆分/脏数据 → 丢弃该样本
            i = j + 1
            continue
        ret = sell / entry - 1 - COST
        trades.append({
            "code": code, "name": name, "time": rows[i][0],
            "entry": entry, "exit": rows[j][0], "held": j - i,
            "reason": reason, "ret": ret, "mae": mae, "score": item["score"],
        })
        i = j + 1  # 平仓后再找下一个信号(自然去重同一段收敛区)
    return trades


def summarize(trades):
    if not trades:
        print("无信号")
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
        print(f"  {r:<12} {len(vs):>4}笔  胜率 {w/len(vs)*100:5.1f}%  均值 {statistics.mean(vs)*100:+6.2f}%")
    print("\n最近15笔:")
    for t in sorted(trades, key=lambda x: x["time"])[-15:]:
        print(f"  {t['time']} {t['code']} {t['name'][:6]:<6} entry={t['entry']:.2f} "
              f"exit={t['exit'][5:]} held={t['held']:>2} {t['reason']:<11} ret={t['ret']*100:+.1f}%")


def main():
    uni = universe()
    pool = "ETF" if ETF_ONLY else "个股"
    strict = "严格" if STRICT else "宽松"
    print(f"{pool}池 {len(uni)} 只, 30分级别 策略六 压缩蓄势({strict}) 回测中 "
          f"(MAX_HOLD={MAX_HOLD}根 LAUNCH_WAIT={LAUNCH_WAIT} TRAIL={TRAIL_PCT})...", flush=True)
    trades, done = [], 0
    with ThreadPoolExecutor(max_workers=12) as ex:
        futs = {ex.submit(run_one, c, n, s): c for c, n, s in uni}
        for fut in as_completed(futs):
            done += 1
            try:
                trades.extend(fut.result())
            except Exception:
                pass
            if done % 500 == 0:
                print(f"  {done}/{len(uni)} 累计信号 {len(trades)}", flush=True)
    summarize(trades)


if __name__ == "__main__":
    main()
