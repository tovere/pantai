#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""中证2000连小阳回测：信号确认后次日开盘买，放量日收盘跑。

入场: 与 screen_csi2000_small_yang 同形态（边缘触发，避免连阳期间重复进场）
离场: 持仓日成交量 ≥ VOL_MULT × 信号窗口均量 → 当日收盘卖
备用: 超时 MAX_HOLD / 跌破信号窗口低点止损
"""
import os
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed

import cache_data
import screen_csi2000_small_yang as sy

START = os.environ.get("START", "2025-01-01")
END = os.environ.get("END", "2026-08-12")
COST = float(os.environ.get("COST", "0.001"))
MAX_HOLD = int(os.environ.get("MAX_HOLD", "15"))
VOL_MULT = float(os.environ.get("VOL_MULT", "2.0"))  # 相对信号窗均量
VOL_LOOKBACK = int(os.environ.get("VOL_LOOKBACK", "0"))  # 0=用信号窗; >0=另用近N日均量
STOP_BELOW = float(os.environ.get("STOP_BELOW", "0.97"))  # 破信号窗最低×该系数止损
COOLDOWN = int(os.environ.get("COOLDOWN", "5"))  # 同票出场后再冷却几天


def signal_at(rows, i):
    """在日线索引 i 判定是否形成连小阳；返回 dict 或 None。"""
    w = sy.WINDOW
    if i < w or i >= len(rows):
        return None
    d = rows[i][0]
    if not (START <= d <= END):
        return None

    win = rows[i - w + 1 : i + 1]
    prev_closes = [float(rows[i - w + k][2]) for k in range(w)]

    yang_flags, small_flags, bodies, chgs, vols = [], [], [], [], []
    for k, r in enumerate(win):
        o, c = float(r[1]), float(r[2])
        pc = prev_closes[k]
        body = (c - o) / o * 100.0 if o else 0.0
        chg = (c / pc - 1.0) * 100.0 if pc else 0.0
        bodies.append(body)
        chgs.append(chg)
        vols.append(float(r[5]))
        is_yang = c > o
        yang_flags.append(is_yang)
        small_flags.append(is_yang and 0 < body <= sy.MAX_BODY and chg <= sy.MAX_CHG)

    yang_n = sum(yang_flags)
    small_n = sum(small_flags)
    streak = 0
    for y in reversed(yang_flags):
        if y:
            streak += 1
        else:
            break

    c0 = prev_closes[0]
    c1 = float(win[-1][2])
    net = (c1 / c0 - 1.0) * 100.0 if c0 else 0.0
    max_chg = max(chgs) if chgs else 0.0
    avg_chg = sum(chgs) / len(chgs)
    avg_body = sum(bodies) / len(bodies)
    win_low = min(float(r[4]) for r in win)
    vol_base = sum(vols) / len(vols) if vols else 0.0

    if streak < sy.MIN_STREAK:
        return None
    if yang_n < sy.MIN_YANG:
        return None
    if small_n < max(sy.MIN_YANG - 1, sy.MIN_STREAK - 1):
        return None
    if not (sy.MIN_NET <= net <= sy.MAX_NET):
        return None
    if max_chg > sy.MAX_CHG + 1.5:
        return None
    if avg_chg > 2.8 or avg_body > 2.5:
        return None
    if vol_base <= 0:
        return None

    return {
        "date": d,
        "close": c1,
        "streak": streak,
        "yang_n": yang_n,
        "small_n": small_n,
        "net": round(net, 2),
        "avg_chg": round(avg_chg, 2),
        "vol_base": vol_base,
        "win_low": win_low,
    }


def is_new_signal(rows, i):
    """边缘触发：今日达标、昨日不达标。"""
    cur = signal_at(rows, i)
    if not cur:
        return None
    if signal_at(rows, i - 1):
        return None
    return cur


def exit_trade(rows, buy_i, sig):
    """buy_i = 买入日索引(开盘买)。返回 (sell_i, sell_px, reason)。"""
    C = [float(r[2]) for r in rows]
    L = [float(r[4]) for r in rows]
    V = [float(r[5]) for r in rows]
    O = [float(r[1]) for r in rows]

    if VOL_LOOKBACK > 0:
        a = max(0, buy_i - VOL_LOOKBACK)
        base = sum(V[a:buy_i]) / max(1, buy_i - a)
    else:
        base = sig["vol_base"]
    stop = sig["win_low"] * STOP_BELOW
    end = min(len(rows) - 1, buy_i + MAX_HOLD)

    for j in range(buy_i, end + 1):
        # 开盘已破止损
        if O[j] <= stop:
            return j, O[j], "stop_open"
        if L[j] <= stop:
            return j, stop, "stop"
        # 放量离场：买入当日也检查（若信号后次日就放量）
        if V[j] >= VOL_MULT * base:
            return j, C[j], "vol_spike"
    return end, C[end], "timeout"


def run_one(code, name, secid):
    rows = cache_data.daily_kline(secid)
    if not rows or len(rows) < sy.WINDOW + 20:
        return []
    out = []
    next_ok = sy.WINDOW
    i = sy.WINDOW
    while i < len(rows) - 2:
        if i < next_ok:
            i += 1
            continue
        sig = is_new_signal(rows, i)
        if not sig:
            i += 1
            continue
        buy_i = i + 1
        if buy_i >= len(rows):
            break
        entry = float(rows[buy_i][1])  # 次日开盘
        if entry <= 0:
            i += 1
            continue
        sell_i, sell_px, reason = exit_trade(rows, buy_i, sig)
        ret = sell_px / entry - 1.0 - COST
        out.append({
            "code": code,
            "name": name,
            "signal": sig["date"],
            "entry_date": rows[buy_i][0],
            "exit_date": rows[sell_i][0],
            "entry": round(entry, 3),
            "exit": round(sell_px, 3),
            "ret": ret,
            "held": sell_i - buy_i + 1,
            "reason": reason,
            "streak": sig["streak"],
            "net": sig["net"],
            "small_n": sig["small_n"],
        })
        next_ok = sell_i + 1 + COOLDOWN
        i = buy_i + 1
    return out


def _bucket(trades, keyfn, title):
    from collections import defaultdict
    g = defaultdict(list)
    for t in trades:
        g[keyfn(t)].append(t["ret"])
    print(f"\n[{title}]")
    for k in sorted(g.keys()):
        rs = g[k]
        wr = sum(1 for r in rs if r > 0) / len(rs) * 100
        print(
            f"  {k:<14} {len(rs):>5}笔  胜率{wr:5.1f}%  "
            f"均{statistics.mean(rs)*100:+6.2f}%  中位{statistics.median(rs)*100:+6.2f}%"
        )


def summarize(trades):
    print(
        f"\n>> 连小阳·放量跑  {START}~{END}  "
        f"VOL≥{VOL_MULT}x窗均量  MAX_HOLD={MAX_HOLD}  信号{len(trades)}笔\n"
    )
    if not trades:
        return
    rs = [t["ret"] for t in trades]
    wins = [r for r in rs if r > 0]
    loss = [r for r in rs if r <= 0]
    print(
        f"整体  {len(trades)}笔  胜率{len(wins)/len(trades)*100:.1f}%  "
        f"均{statistics.mean(rs)*100:+.2f}%  中位{statistics.median(rs)*100:+.2f}%  "
        f"均持仓{statistics.mean(t['held'] for t in trades):.1f}日"
    )
    if wins and loss:
        print(
            f"      盈均{statistics.mean(wins)*100:+.2f}%  "
            f"亏均{statistics.mean(loss)*100:+.2f}%  "
            f"盈亏比{abs(statistics.mean(wins)/statistics.mean(loss)):.2f}"
        )

    from collections import Counter
    rc = Counter(t["reason"] for t in trades)
    print("\n[离场原因]")
    for k, n in rc.most_common():
        sub = [t["ret"] for t in trades if t["reason"] == k]
        wr = sum(1 for r in sub if r > 0) / len(sub) * 100
        print(
            f"  {k:<12} {n:>5}笔  胜率{wr:5.1f}%  均{statistics.mean(sub)*100:+6.2f}%"
        )

    _bucket(trades, lambda t: f"连阳{t['streak']}", "按连阳天数")
    _bucket(
        trades,
        lambda t: ("8连纯小阳" if t["streak"] >= 8 and t["small_n"] >= 8
                   else "8连" if t["streak"] >= 8
                   else "6-7连" if t["streak"] >= 6
                   else "5连"),
        "按形态纯度",
    )

    # 放量离场子样本是核心口径
    vol_ts = [t for t in trades if t["reason"] == "vol_spike"]
    if vol_ts:
        vrs = [t["ret"] for t in vol_ts]
        print(
            f"\n★ 仅放量离场: {len(vol_ts)}笔  "
            f"胜率{sum(1 for r in vrs if r>0)/len(vrs)*100:.1f}%  "
            f"均{statistics.mean(vrs)*100:+.2f}%  "
            f"中位{statistics.median(vrs)*100:+.2f}%  "
            f"均持仓{statistics.mean(t['held'] for t in vol_ts):.1f}日"
        )

    # 最近若干笔样例
    print("\n最近20笔:")
    print("代码    名称     信号日       买入       卖出     持仓  收益%  原因")
    for t in sorted(trades, key=lambda x: x["signal"])[-20:]:
        print(
            f"{t['code']}  {t['name'][:6]:<6} {t['signal']}  "
            f"{t['entry_date']}→{t['exit_date']}  "
            f"{t['held']:>2}  {t['ret']*100:+6.2f}  {t['reason']}"
        )


def main():
    uni = sy.load_csi2000_mainboard()
    print(f"回测池 {len(uni)} 只主板(全A剔创业科创) CACHE_ONLY...", flush=True)
    os.environ.setdefault("CACHE_ONLY", "1")
    trades, done = [], 0
    with ThreadPoolExecutor(max_workers=12) as ex:
        futs = {
            ex.submit(run_one, code, name, sec): (code, name)
            for code, name, sec in uni
        }
        for fut in as_completed(futs):
            done += 1
            try:
                trades.extend(fut.result() or [])
            except Exception:
                pass
            if done % 300 == 0:
                print(f"  {done}/{len(uni)} 累计{len(trades)}笔", flush=True)
    summarize(trades)


if __name__ == "__main__":
    main()
