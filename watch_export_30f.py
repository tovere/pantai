#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""30分钟级别盯盘编排 —— 与日线版 watch_export.py 并行、隔离。

跑 30f 策略变体 -> 附 30分K线 -> watch_data_30f.json。复用 watch_export 的
now_bj/_secid/_levels 与 watch_grade 评级(评级按去掉 _30f 的基础策略名复用日线口径)。
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
import watch_export as W
import watch_grade

HERE = W.HERE
OUT_PATH_30F = os.path.join(HERE, "watch_data_30f.json")
KLT = 30

# key -> (脚本, 标题, 额外env)
VARIANTS_30F = {
    "resonance_stock": ("screen_resonance_30f.py", "★共振·个股·日线三买×30f", {}),
    "resonance_etf":   ("screen_resonance_30f.py", "★共振·ETF·日线三买×30f", {"ETF_ONLY": "1"}),
    "s5_stock_strict": ("screen_chan_wyckoff_3buy_30f.py", "策略五·个股·严格", {"STRICT_BUY": "1"}),
    "s5_stock_loose":  ("screen_chan_wyckoff_3buy_30f.py", "策略五·个股·宽松", {"STRICT_BUY": "0"}),
    "s5_etf_strict":   ("screen_chan_wyckoff_3buy_30f.py", "策略五·ETF·严格", {"ETF_ONLY": "1", "STRICT_BUY": "1"}),
    "s5_etf_loose":    ("screen_chan_wyckoff_3buy_30f.py", "策略五·ETF·宽松", {"ETF_ONLY": "1", "STRICT_BUY": "0"}),
    "s6_stock":        ("screen_squeeze_launch_30f.py", "策略六·个股·压缩蓄势", {}),
    "s6_etf":          ("screen_squeeze_launch_30f.py", "策略六·ETF·压缩蓄势", {"ETF_ONLY": "1"}),
    "s7_stock":        ("screen_spring_2buy_30f.py", "策略七·个股·Spring二买", {}),
    "s7_etf":          ("screen_spring_2buy_30f.py", "策略七·ETF·Spring二买", {"ETF_ONLY": "1"}),
}
VKEYS_30F = list(VARIANTS_30F.keys())

# 回测胜率注解(30f口径, 均为40天小样本, 仅方向性参考)。
BACKTEST_NOTE = {
    "resonance_stock": "40天·14笔 50%胜 −0.5% ·方向性",
    "resonance_etf":   "40天·样本极少 ·观察",
    "s5_stock_strict": "40天·343笔 38%胜 −0.9%",
    "s5_stock_loose":  "40天·1064笔 40%胜 −0.7%",
    "s5_etf_strict":   "40天·167笔 31%胜 −2.1%",
    "s5_etf_loose":    "40天·小样本 ·参考",
    "s6_stock":        "40天·92笔 45%胜 +0.2%",
    "s6_etf":          "40天·样本极少 ·观察",
    "s7_stock":        "40天·37笔 35%胜 −1.0%",
    "s7_etf":          "40天·样本极少 ·观察",
}


def _bars_for_30f(secid, n=80):
    rows = cache_data.min_kline(secid, KLT)
    if not rows:
        return []
    out = []
    for r in rows[-n:]:
        try:
            out.append([r[0], float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])])
        except (ValueError, IndexError):
            continue
    return out


def enrich_section(key, raw):
    script, title, _ = VARIANTS_30F[key]
    strategy = raw.get("strategy", "")
    base = strategy.replace("_30f", "")  # 评级复用日线口径
    is_etf = raw.get("is_etf", False)
    latest = ""
    hits = []
    for hit in raw.get("hits", []):
        secid = W._secid(hit["code"], is_etf)
        bars = _bars_for_30f(secid)
        if bars:
            latest = max(latest, bars[-1][0])
        try:
            g = watch_grade.grade(base, hit, bars)
        except Exception:
            g = {"grade": "-", "score": 0, "note": "", "flags": []}
        hit.update({
            "secid": secid, "grade": g["grade"], "gradeScore": g["score"],
            "gradeNote": g["note"], "flags": g["flags"],
            "levels": W._levels(base, hit), "bars": bars,
        })
        hits.append(hit)
    rank = {"A": 0, "B": 1, "C": 2, "D": 3, "-": 5}
    hits.sort(key=lambda h: rank.get(h["grade"], 9))
    return {
        "key": key, "strategy": strategy, "title": title,
        "is_etf": is_etf, "count": len(hits), "hits": hits,
        "error": raw.get("error"), "latest": latest,
        "btNote": BACKTEST_NOTE.get(key, ""),
        "updatedAt": W.now_bj().strftime("%Y-%m-%d %H:%M"),
    }


