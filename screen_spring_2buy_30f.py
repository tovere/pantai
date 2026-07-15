#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""策略七 · 威科夫 Spring + 缠论二买(底背驰) —— 30 分钟级别筛选器。

与日线版(screen_spring_2buy.py)同一套形态/背驰逻辑, 但:
  - 数据走 30 分钟 K 线(cache_data.min_kline klt=30);
  - Spring/二买/底背驰形态仍在 30 分序列上算(macd_dif / spring_signal 直接复用日线脚本);
  - 大级别过滤 = **日线趋势向上 + 日线成交额达标**(替代日线版的"周线 loose"过滤);
  - 只判**倒数第一根已收完的 30 分 bar**(盘中不吃半根 bar 的假信号)。

盘中每 30 分钟(K线收完时)刷新 30 分数据后重跑即可。

⚠️ 30 分数据仅约 40 交易日(320 根), 样本小, 仅供候选。
"""
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import cache_data
import screen_chan_wyckoff_3buy as d   # 复用 avg
import screen_spring_2buy as sp        # 复用 macd_dif / spring_signal / avg

KLT = 30
ETF_ONLY = os.environ.get("ETF_ONLY", "0") != "0"
MIN_AMOUNT = float(os.environ.get("MIN_AMOUNT", "50000000"))  # 日线成交额门槛(流动性)
DAILY_TREND = os.environ.get("DAILY_TREND", "1") != "0"       # 大级别: 日线趋势向上过滤


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
    if len(rows) < 90:
        return None
    if DAILY_TREND and not dtrend["up"]:
        return None
    T = [r[0] for r in rows]
    O = [float(r[1]) for r in rows]
    C = [float(r[2]) for r in rows]
    H = [float(r[3]) for r in rows]
    L = [float(r[4]) for r in rows]
    V = [float(r[5]) for r in rows]
    i = len(rows) - 1

    dif = sp.macd_dif(C)
    sig = sp.spring_signal(O, H, L, C, V, dif, i)
    if not sig:
        return None
    return {
        "code": code,
        "name": name,
        "close": round(C[i], 2),
        "chg": round((C[i] / C[i - 1] - 1) * 100, 2),
        "range_low": round(sig["range_low"], 2),
        "spring_low": round(sig["spring_low"], 2),
        "spring_date": T[sig["sp"]][5:],           # 30分时间戳 MM-DD HH:MM
        "up_from_spring": round(sig["up_from_spring"] * 100, 1),
        "div_pct": round(sig["div"] / C[i] * 100, 2),   # 背驰强度(DIF差/价)
        "stop": round(sig["spring_low"] * 0.99, 2),
        "amt": round(dtrend["damt"] / 1e8, 1),          # 展示日线额(流动性)
        "bar_time": T[i],                               # 命中所依据的已收完30分bar
    }


def _one(code, name, secid):
    rows = cache_data.min_kline(secid, KLT)
    if not rows or len(rows) < 90:
        return None
    dt = daily_trend(secid)
    if dt is None:
        return None
    return check(code, name, rows, dt)


def main():
    uni = universe()
    pool = "ETF" if ETF_ONLY else "个股"
    print(f"{pool}池 {len(uni)} 只，30分级别 Spring/二买+底背驰(+日线趋势)...", flush=True)
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

    hits.sort(key=lambda x: (x["up_from_spring"], -x["amt"]))
    dump = os.environ.get("WATCH_JSON_OUT")
    if dump:
        import json
        json.dump({
            "strategy": "spring_2buy_30f",
            "variant": ("etf" if ETF_ONLY else "stock") + ("_strict" if DAILY_TREND else "_loose"),
            "is_etf": ETF_ONLY,
            "date": hits[0]["bar_time"] if hits else "",
            "hits": hits,
        }, open(dump, "w"), ensure_ascii=False)
    print(f"\n>>> 30分级别 Spring/二买+底背驰 命中 {len(hits)} 只\n")
    print("代码    名称        现价   本根%  区间下沿 Spring低 Spring(30f)   离Spring% 背驰% 止损   日额(亿)")
    for h in hits[:50]:
        print(
            f"{h['code']}  {h['name'][:6]:<7}{h['close']:>7.2f}{h['chg']:>+6.2f} "
            f"{h['range_low']:>7.2f}{h['spring_low']:>8.2f}{h['spring_date']:>13}{h['up_from_spring']:>+8.1f}%"
            f"{h['div_pct']:>+6.2f}{h['stop']:>7.2f}{h['amt']:>6.1f}"
        )


if __name__ == "__main__":
    main()
