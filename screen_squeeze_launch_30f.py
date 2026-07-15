#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""策略六 · C段加速前临界点(压缩蓄势 squeeze_launch) —— 30 分钟级别筛选器。

与日线版(screen_squeeze_launch.py)同一套‘压缩蓄势’形态逻辑, 但:
  - 数据走 30 分钟 K 线(cache_data.min_kline klt=30);
  - 压缩/蓄势/粘合/缩量/贴前高全部在 30 分序列上算(直接复用 sq.coil_state, 不重写形态);
  - 大级别过滤 = **日线趋势向上 + 日线成交额达标**(替代日线版的"周线向上"),
    抄 30f 模板(screen_chan_wyckoff_3buy_30f)的 daily_trend();
  - 只判**倒数第一根已收完的 30 分 bar**(rows[-1], 盘中不吃半根 bar 的假信号)。

盘中每 30 分钟(K线收完时)刷新 30 分数据后重跑即可。

⚠️ 30 分数据仅约 40 交易日(~320 根), 样本天然小, 命中数偏少属正常。
"""
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import cache_data
import screen_chan_wyckoff_3buy as d      # 复用 avg
import screen_squeeze_launch as sq        # 复用 coil_state / 全部压缩蓄势形态逻辑

KLT = 30
STRICT_BUY = os.environ.get("STRICT_BUY", "1") != "0"
ETF_ONLY = os.environ.get("ETF_ONLY", "0") != "0"
MIN_AMOUNT = float(os.environ.get("MIN_AMOUNT", "50000000"))  # 日线成交额门槛(流动性)
DAILY_TREND = os.environ.get("DAILY_TREND", "1") != "0"       # 大级别: 日线趋势向上过滤


def universe():
    return cache_data.etf_universe() if ETF_ONLY else cache_data.universe()


def daily_trend(secid):
    """大级别过滤: 日线趋势向上 + 日线流动性达标。返回 dict 或 None(不合格)。

    与 30f 模板 screen_chan_wyckoff_3buy_30f.daily_trend 完全一致:
    日线 close>=MA20 且 MA20 上行 且 MA20>=MA60; 日线额 >= MIN_AMOUNT。
    """
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
    """rows: 30分K线 list[list[str]]; dtrend: daily_trend() 结果。判 rows[-1] 是否压缩临界点。"""
    if len(rows) < 90:
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

    cs = sq.coil_state(O, H, L, C, V, i)   # 复用日线脚本的压缩蓄势判定(不重写形态)
    if not cs:
        return None

    close_pos = (C[i] - L[i]) / (H[i] - L[i]) if H[i] > L[i] else 1.0
    denom = 5 if sq.REQUIRE_CONTRACT else 4
    if STRICT_BUY:
        # 严格: 要求真实振幅收窄(contract) + 贴前高蓄势(near_high) + 收在偏上(强临界点),
        # 只用 coil_state 已算好的特征位, 不重写形态。
        if not (cs["contract"] and cs["near_high"] and close_pos >= 0.5):
            return None

    return {
        "code": code,
        "name": name,
        "close": round(C[i], 2),
        "chg": round((C[i] / C[i - 1] - 1) * 100, 2),
        "score": cs["score"],
        "denom": denom,
        "band": round(cs["band"] * 100, 1),
        "dist_high": round(cs["dist_high"] * 100, 1),
        "bias60": round(cs["bias60"] * 100, 1),
        "runup": round(cs["runup"] * 100, 1),
        "vol_ratio": round(cs["vol_ratio"], 2),
        "coil": f"{cs['coil_low']:.2f}-{cs['coil_high']:.2f}",
        "coil_low": round(cs["coil_low"], 2),      # 供回测出场用(硬止损基准)
        "stop": round(cs["coil_low"] * 0.99, 2),
        "amt": round(dtrend["damt"] / 1e8, 1),     # 展示日线额(流动性)
        "bar_time": T[i],                          # 命中所依据的已收完 30分bar
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
    strict = "严格入场" if STRICT_BUY else "宽松候选"
    print(f"{pool}池 {len(uni)} 只，30分级别 C段加速前临界点(压缩蓄势)(+日线趋势) {strict}...", flush=True)
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

    # 越强(前期涨幅越大)、成交额越大越靠前。
    hits.sort(key=lambda x: (-x["runup"], -x["amt"]))
    dump = os.environ.get("WATCH_JSON_OUT")
    if dump:
        import json
        json.dump({
            "strategy": "squeeze_launch_30f",
            "variant": ("etf" if ETF_ONLY else "stock") + ("_strict" if STRICT_BUY else "_loose"),
            "strict": STRICT_BUY,
            "is_etf": ETF_ONLY,
            "date": hits[0]["bar_time"] if hits else "",
            "hits": hits,
        }, open(dump, "w"), ensure_ascii=False)

    print(f"\n>>> 30分级别 压缩蓄势/{strict} 命中 {len(hits)} 只\n")
    print("代码    名称        现价    本根%  压缩分  粘合带  距前高  距MA60  前涨%  量比  蓄势区          止损    日额(亿)  bar")
    for h in hits[:50]:
        print(
            f"{h['code']}  {h['name'][:6]:<7} {h['close']:>7.2f} {h['chg']:>+6.2f} "
            f"{h['score']:>3}/{h['denom']} {h['band']:>5.1f}% {h['dist_high']:>+5.1f}% {h['bias60']:>+5.1f}% "
            f"{h['runup']:>+5.1f} {h['vol_ratio']:>5.2f} {h['coil']:<15} {h['stop']:>7.2f} {h['amt']:>6.1f}  {h['bar_time'][5:]}"
        )


if __name__ == "__main__":
    main()
