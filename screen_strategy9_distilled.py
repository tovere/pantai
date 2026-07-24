#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""策略九 · 八策蒸馏防守版筛选器。

默认只保留回测里最干净的两个入口:
  - coil_launch: 策略六压缩蓄势
  - spring_2buy: 策略七 Spring 二买 + 底背驰

可选 ENABLE_3BUY=1 时加入策略五严格三买, 但实盘默认建议只作为观察池。
"""
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

import cache_data
import screen_chan_wyckoff_3buy as ch
import screen_spring_2buy as sp
import screen_squeeze_launch as sq

TODAY = os.environ.get("SCREEN_DATE", date.today().isoformat())
ENABLE_3BUY = os.environ.get("ENABLE_3BUY", "0") != "0"


def _decorate(hit, kind, setup, priority):
    if not hit:
        return None
    hit = dict(hit)
    hit["kind"] = kind
    hit["setup"] = setup
    hit["s9_priority"] = priority
    return hit


def check(code, name, rows):
    cands = [
        _decorate(sq.check(code, name, rows), "coil_launch", "压缩蓄势", 86),
        _decorate(sp.check(code, name, rows), "spring_2buy", "Spring二买", 92),
    ]
    if ENABLE_3BUY:
        cands.append(_decorate(ch.check(code, name, rows), "chan_3buy", "严格三买", 88))
    cands = [x for x in cands if x]
    if not cands:
        return None
    return max(cands, key=lambda x: (x["s9_priority"], x.get("amt", 0)))


def main():
    uni = cache_data.universe()
    label = "压缩蓄势+Spring二买" + ("+严格三买" if ENABLE_3BUY else "")
    print(f"标的池 {len(uni)} 只，筛 策略九·八策蒸馏({label})...", flush=True)
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

    hits.sort(key=lambda x: (-x["s9_priority"], -x.get("amt", 0)))
    dump = os.environ.get("WATCH_JSON_OUT")
    if dump:
        with open(dump, "w", encoding="utf-8") as f:
            json.dump({
                "strategy": "strategy9_distilled",
                "variant": "stock_defensive",
                "is_etf": False,
                "date": TODAY,
                "hits": hits,
            }, f, ensure_ascii=False)

    print(f"\n>>> 今日({TODAY}) 策略九·八策蒸馏 命中 {len(hits)} 只\n")
    print("代码    名称        入口        现价   今日%  止损   额(亿)  关键信息")
    for h in hits[:50]:
        if h["kind"] == "spring_2buy":
            info = f"背驰{h.get('div_pct', 0):.2f}% 离Spring{h.get('up_from_spring', 0):+.1f}%"
        elif h["kind"] == "coil_launch":
            info = f"压缩{h.get('score', 0)}分 前涨{h.get('runup', 0):+.1f}% 距MA60{h.get('bias60', 0):+.1f}%"
        else:
            info = f"中枢#{h.get('stage', 0)} 距上沿{h.get('dist', 0):+.1f}%"
        print(
            f"{h['code']}  {h['name'][:6]:<7}{h['setup']:<10}"
            f"{h['close']:>7.2f}{h['chg']:>+6.2f}{h.get('stop', 0):>7.2f}"
            f"{h.get('amt', 0):>6.1f}  {info}"
        )


if __name__ == "__main__":
    main()
