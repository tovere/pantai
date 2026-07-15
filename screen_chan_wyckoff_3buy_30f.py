#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""缠论 + 威科夫三买 —— 30 分钟级别筛选器。

与日线版(screen_chan_wyckoff_3buy.py)同一套形态逻辑, 但:
  - 数据走 30 分钟 K 线(cache_data.min_kline klt=30);
  - 信号本级别趋势 = 30分 MA60 向上;
  - 大级别过滤 = **日线趋势向上 + 日线成交额达标**(替代日线版的"周线向上");
  - 只判**倒数第一根已收完的 30 分 bar**(盘中不吃半根 bar 的假信号);
  - 复用日线脚本的 find_box_before_pullback / box_stage / avg, 不重复形态代码。

盘中每 30 分钟(K线收完时)刷新 30 分数据后重跑即可。
"""
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import cache_data
import screen_chan_wyckoff_3buy as d  # 复用: avg / find_box_before_pullback / box_stage

KLT = 30
STRICT_BUY = os.environ.get("STRICT_BUY", "1") != "0"
ETF_ONLY = os.environ.get("ETF_ONLY", "0") != "0"
MIN_AMOUNT = float(os.environ.get("MIN_AMOUNT", "50000000"))  # 日线成交额门槛(流动性)
DAILY_TREND = os.environ.get("DAILY_TREND", "1") != "0"       # 大级别: 日线趋势向上过滤
# 入场前移: >0 时只在收盘价距中枢上沿不超过该比例(贴边)时进场, 并跳过"反弹站回"确认。
# 目的: 入场贴近平台上沿 -> 止损(上沿×0.985)距离更紧。0=原行为(等反弹站回)。
ENTRY_MAX_EXT = float(os.environ.get("ENTRY_MAX_EXT", "0"))


def universe():
    return cache_data.etf_universe() if ETF_ONLY else cache_data.universe()


def daily_trend(secid):
    """大级别过滤: 日线趋势向上 + 日线流动性达标。返回 dict 或 None(不合格)。"""
    drows = cache_data.daily_kline(secid)
    if not drows or len(drows) < 60:
        return None
    C = [float(r[2]) for r in drows]
    A = [float(r[6]) for r in drows]
    i = len(C) - 1
    if A[i] < MIN_AMOUNT:                       # 用日线额做流动性门槛
        return None
    ma = lambda p, k: d.avg(C[k - p + 1 : k + 1])
    up = (C[i] >= ma(20, i) and ma(20, i) > ma(20, i - 5)
          and ma(20, i) >= ma(60, i))
    return {"up": up, "damt": A[i], "dclose": C[i]}


def check(code, name, rows, dtrend):
    """rows: 30分K线 list[list[str]]; dtrend: daily_trend() 结果。"""
    if len(rows) < 80:
        return None
    if DAILY_TREND and not dtrend["up"]:
        return None
    O = [float(r[1]) for r in rows]
    C = [float(r[2]) for r in rows]
    H = [float(r[3]) for r in rows]
    L = [float(r[4]) for r in rows]
    V = [float(r[5]) for r in rows]
    T = [r[0] for r in rows]
    i = len(rows) - 1

    ma = lambda p, k: d.avg(C[k - p + 1 : k + 1])
    if C[i] < ma(60, i) or ma(60, i) <= ma(60, i - 10):   # 30分本级趋势向上
        return None
    if C[i] / C[i - 1] - 1 < -0.055:
        return None

    # 最近 1-8 根是三买/LPS 回踩bar, SOS 在其前。
    for sos in range(max(65, i - 12), i):
        box = d.find_box_before_pullback(H, L, C, V, sos - 1)
        if not box:
            continue
        stage = d.box_stage(L, box)
        if stage["runup"] > d.MAX_RUNUP:
            continue
        if STRICT_BUY and stage["stage"] != 1:
            continue
        upper, mid = box["hi"], box["mid"]
        vbase = d.avg(V[max(0, sos - 20) : sos])
        sos_break = C[sos] > upper * 1.015 and H[sos] > upper * 1.025
        sos_volume = V[sos] >= vbase * 1.25
        if not (sos_break and sos_volume):
            continue
        if min(C[sos + 1 : i + 1] or [C[i]]) < mid:
            continue
        pull_bars = i - sos
        if not (1 <= pull_bars <= 8):
            continue
        pull_low = min(L[sos + 1 : i + 1])
        pull_low_idx = min(range(sos + 1, i + 1), key=lambda x: L[x])
        pull_touch = upper * 0.985 <= pull_low <= upper * 1.08
        if ENTRY_MAX_EXT > 0:
            # 前移: 只在收盘贴近上沿(未大幅反弹)时进 -> 止损(上沿×0.985)更紧
            support = (upper * 0.99 <= C[i] <= upper * (1 + ENTRY_MAX_EXT)) and L[i] >= mid
        else:
            support = C[i] >= upper * 0.995 and L[i] >= mid
        shrink = d.avg(V[sos + 1 : i + 1]) <= V[sos] * 0.78
        close_pos = (C[i] - L[i]) / (H[i] - L[i]) if H[i] > L[i] else 1
        if not (pull_touch and support and shrink and close_pos >= 0.45):
            continue
        if C[i] / C[i - 3] - 1 >= 0.20:
            continue
        if STRICT_BUY:
            if pull_bars < 2:
                continue
            if not (upper * 0.99 <= pull_low <= upper * 1.04):
                continue
            if pull_low_idx <= sos or pull_low_idx >= i:
                continue
            if min(C[sos + 1 : i + 1]) < upper * 0.985:
                continue
            if max(H[sos + 1 : i + 1]) > H[sos] * 1.03:
                continue
            if ENTRY_MAX_EXT <= 0:  # 前移模式跳过"反弹站回"确认(它会强制入场扩展)
                rebound = C[i] > C[i - 1] and C[i] > O[i] and C[i] >= H[i - 1] * 0.995
                reclaimed = C[i] >= upper * 1.01 and close_pos >= 0.6
                if not (rebound and reclaimed):
                    continue

        amt = float(rows[i][6])
        return {
            "code": code,
            "name": name,
            "close": round(C[i], 2),
            "chg": round((C[i] / C[i - 1] - 1) * 100, 2),
            "box": f"{box['lo']:.2f}-{box['hi']:.2f}",
            "upper": round(upper, 2),
            "dist": round((C[i] / upper - 1) * 100, 1),
            "sos_date": T[sos][5:],          # 30分时间戳 MM-DD HH:MM
            "pull_days": pull_bars,          # 回踩 bar 数(30分)
            "vol_shrink": round(d.avg(V[sos + 1 : i + 1]) / V[sos], 2),
            "wbias10": round((C[i] / ma(20, i) - 1) * 100, 1),  # 30分MA20乖离(替周MA10位)
            "buy_low": round(pull_low, 2),
            "amt": round(dtrend["damt"] / 1e8, 1),   # 展示日线额(流动性)
            "runup": round(stage["runup"] * 100, 1),
            "stage": stage["stage"],
            "bar_time": T[i],                # 命中所依据的已收完30分bar
        }
    return None


def _one(code, name, secid):
    rows = cache_data.min_kline(secid, KLT)
    if not rows or len(rows) < 80:
        return None
    dt = daily_trend(secid)
    if dt is None:
        return None
    return check(code, name, rows, dt)


def main():
    uni = universe()
    pool = "ETF" if ETF_ONLY else "个股"
    strict = "严格入场" if STRICT_BUY else "宽松候选"
    print(f"{pool}池 {len(uni)} 只，30分级别 缠论+威科夫三买(+日线趋势) {strict}...", flush=True)
    hits, done = [], 0
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = {ex.submit(_one, code, name, sec): code for code, name, sec in uni}
        for fut in as_completed(futs):
            done += 1
            try:
                item = fut.result()
                if item:
                    hits.append(item)
            except Exception:
                pass
            if done % 500 == 0:
                print(f"  {done}/{len(uni)} 命中{len(hits)}", flush=True)

    hits.sort(key=lambda x: (x["stage"], x["dist"], -x["amt"]))
    dump = os.environ.get("WATCH_JSON_OUT")
    if dump:
        import json
        json.dump({
            "strategy": "chan_wyckoff_3buy_30f",
            "variant": ("etf" if ETF_ONLY else "stock") + ("_strict" if STRICT_BUY else "_loose"),
            "strict": STRICT_BUY,
            "is_etf": ETF_ONLY,
            "date": hits[0]["bar_time"] if hits else "",
            "hits": hits,
        }, open(dump, "w"), ensure_ascii=False)
    print(f"\n>>> 30分级别 三买/{strict} 命中 {len(hits)} 只\n")
    print("代码    名称       现价   本根%  中枢/TR       距上沿  MA20乖离 三买低  SOS(30f)      回踩根 缩量比 日额(亿) 前涨% 中枢#")
    for h in hits[:50]:
        print(
            f"{h['code']}  {h['name'][:6]:<7}{h['close']:>7.2f}{h['chg']:>+6.2f} "
            f"{h['box']:<13}{h['dist']:>+5.1f}%{h['wbias10']:>+6.1f}%{h['buy_low']:>7.2f} "
            f"{h['sos_date']:>12} {h['pull_days']:>4} {h['vol_shrink']:>6.2f} {h['amt']:>6.1f} "
            f"{h['runup']:>+5.1f} {h['stage']:>4}"
        )


if __name__ == "__main__":
    main()
