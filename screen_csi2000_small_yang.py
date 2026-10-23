#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""策略十二 · 全A主板连小阳（排除创业板/科创板/北交所）。

形态参考: 底部后连续多日小阳线缓慢爬升（收>开、涨幅不大、整体上行）。
默认看最近 WINDOW 个交易日。股票池=cache_data.universe()（已剔3/688）。
"""
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

import cache_data

TODAY = os.environ.get("SCREEN_DATE", date.today().isoformat())
WINDOW = int(os.environ.get("YANG_WINDOW", "8"))  # 观察窗口
MIN_YANG = int(os.environ.get("MIN_YANG", "6"))  # 窗口内至少几根阳线
MIN_STREAK = int(os.environ.get("MIN_STREAK", "5"))  # 结尾连续阳线最少根数
MAX_BODY = float(os.environ.get("MAX_BODY", "3.5"))  # 单日实体%上限(相对开盘)
MAX_CHG = float(os.environ.get("MAX_CHG", "4.0"))  # 单日涨幅%上限
MIN_NET = float(os.environ.get("MIN_NET", "2.0"))  # 窗口净涨幅%下限
MAX_NET = float(os.environ.get("MAX_NET", "25.0"))  # 窗口净涨幅%上限(排除暴拉)
# 升胜率档位: 0=全量; 2=窗涨≤8+近20日跌+额0.3-1.2; 3=窗涨≤8+近20日<5%+额0.3-1.0
TIER = int(os.environ.get("YANG_TIER", "0"))


def load_universe():
    """全A沪深主板（cache_data.universe 已剔 ST/创业3/科创688）。"""
    return cache_data.universe()


# 兼容旧回测脚本
load_csi2000_mainboard = load_universe


def _f(row, i):
    return float(row[i])


def analyze(code, name, rows):
    if not rows or rows[-1][0] != TODAY:
        return None
    if len(rows) < max(WINDOW + 1, 21):
        return None

    win = rows[-WINDOW:]
    prev_closes = [_f(rows[-WINDOW - 1 + i], 2) for i in range(WINDOW)]

    yang_flags = []
    small_flags = []
    bodies = []
    chgs = []
    for i, r in enumerate(win):
        o, c = _f(r, 1), _f(r, 2)
        pc = prev_closes[i]
        body = (c - o) / o * 100.0 if o else 0.0
        chg = (c / pc - 1.0) * 100.0 if pc else 0.0
        bodies.append(body)
        chgs.append(chg)
        is_yang = c > o
        yang_flags.append(is_yang)
        # 小阳: 阳线 + 实体不大 + 涨幅可控（允许微跌收阳）
        small_flags.append(is_yang and 0 < body <= MAX_BODY and chg <= MAX_CHG)

    yang_n = sum(yang_flags)
    small_n = sum(small_flags)
    streak = 0
    for y in reversed(yang_flags):
        if y:
            streak += 1
        else:
            break

    c0 = prev_closes[0]
    c1 = _f(win[-1], 2)
    net = (c1 / c0 - 1.0) * 100.0 if c0 else 0.0
    max_chg = max(chgs) if chgs else 0.0
    avg_chg = sum(chgs) / len(chgs)
    avg_body = sum(bodies) / len(bodies)
    vols = [_f(r, 5) for r in win]
    vol_base = sum(vols) / len(vols) if vols else 0.0
    win_low = min(_f(r, 4) for r in win)
    stop = round(win_low * 0.97, 3)
    vol_ratio = (_f(win[-1], 5) / vol_base) if vol_base else 0.0
    ret20 = (c1 / _f(rows[-21], 2) - 1.0) * 100.0 if _f(rows[-21], 2) else 0.0
    ma20 = sum(_f(rows[-20 + k], 2) for k in range(20)) / 20.0
    above_ma20 = int(c1 >= ma20)
    dist_ma20 = (c1 / ma20 - 1.0) * 100.0 if ma20 else 0.0

    # 结尾连续阳 + 窗口多数阳/小阳 + 缓慢上行 + 无单日暴拉
    if streak < MIN_STREAK:
        return None
    if yang_n < MIN_YANG:
        return None
    if small_n < max(MIN_YANG - 1, MIN_STREAK - 1):
        return None
    if not (MIN_NET <= net <= MAX_NET):
        return None
    if max_chg > MAX_CHG + 1.5:  # 允许偶发稍大一根，但不能太夸张
        return None
    # 均涨温和，贴合“爬升”而非脉冲
    if avg_chg > 2.8 or avg_body > 2.5:
        return None

    amt = _f(win[-1], 6) / 1e8

    # 升胜率档: 未涨透 + 额度适中（回测抬胜率主因，不是更长连阳）
    if TIER == 2:
        # 窗涨≤8 + 近20日跌 + 额0.3-1.2 → ~71.6%/+1.87%
        if net > 8 or ret20 >= 0 or not (0.3 <= amt < 1.2):
            return None
    elif TIER == 3:
        # 窗涨≤8 + 近20日<5% + 额0.3-1.0 → ~70.6%/+1.49%
        if net > 8 or ret20 >= 5 or not (0.3 <= amt < 1.0):
            return None

    return {
        "code": code,
        "name": name,
        "close": round(c1, 2),
        "chg": round(chgs[-1], 2),
        "net": round(net, 2),
        "streak": streak,
        "yang_n": yang_n,
        "small_n": small_n,
        "avg_chg": round(avg_chg, 2),
        "avg_body": round(avg_body, 2),
        "max_chg": round(max_chg, 2),
        "amt": round(amt, 2),
        "window": WINDOW,
        "win_low": round(win_low, 3),
        "stop": stop,
        "vol_base": round(vol_base, 0),
        "vol_ratio": round(vol_ratio, 2),
        "ret20": round(ret20, 2),
        "above_ma20": above_ma20,
        "dist_ma20": round(dist_ma20, 2),
        "tier": TIER,
    }


def main():
    uni = load_universe()
    tier_tag = {0: "全量", 2: "2档·未涨透", 3: "3档·温和未透"}.get(TIER, f"T{TIER}")
    print(
        f"全A主板池 {len(uni)} 只(剔创业/科创) | {tier_tag} | 窗口{WINDOW}日 "
        f"连阳≥{MIN_STREAK} 阳线≥{MIN_YANG} 今日={TODAY}",
        flush=True,
    )
    hits, done, missing = [], 0, 0
    with ThreadPoolExecutor(max_workers=12) as ex:
        futs = {
            ex.submit(cache_data.daily_kline, sec): (code, name)
            for code, name, sec in uni
        }
        for fut in as_completed(futs):
            code, name = futs[fut]
            done += 1
            try:
                rows = fut.result()
                if not rows:
                    missing += 1
                else:
                    item = analyze(code, name, rows)
                    if item:
                        hits.append(item)
            except Exception:
                missing += 1
            if done % 300 == 0:
                print(f"  {done}/{len(uni)} 命中{len(hits)}", flush=True)

    hits.sort(key=lambda h: (-h["streak"], -h["small_n"], h["ret20"], -h["net"]))
    out = {
        "strategy": "csi2000_small_yang",
        "date": TODAY,
        "universe": len(uni),
        "params": {
            "window": WINDOW,
            "min_yang": MIN_YANG,
            "min_streak": MIN_STREAK,
            "max_body": MAX_BODY,
            "max_chg": MAX_CHG,
            "min_net": MIN_NET,
            "max_net": MAX_NET,
            "tier": TIER,
            "pool": "all_a_mainboard",
        },
        "hits": hits,
    }
    dump = os.environ.get("WATCH_JSON_OUT", "data_cache/csi2000_small_yang.json")
    Path(dump).parent.mkdir(parents=True, exist_ok=True)
    with open(dump, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"\n>>> 今日({TODAY}) 全A主板连小阳·{tier_tag} 命中 {len(hits)} 只 (缺缓存{missing})\n")
    print("代码    名称        现价   今日%   窗口%  20日%  连阳 阳/小阳 量比  额(亿)")
    for h in hits:
        print(
            f"{h['code']}  {h['name'][:6]:<7} {h['close']:>7.2f} {h['chg']:>+6.2f} "
            f"{h['net']:>+6.2f} {h['ret20']:>+6.2f} {h['streak']:>4} "
            f"{h['yang_n']}/{h['small_n']:<4} {h['vol_ratio']:>4.2f} {h['amt']:>6.1f}"
        )
    print(f"\n结果已写: {dump}")


if __name__ == "__main__":
    main()
