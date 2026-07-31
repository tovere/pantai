#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""策略十一 · VDB(垂直需求柱)后缩量回踩买点 —— 共享信号逻辑。

设计目标(补策略五抓不到的「无箱体也能做的 VDB 回踩」):
  - 不要求周线向上 / 站上 MA60 / 先有箱体突破
  - 买点 = 最近一根有效 VDB 之后的缩量回踩 K 线
  - 止损 = 该 VDB 低点
  - 嵌套: 用「最近仍有效的 VDB」作锚; 但回测显示 chain≥1 无优势, 严格版剔除

分层结论(2025-07~2026-07, ≥200亿收紧池再调优):
  - 阴线入场 / 深跌反转 / 嵌套 → 更差; 「破昨高」在收紧池内不抬胜率
  - 缩≤0.50 + 距≤6 + ret20≥0 + 剔反转 → ~703笔 54.1%/+2.23%(原1970笔46.9%/+1.46%)
  - ABC: 距≤4→A, 缩≤0.45→B
"""
import os

MIN_AMOUNT = float(os.environ.get("MIN_AMOUNT", "50000000"))
VOL_MULT = float(os.environ.get("VDB_VOL_MULT", "1.5"))
RANGE_MULT = float(os.environ.get("VDB_RANGE_MULT", "1.3"))
MIN_CHG = float(os.environ.get("VDB_MIN_CHG", "0.02"))
CLOSE_POS = float(os.environ.get("VDB_CLOSE_POS", "0.55"))
BODY_RATIO = float(os.environ.get("VDB_BODY", "0.45"))
PULL_MIN = int(os.environ.get("VDB_PULL_MIN", "2"))
PULL_MAX = int(os.environ.get("VDB_PULL_MAX", "8"))
SHRINK = float(os.environ.get("VDB_SHRINK", "0.50"))
STOP_TOL = float(os.environ.get("VDB_STOP_TOL", "0.005"))
ENTRY_CLOSE_POS = float(os.environ.get("VDB_ENTRY_POS", "0.45"))
# 总市值下限(元)。默认 100 亿=1e10; 设 0 关闭。盯盘: 宽松 200亿 / 严格 100亿
MIN_MKTCAP = float(os.environ.get("MIN_MKTCAP", "10000000000"))
# 宽松额外收紧: 距低上限 / 回踩天数上限
LOOSE_DIST = float(os.environ.get("VDB_LOOSE_DIST", "6.0"))
LOOSE_PULL_MAX = int(os.environ.get("VDB_LOOSE_PULL_MAX", "6"))
# 严格版: 更干净缩量+短回踩; 默认不再强制破昨高(回测不抬胜率)
STRICT_BUY = os.environ.get("STRICT_BUY", "0") != "0"
STRICT_SHRINK = float(os.environ.get("VDB_STRICT_SHRINK", "0.45"))
STRICT_DIST = float(os.environ.get("VDB_STRICT_DIST", "6.0"))
STRICT_PULL_MIN = int(os.environ.get("VDB_STRICT_PULL_MIN", "2"))
STRICT_PULL_MAX = int(os.environ.get("VDB_STRICT_PULL_MAX", "4"))
REQUIRE_RECLAIM = os.environ.get("VDB_REQUIRE_RECLAIM", "0") != "0"
# 可选偏反转(回测显示偏弱, 默认关); EXCLUDE_REV=1 则剔除深跌/低位背景
REQUIRE_REVERSAL = os.environ.get("VDB_REVERSAL", "0") != "0"
EXCLUDE_REVERSAL = os.environ.get("VDB_EXCLUDE_REV", "0") != "0"
OVERSOLD_20 = float(os.environ.get("VDB_OVERSOLD_20", "-0.08"))
OVERSOLD_BIAS = float(os.environ.get("VDB_OVERSOLD_BIAS", "-0.05"))
# 近20日涨幅下限(%, 如 0=要求 ret20≥0); 默认 -99 不过滤
MIN_RET20 = float(os.environ.get("VDB_MIN_RET20", "-99"))

_MKTCAP_CACHE = None


def avg(xs):
    return sum(xs) / len(xs) if xs else 0.0


def _mktcap_map():
    global _MKTCAP_CACHE
    if _MKTCAP_CACHE is not None:
        return _MKTCAP_CACHE
    try:
        import cache_data
        _MKTCAP_CACHE = cache_data.stock_mktcap()
    except Exception:
        _MKTCAP_CACHE = {}
    return _MKTCAP_CACHE


def _bar(O, H, L, C, V, k):
    rng = H[k] - L[k]
    if rng <= 0 or C[k] <= 0:
        return None
    return {
        "rng": rng,
        "close_pos": (C[k] - L[k]) / rng,
        "body": (C[k] - O[k]) / rng,
        "chg": (C[k] / C[k - 1] - 1) if k > 0 and C[k - 1] > 0 else 0.0,
    }


def is_vdb(O, H, L, C, V, k):
    """第 k 根是否为垂直需求柱。"""
    if k < 21:
        return False
    if C[k] <= O[k]:
        return False
    info = _bar(O, H, L, C, V, k)
    if not info or info["chg"] < MIN_CHG:
        return False
    if info["close_pos"] < CLOSE_POS or info["body"] < BODY_RATIO:
        return False
    vbase = avg(V[k - 20 : k])
    if vbase <= 0 or V[k] < vbase * VOL_MULT:
        return False
    rbase = avg([H[j] - L[j] for j in range(k - 20, k)])
    if rbase <= 0 or info["rng"] < rbase * RANGE_MULT:
        return False
    return True


def count_prior_vdbs(O, H, L, C, V, vdb, lookback=12):
    """当前锚 VDB 之前、仍未跌破其低的更早 VDB 个数(嵌套深度)。"""
    n, floor = 0, L[vdb]
    for k in range(vdb - 1, max(21, vdb - lookback) - 1, -1):
        if L[k] < floor * (1 - STOP_TOL):
            break
        if is_vdb(O, H, L, C, V, k):
            n += 1
            floor = min(floor, L[k])
    return n


def signal_at(code, name, rows, i, today_only=False):
    """在第 i 根判断是否为 VDB 后缩量回踩买点。"""
    if i < 90 or i >= len(rows):
        return None
    D = [r[0] for r in rows]
    O = [float(r[1]) for r in rows]
    C = [float(r[2]) for r in rows]
    H = [float(r[3]) for r in rows]
    L = [float(r[4]) for r in rows]
    V = [float(r[5]) for r in rows]
    A = [float(r[6]) for r in rows]
    if A[i] < MIN_AMOUNT:
        return None
    mktcap = _mktcap_map().get(code)
    # 只滤已知小票; 市值缺失不挡(避免源不全误杀大票)
    if MIN_MKTCAP > 0 and mktcap is not None and mktcap < MIN_MKTCAP:
        return None
    if today_only:
        from datetime import date
        today = os.environ.get("SCREEN_DATE", date.today().isoformat())
        if D[i] != today:
            return None

    einfo = _bar(O, H, L, C, V, i)
    if not einfo or einfo["close_pos"] < ENTRY_CLOSE_POS:
        return None
    # 阴线入场回测转负 → 宽松/严格都不要阴线
    if C[i] <= O[i]:
        return None
    # 破昨高仅当显式打开 VDB_REQUIRE_RECLAIM=1(默认关; 收紧池内不抬胜率)
    if REQUIRE_RECLAIM and not (C[i] > H[i - 1]):
        return None

    ma60 = avg(C[i - 59 : i + 1])
    ret20 = C[i] / C[i - 20] - 1 if C[i - 20] > 0 else 0.0
    bias60 = C[i] / ma60 - 1 if ma60 > 0 else 0.0
    if ret20 * 100 < MIN_RET20:
        return None
    is_rev = ret20 <= OVERSOLD_20 or bias60 <= OVERSOLD_BIAS
    if REQUIRE_REVERSAL and not is_rev:
        return None
    if EXCLUDE_REVERSAL and is_rev:
        return None

    pull_lo = STRICT_PULL_MIN if STRICT_BUY else PULL_MIN
    pull_hi = STRICT_PULL_MAX if STRICT_BUY else min(PULL_MAX, LOOSE_PULL_MAX)
    shrink_cap = STRICT_SHRINK if STRICT_BUY else SHRINK
    dist_cap = STRICT_DIST if STRICT_BUY else LOOSE_DIST

    for vdb in range(i - pull_lo, max(21, i - pull_hi) - 1, -1):
        if not is_vdb(O, H, L, C, V, vdb):
            continue
        pull = list(range(vdb + 1, i + 1))
        if not (pull_lo <= len(pull) <= pull_hi):
            continue
        vdb_low = L[vdb]
        if min(L[j] for j in pull) < vdb_low * (1 - STOP_TOL):
            continue
        pull_vol = avg([V[j] for j in pull])
        if V[vdb] <= 0 or pull_vol > V[vdb] * shrink_cap:
            continue
        if V[i] > V[vdb] * shrink_cap:
            continue
        if C[i] > H[vdb] * 1.08:
            continue
        if is_vdb(O, H, L, C, V, i):
            continue

        chain = count_prior_vdbs(O, H, L, C, V, vdb)
        # 嵌套二段回测无优势 → 宽松/严格都剔除
        if chain >= 1:
            continue
        pull_low = min(L[j] for j in pull)
        dist = (C[i] / vdb_low - 1) * 100 if vdb_low > 0 else 99.0
        if dist > dist_cap:
            continue

        return {
            "date": D[i],
            "code": code,
            "name": name,
            "entry": C[i],
            "close": round(C[i], 2),
            "chg": round((C[i] / C[i - 1] - 1) * 100, 2) if C[i - 1] else 0.0,
            "vdb_date": D[vdb][5:],
            "vdb_low": round(vdb_low, 2),
            "vdb_high": round(H[vdb], 2),
            "stop": round(vdb_low * (1 - STOP_TOL), 2),
            "buy_low": round(pull_low, 2),
            "pull_days": i - vdb,
            "vol_shrink": round(pull_vol / V[vdb], 2),
            "chain": chain,
            "dist_vdb": round(dist, 1),
            "ret20": round(ret20 * 100, 1),
            "bias60": round(bias60 * 100, 1),
            "amt": round(A[i] / 1e8, 1),
            "mktcap": round(mktcap / 1e8, 1) if mktcap else None,  # 亿
            "reversal": int(is_rev),
            "yang": 1,
            "reclaim": int(C[i] > H[i - 1]),
        }
    return None
