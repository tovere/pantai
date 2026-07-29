#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
策略六验证 · C 段加速前临界点是否真能吃到加速腿。

做两件事:
1) 客观定义‘加速腿’: 进场后 FAST_DAYS 日内, 收盘相对进场涨幅 >= ACCEL_RET(默认 6 日内 +12%)。
2) 对历史上的‘压缩临界点’信号, 统计:
   - 命中加速腿的比例(accel hit-rate) —— 这是这个思路成不成立的核心指标;
   - 若按‘未启动时间止损 + 启动后移动止损’交易, 胜率/均值/中位/MAE/持有;
   - 交叉验证: 按压缩分档、按乖离(距MA60)与前期涨幅(runup)档分组,
     看是不是‘压缩越极致 + 位置越靠前(乖离/runup 小)’命中加速的概率越高、收益越好。

结论用途: 若验证成立, 再把 screen_squeeze_launch.py 作为策略5的‘埋伏版’并列上线。
"""
import os
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed

import cache_data
import screen_chan_wyckoff_3buy as chan
import screen_squeeze_launch as sq

START = os.environ.get("START", "2025-07-01")
END = os.environ.get("END", "2026-06-26")
COST = 0.001
MAX_HOLD = int(os.environ.get("MAX_HOLD", "30"))
FAST_DAYS = int(os.environ.get("FAST_DAYS", "6"))       # 加速腿的时间窗(仅用于统计命中率)
ACCEL_RET = float(os.environ.get("ACCEL_RET", "0.12"))  # 加速腿的涨幅门槛(仅用于统计命中率)
REQUIRE_WEEKLY_UP = os.environ.get("REQUIRE_WEEKLY_UP", "1") != "0"
# 策略6专属出场(区别于策略5的顶分型卖):
LAUNCH_RET = float(os.environ.get("LAUNCH_RET", "0.05"))   # 收盘涨幅达到即判定‘已启动’
LAUNCH_WAIT = int(os.environ.get("LAUNCH_WAIT", "5"))      # 未启动时间止损: N 日内没启动就撤
TRAIL_PCT = float(os.environ.get("TRAIL_PCT", "0.08"))     # 启动后移动止损: 从峰值回撤该比例离场
# 异常跳空过滤: 单日跳空超过此比例视为拆分/脏数据(ETF 份额拆分常见), 丢弃该样本。
GAP_LIMIT = float(os.environ.get("GAP_LIMIT", "0.20"))


def _has_gap(O, C, a, b):
    """[a,b] 内是否出现异常跳空(相邻收→开跳幅超过 GAP_LIMIT)。"""
    for j in range(max(1, a), b + 1):
        if C[j - 1] > 0 and abs(O[j] / C[j - 1] - 1) > GAP_LIMIT:
            return True
    return False


def signal_at(code, name, rows, i):
    if i < 85 or i >= len(rows):
        return None
    D = [r[0] for r in rows[: i + 1]]
    O = [float(r[1]) for r in rows[: i + 1]]
    C = [float(r[2]) for r in rows[: i + 1]]
    H = [float(r[3]) for r in rows[: i + 1]]
    L = [float(r[4]) for r in rows[: i + 1]]
    V = [float(r[5]) for r in rows[: i + 1]]
    A = [float(r[6]) for r in rows[: i + 1]]
    if not (START <= D[-1] <= END) or A[-1] < sq.MIN_AMOUNT:
        return None
    if REQUIRE_WEEKLY_UP:
        weekly = chan.weekly_up_state(D, O, H, L, C, V, A)
        if not weekly or not weekly["up"]:
            return None
    cs = sq.coil_state(O, H, L, C, V, i)
    if not cs:
        return None
    # 只在‘临界点首日’记一次信号, 避免同一段收敛区连续多日重复计入。
    prev = sq.coil_state(O[:-1], H[:-1], L[:-1], C[:-1], V[:-1], i - 1)
    if prev:
        return None
    return {
        "date": D[i],
        "code": code,
        "name": name,
        "entry": C[i],
        "coil_low": cs["coil_low"],
        "score": cs["score"],
        "bias60": cs["bias60"],
        "runup": cs["runup"],
    }


def exit_trade(rows, i, rec):
    """策略6出场: 收敛下沿硬止损 → 未启动时间止损 → 启动后从峰值回撤的移动止损。

    - 启动前: 止损固定在收敛区下沿(coil_low*0.99)。埋伏 LAUNCH_WAIT 日仍没启动(收盘涨幅
      < LAUNCH_RET) 就按收盘撤出, 把仓位让给真启动的票。
    - 启动后: 止损上移为 peak*(1-TRAIL_PCT), 给加速腿让出波动空间, 不再用顶分型一碰就走。
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
        # 当日止损位: 已启动用移动止损(基于截至前一日的峰值), 否则用硬止损。
        stop = max(hard_stop, peak * (1 - TRAIL_PCT)) if launched else hard_stop
        worst = min(worst, L[j] / entry - 1)
        if O[j] <= stop:
            return j, O[j], ("trail_open" if launched else "stop_open"), worst
        if L[j] <= stop:
            return j, stop, ("trail" if launched else "stop"), worst
        if not launched and (j - i) >= LAUNCH_WAIT:
            return j, C[j], "no_launch", worst
        # 收盘后更新状态。
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
    for i in range(85, len(rows) - 3):
        rec = signal_at(code, name, rows, i)
        if not rec:
            continue
        # 入场前 70 日窗口有异常跳空(拆分)→ 均线/前涨被污染, 丢弃。
        if _has_gap(O, C, i - 70, i):
            continue
        j, sell, reason, mae = exit_trade(rows, i, rec)
        if reason == "split":   # 持有期内拆分 → 丢弃该样本
            continue
        # 加速腿: 进场后 FAST_DAYS 日内最大收盘涨幅(遇拆分前截断)。
        fwd_end = min(len(rows) - 1, i + FAST_DAYS)
        k_end = i
        for k in range(i + 1, fwd_end + 1):
            if C[k - 1] > 0 and abs(O[k] / C[k - 1] - 1) > GAP_LIMIT:
                break
            k_end = k
        fwd_max = max((C[k] / rec["entry"] - 1 for k in range(i + 1, k_end + 1)), default=0.0)
        rec["accel"] = 1 if fwd_max >= ACCEL_RET else 0
        rec["fwd_max"] = fwd_max
        rec["exit"] = rows[j][0]
        rec["reason"] = reason
        rec["held"] = j - i
        rec["ret"] = sell / rec["entry"] - 1 - COST
        rec["mae"] = mae
        out.append(rec)
    return out


