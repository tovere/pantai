#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""策略十四 · 底部放量第一根大阳。

形态（当日收盘确认，次日开盘买）:
  1) 今日大阳: 收>开、涨幅∈[MIN_CHG, MAX_CHG]%、实体够厚、收盘靠近全日高
  2) 放量: 量 ≥ VOL_MULT × 前5日均量，成交额 ≥ MIN_AMT 亿
  3) 底部: 大阳前已超跌/贴底（近20日弱 + 价位在近60日区间下半）
  4) 第一根: 近 FIRST_LOOKBACK 日内无同类「大涨+放量」阳线

默认股票池=主板+创业板（剔 ST/科创/北交）。INCLUDE_CYB=0 可只跑主板。
"""
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

import cache_data

TODAY = os.environ.get("SCREEN_DATE", date.today().isoformat())
MIN_CHG = float(os.environ.get("S14_MIN_CHG", "7.0"))
MAX_CHG = float(os.environ.get("S14_MAX_CHG", "21.5"))  # 创业板涨停可略超20%
MIN_BODY = float(os.environ.get("S14_MIN_BODY", "4.0"))  # 实体占开盘%
CLOSE_POS = float(os.environ.get("S14_CLOSE_POS", "0.55"))  # (收-低)/(高-低)
VOL_MULT = float(os.environ.get("S14_VOL_MULT", "2.0"))
MIN_AMT = float(os.environ.get("S14_MIN_AMT", "0.3"))  # 亿
MAX_RET20 = float(os.environ.get("S14_MAX_RET20", "0.05"))  # 大阳前近20日涨幅上限
MAX_BIAS60 = float(os.environ.get("S14_MAX_BIAS60", "0.05"))  # 大阳前距MA60
MAX_POS60 = float(os.environ.get("S14_MAX_POS60", "0.40"))  # 大阳前在60日高低区间位置
FIRST_LOOKBACK = int(os.environ.get("S14_FIRST_LOOKBACK", "20"))
CONS_WIN = int(os.environ.get("S14_CONS_WIN", "10"))
MAX_CONS_RANGE = float(os.environ.get("S14_MAX_CONS_RANGE", "0.28"))
INCLUDE_CYB = os.environ.get("S14_INCLUDE_CYB", "1") != "0"
UNIVERSE_PATH = cache_data.CACHE_DIR / "universe_main_cyb.json"


def _keep_main_cyb(code, name, symbol):
    if not code or "ST" in name or "退" in name or "PT" in name:
        return None
    if code.startswith("688") or code.startswith("8") or code.startswith("4"):
        return None
    if code.startswith("6"):
        return (code, name, f"1.{code}")
    if code.startswith("0") or code.startswith("3"):
        return (code, name, f"0.{code}")
    return None


def universe(force=False):
    if not INCLUDE_CYB:
        return cache_data.universe(force=force)
    items = cache_data._cached_list(UNIVERSE_PATH, "hs_a", _keep_main_cyb, force)
    if items:
        return items
    # 无网络/列表残缺时回退主板，避免空池
    return cache_data.universe(force=force)


def _avg(xs):
    return sum(xs) / len(xs) if xs else 0.0


def _is_big_vol_yang(C, O, V, j, min_chg=None, vol_mult=None):
    """第 j 根是否「大涨+放量」阳线（用于「第一根」去重）。"""
    if j < 5 or C[j - 1] <= 0:
        return False
    min_chg = MIN_CHG if min_chg is None else min_chg
    vol_mult = VOL_MULT if vol_mult is None else vol_mult
    if C[j] <= O[j]:
        return False
    chg = C[j] / C[j - 1] - 1
    if chg * 100 < min_chg:
        return False
    base = _avg(V[j - 5 : j])
    return base > 0 and V[j] >= vol_mult * base


def signal_at(code, name, rows, i, today_only=False):
    if i < 70 or i >= len(rows):
        return None
    if today_only and rows[i][0] != TODAY:
        return None

    O = [float(r[1]) for r in rows]
    C = [float(r[2]) for r in rows]
    H = [float(r[3]) for r in rows]
    L = [float(r[4]) for r in rows]
    V = [float(r[5]) for r in rows]
    A = [float(r[6]) for r in rows]

    if C[i - 1] <= 0 or O[i] <= 0:
        return None
    if C[i] <= O[i]:
        return None

    chg = (C[i] / C[i - 1] - 1) * 100
    if not (MIN_CHG <= chg <= MAX_CHG):
        return None

    body = (C[i] - O[i]) / O[i] * 100
    if body < MIN_BODY:
        return None

    rng = H[i] - L[i]
    if rng <= 0 or (C[i] - L[i]) / rng < CLOSE_POS:
        return None

    base_vol = _avg(V[i - 5 : i])
    if base_vol <= 0 or V[i] < VOL_MULT * base_vol:
        return None
    vol_ratio = V[i] / base_vol

    amt = A[i] / 1e8
    if amt < MIN_AMT:
        return None

    # 底部：用大阳前一日状态，避免把今日暴涨算进「已强」
    ret20 = C[i - 1] / C[i - 21] - 1 if C[i - 21] > 0 else 0
    if ret20 > MAX_RET20:
        return None
    ma60 = _avg(C[i - 60 : i])  # 不含今日
    if ma60 <= 0:
        return None
    bias60 = C[i - 1] / ma60 - 1
    if bias60 > MAX_BIAS60:
        return None

    hi60 = max(H[i - 60 : i])
    lo60 = min(L[i - 60 : i])
    span = hi60 - lo60
    if span <= 0:
        return None
    pos60 = (C[i - 1] - lo60) / span
    if pos60 > MAX_POS60:
        return None

    # 启动前一段横着：避免一路阴跌后的单日反抽噪声
    if CONS_WIN > 0 and i >= CONS_WIN + 1:
        cons_hi = max(H[i - CONS_WIN : i])
        cons_lo = min(L[i - CONS_WIN : i])
        cons_rng = (cons_hi - cons_lo) / C[i - 1] if C[i - 1] else 9
        if cons_rng > MAX_CONS_RANGE:
            return None
        base_low = cons_lo
    else:
        base_low = lo60

    # 第一根：近窗内不能已有同类大阳放量
    lo = max(5, i - FIRST_LOOKBACK)
    for j in range(lo, i):
        if _is_big_vol_yang(C, O, V, j):
            return None

    stop = round(min(L[i], base_low) * 0.99, 3)
    score = chg + vol_ratio * 2 - max(0, ret20) * 50 - pos60 * 10

    return {
        "code": code,
        "name": name,
        "date": rows[i][0],
        "close": round(C[i], 2),
        "chg": round(chg, 2),
        "body": round(body, 2),
        "amt": round(amt, 2),
        "vol_ratio": round(vol_ratio, 2),
        "ret20": round(ret20 * 100, 1),
        "bias60": round(bias60 * 100, 1),
        "pos60": round(pos60 * 100, 1),
        "base_low": round(base_low, 3),
        "sig_low": round(L[i], 3),
        "stop": stop,
        "score": round(score, 2),
    }


def check(code, name, rows):
    if not rows or rows[-1][0] != TODAY:
        return None
    return signal_at(code, name, rows, len(rows) - 1, today_only=True)


def main():
    uni = universe()
    pool = "主板+创业板" if INCLUDE_CYB else "主板"
    print(
        f"股票池 {len(uni)} 只({pool})，筛策略十四·底部放量第一根大阳 "
        f"(涨≥{MIN_CHG}% 量≥{VOL_MULT}x)…",
        flush=True,
    )
    hits, done = [], 0
    with ThreadPoolExecutor(max_workers=12) as ex:
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

    hits.sort(key=lambda h: (-h["score"], -h["vol_ratio"], -h["chg"]))
    dump = os.environ.get("WATCH_JSON_OUT")
    if dump:
        json.dump({
            "strategy": "bottom_vol_yang",
            "variant": "stock",
            "is_etf": False,
            "date": TODAY,
            "hits": hits,
        }, open(dump, "w"), ensure_ascii=False)

    print(f"\n>>> 今日({TODAY}) 策略十四·底部放量第一根大阳 命中 {len(hits)} 只\n")
    print("代码    名称        现价   今日%  量比  实体%  20日%  位60%  止损   额(亿)")
    for h in hits[:50]:
        print(
            f"{h['code']}  {h['name'][:6]:<7} {h['close']:>7.2f} {h['chg']:>+6.2f} "
            f"{h['vol_ratio']:>5.1f} {h['body']:>5.1f} {h['ret20']:>+6.1f} "
            f"{h['pos60']:>5.1f} {h['stop']:>6.2f} {h['amt']:>6.1f}"
        )


if __name__ == "__main__":
    main()
