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
    """策略五(缠论/威科夫三买)评级。"""
    flags, score = [], 0
    stage = int(hit.get("stage", 1))
    dist = _f(hit.get("dist"))
    pull = int(hit.get("pull_days", 0))
    shrink = _f(hit.get("vol_shrink"))

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
    if shrink and shrink <= SHRINK_CLEAN:
        score += 1
        flags.append({"text": "缩量干净", "type": "good"})
    elif shrink >= SHRINK_LOOSE:
        score -= 1

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

    grade = _decide(score, flags)
    return {"grade": grade, "score": score, "flags": flags,
            "note": _note_three_buy(grade, flags)}


def _note_three_buy(grade, flags):
    bad = [f["text"] for f in flags if f["type"] == "bad"]
    good = [f["text"] for f in flags if f["type"] == "good"]
    if grade == "A":
        return "干净回踩+转强, 接近下单级别: " + "、".join(good)
    if grade == "D":
        return bad[0] if bad else "晚期中枢剔除"
    if bad:
        return "结构命中但盘口减分: " + "、".join(bad) + " —— 观察不追"
    if grade == "B":
        return "候选, 位置尚可但未到下单级别"
    return "偏弱, 位置/量价一般"


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


def grade_chan_final(hit, bars):
    """策略十(严格笔中枢·缠论三买)评级。

    权重全部有本地一年全市场回测依据(见 strategy_chan_final/README 4.2):
      中枢序号  第1个 +1.03%/笔 vs 第2个 -0.08%  -> 首中枢 +2, #2 警告
      止损距离  结构止损=ZG, 越近盈亏比越好
      滞后 lag  回试低点后越早转强越干净(MAX_LAG=4)
      次级别共振 708 区间套, 理论最值钱但**未进回测**(30分数据仅40个交易日), 只给 +1
    """
    flags, score = [], 0
    stage = int(hit.get("stage", 1))
    risk = _f(hit.get("risk"))          # 现价距结构止损%
    lag = int(hit.get("lag", 0))
    amt = _f(hit.get("amt"))
    sub = hit.get("sub") or ""

    is_etf = bool(hit.get("is_etf"))
    if stage == 1:
        score += 2
        flags.append({"text": "首中枢", "type": "good"})
    elif stage >= 2 and is_etf:
        # ETF 上第2个中枢 -2.36%/23%胜、第3+样本薄, 明确亏钱 -> 直接剔除
        flags.append({"text": f"#{stage}中枢·ETF该档回测-2.4%", "type": "bad"})
        return {"grade": "D", "score": -99, "flags": flags,
                "note": f"第{stage}个中枢, ETF上该档实测负期望(胜率仅23%), 剔除"}
    elif stage == 2:
        flags.append({"text": "#2中枢·回测该档转负", "type": "warn"})
    elif stage >= 3:
        score -= 1
        flags.append({"text": f"#{stage}中枢·晚期(样本仅10笔)", "type": "warn"})

    if sub:
        score += 1
        flags.append({"text": f"30分共振({sub})", "type": "good"})

    if 0 < risk <= 4:
        score += 1
        flags.append({"text": f"止损近(-{risk:.1f}%)", "type": "good"})
    elif risk > 8:
        score -= 1
        flags.append({"text": f"止损偏远(-{risk:.1f}%)", "type": "warn"})

    if lag <= 1:
        score += 1
        flags.append({"text": "刚转强", "type": "good"})
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

    g = _decide(score, flags)
    market_ready = all(k in hit for k in (
        "marketRet5", "marketRet20", "marketRet60",
        "marketAbove20", "marketAbove60", "marketMa20Above60",
    ))
    has_bad = any(flag["type"] == "bad" for flag in flags)
    joint_grade = False
    if market_ready and not is_etf and g != "D" and not has_bad:
        # Fixed at 2025-12-31 on 4,396 prior trades. The 2026 rolling OOS
        # sample kept an A mean-return edge; these grades rank expected return,
        # not the probability of a positive trade.
        x = [
            1.0, float(stage == 1), float(stage == 2),
            float(0 < risk <= 4), float(risk > 8),
            float(lag <= 1), float(lag >= 4), float(bool(amt and amt < 1.5)),
            0.0, float(hit["marketRet5"]) * 10,
            float(hit["marketRet20"]) * 10, float(hit["marketRet60"]) * 5,
            float(bool(hit["marketAbove20"])),
            float(bool(hit["marketAbove60"])),
            float(bool(hit["marketMa20Above60"])),
            float(float(hit["marketRet20"]) >= 0),
        ]
        weights = [
            -0.01093438, 0.00013049, -0.00197477, 0.00592241,
            0.00246035, 0.00349858, -0.00259557, 0.00013726,
            0.00363853, -0.00747207, 0.00954102, 0.00277040,
            0.00385980, -0.00135056, -0.00141536, 0.00192086,
        ]
        expected = sum(a * b for a, b in zip(weights, x))
        g = "A" if expected >= 0.00166646 else "B" if expected >= -0.00444903 else "C"
        joint_grade = True
        score = round(expected * 10000)
        market_text = (
            "市场联合评分偏强" if g == "A" else
            "市场联合评分中性" if g == "B" else "市场联合评分偏弱"
        )
        flags.append({"text": market_text, "type": "good" if g == "A" else "warn"})
    if g == "A":
        note = "首中枢+回试不破ZG+确认转强, 下单级别"
    elif any(f["type"] == "bad" for f in flags):
        note = "结构命中但今日盘口减分, 观察不追"
    elif g == "B":
        note = "三买候选, 结构成立但位置/确认一般"
    elif joint_grade:
        note = "结构成立，但当前结构与市场组合的历史期望偏低"
    else:
        note = "偏弱: 中枢序号靠后或止损偏远"
    # 回测里 0-4 天持有 -1.51%、15-19 天 +7.70% —— 这是慢信号, 提醒别当日内做
    return {"grade": g, "score": score, "flags": flags,
            "note": note + "。⚠️三买是慢信号(回测持有<5天为负, 10天后才转正), 别当天进出"}


def grade(strategy, hit, bars):
    if strategy == "chan_final":
        return grade_chan_final(hit, bars)
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
    return {"grade": "C", "score": 0, "flags": [], "note": ""}