def _bucket_bias(x):
    if x < 0.10:
        return "乖离<10%"
    if x < 0.20:
        return "乖离10-20%"
    return "乖离>=20%"


def _bucket_runup(x):
    if x < 0.25:
        return "前涨<25%"
    if x < 0.50:
        return "前涨25-50%"
    return "前涨>=50%"


def _line(name, ts):
    rs = [t["ret"] for t in ts]
    acc = sum(t["accel"] for t in ts) / len(ts) * 100
    maes = [t["mae"] for t in ts]
    return (
        f"  {name:<12} {len(ts):>4}笔  加速命中 {acc:5.1f}%  "
        f"胜率 {sum(1 for v in rs if v > 0) / len(rs) * 100:5.1f}%  "
        f"均值 {statistics.mean(rs) * 100:+6.2f}%  中位 {statistics.median(rs) * 100:+6.2f}%  "
        f"MAE {statistics.mean(maes) * 100:+6.2f}%"
    )


def summarize(trades):
    print(
        f"\n>> 策略六验证 {START}~{END}  信号 {len(trades)} 笔"
        f"  (加速腿定义: {FAST_DAYS}日内收盘 +{ACCEL_RET*100:.0f}%)\n"
    )
    if not trades:
        return
    rs = [t["ret"] for t in trades]
    acc = sum(t["accel"] for t in trades) / len(trades) * 100
    maes = [t["mae"] for t in trades]
    print(
        f"整体  加速命中 {acc:5.1f}%  胜率 {sum(1 for v in rs if v > 0)/len(rs)*100:5.1f}%  "
        f"均值 {statistics.mean(rs)*100:+6.2f}%  中位 {statistics.median(rs)*100:+6.2f}%"
    )
    print(
        f"      平均持有 {statistics.mean(t['held'] for t in trades):.1f}天  "
        f"平均MAE {statistics.mean(maes)*100:+6.2f}%  最好/最差 {max(rs)*100:+.1f}%/{min(rs)*100:+.1f}%"
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
        keys = order or sorted(g.keys())
        for k in keys:
            if k in g:
                print(_line(str(k), g[k]))

    group(lambda t: f"压缩分{t['score']}", "压缩分档(验证越极致越好)", ["压缩分4", "压缩分5"])
    group(lambda t: _bucket_bias(t["bias60"]), "乖离档(验证越靠前越好)", ["乖离<10%", "乖离10-20%", "乖离>=20%"])
    group(lambda t: _bucket_runup(t["runup"]), "前期涨幅档(验证越靠前越好)", ["前涨<25%", "前涨25-50%", "前涨>=50%"])

    sample = sorted(trades, key=lambda x: x["date"])[-20:]
    print("\n最近20笔信号:")
    for t in sample:
        print(
            f"{t['date']} {t['code']} {t['name'][:6]:<6} entry={t['entry']:.2f} "
            f"score={t['score']} accel={t['accel']} exit={t['exit']} held={t['held']:>2} "
            f"{t['reason']:<11} ret={t['ret']*100:+.1f}%"
        )


def main():
    U = cache_data.universe()
    if sq.INCLUDE_ETF:
        U = U + cache_data.etf_universe()
    print(f"标的池 {len(U)} 只{' + ETF' if sq.INCLUDE_ETF else ''}，策略六(C段加速前临界点)验证中...", flush=True)
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
