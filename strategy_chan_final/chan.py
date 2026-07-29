#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""缠论几何引擎(纯标准库, 无 numpy/pandas)。

严格按《缠中说禅》原文定义逐层构建, 且**级别无关(自同构, 402)**——同一套函数
喂周K得周级别结构、喂日K得日级别结构、喂30分K得30分级别结构, 用法完全一致。

层次链条:
    K线 --包含处理(62课)--> 无包含K线 --顶/底分型(62课)--> 分型
        --新笔(81课)--> 笔 --连续三段重叠(204/504)--> 中枢(ZG/ZD/GG/DD)
        --依次同向且绝对不重叠(206/505)--> 趋势 / 盘整(205)
    MACD(802) --柱面积+黄白线(111/112)--> 背驰 --> 一/二/三类买卖点(106/107/703)

工程口径与取舍(与原文的差异, 已在 README 说明):
  1. 用"笔中枢"而非"线段中枢"。中枢定义要求"三个连续**次级别走势类型**重叠",
     本引擎把笔当作次级别走势单元, 这是业界通用近似; 真正的线段划分(特征序列
     两种情况, 67/81课)滞后且歧义多, 不适合机械回测。
  2. 级别用"周期图"近似"客观级别"(周/日/30分), 原文明确二者不等价(201/403),
     但工程上是唯一可自动化的口径。
