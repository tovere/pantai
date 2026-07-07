#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
策略六 · C 段加速前临界点(压缩蓄势) 盘中筛选器。

思路(承接策略五的讨论):
不追‘已放量突破后的三买’,而是埋伏‘主升/加速腿发令枪之前的最后蓄势点’。
主升发动前几乎必然出现能量压缩 —— 均线粘合、振幅收窄、缩量地量、贴着前高横住。
在这个‘临界点’进场, 止损放在收敛区下沿, 盈亏比天然好; 吃完加速段用顶分型/背驰卖。

关键位置过滤(防‘赶顶末端的假加速’):
乖离(距 MA60)不能过大, 前期涨幅 runup 不能过大 —— 只埋伏能走出‘干净加速’的中前段中枢,
而不是趋势后段那个爆量赶顶、反手极快的收敛区。

这是日线级别的量化近似, 仅供候选池 + 每日盯盘, 具体启动请配合分钟级确认。
"""
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

import cache_data
import screen_chan_wyckoff_3buy as chan

TODAY = os.environ.get("SCREEN_DATE", date.today().isoformat())
MIN_AMOUNT = float(os.environ.get("MIN_AMOUNT", "50000000"))
REQUIRE_WEEKLY_UP = os.environ.get("REQUIRE_WEEKLY_UP", "1") != "0"
INCLUDE_ETF = os.environ.get("INCLUDE_ETF", "0") != "0"  # 个股基础上再加 ETF(混合池)
ETF_ONLY = os.environ.get("ETF_ONLY", "0") != "0"        # 只扫纯 ETF 池(优先级高于 INCLUDE_ETF)

COIL_WIN = int(os.environ.get("COIL_WIN", "10"))          # 蓄势/收敛窗口长度
# 位置过滤(动量版): 回测发现加速偏爱‘已在强趋势中’的票, 所以要够强 ——
# 设前期涨幅下限排掉蔫票; 上限只用来剔除已经垂直拉升、随时反转的极端票。
MIN_RUNUP = float(os.environ.get("MIN_RUNUP", "0.25"))    # 前期涨幅下限: 至少已涨这么多(强势门槛)
MAX_RUNUP = float(os.environ.get("MAX_RUNUP", "1.00"))    # 前期涨幅上限: 太高=可能垂直赶顶
MAX_BIAS60 = float(os.environ.get("MAX_BIAS60", "0.45"))  # 距 MA60 乖离上限
MIN_SCORE = int(os.environ.get("MIN_SCORE", "4"))         # 压缩特征至少满足几项
GLUE_MAX = float(os.environ.get("GLUE_MAX", "0.03"))      # 均线粘合带宽上限
# 振幅收窄(coil 的核心特征)开关。关掉→候选多 4 倍但每笔更薄(实测 +1.10%→+0.86%, 回撤更深);
# 市场躁动、没缩量票时可临时关掉当扩展候选池。
REQUIRE_CONTRACT = os.environ.get("REQUIRE_CONTRACT", "1") != "0"  # 是否把‘振幅收窄’计入压缩特征
CONTRACT_RATIO = float(os.environ.get("CONTRACT_RATIO", "0.65"))   # 收窄比: 近5日均幅 ≤ 前55日均幅*此值


def avg(xs):
    return chan.avg(xs)


def _ma(C, p, k):
    return chan.avg(C[k - p + 1 : k + 1])


def coil_state(O, H, L, C, V, i):
    """检测第 i 根是否处于‘加速前压缩临界点’。命中返回特征 dict, 否则 None。"""
    if i < 80:
        return None
    w = COIL_WIN
    ma5, ma10, ma20, ma60 = _ma(C, 5, i), _ma(C, 10, i), _ma(C, 20, i), _ma(C, 60, i)
    ma60p = _ma(C, 60, i - 10)
    # 趋势背景: 均线多头排列 + MA60 上行 + 价在 MA20 之上(established uptrend 的一次歇脚)。
    if not (ma60 > ma60p and C[i] >= ma20 and ma20 >= ma60):
        return None
    bias60 = C[i] / ma60 - 1 if ma60 > 0 else 9
    if bias60 > MAX_BIAS60:
        return None

    # 1) 均线粘合: 5/10/20 三线间距占价位很窄(缠绕收敛, 即将发散)。
    band = (max(ma5, ma10, ma20) - min(ma5, ma10, ma20)) / C[i] if C[i] > 0 else 9
    glue = band <= GLUE_MAX
    # 2) 振幅收窄: 近 5 日日均真幅 << 前 55 日(coil 核心, 可用 REQUIRE_CONTRACT 关掉)。
    rng = lambda a, b: avg([(H[j] - L[j]) / C[j - 1] for j in range(a, b) if C[j - 1] > 0])
    recent_rng = rng(i - 4, i + 1)
    base_rng = rng(i - 60, i - 5)
    contract = base_rng > 0 and recent_rng <= base_rng * CONTRACT_RATIO
    # 3) 缩量地量: 近 5 日量能 << 前 60 日均量。
    v_recent = avg(V[i - 4 : i + 1])
    v_base = avg(V[i - 60 : i - 5])
    dry = v_base > 0 and v_recent <= v_base * 0.75
    # 4) 横盘蓄势, 不破位: 窗口内几乎不涨不跌, 且守住 MA20。
    drift = abs(C[i] / C[i - w] - 1) if C[i - w] > 0 else 9
    flat = drift <= 0.06 and min(L[i - w + 1 : i + 1]) >= ma20 * 0.96
    # 5) 贴近前高蓄势待发: 收盘处在蓄势区之前那段高点下方一点点(准备 jump the creek)。
    recent_high = max(H[i - 40 : i - w]) if i - w > i - 40 else max(H[max(0, i - 40) : i])
    near_high = recent_high > 0 and recent_high * 0.90 <= C[i] <= recent_high * 1.03

    # 振幅收窄可关: 关掉时移出特征集, 门槛降 1(仍是“允许缺一项”的宽松度)。
    feats = [glue, dry, flat, near_high]
    need = MIN_SCORE
    if REQUIRE_CONTRACT:
        feats.append(contract)
    else:
        need = MIN_SCORE - 1
    score = sum(feats)
    if score < need:
        return None

    # 位置: 前期涨幅(蓄势区下沿相对起涨低点)。
    origin_low = min(L[max(0, i - 70) : i - w]) if i - w > 0 else L[i]
    runup = C[i] / origin_low - 1 if origin_low > 0 else 0.0
    if not (MIN_RUNUP <= runup <= MAX_RUNUP):
        return None

    coil_low = min(L[i - w + 1 : i + 1])
    coil_high = max(H[i - w + 1 : i + 1])
    return {
        "score": score,
        "glue": glue,
        "contract": contract,
        "dry": dry,
        "flat": flat,
        "near_high": near_high,
        "band": band,
        "bias60": bias60,
        "runup": runup,
        "recent_high": recent_high,
        "dist_high": C[i] / recent_high - 1 if recent_high > 0 else 0.0,
        "coil_low": coil_low,
        "coil_high": coil_high,
        "vol_ratio": v_recent / v_base if v_base > 0 else 0.0,
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
    if REQUIRE_WEEKLY_UP:
        weekly = chan.weekly_up_state(D, O, H, L, C, V, A)
        if not weekly or not weekly["up"]:
            return None
    cs = coil_state(O, H, L, C, V, i)
    if not cs:
        return None
    return {
        "code": code,
        "name": name,
        "close": round(C[i], 2),
        "chg": round((C[i] / C[i - 1] - 1) * 100, 2),
        "score": cs["score"],
        "band": round(cs["band"] * 100, 1),
        "dist_high": round(cs["dist_high"] * 100, 1),
        "bias60": round(cs["bias60"] * 100, 1),
        "runup": round(cs["runup"] * 100, 1),
        "vol_ratio": round(cs["vol_ratio"], 2),
        "coil": f"{cs['coil_low']:.2f}-{cs['coil_high']:.2f}",
        "stop": round(cs["coil_low"] * 0.99, 2),
        "amt": round(A[i] / 1e8, 1),
    }


def main():
    if ETF_ONLY:
        uni = cache_data.etf_universe()
    elif INCLUDE_ETF:
        uni = cache_data.universe() + cache_data.etf_universe()
    else:
        uni = cache_data.universe()
    wk = " + 周线向上" if REQUIRE_WEEKLY_UP else ""
    etf = " (纯ETF)" if ETF_ONLY else (" + ETF" if INCLUDE_ETF else "")
    print(f"标的池 {len(uni)} 只{etf}，筛 C段加速前临界点(压缩蓄势){wk}...", flush=True)
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

    # 越强(前期涨幅越大)、成交额越大越靠前。
    hits.sort(key=lambda x: (-x["runup"], -x["amt"]))
    _dump = os.environ.get("WATCH_JSON_OUT")
    if _dump:
        import json as _json
        _json.dump({
            "strategy": "squeeze_launch",
            "variant": ("etf" if (ETF_ONLY or INCLUDE_ETF) else "stock"),
            "is_etf": ETF_ONLY or INCLUDE_ETF,
            "require_contract": REQUIRE_CONTRACT,
            "date": TODAY,
            "hits": hits,
        }, open(_dump, "w"), ensure_ascii=False)
    print(f"\n>>> 今日({TODAY}) C段加速前临界点 命中 {len(hits)} 只\n")
    denom = 5 if REQUIRE_CONTRACT else 4
    print("代码    名称        现价    今日%  压缩分  粘合带  距前高  距MA60  前涨%  量比  蓄势区          止损    额(亿)")
    for h in hits[:50]:
        print(
            f"{h['code']}  {h['name'][:6]:<7} {h['close']:>7.2f} {h['chg']:>+6.2f} "
            f"{h['score']:>3}/{denom} {h['band']:>5.1f}% {h['dist_high']:>+5.1f}% {h['bias60']:>+5.1f}% "
            f"{h['runup']:>+5.1f} {h['vol_ratio']:>5.2f} {h['coil']:<15} {h['stop']:>7.2f} {h['amt']:>6.1f}"
        )


if __name__ == "__main__":
    main()
