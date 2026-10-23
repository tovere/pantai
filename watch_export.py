#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""盯盘数据编排: 跑策略变体 -> 挂评级 -> 附K线/止损位 -> watch_data.json。

支持单策略独立跑(带进度回调)与历史快照, 供 watch_server.py 的异步任务调用。
    python3 watch_export.py                 # 全部变体, 用现有缓存
    REFRESH=1 python3 watch_export.py       # 先刷全市场再跑
每个变体以子进程运行(env 常量隔离), 经 WATCH_JSON_OUT 落 JSON 回收。
"""
import json
import os
import random
import re
import subprocess
import tempfile
import time
from collections import Counter
from datetime import datetime, timedelta

import cache_data
import watch_grade

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_PATH = os.path.join(HERE, "watch_data.json")
HIST_DIR = os.path.join(HERE, "data_cache", "watch_history")
OVERNIGHT_PATH = os.path.join(HERE, "data_cache", "watch_overnight.json")
INDUSTRY_PATH = os.path.join(HERE, "data_cache", "stock_industry.json")
HIT_SNAPSHOT_KEYS = (
    "code", "name", "grade", "close", "chg", "gradeNote",
    "dist", "stage", "pull_days", "runup", "amt", "flags",
    "prev_chg", "vol_shrink", "stop", "is_etf",
)


def now_bj():
    """北京时间(UTC+8), 不依赖本机时区(服务器可能在美西)。"""
    return datetime.utcnow() + timedelta(hours=8)

# key -> (脚本, 标题, 额外env)
VARIANTS = {
    "s5_stock_loose":  ("screen_chan_wyckoff_3buy.py", "策略五·个股·宽松候选",
                        {"STRICT_BUY": "0", "S5_STAGE1_ONLY": "1", "S5_MAX_DIST": "5",
                         "S5_MAX_SHRINK": "0.50", "S5_MAX_RISK": "4", "S5_MIN_PULL": "2",
                         "S5_REQUIRE_UP": "1"}),
    # 个股严格调优: 贴上沿+缩量+止损近+上涨市 (本地一年1161→421, 49.6%/+1.37%)
    "s5_stock_strict": ("screen_chan_wyckoff_3buy.py", "策略五·个股·严格(下单级别)",
                        {"STRICT_BUY": "1", "S5_MAX_DIST": "6", "S5_MAX_SHRINK": "0.60",
                         "S5_MAX_RISK": "5", "S5_REQUIRE_UP": "1"}),
    "s5_etf_loose":    ("screen_chan_wyckoff_3buy.py", "策略五·ETF·宽松", {"ETF_ONLY": "1", "STRICT_BUY": "0"}),
    "s5_etf_strict":   ("screen_chan_wyckoff_3buy.py", "策略五·ETF·严格(狙击)", {"ETF_ONLY": "1", "STRICT_BUY": "1"}),
    "s6_stock":        ("screen_squeeze_launch.py",    "策略六·个股·压缩蓄势", {}),
    "s6_etf":          ("screen_squeeze_launch.py",    "策略六·ETF·压缩蓄势", {"ETF_ONLY": "1"}),
    "s7_stock":        ("screen_oversold_volume_2buy.py", "策略七·超跌放量回踩二买", {}),
    "s8_stock":        ("screen_nzi_reversal.py",      "策略八·个股·N字反包", {}),
    "s9_stock":        ("screen_strategy9_distilled.py", "策略九·防守版(压缩+Spring)", {}),
    # 策略十用回测选出的最优参数: 只做三买(一买负期望/二买弱)、周线MA口径向上、
    # 开次级别30分共振(区间套708)。出场对应顶分型卖, 见 strategy_chan_final/README。
    "s10_stock":       ("strategy_chan_final/screen.py", "策略十·个股·缠论三买(严格笔中枢)",
                        {"ENABLE_TYPES": "3", "WEEKLY_MODE": "ma", "SUB_LEVEL": "1",
                         "S10_STAGE1_ONLY": "1", "S10_MAX_LAG": "2", "S10_MAX_RISK": "12",
                         "S10_REQUIRE_UP": "1"}),
    # ETF: 首中枢保留; 放开 GG/30分以扩样本(304笔·58.2%/+2.63%)。
    # 不破 GG 的仍由评级标 A(原225笔·63.6%/+3.11%); 破 GG 仅过 ZG 的降档。
    "s10_etf":         ("strategy_chan_final/screen.py", "策略十·ETF·缠论三买(移动止损)",
                        {"ETF_ONLY": "1", "ENABLE_TYPES": "3", "WEEKLY_MODE": "ma",
                         "SUB_LEVEL": "0", "PULLBACK_GG": "0", "S10_STAGE1_ONLY": "1"}),
    "s11_vdb_strict":  ("screen_vdb_pullback.py",       "策略十一·VDB后缩量回踩·严格",
                        {"STRICT_BUY": "1", "MIN_MKTCAP": "10000000000",
                         "VDB_STRICT_SHRINK": "0.45", "VDB_STRICT_DIST": "6",
                         "VDB_STRICT_PULL_MIN": "2", "VDB_STRICT_PULL_MAX": "4",
                         "VDB_MIN_RET20": "0", "VDB_EXCLUDE_REV": "1"}),
    "s11_vdb":         ("screen_vdb_pullback.py",       "策略十一·VDB后缩量回踩·宽松",
                        {"STRICT_BUY": "0", "MIN_MKTCAP": "20000000000",
                         "VDB_SHRINK": "0.50", "VDB_LOOSE_DIST": "6",
                         "VDB_MIN_RET20": "0", "VDB_EXCLUDE_REV": "1"}),
    "s12_small_yang":  ("screen_csi2000_small_yang.py", "策略十二·全A主板连小阳(全量)",
                        {"YANG_TIER": "0"}),
    "s12_small_yang_t2": ("screen_csi2000_small_yang.py", "策略十二·连小阳·2档(未涨透)",
                        {"YANG_TIER": "2"}),
    "s12_small_yang_t3": ("screen_csi2000_small_yang.py", "策略十二·连小阳·3档(温和未透)",
                        {"YANG_TIER": "3"}),
    "s14_bottom_vol_yang": ("screen_bottom_vol_yang.py", "策略十四·底部放量第一根大阳", {}),
    "s15_limit_shrink_pull": ("screen_s15_limit_shrink_pull.py", "策略十五·昨大涨今缩量回踩", {}),
}
# 暂停展示/运行但保留配置与回测代码，移出集合即可恢复。
DISABLED_VARIANTS = {"s6_stock", "s6_etf", "s8_stock", "s9_stock"}
# 侧栏按策略号分组: 同号内 ETF→个股、严格→宽松。优先级见 readme，不在此打乱。
VKEYS_ORDER = [
    "s5_etf_strict",
    "s5_etf_loose",
    "s5_stock_strict",
    "s5_stock_loose",
    "s7_stock",
    "s10_etf",
    "s10_stock",
    "s11_vdb_strict",
    "s11_vdb",
    "s12_small_yang",
    "s12_small_yang_t2",
    "s12_small_yang_t3",
    "s14_bottom_vol_yang",
    "s15_limit_shrink_pull",
]
VKEYS = [k for k in VKEYS_ORDER if k in VARIANTS and k not in DISABLED_VARIANTS]
# 兜底: 未列入 ORDER 的启用变体仍挂在末尾
VKEYS += [k for k in VARIANTS if k not in DISABLED_VARIANTS and k not in VKEYS]

# 盯盘注解统一格式:
#   BACKTEST:   {标签} · {N}笔 · {胜}%胜 · {均}%/笔 · {条件}
#   GRADE:      A {胜}%[(n)]/{均}% · B … · C …[ · 备注]
#   CONCLUSION: {怎么用}。{注意}
BACKTEST_NOTE = {
    "s5_stock_loose":  "调优 · 959笔 · 49.4%胜 · +1.51%/笔 · 首中枢+距≤5+缩≤0.50+risk≤4+pull≥2+上涨市",
    "s5_stock_strict": "调优 · 421笔 · 49.6%胜 · +1.37%/笔 · 距≤6+缩≤0.60+risk≤5+上涨市",
    "s5_etf_loose":    "全量 · 2935笔 · 48.7%胜 · +0.88%/笔 · 日线移动止损",
    "s5_etf_strict":   "全量 · 471笔 · 48.8%胜 · +0.75%/笔 · 日线移动止损+严格三买",
    "s6_stock":        "暂停 · 4346笔 · 39.4%胜 · -0.16%/笔 · 压缩蓄势",
    "s6_etf":          "暂停 · 样本不足 · 未分层验证 · ETF压缩蓄势",
    "s7_stock":        "全量 · 3813笔 · 53.3%胜 · +1.00%/笔 · L2止损+涨6%后MA5保护",
    "s8_stock":        "暂停 · 1080笔 · 38.3%胜 · +0.11%/笔 · N字反包",
    "s9_stock":        "暂停 · 7591笔 · 37.6%胜 · -0.14%/笔 · 防守蒸馏",
    "s10_stock":       "调优 · 461笔 · 52.9%胜 · +2.11%/笔 · 首中枢+lag≤2+risk≤12+上涨市",
    "s10_etf":         "调优 · 304笔 · 58.2%胜 · +2.63%/笔 · 首中枢+移动止损(放宽GG/关30分)",
    "s11_vdb":         "调优 · 703笔 · 54.1%胜 · +2.23%/笔 · ≥200亿+缩≤0.50+距≤6+ret20≥0+剔反转",
    "s11_vdb_strict":  "调优 · 263笔 · 55.1%胜 · +1.45%/笔 · ≥100亿+缩≤0.45+距≤6+pull2-4+剔反转",
    "s12_small_yang":  "全量 · 2296笔 · 61.3%胜 · +0.72%/笔 · 次日开盘买+放量≥2x窗均量跑+破窗低止损",
    "s12_small_yang_t2": "调优 · 264笔 · 71.6%胜 · +1.87%/笔 · 窗涨≤8%+近20日跌+额0.3-1.2亿",
    "s12_small_yang_t3": "调优 · 490笔 · 70.6%胜 · +1.49%/笔 · 窗涨≤8%+近20日<5%+额0.3-1.0亿",
    "s14_bottom_vol_yang": "新策略 · 次日开盘买 · 大阳≥7%+量≥2x+底部第一根；待全量回测标定",
    "s15_limit_shrink_pull": "调优 · 4108笔 · 56.4%胜 · -0.03%/笔 · 昨≥6+跌≥-3+缩≤0.80+额≥0.4；尾盘买",
}

GRADE_BACKTEST_NOTE = {
    "s5_stock_loose":  "A 52.2%/+1.97% · B 46.9%/+1.20% · C 45.7%/+0.51% · 胜率A>B>C",
    "s5_stock_strict": "A 58.0%/+2.10% · B 49.7%/+1.76% · C 45.4%/+0.64% · 胜率A>B>C",
    "s5_etf_loose":    "A 52.9%(877)/+1.38% · B 45.9%(1297)/+0.66% · C 48.0%(715)/+0.65% · 均值A>B≈C",
    "s5_etf_strict":   "A 45.9%(242)/+0.87% · B 48.9%(180)/+0.70% · C 63.3%(49)/+0.29% · 胜率不排序",
    "s6_stock":        "A 无 · B 40.6%(2522)/-0.10% · C 38.1%(1380)/-0.18% · D 36.0%(444)/-0.47%",
    "s6_etf":          "ABC未完成多年分层验证",
    "s7_stock":        "A 58.2%(1044)/+1.61% · B 52.4%(2469)/+0.88% · C 43.7%(300)/-0.06% · 胜率A>B>C",
    "s8_stock":        "A 38.1%(21)/+1.15% · B 39.3%(516)/+0.28% · C 37.4%(543)/-0.10% · A样本极薄",
    "s9_stock":        "A 33.9%(3456)/-0.11% · B 40.7%(3129)/-0.15% · C 40.6%(1006)/-0.23% · 胜率反序",
    "s10_stock":       "A 55.0%/+2.90% · B 54.1%/+1.83% · C 43.3%/+1.66% · D 36.2%(130)/-1.66% · 胜率A>B>C>D",
    "s10_etf":         "A 不破GG 63.6%(225)/+3.11% · B/C 仅过ZG 43.0%(79)/+1.24% · 第2中枢直接D",
    "s11_vdb":         "A 55.4%/+2.45% · B 53.2%/+1.94% · C 50.7%/+1.83% · 胜率A>B>C",
    "s11_vdb_strict":  "A 57.7%(175)/+1.49% · B 50.0%(88)/+1.37% · C 0 · 入场已缩≤0.45，实质只分A/B",
    "s12_small_yang":  "放量离场 85.6%(1335)/+4.29% · 整体61.3% · 连阳天数差异不大，A看形态纯度",
    "s12_small_yang_t2": "未涨透过滤后整体71.6%/+1.87%；资金少优先本档",
    "s12_small_yang_t3": "条件略宽于2档，整体70.6%/+1.49%；票比2档多",
    "s14_bottom_vol_yang": "评级按量比/底部深度/实体质量分层，待回测标定ABC",
    "s15_limit_shrink_pull": "A 69.1%(162)/+0.48% · B 56.8%(2338)/+0.04% · C 54.4%(1608)/-0.19% · 胜率A>B>C",
}

CONCLUSION_NOTE = {
    "s5_stock_loose":  "结构宽于严格，同思路过滤；优先A。非上涨市标D仅观察。",
    "s5_stock_strict": "个股下单主看本档；优先A。非上涨市标D仅观察。",
    "s5_etf_loose":    "ETF主线；优先A，按结构止损，同板块勿叠仓。",
    "s5_etf_strict":   "ETF加分项；信号少，上涨环境更好，勿单独重仓。",
    "s6_stock":        "三种市场均无优势，入口已暂停。",
    "s6_etf":          "样本不足未验证，入口已暂停。",
    "s7_stock":        "优先A；胜率高但2023/2026偏弱，结合市场环境。",
    "s8_stock":        "期望接近随机，入口已暂停。",
    "s9_stock":        "三种市场均为负，入口已暂停。",
    "s10_stock":       "缠论严格笔中枢补充；优先A。非上涨市标D(回测36.2%/-1.66%)仅观察。",
    "s10_etf":         "优先A(回试不破GG)；仅过ZG的降档观察。移动止损出场，同板块去重。",
    "s11_vdb":         "补箱体盲区；优先A(距≤4%)，勿深跌硬抄。",
    "s11_vdb_strict":  "优先A(距≤4%)；入场已很干净，C被滤光。勿嵌套二段追。",
    "s12_small_yang":  "全A主板连小阳全量池(剔创业/科创)；票多仅观察。实盘看2/3档。",
    "s12_small_yang_t2": "优先档：未涨透。放量≥2x跑，破窗低止损；票少适合小资金。",
    "s12_small_yang_t3": "次优先：条件略宽。同样放量跑/破窗低止损。",
    "s14_bottom_vol_yang": "收盘确认后次日开盘买；破信号低/底盘低止损，峰值回撤8%或超时离场。创业板默认可扫。",
    "s15_limit_shrink_pull": "尾盘买。破昨低立刻走；次日放量跌或红盘离场；缩量跌再格局。优先A（昨涨停），B可做，C期望为负仅观察。不上涨背景过滤（MA60/周线会降胜率）。不进今早可买。",
}



def _secid(code, is_etf):
    if is_etf:
        return ("1." if code.startswith("5") else "0.") + code
    return ("1." if code.startswith("6") else "0.") + code


_INDUSTRY_CACHE = None


def _industry_map():
    global _INDUSTRY_CACHE
    if _INDUSTRY_CACHE is not None:
        return _INDUSTRY_CACHE
    try:
        with open(INDUSTRY_PATH, encoding="utf-8") as file:
            payload = json.load(file)
        _INDUSTRY_CACHE = payload.get("items", payload) if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        _INDUSTRY_CACHE = {}
    return _INDUSTRY_CACHE


def _industry_for(code, is_etf):
    if is_etf:
        return "ETF"
    item = _industry_map().get(code)
    if isinstance(item, dict):
        return item.get("industry") or item.get("sector") or ""
    return item or ""


def _bars_for(secid, n=None):
    rows = cache_data.daily_kline(secid)
    if not rows:
        return []
    out = []
    selected = rows if n is None else rows[-n:]
    for r in selected:
        try:
            out.append([r[0], float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])])
        except (ValueError, IndexError):
            continue
    return out


def _market_context():
    """Return the benchmark inputs used by the strategy-10 OOS grade model."""
    bars = _bars_for("1.510300", 80)
    closes = [bar[2] for bar in bars]
    if len(closes) < 61 or not closes[-21] or not closes[-61]:
        return {}
    ma20 = sum(closes[-20:]) / 20
    ma60 = sum(closes[-60:]) / 60
    return {
        "marketRet5": closes[-1] / closes[-6] - 1,
        "marketRet20": closes[-1] / closes[-21] - 1,
        "marketRet60": closes[-1] / closes[-61] - 1,
        "marketAbove20": closes[-1] >= ma20,
        "marketAbove60": closes[-1] >= ma60,
        "marketMa20Above60": ma20 >= ma60,
    }


def _levels(strategy, hit):
    if strategy == "chan_wyckoff_3buy":
        box = hit.get("box", "")
        up = None
        if "-" in box:
            try:
                up = float(box.split("-")[1])
            except ValueError:
                up = None
        return {"中枢上沿": up, "三买低(止损)": hit.get("buy_low")}
    if strategy == "squeeze_launch":
        coil = hit.get("coil", "")
        lo = hi = None
        if "-" in coil:
            try:
                lo, hi = (float(x) for x in coil.split("-"))
            except ValueError:
                lo = hi = None
        return {"蓄势上沿": hi, "蓄势下沿": lo, "止损": hit.get("stop")}
    if strategy == "oversold_volume_2buy":
        return {"前低L1": hit.get("l1"), "回踩低L2": hit.get("l2"),
                "止损(L2下1%)": hit.get("stop")}
    if strategy == "strategy9_distilled":
        if hit.get("kind") == "spring_2buy":
            return {"区间下沿": hit.get("range_low"), "Spring低": hit.get("spring_low"),
                    "止损": hit.get("stop")}
        if hit.get("kind") == "coil_launch":
            coil = hit.get("coil", "")
            lo = hi = None
            if "-" in coil:
                try:
                    lo, hi = (float(x) for x in coil.split("-"))
                except ValueError:
                    lo = hi = None
            return {"蓄势上沿": hi, "蓄势下沿": lo, "止损": hit.get("stop")}
        return {"止损": hit.get("stop")}
    if strategy == "nzi_reversal":
        return {"前高": hit.get("peak"), "回踩低": hit.get("pull_low"),
                "止损": hit.get("stop")}
    if strategy == "chan_final":
        return {"中枢上沿ZG": hit.get("zg"), "中枢下沿ZD": hit.get("zd"),
                "三买低": hit.get("buy_low"), "止损": hit.get("stop")}
    if strategy == "vdb_pullback":
        return {"VDB低(止损)": hit.get("stop"), "VDB高": hit.get("vdb_high"),
                "回踩低": hit.get("buy_low")}
    if strategy == "csi2000_small_yang":
        return {"窗低": hit.get("win_low"), "止损": hit.get("stop")}
    if strategy == "bottom_vol_yang":
        return {"底盘低": hit.get("base_low"), "信号低": hit.get("sig_low"),
                "止损": hit.get("stop")}
    if strategy == "limit_shrink_pull":
        return {"昨收": hit.get("prev_close"), "昨低(止损)": hit.get("prev_low"),
                "止损": hit.get("stop")}
    return {}


def _ensure_screen_date():
    # 始终对齐到缓存最新交易日。长驻 server 进程里 SCREEN_DATE 会残留旧值(如昨天),
    # 缓存进入新一天后若不更新, 筛选器的 D[i]!=TODAY 会把全部票挡掉 -> 全0。
    ref = cache_data.daily_kline("0.000001")
    if ref:
        os.environ["SCREEN_DATE"] = ref[-1][0]


def enrich_section(key, raw):
    """把子进程回收的原始 hits 挂上评级/K线/止损位, 组成一个 section。"""
    script, title, env_extra = VARIANTS[key]
    strategy = raw.get("strategy", "")
    is_etf = raw.get("is_etf", False)
    latest = ""
    hits = []
    require_up = (
        not is_etf and (
            env_extra.get("S10_REQUIRE_UP", "0") != "0"
            or env_extra.get("S5_REQUIRE_UP", "0") != "0"
        )
    )
    market = _market_context() if require_up or (strategy == "chan_final" and not is_etf) else {}
    for hit in raw.get("hits", []):
        down_mkt = False
        if require_up:
            if not market:
                down_mkt = True
            elif not (market.get("marketAbove20") and market.get("marketAbove60")
                      and float(market.get("marketRet20") or 0) >= 0):
                down_mkt = True
        secid = _secid(hit["code"], is_etf)
        bars = _bars_for(secid)
        if bars:
            latest = max(latest, bars[-1][0])
        hit["is_etf"] = is_etf
        if market:
            hit.update(market)
        g = watch_grade.grade(strategy, hit, bars)
        if down_mkt:
            g = {
                "grade": "D",
                "score": g.get("score", 0),
                "flags": (g.get("flags") or []) + [
                    {"text": "非上涨市·调优口径不出手", "type": "bad"},
                ],
                "note": "结构命中但当前非上涨市，按调优口径仅观察、不下手",
            }
        hit.update({
            "secid": secid,
            "industry": _industry_for(hit["code"], is_etf),
            "grade": g["grade"],
            "gradeScore": g["score"],
            "gradeNote": g["note"],
            "flags": g["flags"],
            "levels": _levels(strategy, hit),
            "bars": bars,
        })
        hits.append(hit)
    rank = {"A": 0, "B": 1, "C": 2, "D": 3}
    hits.sort(key=lambda h: rank.get(h["grade"], 9))
    return {
        "key": key, "strategy": strategy, "title": title,
        "is_etf": is_etf, "count": len(hits), "hits": hits,
        "error": raw.get("error"), "latest": latest,
        "btNote": BACKTEST_NOTE.get(key, ""),
        "gradeBtNote": GRADE_BACKTEST_NOTE.get(key, "评级分层未回测"),
        "conclusionNote": CONCLUSION_NOTE.get(key, ""),
        "updatedAt": now_bj().strftime("%Y-%m-%d %H:%M"),
    }


def run_variant_live(key, progress_cb=None):
    """单变体: 子进程流式解析进度 -> 回收 JSON -> enrich。progress_cb(done, total)。"""
    _ensure_screen_date()
    script, title, env_extra = VARIANTS[key]
    env = dict(os.environ)
    env.update(env_extra)
    env["CACHE_ONLY"] = "1"  # 筛选只读缓存, 不逐只现拉(缺数据的票跳过, 由全量重拉补)
    fd, path = tempfile.mkstemp(suffix=".json", prefix="watch_")
    os.close(fd)
    env["WATCH_JSON_OUT"] = path
    try:
        proc = subprocess.Popen(
            ["python3", os.path.join(HERE, script)], env=env, cwd=HERE,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
        )
        for line in proc.stdout:
            m = re.search(r"(\d+)/(\d+)", line)
            if m and progress_cb:
                progress_cb(int(m.group(1)), int(m.group(2)))
        proc.wait(timeout=600)
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:
        raw = {"strategy": "", "hits": [], "error": str(e)}
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    return enrich_section(key, raw)


# ---------- 聚合 / 落盘 / 历史 ----------

def empty_payload():
    now = now_bj()
    return {
        "generatedAt": now.strftime("%Y-%m-%d %H:%M"),
        "screenDate": os.environ.get("SCREEN_DATE", ""),
        "latestBar": "",
        "closed": False,
        "summary": {"total": 0, "gradeA": 0, "gradeB": 0},
        "sections": [{"key": k, "strategy": "", "title": VARIANTS[k][1],
                      "is_etf": "etf" in k, "count": 0, "hits": [], "error": None}
                     for k in VKEYS],
    }


def load_payload():
    payload = None
    if os.path.exists(OUT_PATH):
        try:
            with open(OUT_PATH, encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, json.JSONDecodeError):
            payload = None
    if payload is None:
        payload = empty_payload()
    # 丢掉已下线变体, 并补齐新增 VKEYS(否则新策略永远不出现在 tabs)
    bykey = {s["key"]: s for s in payload.get("sections", []) if s.get("key") in VKEYS}
    sections = []
    for key in VKEYS:
        if key in bykey:
            sections.append(bykey[key])
        else:
            sections.append({
                "key": key, "strategy": "", "title": VARIANTS[key][1],
                "is_etf": "etf" in key, "count": 0, "hits": [], "error": None,
            })
    payload["sections"] = sections
    for s in payload["sections"]:
        s["btNote"] = BACKTEST_NOTE.get(s["key"], "")
        s["gradeBtNote"] = GRADE_BACKTEST_NOTE.get(s["key"], "评级分层未回测")
        s["conclusionNote"] = CONCLUSION_NOTE.get(s["key"], "")
        if not s.get("title"):
            s["title"] = VARIANTS[s["key"]][1]
    meta = overnight_meta()
    if meta:
        payload["frozenDate"] = meta["frozenDate"]
        payload["frozenAt"] = meta["frozenAt"]
    return payload


def is_complete_session(latest, now=None):
    """日K已经走完：昨收及更早，或当天 15:00 之后。开盘前跑昨收算收盘定论。"""
    now = now or now_bj()
    today = now.strftime("%Y-%m-%d")
    if not latest:
        return False
    if latest < today:
        return True
    return latest == today and now.hour >= 15


def _resummarize(payload):
    ga = gb = total = 0
    latest = payload.get("latestBar", "")
    for sec in payload["sections"]:
        for h in sec["hits"]:
            total += 1
            if h["grade"] == "A":
                ga += 1
            elif h["grade"] == "B":
                gb += 1
        if sec.get("latest"):
            latest = max(latest, sec["latest"])
    # 0命中时各 section 无 latest, 用参考票的最新交易日兜底, 避免顶部日期显示旧值
    sd = os.environ.get("SCREEN_DATE", "")
    if sd:
        latest = max(latest, sd)
    now = now_bj()
    payload["summary"] = {"total": total, "gradeA": ga, "gradeB": gb}
    payload["latestBar"] = latest
    payload["generatedAt"] = now.strftime("%Y-%m-%d %H:%M")
    payload["closed"] = is_complete_session(latest, now)
    payload["screenDate"] = os.environ.get("SCREEN_DATE", latest)
    return payload


def save_payload(payload):
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)


def merge_section(section):
    """把单个 section 写回聚合结果并重算汇总 + 快照历史。"""
    payload = load_payload()
    bykey = {s["key"]: i for i, s in enumerate(payload["sections"])}
    if section["key"] in bykey:
        payload["sections"][bykey[section["key"]]] = section
    else:
        payload["sections"].append(section)
    _resummarize(payload)
    save_payload(payload)
    snapshot_history(payload)
    return payload


def _slim_watch(payload):
    date = payload.get("latestBar") or payload.get("screenDate") or payload.get("date")
    return {
        "date": date,
        "generatedAt": payload.get("generatedAt"),
        "closed": bool(payload.get("closed")),
        "summary": payload.get("summary") or {},
        "sections": [{
            "key": s.get("key"),
            "title": s.get("title"),
            "count": s.get("count"),
            "is_etf": bool(s.get("is_etf") or "etf" in (s.get("key") or "")),
            "hits": [{k: h.get(k) for k in HIT_SNAPSHOT_KEYS} for h in s.get("hits") or []],
        } for s in payload.get("sections") or []],
    }


def normalize_snapshot_sections(payload):
    for sec in payload.get("sections") or []:
        key = sec.get("key") or ""
        if "is_etf" not in sec:
            sec["is_etf"] = "etf" in key
        for h in sec.get("hits") or []:
            h.setdefault("is_etf", sec["is_etf"])
    return payload


def overnight_meta():
    if not os.path.isfile(OVERNIGHT_PATH):
        return None
    try:
        with open(OVERNIGHT_PATH, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    return {
        "frozenDate": d.get("date"),
        "frozenAt": d.get("generatedAt"),
        "frozenClosed": bool(d.get("closed")),
        "frozenSummary": d.get("summary") or {},
    }


def save_overnight_freeze(payload):
    """仅收盘定论写入隔夜快照。盘中重跑不得调用。"""
    if not payload.get("closed"):
        return
    slim = _slim_watch(payload)
    slim["frozen"] = True
    os.makedirs(os.path.dirname(OVERNIGHT_PATH), exist_ok=True)
    with open(OVERNIGHT_PATH, "w", encoding="utf-8") as f:
        json.dump(slim, f, ensure_ascii=False)


def trading_days():
    rows = cache_data.daily_kline("1.000001") or cache_data.daily_kline("0.000001") or []
    return [r[0] for r in rows if r]


def previous_trading_day(asof=None):
    """今早可买的信号日：asof 之前最近一个交易日。默认今天。"""
    asof = asof or now_bj().strftime("%Y-%m-%d")
    days = [d for d in trading_days() if d < asof]
    return days[-1] if days else None


def snapshot_history(payload):
    """按交易日存精简快照。已收盘的日期禁止被盘中重跑覆盖。"""
    date = payload.get("latestBar") or payload.get("screenDate")
    if not date:
        return
    os.makedirs(HIST_DIR, exist_ok=True)
    path = os.path.join(HIST_DIR, f"{date}.json")
    new_closed = bool(payload.get("closed"))
    if os.path.isfile(path) and not new_closed:
        try:
            with open(path, encoding="utf-8") as f:
                old = json.load(f)
            if old.get("closed"):
                print(f"[watch_export] 跳过覆盖收盘快照 {date}（盘中重跑不进今早可买）",
                      flush=True)
                return
        except (OSError, json.JSONDecodeError):
            pass
    slim = _slim_watch(payload)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(slim, f, ensure_ascii=False)
    if new_closed:
        save_overnight_freeze(payload)


def list_history():
    if not os.path.isdir(HIST_DIR):
        return []
    out = []
    for fn in os.listdir(HIST_DIR):
        if not fn.endswith(".json"):
            continue
        try:
            with open(os.path.join(HIST_DIR, fn), encoding="utf-8") as f:
                d = json.load(f)
            out.append({"date": d["date"], "generatedAt": d.get("generatedAt", ""),
                        "closed": d.get("closed", False), "summary": d.get("summary", {})})
        except (OSError, json.JSONDecodeError):
            continue
    out.sort(key=lambda x: x["date"], reverse=True)
    return out


def get_history(date):
    path = os.path.join(HIST_DIR, f"{date}.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _read_watch_file():
    if not os.path.exists(OUT_PATH):
        return None
    try:
        with open(OUT_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def load_closed_snapshot(date):
    """按日期取已收盘快照。盘中预览即使同日也不用。"""
    if not date:
        return None, None
    hist = get_history(date)
    if hist and (hist.get("closed") or is_complete_session(hist.get("date") or date)):
        return normalize_snapshot_sections(hist), "history"
    if os.path.isfile(OVERNIGHT_PATH):
        try:
            with open(OVERNIGHT_PATH, encoding="utf-8") as f:
                over = json.load(f)
        except (OSError, json.JSONDecodeError):
            over = None
        if over and over.get("closed") and over.get("date") == date:
            return normalize_snapshot_sections(over), "overnight"
    return None, None


def load_auction_watch():
    """今早可买候选：上一交易日收盘快照，不读盘中 live watch_data。"""
    signal = previous_trading_day()
    payload, src = load_closed_snapshot(signal)
    if payload is None:
        live = _read_watch_file()
        sd = (live or {}).get("screenDate") or (live or {}).get("latestBar")
        if live and sd == signal and (live.get("closed") or is_complete_session(sd)):
            return normalize_snapshot_sections(live), signal, "live-closed"
        empty = {
            "date": signal, "screenDate": signal or "", "latestBar": signal or "",
            "closed": True, "sections": [], "summary": {},
        }
        return empty, signal, "missing"
    payload.setdefault("screenDate", signal)
    payload.setdefault("latestBar", payload.get("date") or signal)
    return payload, signal, src


def seed_overnight_from_history():
    """启动时若还没有隔夜锁，用最近一份 closed 历史补上。"""
    if os.path.isfile(OVERNIGHT_PATH):
        return overnight_meta()
    for it in list_history():
        if not it.get("closed"):
            continue
        hist = get_history(it["date"])
        if hist:
            hist["closed"] = True
            save_overnight_freeze(hist)
            return overnight_meta()
    live = _read_watch_file()
    if live and live.get("closed"):
        save_overnight_freeze(live)
        return overnight_meta()
    return None


INDICES = [
    ("上证指数", "1.000001"),
    ("深证成指", "0.399001"),
    ("创业板指", "0.399006"),
    ("沪深300", "1.000300"),
    ("科创50", "1.000688"),
    ("北证50", "0.899050"),
]


def _day_chg(bars):
    """当日涨跌%: 最新收 vs 上一交易日收。分钟线按日期分段找上一日收盘。"""
    last = bars[-1]
    if len(bars) < 2:
        return 0.0
    if len(last[0]) > 10:  # 分钟线, 时间含 HH:MM
        day = last[0][:10]
        for r in reversed(bars):
            if r[0][:10] != day:
                return round((last[2] / r[2] - 1) * 100, 2) if r[2] else 0.0
        return round((last[2] / bars[0][1] - 1) * 100, 2) if bars[0][1] else 0.0
    prev = bars[-2]
    return round((last[2] / prev[2] - 1) * 100, 2) if prev[2] else 0.0


def market_indices(klt=101, n=None):
    """主要大盘指数K线(现拉最新)。klt=101 日线 / 30 / 5 分钟。涨跌恒为当日涨跌。"""
    out = []
    for name, secid in INDICES:
        try:
            if int(klt) == 101:
                rows = cache_data.daily_kline(secid, force=True)
                nn = n or 120
            else:
                rows = cache_data.min_kline(secid, klt=int(klt), force=True)
                nn = n or 240
        except Exception:
            rows = None
        if not rows:
            continue
        bars = []
        for r in rows[-nn:]:
            try:
                bars.append([r[0], float(r[1]), float(r[2]), float(r[3]),
                             float(r[4]), float(r[5])])
            except (ValueError, IndexError):
                continue
        if not bars:
            continue
        out.append({"name": name, "secid": secid, "bars": bars, "klt": int(klt),
                    "close": round(bars[-1][2], 2), "chg": _day_chg(bars),
                    "date": bars[-1][0]})
    return out


def cache_status(sample=400):
    """读磁盘真实缓存状态: 数量 / 最新交易日 / 覆盖率 / 最后拉取时间(mtime, 含命令行拉的) / 日期分布。"""
    ddir = str(cache_data.DAILY_DIR)
    if not os.path.isdir(ddir):
        return {"dailyCount": 0, "latestDay": "", "coveragePct": 0,
                "sampleSize": 0, "lastFetched": "-", "agoMinutes": 0, "breakdown": []}
    entries = [e for e in os.scandir(ddir) if e.name.endswith(".json")]
    count = len(entries)
    last_mtime = max((e.stat().st_mtime for e in entries), default=0)
    names = sorted(e.name for e in entries)
    # 固定种子抽样 -> 每次同一批, 覆盖率/分布不抖动
    samp = random.Random(42).sample(names, min(sample, count)) if count else []
    dist = Counter()
    for n in samp:
        try:
            with open(os.path.join(ddir, n), encoding="utf-8") as f:
                d = json.load(f)
            dist[d["klines"][-1].split(",")[0]] += 1
        except Exception:
            dist["读取失败"] += 1
    dates = [k for k in dist if k[:2] == "20"]
    # "最新交易日"取占比最多的日期(众数), 而非 max —— 抗个别超前/滞后的脏数据
    # (盘前快照可能给个别票写出次日 bar, 用 max 会把覆盖率误算成 0)
    latest = max(dates, key=lambda d: dist[d], default="")
    latest_n = dist.get(latest, 0)
    cov = round(latest_n * 100 / len(samp)) if samp else 0
    # 非最新日全部折叠成一个"其它"桶(多为停牌/退市), 不再列零散旧日期
    others = len(samp) - latest_n
    bj = (datetime.utcfromtimestamp(last_mtime) + timedelta(hours=8)) if last_mtime else None
    ago = int((time.time() - last_mtime) / 60) if last_mtime else 0
    # ETF 缓存数
    etf_n = 0
    if os.path.exists(str(cache_data.ETF_UNIVERSE_PATH)):
        try:
            with open(str(cache_data.ETF_UNIVERSE_PATH), encoding="utf-8") as f:
                etf_n = len(json.load(f).get("items", []))
        except Exception:
            etf_n = 0
    return {
        "dailyCount": count,
        "etfCount": etf_n,
        "latestDay": latest,
        "coveragePct": cov,
        "sampleSize": len(samp),
        "lastFetched": bj.strftime("%Y-%m-%d %H:%M") if bj else "-",
        "agoMinutes": ago,
        "breakdown": (
            ([{"date": latest, "n": latest_n, "latest": True}] if latest else [])
            + ([{"date": "其它(停牌/退市)", "n": others, "latest": False}] if others else [])
        ),
    }


def build(progress_cb=None):
    """全部变体顺序跑(初始化/全量重跑)。progress_cb(key, done, total)。"""
    if os.environ.get("REFRESH", "0") != "0":
        os.environ["BYPASS_CACHE"] = "1"
        cache_data.warmup(max_workers=24)
        os.environ.pop("BYPASS_CACHE", None)
    _ensure_screen_date()
    payload = load_payload()
    for key in VKEYS:
        cb = (lambda d, t, k=key: progress_cb(k, d, t)) if progress_cb else None
        section = run_variant_live(key, cb)
        # 每轮重算 bykey: 新增变体在旧 watch_data.json 里不存在, 直接 append 而不是 KeyError
        bykey = {s["key"]: i for i, s in enumerate(payload["sections"])}
        if key in bykey:
            payload["sections"][bykey[key]] = section
        else:
            payload["sections"].append(section)
    _resummarize(payload)
    save_payload(payload)
    snapshot_history(payload)
    return payload


def main():
    payload = build()
    s = payload["summary"]
    print(f"[watch_export] {payload['generatedAt']} 数据日={payload['latestBar']} "
          f"收盘={payload['closed']} 命中={s['total']} A={s['gradeA']} B={s['gradeB']}")
    print(f"[watch_export] -> {OUT_PATH}")


if __name__ == "__main__":
    main()
