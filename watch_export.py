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


def now_bj():
    """北京时间(UTC+8), 不依赖本机时区(服务器可能在美西)。"""
    return datetime.utcnow() + timedelta(hours=8)

# key -> (脚本, 标题, 额外env)
VARIANTS = {
    "s5_stock_loose":  ("screen_chan_wyckoff_3buy.py", "策略五·个股·宽松候选", {"STRICT_BUY": "0"}),
    "s5_stock_strict": ("screen_chan_wyckoff_3buy.py", "策略五·个股·严格(下单级别)", {"STRICT_BUY": "1"}),
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
                        {"ENABLE_TYPES": "3", "WEEKLY_MODE": "ma", "SUB_LEVEL": "1"}),
    # ETF 版: 出场必须换成移动止损(实测 +1.42% vs 顶分型 +0.41%), 且只买第1个中枢
    # (ETF 第2个中枢 -2.36%/23%胜, 由 watch_grade 直接判 D)。与策略五 ETF 结论一致。
    "s10_etf":         ("strategy_chan_final/screen.py", "策略十·ETF·缠论三买(移动止损)",
                        {"ETF_ONLY": "1", "ENABLE_TYPES": "3", "WEEKLY_MODE": "ma",
                         "SUB_LEVEL": "1", "PULLBACK_GG": "1"}),
}
# 暂停展示/运行但保留配置与回测代码，移出集合即可恢复。
DISABLED_VARIANTS = {"s6_stock", "s9_stock"}
VKEYS = [key for key in VARIANTS if key not in DISABLED_VARIANTS]

# 回测注解(日线口径, 数据见 README)。总胜率 / 启动几率 / 启动后胜率(策略6/7的
# 启动模型口径; 策略5为顶分型/移动止损, 无"启动"概念只给总胜率+均值)。
BACKTEST_NOTE = {
    "s5_stock_loose":  "个股宽松候选·旧口径约40%胜；当前不进主推荐",
    "s5_stock_strict": "个股严格·全量3951笔·37.2%胜·+0.05%/笔",
    "s5_etf_loose":    "日线·移动止损·全量2935笔·48.7%胜·+0.88%/笔",
    "s5_etf_strict":   "日线·移动止损·全量471笔·48.8%胜·+0.75%/笔",
    "s6_stock":        "全量4346笔·39.4%胜·-0.16%/笔；入口已暂停",
    "s6_etf":          "ETF版仅调参样本，未完成多年分层验证",
    "s7_stock":        "全量3813笔·L2止损·涨6%后五日线保护·53.3%胜·+1.00%/笔",
    "s8_stock":        "全量1080笔·38.3%胜·+0.11%/笔",
    "s9_stock":        "全量7591笔·37.6%胜·-0.14%/笔；入口已暂停",
    "s10_stock":       "日线·顶分型卖·总46.1%·+0.90%/笔·首中枢+1.03%",
    "s10_etf":         "日线·移动止损·全量535笔·44.7%胜·+0.35%/笔；2026为-2.61%",
}

# dashboard 当前 A/B/C/D 评级规则的一年期历史重放。括号内为样本数；策略十的
# 一年历史分钟数据不足，因此这里是“不含30分共振”的日线基础评级。
GRADE_BACKTEST_NOTE = {
    "s5_stock_loose":  "宽松版仅作候选池，评级不作为收益排序",
    "s5_stock_strict": "全量3951笔·结构评级：A 37.2%(1894) · B 36.6%(1684) · C 39.9%(373)；仅表示形态完整度",
    "s5_etf_loose":    "全量2935笔：A 52.9%(877)/+1.38% · B 45.9%(1297)/+0.66% · C 48.0%(715)/+0.65%",
    "s5_etf_strict":   "全量471笔：A 45.9%(242)/+0.87% · B 48.9%(180)/+0.70% · C 63.3%(49)/+0.29%；胜率不排序",
    "s6_stock":        "全量4346笔：A无样本 · B 40.6%(2522)/-0.10% · C 38.1%(1380)/-0.18% · D 36.0%(444)/-0.47%",
    "s6_etf":          "ETF版评级尚未完成多年分层验证",
    "s7_stock":        "全量3813笔：A 58.2%(1044)/+1.61% · B 52.4%(2469)/+0.88% · C 43.7%(300)/-0.06%；已按回测把原A/C对调",
    "s8_stock":        "全量1080笔：A 38.1%(21，极薄)/+1.15% · B 39.3%(516)/+0.28% · C 37.4%(543)/-0.10%",
    "s9_stock":        "全量7591笔：A 33.9%(3456)/-0.11% · B 40.7%(3129)/-0.15% · C 40.6%(1006)/-0.23%；均值弱排序、胜率反序",
    "s10_stock":       "三买有效口径1229笔·46.1%胜·+0.90%；市场联合A仅作上涨环境加分",
    "s10_etf":         "全量535笔：A 37.3%(59)/-0.06% · B 47.2%(267)/+1.02% · C 46.7%(122)/+0.61% · D 39.1%(87)/-1.78%",
}

