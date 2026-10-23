#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""盯盘评级引擎: 把人肉盘口判断代码化为 A/B/C/剔除 + 警告标签。

选股器只负责"结构上命中"; 本模块叠加那层"该不该做"的判断:
  - 中枢序号(策略五): #1 加分, #3 直接剔除
  - 距上沿: 贴上沿加分, 追高扣分
  - 回踩天数: 新鲜加分, 磨顶扣分
  - 量价形态(需近K线): 放量滞涨、今日冲高回落长上影 → 红旗封顶
  - 策略六位置: 距MA60 乖离过大 / 前涨过高 → 剔除(垂直赶顶)

规则集中在此文件, 调权重/加信号只改这里, 不动选股器与前端。
每条规则输出一个 flag: {"text": 中文标签, "type": good|warn|bad}
grade: A(可下单级别) / B(候选) / C(弱) / D(剔除)
"""

# ---- 阈值(集中可调) ----
DIST_HUG = 3.0        # 距上沿 ≤ 此值 = 贴上沿(好)
DIST_CHASE = 15.0     # 距上沿 ≥ 此值 = 追高(差)
PULL_FRESH = 3        # 回踩 ≤ 此天数 = 新鲜
PULL_STALE = 7        # 回踩 ≥ 此天数 = 磨顶
SHRINK_CLEAN = 0.60   # 缩量比 ≤ 此值 = 干净缩量
SHRINK_LOOSE = 0.90   # 缩量比 ≥ 此值 = 缩量不足
STALL_FLAT = 1.0      # 突破后区间净涨幅 ≤ 此% 视为滞涨(配合量能未缩)
SQZ_BIAS_TOP = 20.0   # 策略六: 距MA60 ≥ 此值 = 垂直赶顶风险
SQZ_BIAS_KILL = 25.0  # 策略六: 距MA60 ≥ 此值 = 直接剔除
SQZ_RUNUP_TOP = 50.0  # 策略六: 前涨 ≥ 此值 转负档
SQZ_RUNUP_KILL = 60.0 # 策略六: 前涨 ≥ 此值 = 直接剔除


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def _rejection(bars):
    """今日是否冲高回落: 收盘离全天最高 ≥半个振幅 且 收 ≤ 开(阴/平)。
    用 (高-收)/振幅 而非上影线, 以兼容"开盘即最高一路回落"的光头阴线。"""
    if not bars:
        return False
    o, c, h, l = _f(bars[-1][1]), _f(bars[-1][2]), _f(bars[-1][3]), _f(bars[-1][4])
    rng = h - l
    if rng <= 0:
        return False
    return (h - c) / rng >= 0.5 and c <= o


def _volume_stall(bars, window):
    """突破后放量滞涨检测: 近 window 根价格没涨(净涨≤STALL_FLAT%)但量能未缩(≥前段0.9倍)。"""
    n = len(bars)
    w = max(3, min(window, 8))
    if n < w * 2:
        return False
    recent = bars[-w:]
    prior = bars[-w * 2:-w]
    net = (_f(recent[-1][2]) / _f(recent[0][2]) - 1) * 100 if _f(recent[0][2]) else 0
    vr = sum(_f(b[5]) for b in recent) / w
    vp = sum(_f(b[5]) for b in prior) / w
    return net <= STALL_FLAT and vp > 0 and vr >= vp * 0.9


def _decide(score, flags, exclude=False):
    has_bad = any(f["type"] == "bad" for f in flags)
    if exclude:
        return "D"
    if has_bad:                       # 有红旗 → 最高只能 B
        return "B" if score >= 1 else "C"
    if score >= 3:
        return "A"
    if score >= 1:
        return "B"
    return "C"


def grade_three_buy(hit, bars):
    """策略五(缠论/威科夫三买)评级。

    个股: 严格/宽松调优池共用胜率标定 —— dist≤3.5且缩≤0.45→A; dist≤4→B; 其余 C。
    ETF: 仍用结构完整度打分(形态分, 不保证胜率单调)。
    """
    flags, score = [], 0
    stage = int(hit.get("stage", 1))
    dist = _f(hit.get("dist"))
    pull = int(hit.get("pull_days", 0))
    shrink = _f(hit.get("vol_shrink"))
    is_etf = bool(hit.get("is_etf"))
    buy_low = _f(hit.get("buy_low"))
    px = _f(hit.get("close") or hit.get("entry"))
    risk = _f(hit.get("risk"))
    if risk <= 0 and buy_low > 0 and px > 0:
        risk = (px / buy_low - 1) * 100

    # 中枢序号
    if stage >= 3:
        flags.append({"text": f"#{stage}中枢·晚期剔除", "type": "bad"})
        return {"grade": "D", "score": -99, "flags": flags,
                "note": f"第{stage}个中枢, 回测该档转负, 直接剔除"}
    if stage == 1:
        score += 2
        flags.append({"text": "首中枢", "type": "good"})
    elif stage == 2:
        flags.append({"text": "#2中枢·偏中段", "type": "warn"})

    # 距上沿
    if dist <= DIST_HUG:
        score += 2
        flags.append({"text": "贴上沿", "type": "good"})
    elif dist <= 8:
        score += 1
        if not is_etf and dist <= 3.5:
            flags.append({"text": f"贴上沿区(+{dist:.1f}%)", "type": "good"})
    elif dist >= DIST_CHASE:
        score -= 2
        flags.append({"text": f"追高(距上沿+{dist:.0f}%)", "type": "warn"})

    # 回踩天数
    if pull <= PULL_FRESH:
        score += 1
        flags.append({"text": f"回踩新鲜({pull}天)", "type": "good"})
    elif pull >= PULL_STALE:
        score -= 2
        flags.append({"text": f"回踩偏久({pull}天磨顶)", "type": "warn"})

    # 缩量质量
    if shrink and shrink <= (0.45 if not is_etf else SHRINK_CLEAN):
        score += 1
        flags.append({"text": "缩量干净", "type": "good"})
    elif shrink >= SHRINK_LOOSE:
        score -= 1

    if 0 < risk <= 5 and not is_etf:
        flags.append({"text": f"止损近(-{risk:.1f}%)", "type": "good"})

    # 流动性(成交额过小难执行)
    amt = _f(hit.get("amt"))
    if amt and amt < 1.5:
        score -= 1
        flags.append({"text": f"量能偏小({amt:.1f}亿)", "type": "warn"})

    # 量价滞涨(红旗)
    if _volume_stall(bars, pull + 1):
        score -= 2
        flags.append({"text": "放量滞涨·上方派发", "type": "bad"})

    # 今日冲高回落(红旗)
    if _rejection(bars):
        score -= 2
        flags.append({"text": "冲高回落", "type": "bad"})

    has_bad = any(f["type"] == "bad" for f in flags)
    if is_etf:
        grade = _decide(score, flags)
    elif has_bad:
        grade = "B" if score >= 1 else "C"
    elif dist <= 3.5 and shrink and shrink <= 0.45:
        grade = "A"
        score = max(score, 3)
    elif dist <= 4:
        grade = "B"
        score = max(score, 1)
    else:
        grade = "C"

    return {"grade": grade, "score": score, "flags": flags,
            "note": _note_three_buy(grade, flags, is_etf=is_etf)}


def _note_three_buy(grade, flags, is_etf=False):
    bad = [f["text"] for f in flags if f["type"] == "bad"]
    good = [f["text"] for f in flags if f["type"] == "good"]
    if grade == "A":
        if is_etf:
            return "干净回踩+转强, 接近下单级别: " + "、".join(good)
        return "贴上沿+缩量干净, 下单级别: " + ("、".join(good) if good else "距≤3.5%且缩≤0.45")
    if grade == "D":
        return bad[0] if bad else "晚期中枢剔除"
    if bad:
        return "结构命中但盘口减分: " + "、".join(bad) + " —— 观察不追"
    if grade == "B":
        return "候选, 距上沿尚可" if not is_etf else "候选, 位置尚可但未到下单级别"
    return "偏弱, 离上沿偏远" if not is_etf else "偏弱, 位置/量价一般"


def grade_squeeze(hit, bars):
    """策略六(压缩蓄势)评级。"""
    flags, score = [], 0
    bias = _f(hit.get("bias60"))
    runup = _f(hit.get("runup"))
    sc = int(hit.get("score", 0))

    exclude = False
    if bias >= SQZ_BIAS_KILL or runup >= SQZ_RUNUP_KILL:
        exclude = True
        flags.append({"text": f"垂直赶顶(距MA60+{bias:.0f}%/前涨+{runup:.0f}%)", "type": "bad"})
    else:
        if bias >= SQZ_BIAS_TOP:
            score -= 2
            flags.append({"text": f"乖离偏大(+{bias:.0f}%)", "type": "warn"})
        if runup >= SQZ_RUNUP_TOP:
            score -= 2
            flags.append({"text": f"前涨偏高(+{runup:.0f}%)", "type": "warn"})

    if sc >= 4:
        score += 1
        flags.append({"text": f"压缩{sc}分·够格", "type": "good"})
    else:
        flags.append({"text": f"压缩{sc}分·放宽入选", "type": "warn"})

    if _rejection(bars):
        score -= 1
        flags.append({"text": "今日冲高回落", "type": "warn"})

    grade = _decide(score, flags, exclude=exclude)
    if grade == "D":
        note = flags[0]["text"] if flags else "位置过热剔除"
    elif grade == "A":
        note = "标准压缩蓄势, 等放量启动"
    elif grade == "B":
        note = "蓄势候选, 未到启动"
    else:
        note = "位置偏后/放宽入选, 仅板块观察"
    return {"grade": grade, "score": score, "flags": flags, "note": note}


def grade_spring(hit, bars):
    """策略七(威科夫Spring+二买+底背驰)评级。核心看背驰强度, 兼顾离Spring距离/量价。"""
    flags, score = [], 0
    div = _f(hit.get("div_pct"))       # 背驰强度%(≥0.5过门槛)
    up = _f(hit.get("up_from_spring"))  # 离Spring低多远%
    amt = _f(hit.get("amt"))

    # 背驰强度: 越强越好(动能衰竭越明显, Spring 越有效)
    if div >= 1.0:
        score += 2
        flags.append({"text": f"强背驰({div:.1f}%)", "type": "good"})
    elif div >= 0.5:
        score += 1
        flags.append({"text": f"背驰达标({div:.1f}%)", "type": "good"})

    # 离Spring距离: 贴近Spring=低吸/风险小; 太远=已拉起追高
    if up <= 5:
        score += 1
        flags.append({"text": f"贴Spring({up:.0f}%)", "type": "good"})
    elif up >= 15:
        score -= 1
        flags.append({"text": f"离Spring远(+{up:.0f}%)", "type": "warn"})

    # 流动性
    if amt and amt < 1.5:
        score -= 1
        flags.append({"text": f"量能偏小({amt:.1f}亿)", "type": "warn"})

    # 今日冲高回落(红旗)
    if _rejection(bars):
        score -= 2
        flags.append({"text": "冲高回落", "type": "bad"})

    grade = _decide(score, flags)
    if grade == "A":
        note = "强背驰+贴Spring, 二买质量高"
    elif any(f["type"] == "bad" for f in flags):
        note = "命中但今日盘口减分, 观察确认"
    elif grade == "B":
        note = "Spring二买候选, 背驰达标"
    else:
        note = "偏弱: 背驰一般或离Spring较远"
    return {"grade": grade, "score": score, "flags": flags, "note": note}


def grade_oversold_volume_2buy(hit, bars):
    """策略7评级。

    回测显示原始结构评分呈反向收益分层：原C档胜率最高、原A档最低。
    因此保留结构flags解释原因，但最终A/C对调，让Dashboard的A表示实测更优先。
    """
    flags, score = [], 0
    rebound_vr = _f(hit.get("rebound_vr"))
    pull_ratio = _f(hit.get("pull_vol_ratio"))
    higher_low = _f(hit.get("higher_low"))
    risk = (_f(hit.get("close")) / _f(hit.get("stop")) - 1) * 100 if _f(hit.get("stop")) else 99
    if rebound_vr >= 2:
        score += 1
        flags.append({"text": f"反弹放量{rebound_vr:.1f}x", "type": "good"})
    if pull_ratio <= 0.5:
        score += 1
        flags.append({"text": f"回踩缩量{pull_ratio:.2f}", "type": "good"})
    if higher_low >= 3:
        score += 1
        flags.append({"text": f"L2抬高{higher_low:.1f}%", "type": "good"})
    if risk > 8:
        score -= 1
        flags.append({"text": f"止损偏远-{risk:.1f}%", "type": "warn"})
    if _rejection(bars):
        score -= 2
        flags.append({"text": "冲高回落", "type": "bad"})
    raw_grade = _decide(score, flags)
    grade = {"A": "C", "C": "A"}.get(raw_grade, raw_grade)
    return {"grade": grade, "score": score, "flags": flags,
            "note": "超跌放量反弹后缩量回踩，L2不破；涨6%后用五日线保护。ABC已按回测收益分层做A/C对调"}


def grade_nzi(hit, bars):
    """策略八(N字反包)评级: 反包力度(放量)+ 洗盘干净(缩量)+ 歇够久 + 止损距离/量能。"""
    flags, score = [], 0
    vexp = _f(hit.get("vexp"))       # 放量倍
    shrink = _f(hit.get("shrink"))    # 回调缩量比
    pull = int(hit.get("pull_days", 0))
    amt = _f(hit.get("amt"))
    close, stop = _f(hit.get("close")), _f(hit.get("stop"))

    if vexp >= 2.5:
        score += 1
        flags.append({"text": f"强反包({vexp:.1f}x量)", "type": "good"})
    if shrink and shrink <= 0.7:
        score += 1
        flags.append({"text": "洗盘干净", "type": "good"})
    if pull >= 6:
        score += 1
        flags.append({"text": f"歇足{pull}天", "type": "good"})

    # 止损距离(风控): 贴回踩低=盈亏比好; 太远=风险大
    risk = (close - stop) / close * 100 if close else 99
    if 0 < risk <= 4:
        score += 1
        flags.append({"text": f"止损近(-{risk:.0f}%)", "type": "good"})
    elif risk > 8:
        score -= 1
        flags.append({"text": f"止损偏远(-{risk:.0f}%)", "type": "warn"})

    if amt and amt < 1.5:
        score -= 1
        flags.append({"text": f"量能偏小({amt:.1f}亿)", "type": "warn"})

    grade = _decide(score, flags)
    if grade == "A":
        note = "缩量歇足+强放量反包, 中继质量高"
    elif grade == "B":
        note = "N字反包候选, 放量确认"
    else:
        note = "偏弱: 反包力度或止损距离一般"
    return {"grade": grade, "score": score, "flags": flags, "note": note}


def grade_vdb_pullback(hit, bars):
    """策略十一评级(宽松/严格共用规则)。

    宽松调优池(≥200亿·缩≤0.50+距≤6+ret20≥0+剔反转):
      dist≤4 → A(55.4%/+2.45%); shrink≤0.45 → B; 其余 C。
    严格入场已卡缩≤0.45，回测实质只剩 A/B(A57.7%/B50.0%，C=0)。
    """
    flags, score = [], 0
    dist = _f(hit.get("dist_vdb"))
    shrink = _f(hit.get("vol_shrink"))
    pull = int(hit.get("pull_days", 0))
    chain = int(hit.get("chain", 0))
    reversal = int(hit.get("reversal", 0))
    reclaim = int(hit.get("reclaim", 0))
    yang = int(hit.get("yang", 1 if _f(hit.get("chg")) > 0 else 0))
    ret20 = _f(hit.get("ret20"))
    amt = _f(hit.get("amt"))
    vdb_low = _f(hit.get("vdb_low"))
    buy_low = _f(hit.get("buy_low"))
    touch = bool(vdb_low and buy_low and buy_low <= vdb_low * 1.02)

    if not yang:
        flags.append({"text": "阴线入场", "type": "bad"})

    if reclaim:
        flags.append({"text": "收盘破昨高", "type": "good"})

    if not touch:
        score += 1
        flags.append({"text": "回踩未贴死", "type": "good"})
    else:
        flags.append({"text": "回踩贴死VDB低", "type": "warn"})

    if shrink and shrink <= 0.45:
        score += 2
        flags.append({"text": "缩量很干净", "type": "good"})
    elif shrink and shrink <= 0.50:
        score += 1
        flags.append({"text": "缩量干净", "type": "good"})
    elif shrink >= 0.70:
        score -= 1
        flags.append({"text": f"缩量不足({shrink:.2f})", "type": "warn"})

    if dist <= 4:
        score += 2
        flags.append({"text": f"距低近(+{dist:.0f}%)·胜率甜区", "type": "good"})
    elif dist <= 6:
        score += 1
        flags.append({"text": f"距低适中(+{dist:.0f}%)", "type": "good"})
    elif dist >= 12:
        score -= 2
        flags.append({"text": f"离VDB低远(+{dist:.0f}%)", "type": "warn"})

    if 3 <= pull <= 6:
        score += 1
        flags.append({"text": f"回踩{pull}天", "type": "good"})
    elif pull == 2:
        flags.append({"text": "回踩仅2天", "type": "warn"})

    if chain >= 1:
        score -= 2
        flags.append({"text": f"嵌套第{chain + 1}段", "type": "warn"})

    if reversal:
        score -= 1
        flags.append({"text": "深跌/低位背景偏弱", "type": "warn"})

    if ret20 >= 0:
        flags.append({"text": "近20日非弱", "type": "good"})
    if ret20 > 10:
        score += 1

    if amt >= 5:
        score += 1

    if _rejection(bars):
        score -= 2
        flags.append({"text": "冲高回落", "type": "bad"})

    has_bad = any(f["type"] == "bad" for f in flags)
    if has_bad:
        grade = "B" if score >= 1 else "C"
    elif dist <= 4:
        grade = "A"
        score = max(score, 3)
    elif shrink and shrink <= 0.45:
        grade = "B"
        score = max(score, 1)
    else:
        grade = "C"

    if grade == "A":
        note = "距VDB低近, 下单级别: " + "、".join(
            f["text"] for f in flags if f["type"] == "good"
        )
    elif has_bad:
        note = "命中但盘口减分 —— 观察不追"
    elif grade == "B":
        note = "VDB回踩候选, 缩量干净但距低一般"
    else:
        note = "偏弱: 距低偏远或缩量一般"
    return {"grade": grade, "score": score, "flags": flags, "note": note}


def grade_chan_final(hit, bars):
    """策略十(严格笔中枢·缠论三买)评级。

    个股: 在调优池(首中枢+lag≤2+risk≤12+上涨市)内按胜率标定 ABC:
      lag==2 → A; risk>4 → B; 其余 C。旧联合模型排期望不排胜率, 个股停用。
    ETF: 首中枢池内按是否站上 GG 分档(放宽入场后):
      回试不破GG → A(63.6%/+3.11%); 仅过ZG → 偏弱(43%/+1.24%); 第2中枢直接 D。
    """
    flags, score = [], 0
    stage = int(hit.get("stage", 1))
    risk = _f(hit.get("risk"))          # 现价距结构止损%
    lag = int(hit.get("lag", 0))
    amt = _f(hit.get("amt"))
    sub = hit.get("sub") or ""
    gg_gap = hit.get("gg_gap")
    if gg_gap is not None:
        try:
            gg_gap = float(gg_gap)
        except (TypeError, ValueError):
            gg_gap = None

    is_etf = bool(hit.get("is_etf"))
    if stage == 1:
        score += 2
        flags.append({"text": "首中枢", "type": "good"})
    elif stage >= 2 and is_etf:
        flags.append({"text": f"#{stage}中枢·ETF该档回测-2.4%", "type": "bad"})
        return {"grade": "D", "score": -99, "flags": flags,
                "note": f"第{stage}个中枢, ETF上该档实测负期望(胜率仅23%), 剔除"}
    elif stage == 2:
        flags.append({"text": "#2中枢·回测该档转负", "type": "warn"})
    elif stage >= 3:
        score -= 1
        flags.append({"text": f"#{stage}中枢·晚期(样本仅10笔)", "type": "warn"})

    if is_etf and gg_gap is not None:
        if gg_gap >= 0:
            score += 2
            flags.append({"text": "回试不破GG·胜率甜区", "type": "good"})
        else:
            score -= 1
            flags.append({"text": f"仅过ZG未过GG({gg_gap:+.1f}%)", "type": "warn"})

    if sub:
        score += 1
        flags.append({"text": f"30分共振({sub})", "type": "good"})

    if 0 < risk <= 4:
        flags.append({"text": f"止损近(-{risk:.1f}%)", "type": "warn" if not is_etf else "good"})
        if is_etf:
            score += 1
    elif 4 < risk <= 12:
        score += 1
        flags.append({"text": f"止损距适中(-{risk:.1f}%)", "type": "good"})
    elif risk > 12:
        score -= 1
        flags.append({"text": f"止损偏远(-{risk:.1f}%)", "type": "warn"})

    if lag == 2 and not is_etf:
        score += 2
        flags.append({"text": "回试后第2天·胜率甜区", "type": "good"})
    elif lag <= 1:
        if is_etf:
            score += 1
            flags.append({"text": "刚转强", "type": "good"})
        else:
            flags.append({"text": "刚转强·个股胜率不如第2天", "type": "warn"})
    elif lag >= 4:
        score -= 1
        flags.append({"text": f"回试后已{lag}天", "type": "warn"})

    if amt and amt < 1.5:
        score -= 1
        flags.append({"text": f"量能偏小({amt:.1f}亿)", "type": "warn"})

    if _rejection(bars):
        score -= 2
        flags.append({"text": "冲高回落", "type": "bad"})
    if _volume_stall(bars, lag + 2):
        score -= 2
        flags.append({"text": "放量滞涨·上方派发", "type": "bad"})

    has_bad = any(flag["type"] == "bad" for flag in flags)

    if is_etf:
        # 放宽入场后用 GG 分档, 不再只靠结构分(否则扩样本后分不出甜区)
        if has_bad:
            g = "B" if score >= 2 else "C"
        elif gg_gap is not None and gg_gap >= 0:
            g = "A"
        elif gg_gap is not None and gg_gap < 0:
            g = "B" if score >= 2 else "C"
        else:
            g = _decide(score, flags)
        note = (
            "回试不破GG, ETF下单级别"
            if g == "A"
            else ("仅过ZG未过GG —— 观察偏弱" if gg_gap is not None and gg_gap < 0
                  else ("命中但盘口减分 —— 观察不追" if has_bad
                        else "ETF候选, 结构尚可"))
        )
        return {"grade": g, "score": score, "flags": flags, "note": note}

    if has_bad:
        g = "B" if score >= 1 else "C"
    elif lag == 2:
        # 调优池内 lag=2: 62.1%胜/+2.42%
        g = "A"
    elif risk > 4:
        g = "B"
    else:
        # 止损过近在调优池内胜率偏低
        g = "C"

    if g == "A":
        note = "首中枢+回试第2天, 下单级别" if not is_etf else "首中枢+回试不破ZG+确认转强, 下单级别"
    elif has_bad:
        note = "结构命中但今日盘口减分, 观察不追"
    elif g == "B":
        note = "三买候选, 止损距适中" if not is_etf else "三买候选, 结构成立但位置/确认一般"
    else:
        note = "偏弱: 止损过近易洗或确认偏早" if not is_etf else "偏弱: 中枢序号靠后或止损偏远"
    return {"grade": g, "score": score, "flags": flags,
            "note": note + "。⚠️三买是慢信号(回测持有<5天为负, 10天后才转正), 别当天进出"}


def grade_csi2000_small_yang(hit, bars):
    """全A主板连小阳评级。

    回测(放量≥2x窗均量离场, 原中证2000样本): 整体约61%/+0.7%; 仅放量离场85.6%/+4.3%。
    连阳天数胜率差异不大, 按形态纯度分层方便盯盘优先看干净票。
    """
    flags, score = [], 0
    streak = int(hit.get("streak", 0) or 0)
    small_n = int(hit.get("small_n", 0) or 0)
    yang_n = int(hit.get("yang_n", 0) or 0)
    net = _f(hit.get("net"))
    avg_chg = _f(hit.get("avg_chg"))
    avg_body = _f(hit.get("avg_body"))
    max_chg = _f(hit.get("max_chg"))
    vol_ratio = _f(hit.get("vol_ratio"))
    amt = _f(hit.get("amt"))
    chg = _f(hit.get("chg"))

    if streak >= 8 and small_n >= 8:
        score += 3
        flags.append({"text": "8连纯小阳", "type": "good"})
    elif streak >= 8:
        score += 2
        flags.append({"text": f"8连阳·小阳{small_n}", "type": "good"})
    elif streak >= 7:
        score += 2
        flags.append({"text": f"{streak}连阳", "type": "good"})
    elif streak >= 6:
        score += 1
        flags.append({"text": f"{streak}连阳", "type": "good"})
    else:
        flags.append({"text": f"{streak}连阳", "type": "warn"})

    if small_n >= yang_n and yang_n >= 6:
        score += 1
        flags.append({"text": "窗口几乎全小阳", "type": "good"})
    elif small_n <= yang_n - 2:
        flags.append({"text": "夹杂偏大阳", "type": "warn"})

    if 5 <= net <= 12:
        score += 1
        flags.append({"text": f"窗涨温和(+{net:.0f}%)", "type": "good"})
    elif net > 18:
        score -= 1
        flags.append({"text": f"窗涨偏大(+{net:.0f}%)", "type": "warn"})

    if avg_body <= 1.5 and avg_chg <= 1.5:
        score += 1
        flags.append({"text": "爬升很慢", "type": "good"})

    if max_chg >= 5:
        score -= 1
        flags.append({"text": f"单日偏大(+{max_chg:.1f}%)", "type": "warn"})

    if vol_ratio >= 2.0:
        score -= 1
        flags.append({"text": f"今日已放量({vol_ratio:.1f}x)·或已到离场点", "type": "warn"})
    elif vol_ratio >= 1.5:
        flags.append({"text": f"量能抬头({vol_ratio:.1f}x)", "type": "warn"})
    else:
        flags.append({"text": "量仍安静·等放量跑", "type": "good"})

    if amt >= 1.5:
        score += 1
        flags.append({"text": "流动性尚可", "type": "good"})
    elif amt < 0.3:
        score -= 1
        flags.append({"text": "成交偏稀", "type": "warn"})

    if chg < 0:
        flags.append({"text": "今日收阴", "type": "warn"})

    if _rejection(bars):
        score -= 2
        flags.append({"text": "冲高回落", "type": "bad"})

    has_bad = any(f["type"] == "bad" for f in flags)
    if has_bad:
        g = "D"
    elif streak >= 8 and small_n >= 7 and score >= 4:
        g = "A"
    elif streak >= 7 or (streak >= 6 and small_n >= 6 and score >= 3):
        g = "B"
    else:
        g = "C"

    if g == "A":
        note = "连小阳很干净, 优先盯; 放量离场"
    elif g == "B":
        note = "连小阳成立, 候选; 破窗低止损, 放量跑"
    elif g == "D":
        note = "盘口减分, 仅观察"
    else:
        note = "形态偏弱或涨幅/阳线不够纯, 观察"
    return {"grade": g, "score": score, "flags": flags, "note": note}


def grade_bottom_vol_yang(hit, bars):
    """底部放量第一根大阳评级。信号已确认形态，评级看强度与盘口质量。"""
    flags, score = [], 0
    chg = _f(hit.get("chg"))
    vol_ratio = _f(hit.get("vol_ratio"))
    body = _f(hit.get("body"))
    ret20 = _f(hit.get("ret20"))
    pos60 = _f(hit.get("pos60"))
    bias60 = _f(hit.get("bias60"))
    amt = _f(hit.get("amt"))

    if vol_ratio >= 5:
        score += 3
        flags.append({"text": f"爆量{vol_ratio:.1f}x", "type": "good"})
    elif vol_ratio >= 3:
        score += 2
        flags.append({"text": f"放量{vol_ratio:.1f}x", "type": "good"})
    elif vol_ratio >= 2:
        score += 1
        flags.append({"text": f"放量{vol_ratio:.1f}x", "type": "good"})

    if chg >= 9.5:
        score += 2
        flags.append({"text": f"大阳+{chg:.1f}%", "type": "good"})
    elif chg >= 7:
        score += 1
        flags.append({"text": f"阳线+{chg:.1f}%", "type": "good"})

    if body >= 7:
        score += 1
        flags.append({"text": "实体厚实", "type": "good"})
    elif body < 5:
        flags.append({"text": "实体一般", "type": "warn"})

    if ret20 <= -15:
        score += 2
        flags.append({"text": f"深超跌({ret20:.0f}%)", "type": "good"})
    elif ret20 <= -5:
        score += 1
        flags.append({"text": f"偏弱底({ret20:.0f}%)", "type": "good"})
    elif ret20 > 0:
        flags.append({"text": f"前20日未跌({ret20:.0f}%)", "type": "warn"})

    if pos60 <= 20:
        score += 1
        flags.append({"text": "贴60日低区", "type": "good"})
    elif pos60 > 35:
        score -= 1
        flags.append({"text": "位置偏高", "type": "warn"})

    if bias60 <= -10:
        score += 1
        flags.append({"text": "远低于MA60", "type": "good"})

    if amt >= 1.0:
        score += 1
        flags.append({"text": "流动性尚可", "type": "good"})
    elif amt < 0.3:
        score -= 1
        flags.append({"text": "成交偏稀", "type": "warn"})

    if _rejection(bars):
        score -= 2
        flags.append({"text": "冲高回落", "type": "bad"})

    has_bad = any(f["type"] == "bad" for f in flags)
    if has_bad:
        g = "D"
    elif score >= 7 and vol_ratio >= 3 and ret20 <= -5:
        g = "A"
    elif score >= 4:
        g = "B"
    else:
        g = "C"

    if g == "A":
        note = "底部爆量大阳干净, 次日开盘可跟; 破止损走人"
    elif g == "B":
        note = "形态成立, 候选; 次日开盘买, 注意高开不追"
    elif g == "D":
        note = "盘口减分, 仅观察"
    else:
        note = "量/底/实体偏弱, 观察"
    return {"grade": g, "score": score, "flags": flags, "note": note}


def grade_limit_shrink_pull(hit, bars):
    """昨大涨今缩量回踩。尾盘买；破昨低/放量跌/红盘走。

    A 只给昨涨停且分项够干净（收紧后约 69% 胜）；B 昨≥7 或缩量干净；其余 C。
    """
    flags, score = [], 0
    prev_chg = _f(hit.get("prev_chg"))
    chg = _f(hit.get("chg"))
    shrink = _f(hit.get("vol_shrink"))
    amt = _f(hit.get("amt"))
    limit = int(hit.get("limit") or 0) or (prev_chg is not None and prev_chg >= 9.9)

    if limit:
        score += 3
        flags.append({"text": f"昨涨停({prev_chg:.1f}%)", "type": "good"})
    elif prev_chg is not None and prev_chg >= 7:
        score += 2
        flags.append({"text": f"昨大涨+{prev_chg:.1f}%", "type": "good"})
    elif prev_chg is not None:
        score += 1
        flags.append({"text": f"昨涨+{prev_chg:.1f}%", "type": "good"})

    if shrink is not None and shrink <= 0.50:
        score += 2
        flags.append({"text": f"缩量很干净({shrink:.2f}x)", "type": "good"})
    elif shrink is not None and shrink <= 0.70:
        score += 1
        flags.append({"text": f"缩量({shrink:.2f}x)", "type": "good"})
    elif shrink is not None:
        flags.append({"text": f"缩量偏弱({shrink:.2f}x)", "type": "warn"})

    if chg is not None and chg > -1.5:
        score += 1
        flags.append({"text": f"回踩浅({chg:+.1f}%)", "type": "good"})
    elif chg is not None and chg < -2.5:
        flags.append({"text": f"回踩偏深({chg:+.1f}%)", "type": "warn"})
    elif chg is not None:
        flags.append({"text": f"回踩{chg:+.1f}%", "type": "good"})

    if amt is not None and amt >= 1.0:
        score += 1
        flags.append({"text": "流动性尚可", "type": "good"})
    elif amt is not None and amt < 0.5:
        flags.append({"text": "成交偏稀", "type": "warn"})

    if _rejection(bars):
        score -= 1
        flags.append({"text": "冲高回落", "type": "warn"})

    # A: 昨涨停 + 分项够（浅回踩/缩干净/流动性，约 70% 胜）
    # B: 分够 4，或昨≥7 且缩量≤0.70
    # C: 昨刚过 6、缩量偏弱
    if limit and score >= 5:
        g = "A"
    elif score >= 4 or (prev_chg is not None and prev_chg >= 7 and shrink is not None and shrink <= 0.70):
        g = "B"
    else:
        g = "C"

    if g == "A":
        note = "昨涨停今缩量回踩干净, 尾盘可跟; 破昨低走人"
    elif g == "B":
        note = "形态成立, 尾盘候选; 放量跌/红盘离场, 缩量跌再格局"
    else:
        note = "昨涨刚过线或缩量一般, 观察"
    return {"grade": g, "score": score, "flags": flags, "note": note}


def grade(strategy, hit, bars):
    if strategy == "chan_final":
        return grade_chan_final(hit, bars)
    if strategy == "vdb_pullback":
        return grade_vdb_pullback(hit, bars)
    if strategy == "chan_wyckoff_3buy":
        return grade_three_buy(hit, bars)
    if strategy == "squeeze_launch":
        return grade_squeeze(hit, bars)
    if strategy == "oversold_volume_2buy":
        return grade_oversold_volume_2buy(hit, bars)
    if strategy == "strategy9_distilled":
        kind = hit.get("kind")
        if kind == "coil_launch":
            g = grade_squeeze(hit, bars)
        elif kind == "spring_2buy":
            g = grade_spring(hit, bars)
        elif kind == "chan_3buy":
            g = grade_three_buy(hit, bars)
        else:
            return {"grade": "C", "score": 0, "flags": [], "note": ""}
        g["note"] = f"{hit.get('setup', '策略9')}: {g['note']}"
        return g
    if strategy == "nzi_reversal":
        return grade_nzi(hit, bars)
    if strategy == "csi2000_small_yang":
        return grade_csi2000_small_yang(hit, bars)
    if strategy == "bottom_vol_yang":
        return grade_bottom_vol_yang(hit, bars)
    if strategy == "limit_shrink_pull":
        return grade_limit_shrink_pull(hit, bars)
    return {"grade": "C", "score": 0, "flags": [], "note": ""}