"""

# ---------------------------------------------------------------- 1. 包含处理


def merge(H, L):
    """K线包含处理(62课)。

    相邻两根一根区间完全罩住另一根即为包含, 按当前方向合并:
    向上 高取高、低取高; 向下 低取低、高取低。严格遵守顺序原则——
    永远拿"已合并的新K线"去和下一根比, 不跳着比。

    返回 [{h, l, hi, li, i}]: hi/li 为该合并K线的高/低点所在的**原始bar索引**,
    i 为它覆盖的最后一根原始bar索引。
    """
    ms = []
    for i in range(len(H)):
        h, l = H[i], L[i]
        if not ms:
            ms.append({"h": h, "l": l, "hi": i, "li": i, "i": i})
            continue
        p = ms[-1]
        if (h >= p["h"] and l <= p["l"]) or (h <= p["h"] and l >= p["l"]):
            up = True if len(ms) < 2 else p["h"] > ms[-2]["h"]
            if up:  # 向上: 高取高, 低取高
                if h > p["h"]:
                    p["h"], p["hi"] = h, i
                if l > p["l"]:
                    p["l"], p["li"] = l, i
            else:   # 向下: 低取低, 高取低
                if h < p["h"]:
                    p["h"], p["hi"] = h, i
                if l < p["l"]:
                    p["l"], p["li"] = l, i
            p["i"] = i
        else:
            ms.append({"h": h, "l": l, "hi": i, "li": i, "i": i})
    return ms


# ---------------------------------------------------------------- 2. 分型


def fractals(ms):
    """顶/底分型(62课): 无包含图上, 相邻三根里中间那根高点最高(顶)或低点最低(底)。

    返回 [{d: +1顶/-1底, k: 合并序索引, i: 极值原始bar索引, p: 极值价}]。
    """
    out = []
    for k in range(1, len(ms) - 1):
        a, b, c = ms[k - 1], ms[k], ms[k + 1]
        if b["h"] > a["h"] and b["h"] > c["h"] and b["l"] > a["l"] and b["l"] > c["l"]:
            out.append({"d": 1, "k": k, "i": b["hi"], "p": b["h"]})
        elif b["l"] < a["l"] and b["l"] < c["l"] and b["h"] < a["h"] and b["h"] < c["h"]:
            out.append({"d": -1, "k": k, "i": b["li"], "p": b["l"]})
    return out


# ---------------------------------------------------------------- 3. 笔

MIN_GAP = 4  # 新笔(81课): 两分型极值K线之间至少夹3根 -> 合并序索引差 >= 4


def bis(fx):
    """新笔(81课)。条件1 两分型不共用K线(绝不放松); 条件2 极值K线之间≥3根。

    "顶上还有顶, 前一个顶作废"——同向分型出现更极端者时替换/顺延笔终点。
    返回 [{d, si, ei, sp, ep, hi, lo, sk, ek}] (si/ei 为原始bar索引)。
    """
    out = []
    cur = None
    for f in fx:
        if cur is None:
            cur = f
            continue
        if f["d"] == cur["d"]:
            better = (f["p"] > cur["p"]) if f["d"] == 1 else (f["p"] < cur["p"])
            if better:
                if out and out[-1]["ek"] == cur["k"]:
                    b = out[-1]
                    b["ei"], b["ep"], b["ek"] = f["i"], f["p"], f["k"]
                    b["hi"], b["lo"] = max(b["sp"], f["p"]), min(b["sp"], f["p"])
                cur = f
            continue
        if f["k"] - cur["k"] < MIN_GAP:
            continue
        if (cur["d"] == -1 and f["p"] <= cur["p"]) or (cur["d"] == 1 and f["p"] >= cur["p"]):
            continue  # 顶必须真高于底
        out.append({
            "d": 1 if cur["d"] == -1 else -1,
            "si": cur["i"], "ei": f["i"], "sp": cur["p"], "ep": f["p"],
            "hi": max(cur["p"], f["p"]), "lo": min(cur["p"], f["p"]),
            "sk": cur["k"], "ek": f["k"],
        })
        cur = f
    return out


# ---------------------------------------------------------------- 4. 中枢


MAX_EXT = 9  # 中枢延伸段数上限: 超过9段按惯例视为已扩展升级, 就地断开重扫(602)


def pivots(bs):
    """走势中枢(204) + 四个值(504)。

    连续三段(笔)重叠即成中枢: ZG=min(g1,g2) 上沿, ZD=max(d1,d2) 下沿(**只用前两段**),
    GG=max(gn), DD=min(dn)(**用全部段**)。后续段与核心区[ZD,ZG]有重叠 -> 延伸(段数增多,
    ZG/ZD 不变); 某段完全脱离核心区 -> 中枢结束, 该段即"离开段"。

    延伸超过 MAX_EXT 段时就地断开: 此时下一个中枢会与本中枢重叠, trend() 自然判成
    "非趋势", 正对应 602"两个同级别中枢波动区间重叠 = 更大级别中枢诞生"。

    **离开段的识别(503, 关键)**: 向上突破的那一笔是**从中枢内部起步**的, 它必然与核心区
    有重叠, 所以不能靠"这一笔脱离核心区"来找离开段——那样找到的其实是回试笔。正确做法是
    503 的原文: "一个次级别走势离开中枢, 其后的次级别**回抽走势不重新回到中枢内**"。
    因此: 第一根**完全脱离核心区**的笔 bs[k] 就是那个"回抽不回"的回试笔, 它前面那根
    bs[k-1] 才是离开段, 中枢本体到 bs[k-2] 为止。三买/三卖就落在 bs[k] 的端点上。

    返回 [{s, e: 中枢本体笔索引区间, leave: 离开段笔索引(None=没走完),
           zg, zd, gg, dd, si, ei, n}]。
    """
    out = []
    i, n = 0, len(bs)
    while i + 2 < n:
        zg = min(bs[i]["hi"], bs[i + 1]["hi"])
        zd = max(bs[i]["lo"], bs[i + 1]["lo"])

        def ov(k):
            return bs[k]["lo"] <= zg and bs[k]["hi"] >= zd

        if zd >= zg or not ov(i + 2):
            i += 1
            continue
        k = i + 3
        while k < n and ov(k) and (k - i) < MAX_EXT:
            k += 1
        if k < n and not ov(k) and k - 1 >= i + 3:
            end, leave = k - 2, k - 1      # bs[k]=回试(不回中枢), bs[k-1]=离开段
        else:
            end, leave = min(k - 1, n - 1), None   # 还没走完 / 延伸封顶
        end = max(end, i + 2)
        out.append({
            "s": i, "e": end, "leave": leave, "zg": zg, "zd": zd,
            "gg": max(bs[x]["hi"] for x in range(i, end + 1)),
            "dd": min(bs[x]["lo"] for x in range(i, end + 1)),
            "si": bs[i]["si"], "ei": bs[end]["ei"], "n": end - i + 1,
        })
        # 定理501: 连接两个同级别中枢的是次级别以下的走势(即离开段), 它不属于任何中枢;
        # 回试笔 bs[leave+1] 则可以是下一个中枢的第一段。
        i = (leave + 1) if leave is not None else (end + 2)
    return out


def trend(ps):
    """走势类型(206/505)。从最后一个中枢往回数"依次同向且绝对不重叠"的中枢链。

    判据(505): 后DD > 前GG <=> 上涨延续; 后GG < 前DD <=> 下跌延续; 有重叠则
    不是趋势(会升级成更大级别中枢, 602)。返回 (方向 +1/-1/0, 链上中枢个数)。
    ≥2 个 = 趋势(可谈趋势背驰); 1 个 = 盘整(只能谈盘整背驰)。
    """
    if not ps:
        return 0, 0
    d, cnt = 0, 1
    for k in range(len(ps) - 1, 0, -1):
        a, b = ps[k - 1], ps[k]
        if b["dd"] > a["gg"]:
            cur = 1
        elif b["gg"] < a["dd"]:
            cur = -1
        else:
            break
        if d == 0:
            d, cnt = cur, 2
        elif cur == d:
            cnt += 1
        else:
            break
    return d, cnt


def pivot_stage(ps, idx):
    """中枢序号: ps[idx] 是当前同向趋势链里的第几个中枢(1=底部第一个, 最稳)。"""
    stage = 1
    d = 0
    for k in range(idx, 0, -1):
        a, b = ps[k - 1], ps[k]
        if b["dd"] > a["gg"]:
            cur = 1
        elif b["gg"] < a["dd"]:
            cur = -1
        else:
            break
        if d == 0:
            d = cur
        elif cur != d:
            break
        stage += 1
    return stage


# ---------------------------------------------------------------- 5. MACD


def ema(xs, n):
    k = 2.0 / (n + 1)
    out, prev = [], xs[0]
    for x in xs:
        prev = x * k + prev * (1 - k)
        out.append(prev)
    return out


def macd(C, fast=12, slow=26, sig=9):
    """返回 (dif, dea, hist)。hist = 2*(DIF-DEA), 国内软件口径。"""
    ef, es = ema(C, fast), ema(C, slow)
    dif = [a - b for a, b in zip(ef, es)]
    dea = ema(dif, sig)
    return dif, dea, [2 * (a - b) for a, b in zip(dif, dea)]


# ---------------------------------------------------------------- 6. 背驰


def area(hist, a, b, d):
    """[a,b] 内与方向 d 同号的柱子面积(111 均线面积的工程替代)。比"一片"不比"一根"。"""
    s = 0.0
    for j in range(max(0, a), min(len(hist) - 1, b) + 1):
        v = hist[j]
        if (d > 0 and v > 0) or (d < 0 and v < 0):
            s += abs(v)
    return s


def diverge(H, L, dif, hist, a, c, d, max_area=0.85, max_dif=0.95):
    """背驰判定(111/112 + 802)。

    a=(a0,a1) A段(进入最后中枢的同向推动段), c=(c0,c1) C段(离开最后中枢的段),
    d=+1 比顶背驰 / -1 比底背驰。四个条件缺一不可:
      ① 价格更极端(C段创新高/新低)
      ② 柱面积 C < A * max_area          (低头看红绿柱, 精确打击)
      ③ 黄白线 C 不创新极值, 且幅度 < A * max_dif  (抬头看黄白线, 定背驰段)
      ④ 802: 底背驰要求 DIF 在 0 轴下, 顶背驰要求在 0 轴上
    返回 None(不成立) 或 {ar, dr, pa, pc, ...}。
    """
    a0, a1 = a
    c0, c1 = c
    if a1 <= a0 or c1 <= c0 or c0 < a1:
        return None
    pa, pc = area(hist, a0, a1, d), area(hist, c0, c1, d)
    if pa <= 0 or pc <= 0:
        return None
    if d < 0:
        if min(L[c0:c1 + 1]) >= min(L[a0:a1 + 1]):
            return None
        da, dc = min(dif[a0:a1 + 1]), min(dif[c0:c1 + 1])
        if dc >= 0 or da >= 0 or dc <= da:
            return None
        dr = dc / da
    else:
        if max(H[c0:c1 + 1]) <= max(H[a0:a1 + 1]):
            return None
        da, dc = max(dif[a0:a1 + 1]), max(dif[c0:c1 + 1])
        if dc <= 0 or da <= 0 or dc >= da:
            return None
        dr = dc / da
    ar = pc / pa
    if ar > max_area or dr > max_dif:
        return None
    return {"ar": ar, "dr": dr, "pa": pa, "pc": pc, "da": da, "dc": dc}


# ---------------------------------------------------------------- 7. 结构快照


def build(rows, n=None):
    """把一段K线(项目通用格式 [日期,开,收,高,低,量,额])转成缠论结构快照。

    n 给定时只取前 n 根(as-of 切片, 防未来函数)。
    """
    r = rows if n is None else rows[:n]
    if len(r) < 30:
        return None
    D = [x[0] for x in r]
    O = [float(x[1]) for x in r]
    C = [float(x[2]) for x in r]
    H = [float(x[3]) for x in r]
    L = [float(x[4]) for x in r]
    V = [float(x[5]) for x in r]
    A = [float(x[6]) for x in r]
    ms = merge(H, L)
    fx = fractals(ms)
    bs = bis(fx)
    ps = pivots(bs)
    dif, dea, hist = macd(C)
    td, tn = trend(ps)
    return {
        "D": D, "O": O, "C": C, "H": H, "L": L, "V": V, "A": A,
        "ms": ms, "fx": fx, "bs": bs, "ps": ps,
        "dif": dif, "dea": dea, "hist": hist,
        "td": td, "tn": tn, "i": len(r) - 1,
    }
