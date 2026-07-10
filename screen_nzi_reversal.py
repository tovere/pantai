#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""策略八:N字反包 · 主升中继(右侧确认买点)。

强势股急涨后缩量歇脚, 今日放量阳线反包(收复昨日整根阴线)+ 站上MA5, 买 N 字第二腿起点。
与现有策略的区别: 三/四是左侧低吸(赌回调不破), 本策略等‘放量反包’右侧确认才买。

- 多头前提: MA5>=MA10>=MA20 且 MA20 上行; 前期已涨(runup >= MIN_RUNUP, 已在强势中)。
- 缩量回调: 近高点后回调 2~PULL_MAX 天, 幅度 <= MAX_PULL 且不破 MA10; 回调段缩量(洗盘非出货)。
- 反包触发(今日): 阳线 + 收盘 >= 昨日最高 + 站上MA5 + 放量(>=回调均量*VOL_EXPAND) + 涨幅适中。
- 止损: 贴回调低点(pull_low*0.99)。
"""
import os
from datetime import date

import cache_data
import screen_chan_wyckoff_3buy as chan  # 复用 weekly_up_state

TODAY = os.environ.get("SCREEN_DATE", date.today().isoformat())
MIN_AMOUNT = float(os.environ.get("MIN_AMOUNT", "50000000"))
REQUIRE_WEEKLY_UP = os.environ.get("REQUIRE_WEEKLY_UP", "1") != "0"
PULL_MIN = int(os.environ.get("PULL_MIN", "5"))          # 回调最少天数(调优: 5-6天最肥, +1.3~2%)
PULL_MAX = int(os.environ.get("PULL_MAX", "6"))          # 回调最多天数(回测: 7-8天转弱, 5-6天最肥)
MAX_PULL = float(os.environ.get("MAX_PULL", "0.12"))     # 回调幅度上限(不破太深)
VOL_SHRINK = float(os.environ.get("VOL_SHRINK", "0.90")) # 回调段均量 <= 前段均量*此值(缩量洗盘)
VOL_EXPAND = float(os.environ.get("VOL_EXPAND", "1.50")) # 今日量 >= 回调段均量*此值(放量反包)
MIN_RUNUP = float(os.environ.get("MIN_RUNUP", "0.15"))   # 前期涨幅下限(要够强)
MAX_RUNUP = float(os.environ.get("MAX_RUNUP", "0.25"))   # 前期涨幅上限(N字反包越早期越好, 调优=0.25)


def avg(xs):
    return sum(xs) / len(xs) if xs else 0


def nzi_signal(O, H, L, C, V, i):
    """核心信号(可被回测复用)。i=当前日下标, 用 [:i+1] 数据。命中返回 dict, 否则 None。"""
    if i < 70:
        return None
    ma5, ma10, ma20 = avg(C[i - 4 : i + 1]), avg(C[i - 9 : i + 1]), avg(C[i - 19 : i + 1])
    ma20p = avg(C[i - 24 : i - 4])
    if not (ma5 >= ma10 >= ma20 * 0.998 and ma20 > ma20p):  # 多头排列 + MA20上行
        return None

    # 近期波段高点 ph(取 i-2 及之前 12 日内最高), 回调段 = ph 之后到昨天
    ph, hh = None, -1.0
    for k in range(max(1, i - 12), i - 1):
        if H[k] > hh:
            hh, ph = H[k], k
    if ph is None:
        return None
    pull_days = i - ph
    if not (PULL_MIN <= pull_days <= PULL_MAX):
        return None
    peak = H[ph]
    pull_low = min(L[ph + 1 : i])                    # 回调低(不含今日)
    if pull_low >= peak * 0.999:                     # 没真回调
        return None
    if pull_low < peak * (1 - MAX_PULL):             # 回调太深
        return None
    if pull_low < ma10 * 0.97:                       # 破 MA10 太多
        return None

    pv = avg(V[ph + 1 : i])                           # 回调段均量
    base = avg(V[max(0, ph - 4) : ph + 1])           # 上涨段均量
    if not (base > 0 and pv <= base * VOL_SHRINK):   # 回调缩量
        return None

    chg = C[i] / C[i - 1] - 1
    if C[i] <= O[i]:                                  # 今日阳线
        return None
    if C[i] < H[i - 1]:                              # 反包: 收盘吃掉昨日整根
        return None
    if C[i] < ma5 * 0.995:                            # 站上 MA5
        return None
    if V[i] < pv * VOL_EXPAND:                        # 放量反包
        return None
    if not (0.01 <= chg <= 0.095):                    # 涨幅适中(非一字/巨阳追不上)
        return None

    lo0 = min(L[max(0, ph - 40) : ph + 1])
    runup = (peak / lo0 - 1) if lo0 > 0 else 0.0
    if not (MIN_RUNUP <= runup <= MAX_RUNUP):
        return None

    return {
        "entry": C[i], "peak": round(peak, 2), "pull_low": round(pull_low, 2),
        "pull_days": pull_days, "shrink": round(pv / base, 2),
        "vexp": round(V[i] / pv, 2) if pv else 0, "runup": runup, "ma5": round(ma5, 2),
    }


def check(code, name, rows):
    if len(rows) < 80:
        return None
    D = [r[0] for r in rows]
    O = [float(r[1]) for r in rows]
    C = [float(r[2]) for r in rows]
    H = [float(r[3]) for r in rows]
    L = [float(r[4]) for r in rows]
    V = [float(r[5]) for r in rows]
    A = [float(r[6]) for r in rows]
    i = len(rows) - 1
    if D[i] != TODAY or A[i] < MIN_AMOUNT:
        return None
    if REQUIRE_WEEKLY_UP:
        w = chan.weekly_up_state(D, O, H, L, C, V, A)
        if not w or not w["up"]:
            return None
    sig = nzi_signal(O, H, L, C, V, i)
    if not sig:
        return None
    return {
        "code": code, "name": name,
        "close": round(C[i], 2), "chg": round((C[i] / C[i - 1] - 1) * 100, 2),
        "peak": sig["peak"], "pull_low": sig["pull_low"], "pull_days": sig["pull_days"],
        "shrink": sig["shrink"], "vexp": sig["vexp"], "runup": round(sig["runup"] * 100, 1),
        "stop": round(sig["pull_low"] * 0.99, 2), "amt": round(A[i] / 1e8, 1),
    }


def main():
    from concurrent.futures import ThreadPoolExecutor, as_completed

    uni = cache_data.universe()
    wk = " + 周线向上" if REQUIRE_WEEKLY_UP else ""
    print(f"标的池 {len(uni)} 只，筛 N字反包(缩量回调+放量反包中继){wk}...", flush=True)
    hits, done = [], 0
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = {ex.submit(cache_data.daily_kline, sec): (code, name) for code, name, sec in uni}
        for fut in as_completed(futs):
            code, name = futs[fut]
            done += 1
            try:
                rows = fut.result()
                if rows:
                    item = check(code, name, rows)
                    if item:
                        hits.append(item)
            except Exception:
                pass
            if done % 500 == 0:
                print(f"  {done}/{len(uni)} 命中{len(hits)}", flush=True)

    hits.sort(key=lambda x: (x["pull_days"], -x["amt"]))
    _dump = os.environ.get("WATCH_JSON_OUT")
    if _dump:
        import json as _json
        _json.dump({"strategy": "nzi_reversal", "variant": "stock", "is_etf": False,
                    "date": TODAY, "hits": hits}, open(_dump, "w"), ensure_ascii=False)
    print(f"\n>>> 今日({TODAY}) N字反包·主升中继 命中 {len(hits)} 只\n")
    print("代码    名称        现价   今日%  前高   回踩低 回调天 缩量比 放量倍 前涨%  止损   额(亿)")
    for h in hits[:50]:
        print(
            f"{h['code']}  {h['name'][:6]:<7}{h['close']:>7.2f}{h['chg']:>+6.2f} "
            f"{h['peak']:>6.2f}{h['pull_low']:>7.2f}{h['pull_days']:>6}{h['shrink']:>7.2f}"
            f"{h['vexp']:>7.2f}{h['runup']:>+7.1f}{h['stop']:>7.2f}{h['amt']:>6.1f}"
        )


if __name__ == "__main__":
    main()
