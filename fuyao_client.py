#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""扶摇 REST 客户端。Key 只从环境变量或用户级凭据文件读取，不写进仓库。"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://fuyao.aicubes.cn"
CRED_PATH = os.path.expanduser(
    "~/Library/Application Support/hithink-finance/credentials.env"
)
_KEY = None


def _load_key():
    global _KEY
    if _KEY:
        return _KEY
    key = os.environ.get("HITHINK_FINANCE_API_KEY") or os.environ.get("FUYAO_TOKEN")
    if not key and os.path.isfile(CRED_PATH):
        with open(CRED_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("HITHINK_FINANCE_API_KEY="):
                    key = line.split("=", 1)[1].strip()
                    break
    if not key:
        raise RuntimeError(
            "未找到扶摇 API Key。请配置 HITHINK_FINANCE_API_KEY "
            "或 ~/Library/Application Support/hithink-finance/credentials.env"
        )
    _KEY = key
    return _KEY


def get(path, params=None, retries=3):
    """GET JSON。成功条件: HTTP 200 且 code==0。4001/5xxx 有界重试。"""
    q = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None})
    url = BASE + path + (("?" + q) if q else "")
    last_err = None
    for i in range(retries):
        req = urllib.request.Request(url, headers={"X-api-key": _load_key()})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                body = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace")
            try:
                body = json.loads(raw)
            except json.JSONDecodeError:
                raise RuntimeError(f"HTTP {e.code} {path}: {raw[:200]}") from e
        code = body.get("code")
        if code == 0:
            return body.get("data")
        if code in (4001, 5001, 5002, 5003) and i + 1 < retries:
            time.sleep(1.5 * (i + 1))
            last_err = body
            continue
        raise RuntimeError(
            f"fuyao {path} code={code} {body.get('message')} "
            f"req={body.get('request_id')}"
        )
    raise RuntimeError(f"fuyao retry exhausted: {last_err}")


def chunked(seq, n=100):
    seq = list(seq)
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def auction_snapshot(thscodes, stage="final"):
    """批量竞价快照，每次最多 100 只。返回 thscode -> item。"""
    out = {}
    meta = {"auction_phase": None, "data_status": None, "timestamp": None}
    for batch in chunked(thscodes, 100):
        data = get("/api/a-share/auction/snapshot", {
            "thscodes": ",".join(batch),
            "stage": stage,
        })
        if not data:
            continue
        meta["auction_phase"] = data.get("auction_phase")
        meta["data_status"] = data.get("data_status")
        meta["timestamp"] = data.get("timestamp")
        for it in data.get("item") or []:
            out[it["thscode"]] = it
        time.sleep(0.12)
    return out, meta


def prices_snapshot(thscodes):
    """A 股行情快照，每次最多约按逗号列表批量。"""
    out = {}
    for batch in chunked(thscodes, 100):
        data = get("/api/a-share/prices/snapshot", {
            "thscodes": ",".join(batch),
        })
        if not data:
            continue
        for it in data.get("item") or []:
            out[it["thscode"]] = it
        time.sleep(0.12)
    return out


def fund_snapshot(thscode):
    """单只 ETF/LOF 场内快照。不支持时返回 None。"""
    try:
        data = get("/api/fund/market/snapshot", {"thscode": thscode})
    except RuntimeError as e:
        if "code=3004" in str(e) or "code=3001" in str(e):
            return None
        raise
    items = (data or {}).get("item") or []
    return items[0] if items else data


def auction_benchmark(date=None):
    params = {}
    if date:
        params["date"] = date
    return get("/api/a-share/auction/short-term-benchmark", params)
