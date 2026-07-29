#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""策略十·缠论完备体系 —— 每日选股(多级别共振)。

三级联动, 每一级都对应一条定理:
  周线(大级别) —— 操作级别铁律: 只参与上涨与盘整, 回避下跌(38/45课)。
  日线(操作级别) —— 三类买卖点在这一级产生, 买卖只认这一级(704 完备性)。
  30分(次级别) —— 706/708 区间套 + 702 定律一 + 70b 小背驰-大转折:
                   日线买点上再叠一个 30 分钟买点, 才是"最精确的转折点", 止损最小。

输出列固定, 与本项目其它盯盘表一致; 设 WATCH_JSON_OUT 可把命中落 JSON 供盯盘台回收。
"""
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent))
os.environ.setdefault("MA_CACHE_DIR", str(_HERE.parent / "data_cache"))

import cache_data  # noqa: E402
import chan  # noqa: E402
import signals as sg  # noqa: E402

TODAY = os.environ.get("SCREEN_DATE", date.today().isoformat())
MIN_AMOUNT = float(os.environ.get("MIN_AMOUNT", "50000000"))
SUB_LEVEL = os.environ.get("SUB_LEVEL", "1") != "0"   # 是否做 30 分钟次级别共振确认
ETF_ONLY = os.environ.get("ETF_ONLY", "0") != "0"
INCLUDE_ETF = os.environ.get("INCLUDE_ETF", "0") != "0"
KLT = 30


def check(code, name, secid, rows):
    if not rows or len(rows) < 130:
        return None
    D = [r[0] for r in rows]
    if D[-1] != TODAY or float(rows[-1][6]) < MIN_AMOUNT:
        return None
    st = chan.build(rows)
    if not st:
        return None
    bp = sg.buy_point(st)
    if not bp:
        return None
    if not sg.big_level_ok(rows):
        return None

    i = st["i"]
    C, V, A = st["C"], st["V"], st["A"]
    stop = min(bp["low"], bp["zg"]) if bp["type"] == 3 else bp["low"]
    item = {
        "code": code, "name": name, "kind": bp["kind"], "type": bp["type"],
        "close": round(C[i], 2), "chg": round((C[i] / C[i - 1] - 1) * 100, 2),
        "buy_low": round(bp["low"], 2), "stop": round(stop, 2),
        "risk": round((C[i] / stop - 1) * 100, 1),
        "zg": round(bp["zg"], 2), "zd": round(bp["zd"], 2),
        # dist = 距中枢上沿 ZG(与策略五的"距上沿"同义, 盯盘台复用同一列)
        "dist": round((C[i] / bp["zg"] - 1) * 100, 1) if bp["zg"] else 0.0,
        "stage": bp.get("stage", 0), "lag": bp["lag"], "pull_days": bp["lag"],
        # 回试低点相对中枢实际顶部 GG 的位置(<0 = 只过了 ZG 没过 GG, ETF 上该档负期望)
        "gg": round(bp.get("gg", 0), 3), "gg_gap": round(bp.get("gg_gap", 0) * 100, 1),
        # 评级引擎按池子分档: ETF 上第2个中枢实测 -2.36%/23%胜(个股只是打平)
        "is_etf": ETF_ONLY,
        "pos": sg.POSITION[bp["type"]],
        "vr": round(V[i] / (sum(V[i - 20:i]) / 20), 2) if i >= 20 else 1.0,
        "amt": round(A[i] / 1e8, 1),
        "sub": "",
    }
    if SUB_LEVEL:
        # 二买必须去次级别找一买(702); 一买/三买用次级别买点做区间套/小背驰确认(708/70b)。
        want = (1,) if bp["type"] == 2 else (1, 2, 3)
        try:
            sub = sg.sub_level_buy(cache_data.min_kline(secid, KLT), TODAY, want)
        except Exception:
            sub = None
        item["sub"] = sub["kind"] if sub else ""
    return item


def grade(h):
    """评级: 大级别方向已过滤, 这里只评"这一单该不该下"。"""
    s = 0
    s += {3: 2, 2: 1, 1: 0}[h["type"]]          # 三买最确定, 一买最险(背驰≠反转 70a)
    if h["sub"]:
        s += 2                                   # 次级别共振 = 区间套收口, 最值钱的一分
    if h["type"] == 3 and h["stage"] == 1:
        s += 1                                   # 第一个中枢(底部吸筹)
    if h["risk"] <= 4:
        s += 1                                   # 止损位近
    if h["lag"] <= 1:
        s += 1                                   # 刚转强, 不是追高
    return "A" if s >= 5 else "B" if s >= 3 else "C"


def main():
    if ETF_ONLY:
        uni = cache_data.etf_universe()
    else:
        uni = cache_data.universe()
        if INCLUDE_ETF:
            uni = uni + cache_data.etf_universe()
    print(f"标的池 {len(uni)} 只, 缠论三类买点扫描 (周线={sg.WEEKLY_MODE} "
          f"买点={sg.ENABLE_TYPES} 次级别共振={'on' if SUB_LEVEL else 'off'})...", flush=True)

    hits, done = [], 0
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = {ex.submit(cache_data.daily_kline, s): (c, n, s) for c, n, s in uni}
        for fut in as_completed(futs):
            code, name, secid = futs[fut]
            done += 1
            try:
                item = check(code, name, secid, fut.result())
                if item:
                    hits.append(item)
            except Exception:
                pass
            if done % 500 == 0:
                print(f"  {done}/{len(uni)} 命中{len(hits)}", flush=True)

    for h in hits:
        h["grade"] = grade(h)
    hits.sort(key=lambda x: (x["grade"], -x["type"], x["risk"], -x["amt"]))

    dump = os.environ.get("WATCH_JSON_OUT")
    if dump:
        json.dump({"strategy": "chan_final", "variant": "etf" if ETF_ONLY else "stock",
                   "is_etf": ETF_ONLY, "date": TODAY, "hits": hits},
                  open(dump, "w"), ensure_ascii=False)

    print(f"\n>>> {TODAY} 缠论完备体系 命中 {len(hits)} 只 "
          f"(A={sum(1 for h in hits if h['grade']=='A')} "
          f"B={sum(1 for h in hits if h['grade']=='B')})\n")
    print("评级 代码    名称      买点     现价    今日%  买点低  止损位  风险%  中枢下沿-上沿      中枢# 滞后 量比 额(亿) 次级别共振 仓位")
    for h in hits[:60]:
        print(f" {h['grade']}  {h['code']}  {h['name'][:6]:<7} {h['kind']:<8} {h['close']:>7.2f} "
              f"{h['chg']:>+6.2f} {h['buy_low']:>7.2f} {h['stop']:>7.2f} {h['risk']:>5.1f} "
              f"{h['zd']:>8.2f}-{h['zg']:<8.2f} {h['stage']:>4} {h['lag']:>4} {h['vr']:>4.1f} "
              f"{h['amt']:>6.1f} {h['sub'] or '-':<10} {h['pos']:.1f}")
    if not hits:
        print("(今日无命中 —— 三类买点本就稀有, 空仓也是操作: 持币等买点)")


if __name__ == "__main__":
    main()
