#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""盯盘数据后端(纯标准库, 异步任务模型)。

前端 /api 经 Vite 代理到 :5320。接口:
  GET  /api/watch/data                 取最近一次聚合结果
  POST /api/watch/run?key=<变体|all>   异步跑单个策略变体(或全部), 立即返回
  POST /api/cache/update               异步更新大盘K线缓存(全市场重拉)
  GET  /api/jobs                       所有后台任务的进度快照(前端轮询, 刷新页面不丢)
  GET  /api/watch/history              历史命中日期列表
  GET  /api/watch/history?date=<日>    某日命中快照
任务状态存服务端内存, 单用户本地工具足够; 刷新页面靠轮询 /jobs 续上进度。
"""
import json
import os
import re
import subprocess
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import watch_export
import watch_export_30f

PORT = int(os.environ.get("PORT", "5320"))
HERE = watch_export.HERE

# ---- auth stub (accessMode=frontend, 菜单来自前端路由) ----
_USER = {"id": 0, "realName": "盯盘", "roles": ["super"],
         "username": "admin", "homePath": "/watch/board", "avatar": ""}
_TOKEN = "watch-local-token"

# ---- 任务注册表 ----
_jlock = threading.Lock()
JOBS = {}   # key -> {key,label,kind,status,done,total,pct,startedAt,finishedAt,error}


def _job_set(key, **kw):
    with _jlock:
        j = JOBS.setdefault(key, {"key": key})
        j.update(kw)
        if "done" in j and "total" in j and j.get("total"):
            j["pct"] = min(99, int(j["done"] * 100 / j["total"]))
        if kw.get("status") == "done":
            j["pct"] = 100


def _running(key):
    with _jlock:
        return JOBS.get(key, {}).get("status") == "running"


def _run_variant(key):
    if _running(key):
        return
    label = watch_export.VARIANTS[key][1]
    _job_set(key, label=label, kind="variant", status="running",
             done=0, total=0, pct=0, error=None,
             startedAt=watch_export.now_bj().strftime("%H:%M:%S"), finishedAt=None)

    def cb(done, total):
        _job_set(key, done=done, total=total)

    try:
        section = watch_export.run_variant_live(key, cb)
        watch_export.merge_section(section)
        _job_set(key, status="done", done=section["count"] or 1,
                 total=section["count"] or 1,
                 finishedAt=watch_export.now_bj().strftime("%H:%M:%S"),
                 error=section.get("error"))
    except Exception as e:
        _job_set(key, status="error", error=str(e),
                 finishedAt=watch_export.now_bj().strftime("%H:%M:%S"))


def _run_all():
    for key in watch_export.VKEYS:
        _run_variant(key)


def _run_cache_update(fast=False):
    key = "cache"
    if _running(key):
        return
    _job_set(key, label=("快速补最新" if fast else "大盘K线全量"), kind="cache",
             mode=("fast" if fast else "full"), status="running",
             done=0, total=0, pct=0, error=None,
             startedAt=watch_export.now_bj().strftime("%H:%M:%S"), finishedAt=None)
    try:
        if fast:
            code = "import cache_data; cache_data.snapshot_update()"
        else:
            code = ("import os; os.environ['BYPASS_CACHE']='1'; "
                    "import cache_data; cache_data.warmup(max_workers=24)")
        proc = subprocess.Popen(["python3", "-c", code], cwd=HERE,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, bufsize=1)
        note = None
        for line in proc.stdout:
            if "EM_BLOCKED" in line:
                note = line.split("EM_BLOCKED", 1)[1].strip() or "行情源无响应，已跳过，旧数据保留"
            m = re.search(r"cached (\d+)/(\d+)", line)
            if m:
                _job_set(key, done=int(m.group(1)), total=int(m.group(2)))
        proc.wait(timeout=1800)
        _job_set(key, status="done", note=note,
                 finishedAt=watch_export.now_bj().strftime("%H:%M:%S"))
    except Exception as e:
        _job_set(key, status="error", error=str(e),
                 finishedAt=watch_export.now_bj().strftime("%H:%M:%S"))


# ---- 30f (30分钟级别) 任务 ----
def _run_variant_30f(key):
    jk = "m30:" + key
    if _running(jk):
        return
    label = watch_export_30f.VARIANTS_30F[key][1]
    _job_set(jk, label=label, kind="variant30f", status="running",
             done=0, total=0, pct=0, error=None,
             startedAt=watch_export.now_bj().strftime("%H:%M:%S"), finishedAt=None)

    def cb(done, total):
        _job_set(jk, done=done, total=total)

    try:
        section = watch_export_30f.run_variant_live(key, cb)
        watch_export_30f.merge_section(section)
        _job_set(jk, status="done", done=section["count"] or 1,
                 total=section["count"] or 1,
                 finishedAt=watch_export.now_bj().strftime("%H:%M:%S"),
                 error=section.get("error"))
    except Exception as e:
        _job_set(jk, status="error", error=str(e),
                 finishedAt=watch_export.now_bj().strftime("%H:%M:%S"))


def _run_all_30f():
    for key in watch_export_30f.VKEYS_30F:
        _run_variant_30f(key)


def _run_min_update():
    key = "m30:cache"
    if _running(key):
        return
    _job_set(key, label="30分K线刷新", kind="min_cache", status="running",
             done=0, total=0, pct=0, error=None,
             startedAt=watch_export.now_bj().strftime("%H:%M:%S"), finishedAt=None)
    code = "import cache_data; cache_data.warmup_minute(klts=(30,), max_workers=20)"
    try:
        proc = subprocess.Popen(["python3", "-c", code], cwd=HERE,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, bufsize=1)
        for line in proc.stdout:
            m = re.search(r"cached (\d+)/(\d+)", line)
            if m:
                _job_set(key, done=int(m.group(1)), total=int(m.group(2)))
        proc.wait(timeout=1800)
        _job_set(key, status="done",
                 finishedAt=watch_export.now_bj().strftime("%H:%M:%S"))
    except Exception as e:
        _job_set(key, status="error", error=str(e),
                 finishedAt=watch_export.now_bj().strftime("%H:%M:%S"))


def _spawn(target, *args):
    threading.Thread(target=target, args=args, daemon=True).start()


class Handler(BaseHTTPRequestHandler):
    def _send(self, obj, code=200):
        body = json.dumps({"code": 0, "data": obj, "error": None, "message": "ok"},
                          ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _path_query(self):
        u = urlparse(self.path)
        p = u.path
        if p.startswith("/api"):
            p = p[4:]
        return p, parse_qs(u.query)

    def _read_body(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        return self.rfile.read(n) if n else b""

    def do_OPTIONS(self):
        self._send({})

    def do_GET(self):
        p, q = self._path_query()
        if p in ("/watch/data", "/watch"):
            self._send(watch_export.load_payload())
        elif p == "/jobs":
            with _jlock:
                self._send(list(JOBS.values()))
        elif p == "/cache/status":
            self._send(watch_export.cache_status())
        elif p in ("/min/data", "/min/watch"):
            self._send(watch_export_30f.load_payload())
        elif p == "/min/status":
            self._send(watch_export_30f.min_cache_status())
        elif p == "/market/indices":
            klt = (q.get("klt") or ["101"])[0]
            self._send(watch_export.market_indices(klt=klt))
        elif p == "/watch/history":
            if q.get("date"):
                d = watch_export.get_history(q["date"][0])
                self._send(d if d else {"error": "no data"}, 200 if d else 404)
            else:
                self._send(watch_export.list_history())
        elif p == "/user/info":
            self._send(_USER)
        elif p == "/auth/codes":
            self._send([])
        elif p == "/menu/all":
            self._send([])
        elif p in ("/", "/health"):
            self._send({"ok": True})
        else:
            self._send({"error": "not found", "path": p}, 404)

    def do_POST(self):
        p, q = self._path_query()
        self._read_body()
        if p == "/watch/run":
            key = (q.get("key") or ["all"])[0]
            if key == "all":
                _spawn(_run_all)
            elif key in watch_export.VARIANTS:
                _spawn(_run_variant, key)
            else:
                return self._send({"error": "bad key"}, 400)
            self._send({"started": key})
        elif p == "/cache/update":
            fast = (q.get("mode") or [""])[0] == "fast"
            _spawn(_run_cache_update, fast)
            self._send({"started": "cache", "mode": "fast" if fast else "full"})
        elif p == "/min/run":
            key = (q.get("key") or ["all"])[0]
            if key == "all":
                _spawn(_run_all_30f)
            elif key in watch_export_30f.VARIANTS_30F:
                _spawn(_run_variant_30f, key)
            else:
                return self._send({"error": "bad key"}, 400)
            self._send({"started": key})
        elif p == "/min/update":
            _spawn(_run_min_update)
            self._send({"started": "m30:cache"})
        elif p == "/auth/login":
            self._send({**_USER, "accessToken": _TOKEN})
        elif p == "/auth/refresh":
            self._send({"data": _TOKEN, "status": 0})
        elif p == "/auth/logout":
            self._send(None)
        else:
            self._send({"error": "not found", "path": p}, 404)

    def log_message(self, fmt, *args):
        pass


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"[watch_server] 盯盘后端 http://127.0.0.1:{PORT}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[watch_server] 已停止")


if __name__ == "__main__":
    main()
