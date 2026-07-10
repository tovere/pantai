#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Local cache for Eastmoney A-share universe and daily K lines."""
import json
import os
import re
import subprocess
import tempfile
import time
from datetime import date
from pathlib import Path

UA = "Mozilla/5.0"
CACHE_DIR = Path(os.environ.get("MA_CACHE_DIR", "data_cache"))
UNIVERSE_PATH = CACHE_DIR / "universe.json"
ETF_UNIVERSE_PATH = CACHE_DIR / "etf_universe.json"
DAILY_DIR = CACHE_DIR / "daily"
MIN_DIR = CACHE_DIR / "minute"
MIN_KLTS = (5, 30)  # 缓存的分钟级别
DAILY_BEG = os.environ.get("MA_DAILY_BEG", "20240101")  # 日线起点(默认2024, 可env覆盖)
BYPASS_CACHE = os.environ.get("BYPASS_CACHE", "0") == "1"
# 默认纯东财; 新浪源(量=股/额=估算/复权存疑)只在显式开启时作应急整段替换, 不掺入拼接
ALLOW_SINA = os.environ.get("ALLOW_SINA", "0") == "1"


def _get(url, tries=4, timeout=10):
    for _ in range(tries):
        p = subprocess.run(
            ["curl", "--http1.1", "-s", "-m", str(timeout), "-A", UA, url],
            capture_output=True,
            text=True,
        )
        if p.returncode == 0 and p.stdout:
            return p.stdout
    return ""


def _get_json(url, tries=4, timeout=10):
    for _ in range(tries):
        try:
            return json.loads(_get(url, tries=1, timeout=timeout))
        except json.JSONDecodeError:
            continue
    return {}


def _atomic_write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _read_json(path):
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def universe(force=False):
    today = date.today().isoformat()
    cached = None if (force or BYPASS_CACHE) else _read_json(UNIVERSE_PATH)
    if cached and cached.get("date") == today and cached.get("items"):
        return [tuple(x) for x in cached["items"]]

    out, pn = [], 1
    while True:
        url = (
            f"https://push2delay.eastmoney.com/api/qt/clist/get?pn={pn}&pz=100&po=1&np=1"
            "&fltt=2&invt=2&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"
            "&fields=f12,f14"
        )
        data = _get_json(url).get("data")
        if not data or not data.get("diff"):
            break
        for item in data["diff"]:
            code, name = item["f12"], item["f14"]
            if "ST" in name or "退" in name or "PT" in name:
                continue
            if code.startswith("688") or code.startswith("3"):
                continue
            if code.startswith("6"):
                out.append((code, name, f"1.{code}"))
            elif code.startswith("0"):
                out.append((code, name, f"0.{code}"))
        if pn * 100 >= data.get("total", 0):
            break
        pn += 1
    if out:
        _atomic_write_json(UNIVERSE_PATH, {"date": today, "items": out})
        return out
    # 网络失败/空 → 回退到旧缓存(避免日期滚动+网络抖动清空股票池)
    if cached and cached.get("items"):
        return [tuple(x) for x in cached["items"]]
    return out


def _fetch_etf_list_em():
    """东财 ETF 板块 b:MK0021 翻页。返回 (items, complete)。complete=翻到 total。
    易限流、翻页可能中途断; 断了 complete=False, 交由上层丢弃残缺结果。"""
    out, pn, total, complete = [], 1, 0, False
    while True:
        url = (
            f"https://push2.eastmoney.com/api/qt/clist/get?pn={pn}&pz=100&po=1&np=1"
            "&fltt=2&invt=2&fid=f6&fs=b:MK0021&fields=f12,f14"
        )
        data = _get_json(url).get("data")
        if not data or not data.get("diff"):
            break
        total = data.get("total", 0) or total
        for item in data["diff"]:
            code, name = item["f12"], item["f14"]
            if code.startswith("5"):
                out.append((code, name, f"1.{code}"))
            elif code.startswith("1"):
                out.append((code, name, f"0.{code}"))
        if total and pn * 100 >= total:
            complete = True
            break
        pn += 1
    return out, complete