CONCLUSION_NOTE = {
    "s5_stock_loose":  "个股宽松只作观察池；真正主线看策略5 ETF宽松。",
    "s5_stock_strict": "个股严格接近零期望，ABC只表示形态完整度，不作为下单排序。",
    "s5_etf_loose":    "当前主线：三种市场状态相对最稳，优先观察A档并按结构止损。",
    "s5_etf_strict":   "ETF狙击版：信号少，上涨环境更好，可作为宽松版里的加分项。",
    "s6_stock":        "上涨/震荡/下跌均无优势，六年总体负期望，dashboard入口已暂停。",
    "s6_etf":          "ETF压缩蓄势未进入主排名，仅保留观察。",
    "s7_stock":        "L2跌破止损；浮盈达到6%后收盘跌破MA5止盈。胜率最高但2023/2026仍为负，优先看A档和市场环境。",
    "s8_stock":        "弱观察：上涨环境才看，样本A仅21笔，不进主策略。",
    "s9_stock":        "三种市场状态均为负且A胜率最低，dashboard入口已暂停。",
    "s10_stock":       "策略5的严格缠论补充：只在上涨环境看联合A，非上涨环境优先策略5 ETF宽松。",
    "s10_etf":         "和策略5 ETF重叠但更不稳；仅上涨环境观察，当前暂停主入口。",
}


def _secid(code, is_etf):
    if is_etf:
        return ("1." if code.startswith("5") else "0.") + code
    return ("1." if code.startswith("6") else "0.") + code


def _bars_for(secid, n=60):
    rows = cache_data.daily_kline(secid)
    if not rows:
        return []
    out = []
    for r in rows[-n:]:
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
    return {}


def _ensure_screen_date():
    # 始终对齐到缓存最新交易日。长驻 server 进程里 SCREEN_DATE 会残留旧值(如昨天),
    # 缓存进入新一天后若不更新, 筛选器的 D[i]!=TODAY 会把全部票挡掉 -> 全0。
    ref = cache_data.daily_kline("0.000001")
    if ref:
        os.environ["SCREEN_DATE"] = ref[-1][0]


def enrich_section(key, raw):
    """把子进程回收的原始 hits 挂上评级/K线/止损位, 组成一个 section。"""
    script, title, _ = VARIANTS[key]
    strategy = raw.get("strategy", "")
    is_etf = raw.get("is_etf", False)
    latest = ""
    hits = []
    market = _market_context() if strategy == "chan_final" and not is_etf else {}
    for hit in raw.get("hits", []):
        secid = _secid(hit["code"], is_etf)
        bars = _bars_for(secid)
        if bars:
            latest = max(latest, bars[-1][0])
        if market:
            hit.update(market)
        g = watch_grade.grade(strategy, hit, bars)
        hit.update({
            "secid": secid,
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
    payload["sections"] = [
        section for section in payload.get("sections", [])
        if section.get("key") in VKEYS
    ]
    for s in payload.get("sections", []):  # 老缓存也补上回测胜率注解
        s["btNote"] = BACKTEST_NOTE.get(s["key"], "")
        s["gradeBtNote"] = GRADE_BACKTEST_NOTE.get(s["key"], "评级分层未回测")
        s["conclusionNote"] = CONCLUSION_NOTE.get(s["key"], "")
    return payload


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
    payload["closed"] = bool(latest == now.strftime("%Y-%m-%d") and now.hour >= 15)
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


def snapshot_history(payload):
    """按交易日存一份精简快照(不含K线), 最新覆盖当日。"""
    date = payload.get("latestBar") or payload.get("screenDate")
    if not date:
        return
    os.makedirs(HIST_DIR, exist_ok=True)
    slim = {
        "date": date,
        "generatedAt": payload["generatedAt"],
        "closed": payload["closed"],
        "summary": payload["summary"],
        "sections": [{
            "key": s["key"], "title": s["title"], "count": s["count"],
            "hits": [{k: h.get(k) for k in
                      ("code", "name", "grade", "close", "chg", "gradeNote",
                       "dist", "stage", "pull_days", "runup", "amt", "flags")}
                     for h in s["hits"]],
        } for s in payload["sections"]],
    }
    with open(os.path.join(HIST_DIR, f"{date}.json"), "w", encoding="utf-8") as f:
        json.dump(slim, f, ensure_ascii=False)


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
