#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""昨晚策略命中 ∩ 今早竞价/开盘：产出 9:30 可买清单。

否决 / 降档：
  一字/近涨停买不进、开盘破止损。
  策略十二全量池仅观察。策略十四/十五不进入本清单（十四高开持有不合，十五尾盘买）。
  竞价量比过低=真空开、未匹配卖盘过重=抛压 → 可买降观察。
  量比高且买盘未匹配=抢筹、量比很高=放量 → 可买理由写盘口。
  9:15–9:25 连拍 live，终态对照最后一拍：尾盘砸盘/翻空降观察。
  ETF 无竞价接口，改用场内快照开盘价。
  MCP 没有 9:25 最后一秒 tick，用 9:20–9:25 最后一拍 live vs final 近似结算。

    python3 auction_open_screen.py              # stage=final
    python3 auction_open_screen.py --stage live
    python3 auction_open_screen.py --watch      # 9:15–9:25 连拍后出终态
    python3 auction_open_screen.py --reclassify # 用已落盘快照重打标签
"""
import argparse
import json
import os
import threading
import time
from datetime import datetime, timedelta, time as dtime

import fuyao_client
import watch_export

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_PATH = os.path.join(HERE, "data_cache", "auction_open.json")
HIST_DIR = os.path.join(HERE, "data_cache", "auction_open_history")
TAPE_DIR = os.path.join(HERE, "data_cache", "auction_tape")
_TAPE_LOCK = threading.Lock()

GRADE_RANK = {"A": 0, "B": 1, "C": 2, "D": 3}
WATCH_ONLY_KEYS = {"s12_small_yang"}
EXCLUDE_SECTION_KEYS = {"s14_bottom_vol_yang", "s15_limit_shrink_pull"}
LIMIT_RATIO = 0.95
# 竞价盘口：量比过低=真空；未匹配/成交量过负=卖压；量比高+买剩=抢筹。
VACUUM_VR = 0.35
SELL_IMBALANCE = -0.40
GRAB_VR = 1.20
GRAB_UM = 0.05
HOT_VR = 1.50
TAG_RANK = {"抢筹": 0, "放量": 1, "均衡": 2, "无竞价": 3, "真空": 4, "抛压": 5, "无数据": 6}
SETTLE_RANK = {
    "尾盘抢筹": 0, "尾盘翻多": 1, "尾盘放量": 2, "平稳撮合": 3,
    "无对照": 4, "竞价中": 4, "尾盘翻空": 5, "尾盘砸盘": 6,
}
SETTLE_VOL_SURGE = 0.25
SETTLE_FLIP_UMR = 0.35
TAPE_MAX_TICKS = 90
AUCTION_OPEN = dtime(9, 15, 0)
AUCTION_LOCK = dtime(9, 20, 0)
SETTLE_CUT = dtime(9, 25, 0)
AUCTION_END = dtime(9, 25, 2)
NOTE = (
    "候选只读上一交易日收盘快照，盘中重跑策略不会改这份名单。"
    "竞价用成交量/未匹配/量比；9:20–9:25 live 对照终态看尾盘撮合。"
    "真空开、抛压、尾盘砸盘/翻空降观察。近涨停买不进、开盘破止损放弃。"
    "不构成投资建议。"
)


def now_bj():
    return datetime.utcnow() + timedelta(hours=8)


def _num(v):
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def session_closed(now=None):
    """周一到周五 15:00 前视为未收盘，收盘价留空。"""
    now = now or now_bj()
    return not (now.weekday() < 5 and now.time() < dtime(15, 0))


def in_call_auction(now=None):
    t = (now or now_bj()).time()
    return AUCTION_OPEN <= t < AUCTION_END


def attach_close_chg(row):
    """相对昨收的收盘涨跌幅。未收盘则空。"""
    px = _num(row.get("close_price"))
    prev = _num(row.get("prev_price")) or _num(row.get("close"))
    if px is None or not prev:
        row["close_pct"] = None
        return row
    row["close_pct"] = round((px / float(prev) - 1) * 100, 2)
    return row


def auction_poll_interval(now=None):
    t = (now or now_bj()).time()
    if t >= dtime(9, 24, 0):
        return 2.0
    if t >= AUCTION_LOCK:
        return 6.0
    return 10.0


def tape_path(date=None):
    d = date or now_bj().strftime("%Y-%m-%d")
    return os.path.join(TAPE_DIR, d + ".json")


def load_tape(date=None):
    path = tape_path(date)
    if not os.path.isfile(path):
        return {"date": date or now_bj().strftime("%Y-%m-%d"), "ticks": []}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_tape(tape):
    os.makedirs(TAPE_DIR, exist_ok=True)
    path = tape_path(tape.get("date"))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(tape, f, ensure_ascii=False)


def append_tape(auc, meta, stage="live"):
    """只在 9:15–9:25 窗口把 live 快照追加进当日 tape。"""
    now = now_bj()
    if stage != "live" or not in_call_auction(now):
        return load_tape()
    compact = {}
    for ts, it in (auc or {}).items():
        compact[ts] = {
            "p": it.get("auction_price"),
            "pct": it.get("auction_pct"),
            "v": it.get("auction_volume"),
            "a": it.get("auction_amount"),
            "u": it.get("auction_unmatched"),
            "vr": it.get("auction_volume_ratio"),
        }
    tick = {
        "t": now.strftime("%H:%M:%S"),
        "ts": now.strftime("%Y-%m-%d %H:%M:%S"),
        "stage": stage,
        "auction_phase": (meta or {}).get("auction_phase"),
        "data_status": (meta or {}).get("data_status"),
        "by": compact,
    }
    with _TAPE_LOCK:
        tape = load_tape(now.strftime("%Y-%m-%d"))
        ticks = tape.get("ticks") or []
        ticks.append(tick)
        tape["ticks"] = ticks[-TAPE_MAX_TICKS:]
        tape["date"] = now.strftime("%Y-%m-%d")
        save_tape(tape)
        return tape


def pre_settle_tick(tape=None):
    """优先取 9:20–9:25 最后一拍（不可撤单段），否则取 9:15 后最后一拍。"""
    ticks = (tape or load_tape()).get("ticks") or []
    lock, open_, end = [], [], []
    for tk in ticks:
        t = tk.get("t") or ""
        if AUCTION_LOCK.strftime("%H:%M:%S") <= t < SETTLE_CUT.strftime("%H:%M:%S"):
            lock.append(tk)
        elif AUCTION_OPEN.strftime("%H:%M:%S") <= t < SETTLE_CUT.strftime("%H:%M:%S"):
            open_.append(tk)
        else:
            end.append(tk)
    if lock:
        return lock[-1]
    if open_:
        return open_[-1]
    return None


def attach_settle(row, pre):
    """final 对照 pre-settle live：尾量=撮合那一下多出来的成交。"""
    if not pre:
        row["settle_tag"] = "无对照"
        row["pre_settle_at"] = None
        row["vol_delta"] = None
        row["vol_delta_pct"] = None
        row["unmatched_delta"] = None
        row["price_delta"] = None
        row["settle_strength"] = None
        return row
    fin_v = _num(row.get("auction_volume"))
    pre_v = _num(pre.get("v"))
    fin_u = _num(row.get("auction_unmatched"))
    pre_u = _num(pre.get("u"))
    fin_p = _num(row.get("auction_price"))
    pre_p = _num(pre.get("p"))
    vol_delta = None if fin_v is None or pre_v is None else fin_v - pre_v
    vol_pct = None
    if vol_delta is not None and pre_v not in (None, 0):
        vol_pct = vol_delta / pre_v
    um_delta = None if fin_u is None or pre_u is None else fin_u - pre_u
    px_delta = None if fin_p is None or pre_p is None else fin_p - pre_p
    fin_umr = None
    pre_umr = None
    if fin_v not in (None, 0) and fin_u is not None:
        fin_umr = fin_u / fin_v
    if pre_v not in (None, 0) and pre_u is not None:
        pre_umr = pre_u / pre_v

    tag = "平稳撮合"
    surged = vol_pct is not None and vol_pct >= SETTLE_VOL_SURGE
    if surged and (fin_u or 0) < 0 and (um_delta or 0) <= 0:
        tag = "尾盘砸盘"
    elif surged and (fin_u or 0) > 0 and (um_delta or 0) >= 0:
        tag = "尾盘抢筹"
    elif surged:
        tag = "尾盘放量"
    elif (pre_umr is not None and fin_umr is not None
          and pre_umr >= 0.05 and fin_umr <= -SETTLE_FLIP_UMR):
        tag = "尾盘翻空"
    elif (pre_umr is not None and fin_umr is not None
          and pre_umr <= -0.05 and fin_umr >= SETTLE_FLIP_UMR):
        tag = "尾盘翻多"

    row["settle_tag"] = tag
    row["pre_settle_at"] = pre.get("t")
    row["vol_delta"] = None if vol_delta is None else round(vol_delta, 2)
    row["vol_delta_pct"] = None if vol_pct is None else round(vol_pct, 3)
    row["unmatched_delta"] = None if um_delta is None else round(um_delta, 2)
    row["price_delta"] = None if px_delta is None else round(px_delta, 4)
    strength = None
    if vol_pct is not None:
        strength = vol_pct * (1.0 + (fin_umr or 0))
    row["settle_strength"] = None if strength is None else round(strength, 3)
    return row


def to_thscode(code, is_etf):
    c = str(code).split(".")[0].zfill(6)
    if is_etf:
        return c + (".SH" if c.startswith("5") else ".SZ")
    if c.startswith(("6", "9")):
        return c + ".SH"
    if c.startswith(("0", "3")):
        return c + ".SZ"
    return c + ".BJ"


def limit_pct(code, is_etf):
    c = str(code).split(".")[0]
    if is_etf:
        return 10.0
    if c.startswith(("300", "688")):
        return 20.0
    if c.startswith(("8", "4")):
        return 30.0
    return 10.0


def hit_stop(h):
    for k in ("buy_low", "stop", "win_low", "sig_low", "l2", "vdb_low", "base_low"):
        v = h.get(k)
        if v not in (None, ""):
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    for k, v in (h.get("levels") or {}).items():
        if v in (None, ""):
            continue
        if "止损" in k or k in ("三买低(止损)", "窗低", "信号低"):
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    return None


def load_watch_for_auction():
    watch, signal, src = watch_export.load_auction_watch()
    labels = {
        "history": "收盘快照",
        "overnight": "隔夜锁定",
        "live-closed": "收盘盯盘",
        "missing": "无收盘快照",
    }
    extra = {
        "screenDate": signal or "",
        "latestBar": signal or watch.get("date") or "",
        "frozenDate": signal,
        "watchSource": src,
        "watchFrozen": src != "missing",
        "watchSourceLabel": labels.get(src, src or ""),
    }
    err = None
    if src == "missing":
        err = f"没有 {signal or '?'} 的收盘快照。请在前一交易日 15:00 后跑一遍盯盘。"
    return watch, extra, err


def collect_candidates(payload):
    """同代码合并：保留最好评级，汇总策略来源。"""
    by = {}
    for sec in payload.get("sections") or []:
        key = sec.get("key") or ""
        if key in EXCLUDE_SECTION_KEYS:
            continue
        title = sec.get("title") or key
        is_etf_sec = bool(sec.get("is_etf"))
        for h in sec.get("hits") or []:
            code = str(h.get("code") or "")
            if not code:
                continue
            is_etf = bool(h.get("is_etf") or is_etf_sec)
            thscode = to_thscode(code, is_etf)
            name = h.get("name") or ""
            if "ST" in name or "退" in name or "PT" in name:
                continue
            rec = by.get(thscode)
            grade = h.get("grade") or "C"
            cand = {
                "code": code,
                "thscode": thscode,
                "name": name,
                "industry": h.get("industry") or "",
                "is_etf": is_etf,
                "grade": grade,
                "gradeNote": h.get("gradeNote") or "",
                "close": h.get("close"),
                "stop": hit_stop(h),
                "section_keys": [key],
                "strategies": [title],
            }
            if rec is None:
                by[thscode] = cand
                continue
            rec["section_keys"].append(key)
            if title not in rec["strategies"]:
                rec["strategies"].append(title)
            if GRADE_RANK.get(grade, 9) < GRADE_RANK.get(rec["grade"], 9):
                rec["grade"] = grade
                rec["gradeNote"] = cand["gradeNote"]
                rec["stop"] = cand["stop"] or rec["stop"]
                rec["close"] = cand["close"] or rec["close"]
            elif rec["stop"] is None:
                rec["stop"] = cand["stop"]
    return list(by.values())


def drop_excluded(rows):
    """已落盘清单里去掉十四/十五：只命中这些的整行删，重叠的只剥来源。"""
    out = []
    for row in rows:
        keys = [k for k in (row.get("section_keys") or []) if k not in EXCLUDE_SECTION_KEYS]
        if not keys:
            continue
        titles = [
            t for t in (row.get("strategies") or [])
            if "策略十四" not in (t or "") and "策略十五" not in (t or "")
        ]
        row["section_keys"] = keys
        row["strategies"] = titles or row.get("strategies") or []
        out.append(row)
    return out


def attach_auction_micro(row):
    """用 MCP 竞价快照的量、未匹配、量比打标签。没有最后一秒分时，只有 live/final 截面。"""
    vol = row.get("auction_volume")
    unmatched = row.get("auction_unmatched")
    vr = row.get("auction_volume_ratio")
    umr = None
    try:
        if vol not in (None, "", 0) and unmatched is not None:
            umr = float(unmatched) / float(vol)
    except (TypeError, ValueError, ZeroDivisionError):
        umr = None
    row["unmatched_ratio"] = None if umr is None else round(umr, 3)

    if row.get("is_etf") and vr is None and vol is None:
        row["auction_tag"] = "无竞价"
        row["auction_strength"] = None
        return row

    tag = "均衡"
    if vr is None and vol is None:
        tag = "无数据"
    elif vr is not None and float(vr) < VACUUM_VR:
        tag = "真空"
    if umr is not None and umr <= SELL_IMBALANCE:
        tag = "抛压"
    elif vr is not None and float(vr) >= GRAB_VR and (umr or 0) >= GRAB_UM:
        tag = "抢筹"
    elif vr is not None and float(vr) >= HOT_VR and tag == "均衡":
        tag = "放量"
    row["auction_tag"] = tag
    strength = None
    if vr is not None:
        strength = float(vr) * (1.0 + (umr or 0))
    row["auction_strength"] = None if strength is None else round(strength, 3)
    return row


def classify(row):
    keys = row.get("section_keys") or []
    tradable = [k for k in keys if k not in WATCH_ONLY_KEYS]
    px = row.get("auction_price") or row.get("open_price")
    prev = row.get("prev_price") or row.get("close")
    pct = row.get("auction_pct")
    if pct is None and px and prev:
        pct = (float(px) / float(prev) - 1) * 100
    row["open_pct"] = None if pct is None else round(float(pct), 2)
    row["ref_price"] = px
    attach_auction_micro(row)
    vr = row.get("auction_volume_ratio")
    umr = row.get("unmatched_ratio")
    tag = row.get("auction_tag")

    if row.get("grade") == "D":
        return "skip", "评级 D，仅观察不买"
    if px is None:
        return "skip", "无开盘/竞价价"
    if pct is not None:
        cap = limit_pct(row["code"], row["is_etf"])
        if float(pct) >= cap * LIMIT_RATIO:
            extra = ""
            if umr is not None and umr > 0:
                extra = "，未匹配买盘封死"
            return "skip", f"开盘 {pct:.2f}% 接近涨停，买不进{extra}"
    stop = row.get("stop")
    if stop is not None and float(px) < float(stop):
        return "skip", f"开盘 {px} 已破止损 {stop}"
    if not tradable:
        return "watch", "来源仅为策略十二全量池，实盘不作为下单池"
    if row.get("grade") == "C":
        return "watch", "评级 C 偏弱"
    settle = row.get("settle_tag")
    vdp = row.get("vol_delta_pct")
    tail = f"，尾量 {vdp:.0%}" if vdp is not None else ""
    if tag == "真空":
        vrs = f"{float(vr):.2f}" if vr is not None else "-"
        return "watch", f"竞价量比 {vrs} 过低，真空开"
    if tag == "抛压":
        ums = f"{umr:.0%}" if umr is not None else "-"
        return "watch", f"竞价未匹配卖盘重({ums})，抛压"
    if settle in ("尾盘砸盘", "尾盘翻空"):
        return "watch", f"结算{settle}{tail}"
    if tag == "抢筹":
        vrs = f"{float(vr):.2f}" if vr is not None else "-"
        extra = f"；结算{settle}{tail}" if settle in ("尾盘抢筹", "尾盘放量", "尾盘翻多") else ""
        return "buy", f"可买：竞价抢筹，量比 {vrs} 且买盘未匹配{extra}"
    if tag == "放量":
        vrs = f"{float(vr):.2f}" if vr is not None else "-"
        extra = f"；结算{settle}{tail}" if settle in ("尾盘抢筹", "尾盘放量", "尾盘翻多") else ""
        return "buy", f"可买：竞价放量，量比 {vrs}{extra}"
    if settle in ("尾盘抢筹", "尾盘翻多"):
        return "buy", f"可买：结算{settle}{tail}"
    if settle == "尾盘放量":
        return "buy", f"可买：结算尾盘放量{tail}"
    return "buy", "可买：评级过关且开盘可执行"


def _sort_rows(rows):
    order = {"buy": 0, "watch": 1, "skip": 2}

    def sort_key(r):
        strength = r.get("auction_strength")
        if strength is None:
            strength = -99
        return (
            order[r["action"]],
            SETTLE_RANK.get(r.get("settle_tag") or "无对照", 9),
            TAG_RANK.get(r.get("auction_tag") or "无数据", 9),
            GRADE_RANK.get(r["grade"], 9),
            -strength,
        )

    rows.sort(key=sort_key)
    return rows


def fetch_snapshots(cands, stage, with_px=True, with_bench=True):
    stocks = [c["thscode"] for c in cands if not c["is_etf"]]
    etfs = [c["thscode"] for c in cands if c["is_etf"]]
    auc, auc_meta = {}, {}
    px = {}
    if stocks:
        auc, auc_meta = fuyao_client.auction_snapshot(stocks, stage=stage)
        if with_px:
            px = fuyao_client.prices_snapshot(stocks)
    fund = {}
    if with_px:
        for ts in etfs:
            it = fuyao_client.fund_snapshot(ts)
            if it:
                fund[ts] = it
    bench = None
    if with_bench:
        try:
            bench = fuyao_client.auction_benchmark()
        except Exception:
            bench = None
    return auc, auc_meta, px, fund, bench


def rows_from(cands, auc, px, fund, stage, pre_tick=None):
    pre_by = (pre_tick or {}).get("by") or {}
    rows = []
    for c in cands:
        ts = c["thscode"]
        a = auc.get(ts) or {}
        p = px.get(ts) or fund.get(ts) or {}
        row = dict(c)
        row["auction_price"] = a.get("auction_price")
        row["auction_pct"] = a.get("auction_pct")
        row["auction_volume"] = a.get("auction_volume")
        row["auction_amount"] = a.get("auction_amount")
        row["auction_unmatched"] = a.get("auction_unmatched")
        row["auction_volume_ratio"] = a.get("auction_volume_ratio")
        row["auction_turnover_pct"] = a.get("auction_turnover_pct")
        row["auction_yesterday_ratio_pct"] = a.get("auction_yesterday_ratio_pct")
        row["open_price"] = p.get("open_price") or a.get("open_price")
        row["last_price"] = p.get("last_price") or a.get("last_price")
        row["prev_price"] = p.get("prev_price") or a.get("pre_close_price")
        if row["prev_price"] is None:
            row["prev_price"] = c.get("close")
        if session_closed():
            row["close_price"] = _num(row.get("last_price"))
        else:
            row["close_price"] = None
        attach_close_chg(row)
        if stage == "live":
            row["settle_tag"] = "竞价中" if in_call_auction() else "无对照"
            row["pre_settle_at"] = None
            row["vol_delta"] = None
            row["vol_delta_pct"] = None
            row["unmatched_delta"] = None
            row["price_delta"] = None
            row["settle_strength"] = None
        else:
            attach_settle(row, pre_by.get(ts))
            if pre_tick and not row.get("pre_settle_at"):
                row["pre_settle_at"] = pre_tick.get("t")
        action, reason = classify(row)
        row["action"] = action
        row["reason"] = reason
        vdp = row.get("vol_delta_pct")
        if row.get("auction_strength") is not None and vdp is not None:
            row["auction_strength"] = round(
                float(row["auction_strength"]) * (1.0 + max(-0.5, min(2.0, vdp))), 3
            )
        rows.append(row)
    return _sort_rows(rows)


def enrich(cands, stage):
    auc, auc_meta, px, fund, bench = fetch_snapshots(cands, stage)
    if stage == "live":
        append_tape(auc, auc_meta, stage="live")
    pre = None if stage == "live" else pre_settle_tick()
    rows = rows_from(cands, auc, px, fund, stage, pre)
    return rows, auc_meta, bench, pre


def summarize(rows):
    n = {"buy": 0, "watch": 0, "skip": 0}
    for r in rows:
        n[r["action"]] = n.get(r["action"], 0) + 1
    return n


def tape_meta(pre=None):
    tape = load_tape()
    ticks = tape.get("ticks") or []
    if pre is None:
        pre = pre_settle_tick(tape)
    return {
        "tapeDate": tape.get("date"),
        "tapeTicks": len(ticks),
        "preSettleAt": (pre or {}).get("t"),
    }


def save(payload):
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    # 终态按「买入日」存档，以后才能回放真实 tab（含竞价标签）
    if payload.get("stage") == "final":
        buy_d = now_bj().strftime("%Y-%m-%d")
        os.makedirs(HIST_DIR, exist_ok=True)
        slim = {
            "date": buy_d,
            "screenDate": payload.get("screenDate"),
            "generatedAt": payload.get("generatedAt"),
            "summary": payload.get("summary"),
            "items": [{
                k: r.get(k) for k in (
                    "code", "name", "grade", "action", "reason", "is_etf",
                    "section_keys", "strategies", "open_price", "open_pct",
                    "prev_price", "stop", "auction_tag", "settle_tag",
                    "auction_volume_ratio", "unmatched_ratio", "vol_delta_pct",
                    "close_price", "close_pct",
                )
            } for r in (payload.get("items") or [])],
        }
        with open(os.path.join(HIST_DIR, f"{buy_d}.json"), "w", encoding="utf-8") as f:
            json.dump(slim, f, ensure_ascii=False)
    return OUT_PATH


def load_payload():
    if not os.path.isfile(OUT_PATH):
        return {
            "generatedAt": "",
            "screenDate": "",
            "stage": "final",
            "summary": {"buy": 0, "watch": 0, "skip": 0, "total": 0},
            "items": [],
            "benchmark": None,
            "auctionMeta": {},
            "error": None,
        }
    with open(OUT_PATH, encoding="utf-8") as f:
        return json.load(f)


def reclassify_payload(payload=None):
    """不重新拉 MCP，用已落盘快照 + 当日 tape 重打标签。"""
    payload = payload or load_payload()
    rows = drop_excluded(payload.get("items") or [])
    pre = pre_settle_tick()
    pre_by = (pre or {}).get("by") or {}
    for row in rows:
        if payload.get("stage") == "live":
            row["settle_tag"] = "竞价中" if in_call_auction() else (row.get("settle_tag") or "无对照")
        else:
            attach_settle(row, pre_by.get(row.get("thscode")))
            if pre:
                row["pre_settle_at"] = pre.get("t")
        action, reason = classify(row)
        row["action"] = action
        row["reason"] = reason
        if session_closed() and row.get("close_price") in (None, ""):
            row["close_price"] = _num(row.get("last_price"))
        attach_close_chg(row)
    rows = _sort_rows(rows)
    n = summarize(rows)
    payload["items"] = rows
    payload["summary"] = {**n, "total": len(rows)}
    payload["generatedAt"] = now_bj().strftime("%Y-%m-%d %H:%M")
    payload.update(tape_meta(pre))
    payload["note"] = NOTE
    save(payload)
    return payload


def run(stage="final"):
    watch, extra, err = load_watch_for_auction()
    cands = collect_candidates(watch)
    rows, auc_meta, bench, pre = enrich(cands, stage)
    n = summarize(rows)
    payload = {
        "generatedAt": now_bj().strftime("%Y-%m-%d %H:%M"),
        "stage": stage,
        "summary": {**n, "total": len(rows)},
        "items": rows,
        "benchmark": {
            "date": (bench or {}).get("date"),
            "count": len((bench or {}).get("item") or []),
            "item": (bench or {}).get("item") or [],
        } if bench else None,
        "auctionMeta": auc_meta,
        "error": err,
        "note": NOTE,
        **extra,
        **tape_meta(pre),
    }
    save(payload)
    return payload


def watch_live(progress=None):
    """9:15 起连拍 live，9:25 后拉终态对照最后一拍。非竞价时段直接出终态。"""
    now = now_bj()
    if now.weekday() < 5 and now.time() < AUCTION_OPEN:
        target = now.replace(hour=9, minute=15, second=0, microsecond=0)
        while now_bj() < target:
            left = int((target - now_bj()).total_seconds())
            if progress:
                progress(0, 100, f"等到 09:15 开竞价 {left}s")
            time.sleep(min(5.0, max(0.5, float(left))))
    if not in_call_auction():
        payload = run("final")
        payload["watchSkipped"] = "非竞价时段，未录 live tape；有当日 tape 仍会对照终态"
        payload["note"] = NOTE + payload["watchSkipped"]
        save(payload)
        return payload

    watch, extra, err = load_watch_for_auction()
    cands = collect_candidates(watch)
    px, fund, bench = {}, {}, None
    n_ticks = 0
    while in_call_auction():
        first = n_ticks == 0
        auc, meta, px_n, fund_n, bench_n = fetch_snapshots(
            cands, "live", with_px=first, with_bench=first)
        if first:
            px, fund, bench = px_n, fund_n, bench_n
        tape = append_tape(auc, meta, "live")
        n_ticks = len((tape or {}).get("ticks") or [])
        rows = rows_from(cands, auc, px, fund, "live")
        n = summarize(rows)
        now = now_bj()
        payload = {
            "generatedAt": now.strftime("%Y-%m-%d %H:%M"),
            "stage": "watch",
            "summary": {**n, "total": len(rows)},
            "items": rows,
            "benchmark": {
                "date": (bench or {}).get("date"),
                "count": len((bench or {}).get("item") or []),
                "item": (bench or {}).get("item") or [],
            } if bench else None,
            "auctionMeta": meta,
            "error": err,
            "note": f"竞价连拍中 {now.strftime('%H:%M:%S')} 第 {n_ticks} 拍，9:25 对照终态。",
            **extra,
            **tape_meta(),
        }
        save(payload)
        span = (
            datetime.combine(now.date(), AUCTION_END)
            - datetime.combine(now.date(), AUCTION_OPEN)
        ).total_seconds()
        elapsed = (
            now - datetime.combine(now.date(), AUCTION_OPEN)
        ).total_seconds()
        pct = min(99, int(100 * max(0, elapsed) / span)) if span else 0
        if progress:
            progress(pct, 100, f"{now.strftime('%H:%M:%S')} 第 {n_ticks} 拍")
        left = (
            datetime.combine(now.date(), AUCTION_END) - now
        ).total_seconds()
        if left <= 0:
            break
        time.sleep(min(auction_poll_interval(now), max(0.4, left)))
    if progress:
        progress(99, 100, "拉竞价终态对照")
    return run("final")


def _print(payload):
    s = payload["summary"]
    print(f"[auction_open] {payload['generatedAt']} 数据日={payload['screenDate']} "
          f"stage={payload['stage']} 候选={s['total']} "
          f"可买={s['buy']} 观察={s['watch']} 放弃={s['skip']} "
          f"tape={payload.get('tapeTicks', 0)} 对照={payload.get('preSettleAt') or '-'}")
    print(f"[auction_open] -> {OUT_PATH}")
    if payload.get("watchSkipped"):
        print(f"[auction_open] {payload['watchSkipped']}")
    label = {"buy": "可买", "watch": "观察", "skip": "放弃"}
    print(f"{'结论':<4} {'评':<2} {'竞价':<4} {'结算':<6} {'代码':<8} {'名称':<10} "
          f"{'开盘%':>7} {'量比':>6} {'尾量':>6}  原因")
    for r in payload["items"]:
        pct = r.get("open_pct")
        pcts = f"{pct:+.2f}" if pct is not None else "   -"
        vr = r.get("auction_volume_ratio")
        vrs = f"{vr:.2f}" if vr is not None else "-"
        vdp = r.get("vol_delta_pct")
        vdps = f"{vdp:.0%}" if vdp is not None else "-"
        print(f"{label[r['action']]:<4} {r['grade']:<2} {(r.get('auction_tag') or '-'):<4} "
              f"{(r.get('settle_tag') or '-'):<6} {r['code']:<8} {(r['name'] or '')[:10]:<10} "
              f"{pcts:>7} {vrs:>6} {vdps:>6}  {r['reason']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=("live", "final", "watch"), default="final")
    ap.add_argument("--watch", action="store_true", help="9:15–9:25 连拍后出终态")
    ap.add_argument("--reclassify", action="store_true",
                    help="不拉 MCP，用已落盘快照重打竞价标签")
    args = ap.parse_args()
    if args.reclassify:
        payload = reclassify_payload()
    elif args.watch or args.stage == "watch":
        payload = watch_live()
    else:
        payload = run(stage=args.stage)
    _print(payload)


if __name__ == "__main__":
    main()
