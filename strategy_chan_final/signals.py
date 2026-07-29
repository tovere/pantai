#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""三类买卖点识别 + 多级别共振(级别无关, 自同构)。

买卖点完备性定理(704): 能赚钱的买卖点只有一、二、三类, 没有第四类。本文件就把
这三类(及其对称的卖点)在 chan.py 的结构上逐条实现, 每条都注明所依据的定理编号。

级别无关: 同一组函数喂日线结构得日线买卖点, 喂30分结构得30分买卖点。
从而 706(大级别买卖点必然是次级别以下某级别的买卖点) / 708(区间套) 只是把同一组
函数在两个级别上跑一遍再取交集。
"""
import os

import chan

# ---- 可调参数(env 覆盖) ----
LEAVE_MIN = float(os.environ.get("LEAVE_MIN", "0.02"))    # 三买: 离开段须高出 ZG 的幅度
ZG_TOL = float(os.environ.get("ZG_TOL", "0.005"))         # 三买: 回试破 ZG 的容忍(毛刺)
MAX_LAG = int(os.environ.get("MAX_LAG", "4"))             # 买点确认后允许的滞后K线数
# 三买回试的参照位: 0=按原文 703/504 只要求不破 ZG=min(g1,g2); 1=严口径, 还要求不破
# 中枢**实际顶部 GG**。504 规定 ZG 只由前两段决定, 中枢越宽越长 ZG 就离 GG 越远,
# "不破 ZG" 会松到肉眼看不出是三买。实测两种口径的优劣**个股与ETF相反**:
#   个股 低点<GG 反而更好(+1.03% vs +0.73%) -> 保持原文口径 0
#   ETF  低点<GG 直接转负(-0.16%/36%胜 vs +2.19%/58%胜) -> 必须开 1
PULLBACK_GG = os.environ.get("PULLBACK_GG", "0") != "0"
MAX_EXT_BUY = float(os.environ.get("MAX_EXT_BUY", "0.06"))  # 距买点低点已涨超此值 = 追高, 放弃
DIV_AREA = float(os.environ.get("DIV_AREA", "0.85"))      # 背驰: C段柱面积 / A段
DIV_DIF = float(os.environ.get("DIV_DIF", "0.95"))        # 背驰: C段黄白线幅度 / A段
# 趋势背驰(≥2个同向不重叠中枢)才是标准一买, 盘整背驰级别低、多抓反弹(15课)。
# 但日线笔中枢上"绝对不重叠"极罕见, 默认放行盘整背驰并单独打标, 由回测分档验证。
ALLOW_PANZHENG = os.environ.get("ALLOW_PANZHENG", "1") != "0"


# ---------------------------------------------------------------- 工具


def _last_dir_bi(bs, d, before):
    """向前找最近一个方向为 d 的笔(索引 < before)。"""
    for k in range(before - 1, -1, -1):
        if bs[k]["d"] == d:
            return bs[k], k
    return None, -1


def _ext(st, price):
    """当前收盘相对某价位已经拉开的幅度。"""
    return st["C"][st["i"]] / price - 1 if price > 0 else 9


def _confirm(st, low, ei):
    """买点确认: 转折点走出来之后再动手, 不猜底(106 易错点②)。

    低点已过 MAX_LAG 根仍未转强 -> 视为失效; 当日必须收在低点之上且不是阴线。
    """
    i = st["i"]
    if ei > i or i - ei > MAX_LAG:
        return False
    if st["C"][i] < st["O"][i]:
        return False
    return st["C"][i] > low * 1.002


def left_pivot_down(st, li):
    """li 处的低点是否由"向下离开某中枢"的那一段造成(503 中枢破坏的向下版)。

    是二买的位置前提: 前低得是一段真正的下跌离开段的终点, 而不是随便一个小坑。
    """
    ps, bs = st["ps"], st["bs"]
    for zi in range(len(ps) - 1, -1, -1):
        Z = ps[zi]
        if Z["ei"] >= li:
            continue
        if Z["leave"] is None:
            return None
        lv = bs[Z["leave"]]
        return Z if (lv["d"] == -1 and lv["lo"] < Z["zd"]) else None
    return None


def div_at_low(st, li):
    """判断原始bar索引 li 处的低点是不是一个"背驰底"(即一个第一类买点)。

    做法就是 106 的定义: 找 li 之前最后一个被**向下离开**的中枢 Z,
    A段 = 进入 Z 的下跌笔, C段 = Z 结束 -> li, 比两段力度。
    返回 (背驰明细, 中枢Z, 是否趋势背驰) 或 None。这是一买的核心, 也被二买复用
    ——因为 107 要求二买必须跟在一个一买后面。
    """
    ps, bs = st["ps"], st["bs"]
    for zi in range(len(ps) - 1, -1, -1):
        Z = ps[zi]
        if Z["ei"] >= li:
            continue
        if Z["leave"] is None:
            return None
        lv = bs[Z["leave"]]
        if lv["d"] != -1 or lv["lo"] >= Z["zd"]:
            return None                   # 中枢不是被向下离开的
        a, _ = _last_dir_bi(bs, -1, Z["s"])
        if a is None:
            return None
        dv = chan.diverge(st["H"], st["L"], st["dif"], st["hist"],
                          (a["si"], a["ei"]), (Z["ei"], li), -1, DIV_AREA, DIV_DIF)
        if not dv:
            return None
        td2, tn2 = chan.trend(ps[:zi + 1])
        return dv, Z, (td2 == -1 and tn2 >= 2)
    return None


# ---------------------------------------------------------------- 第一类买点


def first_buy(st):
    """第一类买点(106 + 802 + 707)。

    男上位最后一吻后的背驰式下跌造出的那个坑:
      ① 下跌趋势——最后一个中枢向下被离开(离开段跌破 ZD);
         趋势背驰要求 ≥2 个依次向下不重叠中枢(206), 只有1个中枢的是盘整背驰(级别低);
      ② A段 = 进入最后中枢的下跌笔, C段 = 中枢结束 -> 当前底分型低点;
      ③ diverge(): 价格新低 + 柱面积萎缩 + 黄白线不新低 + DIF 在0轴下(802);
      ④ **确认后才动手**——底分型已经走出来且收盘转强, 不猜底、不接飞刀。
    """
    ps, bs, fx = st["ps"], st["bs"], st["fx"]
    if not ps or len(bs) < 4 or not fx or fx[-1]["d"] != -1:
        return None                       # 必须已出底分型
    f = fx[-1]
    i = st["i"]
    if not _confirm(st, f["p"], f["i"]):
        return None
    r = div_at_low(st, f["i"])
    if not r:
        return None
    dv, Z, is_trend = r
    if not is_trend and not ALLOW_PANZHENG:
        return None
    if _ext(st, f["p"]) > MAX_EXT_BUY:
        return None
    return {
        "type": 1, "kind": "一买" if is_trend else "一买(盘整背驰)",
        "trend_div": is_trend, "low": f["p"], "stop_ref": f["p"],
        "zg": Z["zg"], "zd": Z["zd"], "lag": i - f["i"], "sid": ("1", f["i"]),
        "ar": dv["ar"], "dr": dv["dr"], "npivot": st["tn"],
    }


# ---------------------------------------------------------------- 第二类买点


def second_buy(st):
    """第二类买点(107 / 定律一 702 / 802)。

    女上位第一吻后的那次回踩:
      ① 前面有一段下跌笔造出的低点 lo0(一买位置);
      ② 之后一段向上笔(次级别上涨), 且 DIF **第一次上 0 轴**(802: 二买 = 第一次上0轴后回抽确认);
      ③ 再一段向下回调, 低点**不创新低**(>= lo0);
      ④ 回调本身力度衰竭(DIF 不再新低)——本级别近似; 真正的 702 要求这段回调在
         **次级别**上构成一个第一类买点, 由 resonance 层用 30 分钟数据确认。
    """
    bs = st["bs"]
    if len(bs) < 3:
        return None
    pull = bs[-1]
    if pull["d"] != -1:
        return None
    up = bs[-2]
    prev, _ = _last_dir_bi(bs, -1, len(bs) - 1)
    if up["d"] != 1 or prev is None:
        return None
    lo0, lo1 = prev["ep"], pull["ep"]
    if lo1 < lo0:
        return None                        # 创新低 -> 不是二买
    dif = st["dif"]
    if dif[prev["ei"]] >= 0:
        return None                        # 802: 一买必在 0 轴之下形成
    if not left_pivot_down(st, prev["ei"]):
        return None                        # 前低必须是"向下离开中枢"的下跌末端, 不是随便一个坑
    base = div_at_low(st, prev["ei"])       # 前低同时是背驰底 -> 标准二买(107), 否则记作类二买
    if max(dif[up["si"]:up["ei"] + 1]) <= 0:
        return None                        # 802: 二买是"第一次上 0 轴后回抽确认"
    if up["ep"] / lo0 - 1 < 0.03 or up["ep"] / lo1 - 1 < 0.02:
        return None                        # 反弹与回调都得像样, 不是碎步震荡
    if dif[pull["ei"]] <= dif[prev["ei"]]:
        return None                        # 回调力度未衰竭
    if not _confirm(st, lo1, pull["ei"]) or _ext(st, lo1) > MAX_EXT_BUY:
        return None
    return {
        "type": 2, "kind": "二买" if base else "类二买", "base_div": bool(base), "low": lo1, "stop_ref": lo0,
        "zg": st["ps"][-1]["zg"] if st["ps"] else lo1,
        "zd": st["ps"][-1]["zd"] if st["ps"] else lo1,
        "lag": st["i"] - pull["ei"], "base_low": lo0, "sid": ("2", pull["ei"]),
    }


# ---------------------------------------------------------------- 第三类买点


def third_buy(st):
    """第三类买点(703 + 503)。

    一个次级别走势(笔)向上离开中枢, 再一个次级别走势回试, 低点**不跌破 ZG**:
      ① 中枢 Z 已被向上离开(离开笔的高点 >= ZG*(1+LEAVE_MIN));
      ② 紧接的回试笔低点 >= ZG(容忍 ZG_TOL 的毛刺)——破了就是中枢延伸/扩展, 不是三买;
      ③ 回试结束后收盘转强, 且仍站在 ZG 上方;
      ④ 中枢序号: 趋势里的第几个中枢。第1个=底部吸筹最稳, 越往后越接近背驰赶顶
         (策略五在本项目上已实证第1个中枢显著更优)。
    """
    ps, bs = st["ps"], st["bs"]
    if not ps:
        return None
    i = st["i"]
    for zi in range(len(ps) - 1, max(-1, len(ps) - 4), -1):
        Z = ps[zi]
        le = Z["leave"]
        if le is None or le + 1 >= len(bs):
            continue
        lv, pb = bs[le], bs[le + 1]
        if lv["d"] != 1 or pb["d"] != -1:
            continue
        if lv["ep"] < Z["zg"] * (1 + LEAVE_MIN):
            continue                       # 没有明显离开中枢
        if pb["lo"] < Z["zg"] * (1 - ZG_TOL):
            continue                       # 回试跌回中枢 -> 中枢延伸, 不是三买
        if PULLBACK_GG and pb["ep"] < Z["gg"]:
            continue                       # 严口径: 回试低点还得站在中枢实际顶部之上
        if le + 2 < len(bs):
            continue                       # 已经走出下一笔, 三买过时了
        if not _confirm(st, pb["ep"], pb["ei"]):
            continue                       # 回试后须转强
        if st["C"][i] < Z["zg"]:
            continue                       # 收盘必须仍在 ZG 之上
        if _ext(st, pb["ep"]) > MAX_EXT_BUY:
            continue
        return {
            "type": 3, "kind": "三买", "low": pb["ep"], "stop_ref": Z["zg"],
            "zg": Z["zg"], "zd": Z["zd"], "gg": Z["gg"], "dd": Z["dd"],
            "stage": chan.pivot_stage(ps, zi), "lag": i - pb["ei"],
            "leave_high": lv["ep"], "pivot_n": Z["n"], "sid": ("3", pb["ei"]),
            # 中枢形态: 跨度(K线根数)、活动区宽度、回试低点相对**实际顶部 GG** 的位置。
            # 504 规定 ZG=min(g1,g2) 只用前两段, 中枢越宽越长 ZG 就离 GG 越远,
            # "回试不破 ZG" 会松到肉眼看不出是三买 —— 这三个字段就是用来分档验证的。
            "zdays": Z["ei"] - Z["si"], "zwidth": Z["gg"] / Z["dd"] - 1 if Z["dd"] else 0,
            "gg_gap": pb["ep"] / Z["gg"] - 1 if Z["gg"] else 0,
        }
    return None


# ---------------------------------------------------------------- 卖点


def first_sell(st):
    """第一类卖点(106 对称 + 802): 上涨趋势末端顶背驰。卖点优先级最高, 出现即清。"""
    ps, bs = st["ps"], st["bs"]
    if not ps or len(bs) < 4:
        return None
    Z = ps[-1]
    if Z["leave"] is None:
        return None
    lv = bs[Z["leave"]]
    if lv["d"] != 1 or lv["hi"] <= Z["zg"]:
        return None
    a, _ = _last_dir_bi(bs, 1, Z["s"])
    if a is None:
        return None
    fx = st["fx"]
    if not fx or fx[-1]["d"] != 1:
        return None
    f = fx[-1]
    i = st["i"]
    if f["i"] < Z["ei"] or i - f["i"] > MAX_LAG:
        return None
    dv = chan.diverge(st["H"], st["L"], st["dif"], st["hist"],
                      (a["si"], a["ei"]), (Z["ei"], f["i"]), 1, DIV_AREA, DIV_DIF)
    if not dv:
        return None
    is_trend = st["td"] == 1 and st["tn"] >= 2
    if not is_trend and not ALLOW_PANZHENG:
        return None
    return {"type": -1, "kind": "一卖" if is_trend else "一卖(盘整背驰)",
            "high": f["p"], "ar": dv["ar"], "dr": dv["dr"]}


def third_sell(st):
    """第三类卖点(703 对称): 向下离开中枢后回抽不破 ZD。最晚最凶的逃命点。"""
    ps, bs = st["ps"], st["bs"]
    if not ps:
        return None
    Z = ps[-1]
    le = Z["leave"]
    if le is None or le + 1 >= len(bs) or le + 2 < len(bs):
        return None
    lv, rb = bs[le], bs[le + 1]
    if lv["d"] != -1 or rb["d"] != 1:
        return None
    if lv["ep"] > Z["zd"] * (1 - LEAVE_MIN):
        return None
    if rb["hi"] > Z["zd"] * (1 + ZG_TOL):
        return None
    if st["i"] - rb["ei"] > MAX_LAG:
        return None
    return {"type": -3, "kind": "三卖", "high": rb["ep"], "zd": Z["zd"]}


# ---------------------------------------------------------------- 汇总


ENABLE_TYPES = os.environ.get("ENABLE_TYPES", "23")   # 默认只做二买/三买, 一买见 README


def buy_point(st, types=None):
    """返回当前 bar 上成立的买点(按"买点越靠前风险收益比越好"的顺序取第一个)。

    一买 > 二买 > 三买 —— 但一买是抄背驰底(风险最大, 只配试仓), 三买是趋势确立
    (位置最高但确定性最好, 是第一/第二利润最大模式的主战场), 仓位由 POSITION 给出。
    """
    types = ENABLE_TYPES if types is None else types
    for t, fn in ((1, first_buy), (2, second_buy), (3, third_buy)):
        if str(t) not in types:
            continue
        r = fn(st)
        if r:
            return r
    return None


def sell_point(st):
    """返回当前 bar 上成立的卖点。卖点优先级铁律: 一卖 > 二卖 > 三卖。"""
    for fn in (first_sell, third_sell):
        r = fn(st)
        if r:
            return r
    return None


# 仓位建议(背驰-转折定理 70a: 背驰后有中枢扩展/更大级别盘整/反趋势三种去向,
# 所以一买只配试仓; 二买是"验货"后加仓; 三买是趋势确立可上重仓)。
POSITION = {1: 0.3, 2: 0.6, 3: 1.0}


# ---------------------------------------------------------------- 多级别


def weekly_bars(rows):
    """日K -> 周K(大级别)。"""
    from datetime import date as _date

    out, cur = [], None
    for r in rows:
        y, w, _ = _date.fromisoformat(r[0]).isocalendar()
        if cur is None or cur[0] != (y, w):
            if cur:
                out.append(cur[1])
            cur = ((y, w), [r[0], r[1], r[2], r[3], r[4], float(r[5]), float(r[6])])
        else:
            b = cur[1]
            b[0] = r[0]
            b[2] = r[2]
            b[3] = max(float(b[3]), float(r[3]))
            b[4] = min(float(b[4]), float(r[4]))
            b[5] += float(r[5])
            b[6] += float(r[6])
    if cur:
        out.append(cur[1])
    return out


WEEKLY_MODE = os.environ.get("WEEKLY_MODE", "ma")   # ma | chan | both | off


def chan_weekly_ok(rows):
    """周线缠论走势类型: 用 109(下跌 = 高点降低 且 低点降低)在周线笔上判定。"""
    w = weekly_bars(rows)
    if len(w) < 20:
        return True                        # 数据不足, 不做否决
    st = chan.build(w)
    if not st:
        return True
    ups = [b for b in st["bs"] if b["d"] == 1][-2:]
    dns = [b for b in st["bs"] if b["d"] == -1][-2:]
    if len(ups) < 2 or len(dns) < 2:
        return True
    return not (ups[-1]["ep"] < ups[-2]["ep"] and dns[-1]["ep"] < dns[-2]["ep"])


def ma_weekly_up(rows):
    """周线均线口径的"向上"(沿用本项目策略五已实证的 weekly_up_state)。

    纯几何的 109 判据太宽(只否掉"高低点双降"这种教科书下跌), 实测过滤力远不如
    这个均线口径: 周收盘 > 周MA10 且 周MA10 上行 + 近期不破位。
    """
    W = weekly_bars(rows)
    if len(W) < 16:
        return False
    WC = [float(w[2]) for w in W]
    WH = [float(w[3]) for w in W]
    WL = [float(w[4]) for w in W]
    i = len(W) - 1
    avg = lambda xs: sum(xs) / len(xs)
    ma5, ma10, ma10p = avg(WC[i - 4:i + 1]), avg(WC[i - 9:i + 1]), avg(WC[i - 12:i - 2])
    tail = WC[max(0, i - 5):i + 1]
    recent_mid = sorted(tail)[len(tail) // 2]
    higher_lows = WL[i] >= min(WL[max(0, i - 6):i]) * 0.98
    not_lower_highs = WH[i] >= max(WH[max(0, i - 8):i]) * 0.94
    return bool(WC[i] > ma10 and ma10 > ma10p and WC[i] >= recent_mid
                and (ma5 >= ma10 * 0.995 or higher_lows) and not_lower_highs)


def big_level_ok(rows, mode=None):
    """大级别方向过滤——操作级别铁律: 只参与上涨与盘整, **回避下跌**(38/45课)。"""
    mode = WEEKLY_MODE if mode is None else mode
    if mode == "off":
        return True
    if mode == "chan":
        return chan_weekly_ok(rows)
    if mode == "both":
        return ma_weekly_up(rows) and chan_weekly_ok(rows)
    return ma_weekly_up(rows)


def sub_level_buy(mrows, day, kinds=(1,)):
    """次级别(30分钟)买点确认。

    用途三合一:
      · 702 定律一——本级别二买 = 次级别一买。想确认日线二买, 就到 30 分钟去找一买。
      · 708 区间套——日线背驰段里再套出 30 分钟背驰段, 两级别买点收敛到同一位置,
        才是最精确的转折点(止损最小)。
      · 70b 小背驰-大转折——三买 + 次级别背驰 = 小火星引爆大级别的必要条件。

    mrows 为 30 分钟K线; day 为交易日(只用当日收盘前已走完的分钟bar, 不吃未来)。
    """
    if not mrows:
        return None
    end = 0
    for j, r in enumerate(mrows):
        if r[0][:10] <= day:
            end = j
        else:
            break
    if end < 60 or mrows[end][0][:10] != day:
        return None
    st = chan.build(mrows, end + 1)
    if not st:
        return None
    for t in kinds:
        r = {1: first_buy, 2: second_buy, 3: third_buy}[t](st)
        if r:
            return r
    return None