def _fetch_etf_list_sina():
    """新浪 ETF 列表(备用源, 东财限流时用; 覆盖比东财板块更全)。返回 (items, complete)。
    symbol 形如 sh511360/sz159915 -> secid 1.xxx/0.xxx。"""
    base = ("https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
            "Market_Center.")
    cnt = _get(base + "getHQNodeStockCount?node=etf_hq_fund")
    try:
        total = int(cnt.strip().strip('"'))
    except (ValueError, AttributeError):
        total = 0
    if total <= 0:
        return [], False
    out, num = [], 100
    for pg in range(1, (total + num - 1) // num + 1):
        raw = _get(base + f"getHQNodeData?page={pg}&num={num}&sort=amount&asc=0"
                          "&node=etf_hq_fund&symbol=&_s_r_a=page")
        try:
            arr = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            arr = None
        if not arr:
            break
        for it in arr:
            sym, code, name = it.get("symbol", ""), it.get("code", ""), it.get("name", "")
            if not code:
                continue
            if sym.startswith("sh"):
                out.append((code, name, f"1.{code}"))
            elif sym.startswith("sz"):
                out.append((code, name, f"0.{code}"))
    return out, (len(out) >= total * 0.9)


def etf_universe(force=False):
    """场内 ETF 列表。缓存到 etf_universe.json。secid: 5/56/58->沪(1.); 15/16->深(0.)。

    东财优先, 限流/残缺则退新浪。只有'完整拉取、且不比旧缓存短'才允许覆盖落盘;
    残缺结果一律丢弃并回退到上一份完整列表 —— 否则会把上千只的 ETF 池截断成一两百只,
    导致筛选秒退、命中恒 0(快速刷新内部会调用本函数, 会连锁触发此重取)。"""
    disk = _read_json(ETF_UNIVERSE_PATH)
    prev = [tuple(x) for x in disk["items"]] if (disk and disk.get("items")) else []
    today = date.today().isoformat()
    # 今天的缓存且上次已完整拉取 -> 直接用, 不再打网络
    if not (force or BYPASS_CACHE) and disk and disk.get("date") == today \
            and disk.get("complete") and prev:
        return prev

    out, complete = _fetch_etf_list_em()
    if not complete:  # 东财限流/残缺 -> 退新浪(更全更稳)
        s_out, s_complete = _fetch_etf_list_sina()
        if len(s_out) > len(out):
            out, complete = s_out, s_complete

    # 只有完整且不短于旧缓存才覆盖; 否则保留上一份完整列表, 绝不用残缺列表截断池子
    if out and complete and len(out) >= len(prev):
        _atomic_write_json(ETF_UNIVERSE_PATH,
                           {"date": today, "complete": True, "items": out})
        return out
    if prev:
        return prev
    # 从未有过缓存: 只能先用这次拿到的(可能不完整), 不标 complete, 下次继续补全
    if out:
        _atomic_write_json(ETF_UNIVERSE_PATH,
                           {"date": today, "complete": complete, "items": out})
    return out


def _daily_path(secid):
    return DAILY_DIR / f"{secid}.json"


def _fetch_daily(secid, beg=None, allow_sina=True):
    beg = beg or DAILY_BEG
    url = (
        "https://push2his.eastmoney.com/api/qt/stock/kline/get"
        f"?secid={secid}&fields1=f1,f2,f3,f4,f5,f6"
        "&fields2=f51,f52,f53,f54,f55,f56,f57&klt=101&fqt=1"
        f"&beg={beg}&end=20500101"
    )
    data = _get_json(url, tries=3, timeout=8).get("data")
    if not data or not data.get("klines"):
        # 新浪应急源默认关闭(ALLOW_SINA); 且拼接场景(allow_sina=False)永不走新浪, 避免混源
        return _fetch_sina_daily(secid) if (allow_sina and ALLOW_SINA) else None
    return data["klines"]


def _fetch_sina_daily(secid, datalen=700):
    market, code = secid.split(".", 1)
    prefix = "sh" if market == "1" else "sz"
    symbol = f"{prefix}{code}"
    url = (
        "https://quotes.sina.cn/cn/api/jsonp.php/var%20_"
        f"{symbol}_day=/CN_MarketDataService.getKLineData?symbol={symbol}"
        f"&scale=240&ma=no&datalen={datalen}"
    )
    text = _get(url, tries=3, timeout=8)
    m = re.search(r"=\((.*)\);", text, re.S)
    if not m:
        return None
    try:
        rows = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    klines = []
    for row in rows:
        try:
            close = float(row["close"])
            volume = float(row.get("volume") or 0)
            amount = close * volume
            klines.append(
                ",".join(
                    [
                        row["day"],
                        row["open"],
                        row["close"],
                        row["high"],
                        row["low"],
                        str(volume),
                        f"{amount:.3f}",
                    ]
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return klines or None


def daily_kline(secid, force=False, expected_date=None):
    path = _daily_path(secid)
    expected_date = expected_date or os.environ.get("SCREEN_DATE")
    cached = None if (force or BYPASS_CACHE) else _read_json(path)
    if cached and cached.get("klines"):
        last_date = cached["klines"][-1].split(",", 1)[0]
        if not expected_date or last_date >= expected_date:
            return [row.split(",") for row in cached["klines"]]

    # 筛选阶段(CACHE_ONLY=1): 只读缓存, 绝不逐只现拉。有缓存就用(旧数据由筛选器的
    # 日期门自行剔除), 没缓存就跳过 —— 避免行情源限流时把单次筛选拖到几十秒。
    if os.environ.get("CACHE_ONLY") == "1":
        if cached and cached.get("klines"):
            return [row.split(",") for row in cached["klines"]]
        return None

    klines = _fetch_daily(secid)
    if not klines and cached and cached.get("klines"):
        return [row.split(",") for row in cached["klines"]]
    if not klines:
        return None
    _atomic_write_json(path, {"secid": secid, "fqt": 1, "klt": 101, "klines": klines})
    return [row.split(",") for row in klines]


def daily_update_recent(secid, beg=None):
    """增量更新: 只拉最近窗口(beg起)并合并进现有缓存, 不重下2024至今全history。
    包很小、请求轻(防反爬); 无本地缓存的票退回全量。⚠️ 前复权当天除权除息可能短暂接不上。"""
    from datetime import timedelta

    beg = beg or (date.today() - timedelta(days=20)).strftime("%Y%m%d")
    path = _daily_path(secid)
    cached = _read_json(path)
    if not cached or not cached.get("klines"):
        return daily_kline(secid, force=True)
    fresh = _fetch_daily(secid, beg=beg, allow_sina=False)  # 只走东财小包, 不 fallback 新浪重源
    if not fresh:
        return [row.split(",") for row in cached["klines"]]
    merged = _merge_klines(cached["klines"], fresh)
    _atomic_write_json(path, {"secid": secid, "fqt": 1, "klt": 101, "klines": merged})
    return [row.split(",") for row in merged]


def _min_path(secid, klt):
    return MIN_DIR / str(klt) / f"{secid}.json"


def _fetch_min(secid, klt, beg="20250101"):
    """分钟K线(klt=5/30/...)。东财接口只回最近约1.5个月滚动窗口, beg 基本无效。
    字段与日线一致: f51..f57 -> 时间,开,收,高,低,量,额 (时间形如 'YYYY-MM-DD HH:MM')。"""
    url = (
        "https://push2his.eastmoney.com/api/qt/stock/kline/get"
        f"?secid={secid}&fields1=f1,f2,f3,f4,f5,f6"
        "&fields2=f51,f52,f53,f54,f55,f56,f57"
        f"&klt={klt}&fqt=1&beg={beg}&end=20500101"
    )
    data = _get_json(url, tries=3, timeout=8).get("data")
    if not data or not data.get("klines"):
        return None
    return data["klines"]


def _merge_klines(old, new):
    """按时间键(逗号前)去重合并, 新数据覆盖旧, 时间字符串可字典序排序。
    使分钟历史能突破接口 1.5 月窗口持续累积。"""
    merged = {}
    for row in old or []:
        merged[row.split(",", 1)[0]] = row
    for row in new or []:
        merged[row.split(",", 1)[0]] = row
    return [merged[k] for k in sorted(merged)]


def min_kline(secid, klt=5, force=False, expected_date=None):
    """分钟K线缓存。返回形状同 daily_kline: list[list[str]]
    每行 [时间,开,收,高,低,量,额] (r[1]=开 r[2]=收 r[3]=高 r[4]=低 r[5]=量 r[6]=额)。
    与 daily_kline 完全独立, 不影响任何现有日线策略。"""
    path = _min_path(secid, klt)
    expected_date = expected_date or os.environ.get("SCREEN_DATE")
    cached = None if (force or BYPASS_CACHE) else _read_json(path)
    if cached and cached.get("klines"):
        last_date = cached["klines"][-1].split(",", 1)[0][:10]
        if not expected_date or last_date >= expected_date:
            return [row.split(",") for row in cached["klines"]]

    fresh = _fetch_min(secid, klt)
    if not fresh:
        if cached and cached.get("klines"):
            return [row.split(",") for row in cached["klines"]]
        return None
    merged = _merge_klines(cached.get("klines") if cached else None, fresh)
    _atomic_write_json(path, {"secid": secid, "fqt": 1, "klt": klt, "klines": merged})
    return [row.split(",") for row in merged]


def warmup(max_workers=10):
    from concurrent.futures import ThreadPoolExecutor, as_completed

    # 探测: 东财空且新浪未开 -> 放弃, 不做全市场无谓请求, 旧数据保留
    if _fetch_daily("0.000001", allow_sina=True) is None:
        print("  cached 0/0", flush=True)
        print("EM_BLOCKED 东财限流中, 全量已跳过, 旧数据保留(应急可开新浪: ALLOW_SINA=1)", flush=True)
        return
    items = universe() + etf_universe()  # ETF 也要刷, 否则其日线停在旧日期 -> 筛选 D[i]!=TODAY 全挡 -> ETF 恒空
    done = ok = 0
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(daily_kline, sec): sec for _, _, sec in items}
        for fut in as_completed(futs):
            done += 1
            if fut.result():
                ok += 1
            if done % 500 == 0:
                print(f"  cached {done}/{len(items)} ok={ok}", flush=True)
    print(f"cache warmup done: {ok}/{len(items)}")


CLIST_STOCK_FS = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"
CLIST_ETF_FS = "b:MK0021"
_SNAP_FIELDS = "f12,f13,f17,f2,f15,f16,f5,f6"  # 代码,市场,今开,现价,最高,最低,量(手),额(元)


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _clist_snapshot(fs):
    """分页抓 clist 今日快照(每次100只)。返回 diff 汇总; 空=被限。"""
    out, pn = [], 1
    while True:
        url = (
            f"https://push2.eastmoney.com/api/qt/clist/get?pn={pn}&pz=100&po=1&np=1"
            f"&fltt=2&invt=2&fs={fs}&fields={_SNAP_FIELDS}"
        )
        data = _get_json(url).get("data")
        if not data or not data.get("diff"):
            break
        out.extend(data["diff"])
        if pn * 100 >= data.get("total", 0):
            break
        pn += 1
    return out


# ---- 盘中快照源(可切换): 默认腾讯 qt 批量; 东财 clist 保留 ----

def _tx_code(secid):
    mkt, code = secid.split(".", 1)
    return ("sh" if mkt == "1" else "sz") + code


def _get_gbk(url, tries=3, timeout=10):
    """腾讯/新浪返回 GBK, 取原始字节自行解码(数字字段为ASCII, 不受名称乱码影响)。"""
    for _ in range(tries):
        p = subprocess.run(["curl", "--http1.1", "-s", "-m", str(timeout), "-A", UA, url],
                           capture_output=True)
        if p.returncode == 0 and p.stdout:
            return p.stdout.decode("gbk", "ignore")
    return ""


def _snapshot_rows_tencent(include_etf=True, batch=300):
    """腾讯 qt 批量实时(一次~300只)。日期取自返回时间戳, 无需东财。量=手/额=元。
    返回 (trade_date, [ {secid,o,c,h,l,v,a} ])。"""
    items = universe() + (etf_universe() if include_etf else [])
    secids = [sec for _, _, sec in items]
    out, trade_date = [], None
    for i in range(0, len(secids), batch):
        codes = ",".join(_tx_code(s) for s in secids[i:i + batch])
        for line in _get_gbk(f"https://qt.gtimg.cn/q={codes}").split("\n"):
            if '="' not in line:
                continue
            sym = line.split("=", 1)[0].strip()[2:]  # v_sh600519 -> sh600519
            f = line.split('="', 1)[1].rstrip('";').strip().split("~")
            if len(f) < 36 or len(sym) < 3:
                continue
            try:
                o, c, h, l = float(f[5]), float(f[3]), float(f[33]), float(f[34])
                v = float(f[6])                      # 手
                a = float(f[35].split("/")[2])       # 元
                t = f[30]
            except (ValueError, IndexError):
                continue
            if c <= 0:
                continue
            secid = ("1." if sym[:2] == "sh" else "0.") + sym[2:]
            out.append({"secid": secid, "o": o, "c": c, "h": h, "l": l, "v": v, "a": a})
            if t and len(t) >= 8:
                trade_date = f"{t[:4]}-{t[4:6]}-{t[6:8]}"
    return trade_date, out


def _snapshot_rows_clist(include_etf=True):
    """东财 clist 批量(保留)。日期靠参考票 kline; 被限则 date=None。量=手/额=元。"""
    raw = _fetch_daily("0.000001", allow_sina=True)
    trade_date = raw[-1].split(",", 1)[0] if raw else None
    diff = _clist_snapshot(CLIST_STOCK_FS)
    if include_etf:
        diff += _clist_snapshot(CLIST_ETF_FS)
    out = []
    for it in diff:
        code, mkt = it.get("f12"), it.get("f13")
        o, c, h, l = _num(it.get("f17")), _num(it.get("f2")), _num(it.get("f15")), _num(it.get("f16"))
        v, a = _num(it.get("f5")), _num(it.get("f6"))
        if code and mkt is not None and None not in (o, c, h, l) and c > 0:
            out.append({"secid": f"{mkt}.{code}", "o": o, "c": c, "h": h, "l": l,
                        "v": v or 0, "a": a or 0})
    return trade_date, out


def _row_vol_scale(klines, trade_date, r):
    """逐只校准: 该票缓存量单位(股/手)可能不同(个股常为股, ETF常为手)。
    用该票'最近一根非今日历史bar'的 量/(额÷价) 对比快照(手), 得到把快照量对齐到本票缓存的系数。"""
    try:
        base = None
        for row in reversed(klines):
            if row.split(",", 1)[0] != trade_date:
                base = row.split(",")
                break
        if not base:
            return 1.0
        bc, bv, ba = float(base[2]), float(base[5]), float(base[6])
        ratio = (bv / (ba / bc)) / (r["v"] / (r["a"] / r["c"]))
        return 100.0 if 30 < ratio < 300 else 1.0  # 不确定就用1(价格已准, 量宁可不缩)
    except Exception:
        return 1.0


def snapshot_update(include_etf=True, source=None):
    """快速刷新: 批量实时快照更新每只票的'今日bar'(只改最新一根, 历史不动)。
    source: 'tencent'(默认, 不受东财限流) / 'clist'(东财, 保留)。量按缓存单位自动校准。"""
    source = source or os.environ.get("SNAPSHOT_SOURCE", "tencent")
    if source == "clist":
        trade_date, rows = _snapshot_rows_clist(include_etf)
        blocked_msg = "东财限流中, 已跳过本次快速刷新, 旧数据保留"
    else:
        source = "tencent"
        trade_date, rows = _snapshot_rows_tencent(include_etf)
        blocked_msg = "腾讯行情源无响应, 已跳过本次快速刷新, 旧数据保留"

    if not rows or not trade_date:
        print("  cached 0/0", flush=True)
        print(f"EM_BLOCKED {blocked_msg}", flush=True)
        return {"blocked": True, "updated": 0, "source": source}

    print(f"  source={source} (逐只校准量单位)", flush=True)
    total, done, updated = len(rows), 0, 0
    print(f"  cached 0/{total}", flush=True)
    for r in rows:
        done += 1
        cached = _read_json(_daily_path(r["secid"]))
        kl = cached.get("klines") if cached else None
        if kl:
            scale = _row_vol_scale(kl, trade_date, r)  # 逐只: 该票缓存单位 vs 快照(手)
            bar = (f"{trade_date},{r['o']},{r['c']},{r['h']},{r['l']},"
                   f"{r['v'] * scale:.0f},{r['a']:.3f}")
            merged = _merge_klines(kl, [bar])
            _atomic_write_json(_daily_path(r["secid"]),
                               {"secid": r["secid"], "fqt": 1, "klt": 101, "klines": merged})
            updated += 1
        if done % 1000 == 0 or done == total:
            print(f"  cached {done}/{total} ok={updated}", flush=True)
    print(f"cache snapshot done: {updated}/{total} 交易日{trade_date} 源={source}", flush=True)
    return {"updated": updated, "total": total, "trade_date": trade_date, "source": source}


def warmup_recent(max_workers=10, days=20, min_age_sec=120):
    """快速增量: 全市场只拉'最近 days 天'小包并合并 —— 会覆盖当天bar, 所以盘中反复点能刷新最新价。
    只跳过'min_age_sec 秒内刚拉过'的票(防重复点击空转); 东财被限时保留旧缓存不砸新浪(轻)。
    请求数≈全市场, 但每个是小包(约十几根 vs 全量700根)、更快, 且无前复权全量重写。进度格式同 warmup。"""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from datetime import timedelta

    beg = (date.today() - timedelta(days=days)).strftime("%Y%m%d")
    # 先探测东财是否被限流(参考票小包): 空=限流, 立即放弃, 不做无谓的全市场请求, 旧缓存保留
    if _fetch_daily("0.000001", beg=beg, allow_sina=False) is None:
        print("  cached 0/0", flush=True)
        print("EM_BLOCKED 东财限流中, 已跳过本次快速刷新, 旧数据保留", flush=True)
        return
    items = universe() + etf_universe()  # ETF 也要刷, 与 warmup/snapshot 保持一致, 否则 ETF 日线滞后 -> 恒空
    now = time.time()

    def _recently_pulled(secid):
        try:
            return (now - _daily_path(secid).stat().st_mtime) < min_age_sec
        except OSError:
            return False

    todo = [sec for _, _, sec in items if not _recently_pulled(sec)]
    total = len(todo)
    skipped = len(items) - total
    print(f"  cached 0/{total}", flush=True)  # 让前端立即拿到总数
    done = ok = 0
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(daily_update_recent, sec, beg): sec for sec in todo}
        for fut in as_completed(futs):
            done += 1
            if fut.result():
                ok += 1
            if done % 200 == 0 or done == total:
                print(f"  cached {done}/{total} ok={ok}", flush=True)
    print(f"cache fast-update done: {ok}/{total} (跳过 {skipped} 只刚拉过)")


def warmup_minute(klts=MIN_KLTS, max_workers=10):
    from concurrent.futures import ThreadPoolExecutor, as_completed

    items = universe()
    for klt in klts:
        done = ok = 0
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futs = {ex.submit(min_kline, sec, klt): sec for _, _, sec in items}
            for fut in as_completed(futs):
                done += 1
                if fut.result():
                    ok += 1
                if done % 500 == 0:
                    print(f"  [klt={klt}] cached {done}/{len(items)} ok={ok}", flush=True)
        print(f"minute warmup done klt={klt}: {ok}/{len(items)}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] in ("minute", "min"):
        klts = [int(x) for x in sys.argv[2:]] or list(MIN_KLTS)
        warmup_minute(klts)
    else:
        warmup()
