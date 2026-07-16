#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""三重共振扫描: 周线向上 + 日线三买(选池) × 30f三买(择时) + 入场前移。

高置信度盯盘清单。默认 30f 严格 + 入场前移(ENTRY_MAX_EXT=0.02),日线用宽松选池。
先并行扫 30f三买(快、只剩几只),再对这几只顺序查"近 POOL_DAYS 日是否有日线三买"
(日线 check 用模块级 TODAY,顺序执行避免线程竞态)。
"""
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import cache_data
import screen_chan_wyckoff_3buy as dstk
import screen_chan_wyckoff_3buy_30f as m30

POOL_DAYS = int(os.environ.get("POOL_DAYS", "5"))
ETF_ONLY = os.environ.get("ETF_ONLY", "0") != "0"
# 日线选池宽松(候选结构); 30f择时严格 + 入场前移
dstk.STRICT_BUY = os.environ.get("DAILY_STRICT", "0") != "0"
m30.STRICT_BUY = os.environ.get("STRICT_BUY", "1") != "0"
m30.ENTRY_MAX_EXT = float(os.environ.get("ENTRY_MAX_EXT", "0.02"))


def universe():
    return cache_data.etf_universe() if ETF_ONLY else cache_data.universe()


def _scan_30f(code, name, secid):
    mrows = cache_data.min_kline(secid, 30)
    if not mrows or len(mrows) < 80:
        return None
    dt = m30.daily_trend(secid)
    if dt is None:
        return None
    try:
        item = m30.check(code, name, mrows, dt)
    except Exception:
        return None
    if item:
        item["secid_"] = secid
    return item


def _daily_pool_date(code, name, drows):
    """近 POOL_DAYS 根日线里最近一次日线三买的日期; 无则 None。"""
    dd = [r[0] for r in drows]
    for di in range(len(dd) - 1, max(79, len(dd) - POOL_DAYS - 1), -1):
        dstk.TODAY = dd[di]
        try:
            if dstk.check(code, name, drows[: di + 1]):
                return dd[di]
        except Exception:
            pass
    return None


def main():
    uni = universe()
    pool = "ETF" if ETF_ONLY else "个股"
    print(f"{pool}池 {len(uni)} 只，三重共振(日线三买×30f三买+前移)扫描...", flush=True)

    # 1) 并行扫 30f三买(快)
    cand = []
    done = 0
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = {ex.submit(_scan_30f, c, n, s): (c, n) for c, n, s in uni}
        for fut in as_completed(futs):
            done += 1
            item = fut.result()
            if item:
                c, n = futs[fut]
                cand.append((c, n, item))
            if done % 500 == 0:
                print(f"  {done}/{len(uni)} 30f候选{len(cand)}", flush=True)

    # 2) 顺序过滤: 必须在日线三买观察池内
    hits = []
    for c, n, item in cand:
        drows = cache_data.daily_kline(item.pop("secid_"))
        if not drows or len(drows) < 80:
            continue
        sd = _daily_pool_date(c, n, drows)
        if sd:
            item["daily_sig"] = sd[5:]  # 日线三买日期 MM-DD
            hits.append(item)

    hits.sort(key=lambda x: (x.get("stage", 9), x.get("dist", 99)))
    dump = os.environ.get("WATCH_JSON_OUT")
    if dump:
        import json
        json.dump({
            "strategy": "chan_wyckoff_3buy_30f",  # 复用三买评级/止损位/K线
            "variant": ("etf" if ETF_ONLY else "stock") + "_resonance",
            "strict": True, "is_etf": ETF_ONLY,
            "date": hits[0]["bar_time"] if hits else "",
            "hits": hits,
        }, open(dump, "w"), ensure_ascii=False)

    print(f"\n>>> 三重共振 命中 {len(hits)} 只(日线三买池 ∩ 30f三买进场)\n")
    for h in hits[:50]:
        print(f"  {h['code']} {h['name'][:8]:<8} 现价{h['close']:>8}  距上沿{h['dist']:+.1f}%  "
              f"日线三买={h['daily_sig']}  30fbar={h['bar_time']}")


if __name__ == "__main__":
    main()
