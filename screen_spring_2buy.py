#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
策略七 · 威科夫 Spring + 缠论第二类买点(底背驰确认)。

思路(承接讨论):策略5买3买(突破回踩, 最靠后/空间最小), 策略6埋伏突破前的蓄势。
策略七反过来去买两个框架都公认 R:R 最高、但拥挤度最低的点 —— 下跌末端的‘确认过的低点’:

- 威科夫 Spring: 价格假跌破前期区间下沿(甩掉浮筹), 随即收回支撑上方。
- 缠论底背驰: 这个新低相对前低, MACD-DIF 不再创新低(动能背离), 确认下跌衰竭。
- 二买 / Test: Spring 之后回踩不破 Spring 低(更高的低), 缩量、收阳、站回支撑 —— 入场。
- 风控: 止损贴 Spring 低点下方(极紧); 启动后移动止损让利润奔跑。

与 5/6 的关键区别: 不要求趋势向上 —— 它专门在‘底部/转折’这个不同的 regime 工作。
日线级别近似, Spring 的‘缩量’与背驰在分钟级更干净, 仅供候选。
"""
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

import cache_data
import screen_chan_wyckoff_3buy as chan

TODAY = os.environ.get("SCREEN_DATE", date.today().isoformat())
MIN_AMOUNT = float(os.environ.get("MIN_AMOUNT", "50000000"))
INCLUDE_ETF = os.environ.get("INCLUDE_ETF", "0") != "0"
# 周线过滤: off / loose / strict。
# loose = 周MA10仍上行 + 近期没创周线新低(大级别趋势在, Spring 只是级别内洗盘);
# strict = 复用策略5/6 的 weekly_up_state.up(过严, 和 Spring 冲突, 仅供对比)。
WEEKLY_FILTER = os.environ.get("WEEKLY_FILTER", "loose")


def weekly_ok(D, O, H, L, C, V, A):
    if WEEKLY_FILTER == "off":
        return True
    if WEEKLY_FILTER == "strict":
        wk = chan.weekly_up_state(D, O, H, L, C, V, A)
        return bool(wk and wk["up"])
    # loose
    W = chan.weekly_bars(D, O, H, L, C, V, A)
    if len(W) < 12:
        return False
    WC = [w["close"] for w in W]
    WL = [w["low"] for w in W]
    i = len(W) - 1
    ma10 = avg(WC[i - 9 : i + 1])
    ma10p = avg(WC[i - 12 : i - 2])
    rising = ma10 > ma10p                                   # 周MA10 上行
    holding = WL[i] >= min(WL[max(0, i - 8) : i]) * 0.95    # 没深破周线近低
    return rising and holding

LOW_BACK = int(os.environ.get("LOW_BACK", "25"))       # 找前低的回看窗口(短支撑=上升趋势内洗盘)
SPRING_WIN = int(os.environ.get("SPRING_WIN", "8"))    # Spring 允许出现在最近几日内
MAX_UP_FROM_SPRING = float(os.environ.get("MAX_UP_FROM_SPRING", "0.15"))  # 入场离 Spring 低不追太高
MIN_DIV_PCT = float(os.environ.get("MIN_DIV_PCT", "0.005"))  # 背驰强度门槛: (DIF_sp-DIF_low1)/价 ≥此值(关键)


def avg(xs):
    return chan.avg(xs)


def macd_dif(C):
    """MACD DIF 序列(EMA12-EMA26), 用于背驰比较。"""
    def ema(xs, p):
        k = 2.0 / (p + 1)
        e = xs[0]
        out = []
        for x in xs:
            e = x * k + e * (1 - k)
            out.append(e)
        return out

    e12, e26 = ema(C, 12), ema(C, 26)
    return [a - b for a, b in zip(e12, e26)]


def spring_signal(O, H, L, C, V, dif, i):
    """第 i 根是否为 Spring 后的二买/Test 入场点。命中返回特征 dict, 否则 None。"""
    if i < 70:
        return None
    a, b = i - LOW_BACK, i - 12
    if a < 0:
        return None
    # 1) 前低 low1
    low1 = min(range(a, b + 1), key=lambda k: L[k])
    range_low = L[low1]
    # 2) Spring: 近 SPRING_WIN 日内某根跌破前低后收回(甩浮筹, 不是崩盘)
    sp = None
    for k in range(max(low1 + 3, i - SPRING_WIN), i):
        if L[k] < range_low * 0.995 and C[k] > range_low * 0.99 and L[k] > range_low * 0.85:
            sp = k
    if sp is None:
        return None
    spring_low = L[sp]
    # 3) 底背驰: 价创新低(spring_low<range_low)但 DIF 更高(动能不创新低), 且背驰幅度够大
    if dif[sp] - dif[low1] < MIN_DIV_PCT * C[sp]:
        return None
    # 4) 二买/Test: 更高的低 + 缩量 + 收阳转强 + 站回支撑
    if L[i] < spring_low:
        return None
    if not (C[i] > O[i] and C[i] > C[i - 1]):
        return None
    if V[i] > avg(V[i - 20 : i]) * 0.9:
        return None
    if C[i] < range_low * 0.98:
        return None
    up = C[i] / spring_low - 1
    if up > MAX_UP_FROM_SPRING:
        return None
    # 反转确认(过滤一路阴跌的假 Spring): 站回 MA10 上方 + MA5 拐头向上。
    ma10 = avg(C[i - 9 : i + 1])
    ma5, ma5p = avg(C[i - 4 : i + 1]), avg(C[i - 5 : i])
    if C[i] < ma10 or ma5 <= ma5p:
        return None
    return {
        "low1": low1,
        "range_low": range_low,
        "sp": sp,
        "spring_low": spring_low,
        "up_from_spring": up,
        "div": dif[sp] - dif[low1],
    }


def check(code, name, rows):
    if len(rows) < 90:
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
    if not weekly_ok(D, O, H, L, C, V, A):
        return None
    dif = macd_dif(C)
    sig = spring_signal(O, H, L, C, V, dif, i)
    if not sig:
        return None
    return {
        "code": code,
        "name": name,
        "close": round(C[i], 2),
        "chg": round((C[i] / C[i - 1] - 1) * 100, 2),
        "range_low": round(sig["range_low"], 2),
        "spring_low": round(sig["spring_low"], 2),
        "spring_date": D[sig["sp"]][5:],
        "up_from_spring": round(sig["up_from_spring"] * 100, 1),
        "div_pct": round(sig["div"] / C[i] * 100, 2),  # 背驰强度(DIF差/价), ≥0.5%过门槛
        "stop": round(sig["spring_low"] * 0.99, 2),
        "amt": round(A[i] / 1e8, 1),
    }


def main():
    uni = cache_data.universe()
    if INCLUDE_ETF:
        uni = uni + cache_data.etf_universe()
    print(f"标的池 {len(uni)} 只{' + ETF' if INCLUDE_ETF else ''}，筛 Spring/二买 + 底背驰...", flush=True)
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

    hits.sort(key=lambda x: (x["up_from_spring"], -x["amt"]))
    _dump = os.environ.get("WATCH_JSON_OUT")
    if _dump:
        import json as _json
        _json.dump({
            "strategy": "spring_2buy",
            "variant": "etf" if INCLUDE_ETF else "stock",
            "is_etf": INCLUDE_ETF,
            "date": TODAY,
            "hits": hits,
        }, open(_dump, "w"), ensure_ascii=False)
    print(f"\n>>> 今日({TODAY}) Spring/二买+底背驰 命中 {len(hits)} 只\n")
    print("代码    名称        现价   今日%  区间下沿 Spring低 Spring日 离Spring% 止损   额(亿)")
    for h in hits[:50]:
        print(
            f"{h['code']}  {h['name'][:6]:<7}{h['close']:>7.2f}{h['chg']:>+6.2f} "
            f"{h['range_low']:>7.2f}{h['spring_low']:>8.2f}{h['spring_date']:>7}{h['up_from_spring']:>+8.1f}%"
            f"{h['stop']:>7.2f}{h['amt']:>6.1f}"
        )


if __name__ == "__main__":
    main()
