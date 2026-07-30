#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""策略十一 · 每日筛选: VDB 后缩量回踩买点。

  VDB_REVERSAL=1  只收长跌/低位反转背景
  ETF_ONLY=1      只扫 ETF
"""
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

import cache_data
import vdb_pullback as sig

TODAY = os.environ.get("SCREEN_DATE", date.today().isoformat())


def universe():
    if os.environ.get("ETF_ONLY", "0") != "0":
        return cache_data.etf_universe()
    return cache_data.universe()


def check(code, name, rows):
    if not rows or rows[-1][0] != TODAY:
        return None
    return sig.signal_at(code, name, rows, len(rows) - 1, today_only=True)


def main():
    uni = universe()
    rev = " + 偏反转" if sig.REQUIRE_REVERSAL else ""
    strict = "严格" if sig.STRICT_BUY else "宽松"
    print(f"股票池 {len(uni)} 只，筛策略十一·VDB后缩量回踩·{strict}{rev}...", flush=True)
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

    # 嵌套段 / 贴 VDB 低 / 缩量干净 优先
    hits.sort(key=lambda h: (-h.get("chain", 0), h.get("dist_vdb", 99), h.get("vol_shrink", 9)))
    _dump = os.environ.get("WATCH_JSON_OUT")
    if _dump:
        _is_etf = os.environ.get("ETF_ONLY", "0") != "0"
        json.dump({
            "strategy": "vdb_pullback",
            "variant": (
                ("etf" if _is_etf else "stock")
                + ("_strict" if sig.STRICT_BUY else "_loose")
                + ("_reversal" if sig.REQUIRE_REVERSAL else "")
            ),
            "is_etf": _is_etf,
            "date": TODAY,
            "hits": hits,
        }, open(_dump, "w"), ensure_ascii=False)

    print(f"\n>>> 今日({TODAY}) 策略十一·VDB后缩量回踩 命中 {len(hits)} 只\n")
    print("代码    名称        现价    今日%  VDB日  VDB低  止损   回踩天  缩量比  嵌套  距低%  20日%  额(亿)")
    for h in hits[:50]:
        print(
            f"{h['code']}  {h['name'][:6]:<7} {h['close']:>7.2f} {h['chg']:>+6.2f} "
            f"{h['vdb_date']:>5} {h['vdb_low']:>6.2f} {h['stop']:>6.2f} "
            f"{h['pull_days']:>5} {h['vol_shrink']:>7.2f} {h['chain']:>4} "
            f"{h['dist_vdb']:>+5.1f} {h['ret20']:>+5.1f} {h['amt']:>6.1f}"
        )


if __name__ == "__main__":
    main()