def run_variant_live(key, progress_cb=None):
    script, title, env_extra = VARIANTS_30F[key]
    env = dict(os.environ)
    env.update(env_extra)
    env["CACHE_ONLY"] = "1"  # 筛选只读缓存
    fd, path = tempfile.mkstemp(suffix=".json", prefix="watch30f_")
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


def empty_payload():
    now = W.now_bj()
    return {
        "generatedAt": now.strftime("%Y-%m-%d %H:%M"),
        "latestBar": "", "closed": False,
        "summary": {"total": 0, "gradeA": 0, "gradeB": 0},
        "sections": [{"key": k, "strategy": "", "title": VARIANTS_30F[k][1],
                      "is_etf": "etf" in k, "count": 0, "hits": [], "error": None}
                     for k in VKEYS_30F],
    }


def load_payload():
    payload = None
    if os.path.exists(OUT_PATH_30F):
        try:
            with open(OUT_PATH_30F, encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, json.JSONDecodeError):
            payload = None
    if payload is None:
        payload = empty_payload()
    for s in payload.get("sections", []):
        s["btNote"] = BACKTEST_NOTE.get(s["key"], "")
    return payload


def merge_section(section):
    payload = load_payload()
    bykey = {s["key"]: i for i, s in enumerate(payload["sections"])}
    if section["key"] in bykey:
        payload["sections"][bykey[section["key"]]] = section
    else:
        payload["sections"].append(section)
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
    payload["summary"] = {"total": total, "gradeA": ga, "gradeB": gb}
    payload["latestBar"] = latest
    payload["generatedAt"] = W.now_bj().strftime("%Y-%m-%d %H:%M")
    payload["closed"] = False
    with open(OUT_PATH_30F, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    return payload


def min_cache_status(sample=300):
    """30分缓存状态: 标的数 / 最新bar日期(众数) / 覆盖率 / 最后拉取。"""
    ddir = os.path.join(str(cache_data.MIN_DIR), str(KLT))
    if not os.path.isdir(ddir):
        return {"count": 0, "latest": "", "coveragePct": 0, "sampleSize": 0,
                "lastFetched": "-", "agoMinutes": 0}
    entries = [e for e in os.scandir(ddir) if e.name.endswith(".json")]
    count = len(entries)
    last_mtime = max((e.stat().st_mtime for e in entries), default=0)
    names = sorted(e.name for e in entries)
    samp = random.Random(42).sample(names, min(sample, count)) if count else []
    dist = Counter()
    last_bar = ""
    for n in samp:
        try:
            with open(os.path.join(ddir, n), encoding="utf-8") as f:
                d = json.load(f)
            t = d["klines"][-1].split(",")[0]
            dist[t[:10]] += 1
            last_bar = max(last_bar, t)
        except Exception:
            dist["坏"] += 1
    dates = [k for k in dist if k[:2] == "20"]
    latest = max(dates, key=lambda x: dist[x], default="")
    cov = round(dist.get(latest, 0) * 100 / len(samp)) if samp else 0
    bj = (datetime.utcfromtimestamp(last_mtime) + timedelta(hours=8)) if last_mtime else None
    ago = int((time.time() - last_mtime) / 60) if last_mtime else 0
    return {
        "count": count, "latest": latest, "lastBar": last_bar, "coveragePct": cov,
        "sampleSize": len(samp),
        "lastFetched": bj.strftime("%Y-%m-%d %H:%M") if bj else "-", "agoMinutes": ago,
    }
