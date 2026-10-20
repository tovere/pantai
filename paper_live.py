"""Timestamped real-time paper executor. Standalone worker, SQLite audit trail."""
import json
import time
import sqlite3
from datetime import datetime
from pathlib import Path
from contextlib import contextmanager
import cache_data
import paper_agent as paper

DB = Path(__file__).resolve().parent / "data_cache" / "paper_live.sqlite3"


@contextmanager
def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB), timeout=20)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS quotes(code TEXT, stamp TEXT, received TEXT, body TEXT, PRIMARY KEY(code,stamp));
    CREATE TABLE IF NOT EXISTS orders(id TEXT PRIMARY KEY, state TEXT, body TEXT);
    CREATE TABLE IF NOT EXISTS events(time TEXT, kind TEXT, body TEXT);
    CREATE TABLE IF NOT EXISTS feature_states(id TEXT PRIMARY KEY, body TEXT);
    CREATE TABLE IF NOT EXISTS heartbeat(id INTEGER PRIMARY KEY, body TEXT);
    """)
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def quotes(codes):
    output = {}
    symbols = ",".join(("sh" if c.startswith(("6","5")) else "sz")+c for c in sorted(codes))
    if not symbols:
        return output
    raw = cache_data._get_gbk("https://qt.gtimg.cn/q="+symbols, tries=1, timeout=8)
    for line in raw.splitlines():
        if '="' not in line:
            continue
        fields = line.split('="',1)[1].rstrip('";').split("~")
        try:
            code, last, prev = fields[2], float(fields[3]), float(fields[4])
            stamp = datetime.strptime(fields[30], "%Y%m%d%H%M%S").replace(tzinfo=paper.TZ)
            if last <= 0 or prev <= 0 or not 0 <= (paper.now()-stamp).total_seconds() <= 30:
                continue
            output[code] = {"code":code,"last":last,"prev":prev,"bid":float(fields[9]),
                            "ask":float(fields[19]),"stamp":stamp.isoformat(),"source":"tencent"}
        except (ValueError,IndexError):
            continue
    return output


def tick():
    stamp = paper.now()
    session = stamp.weekday()<5 and ("09:30" <= stamp.strftime("%H:%M") < "11:30" or "13:00" <= stamp.strftime("%H:%M") < "15:00")
    with paper.connect():
        pass
    with connect() as live:
        live.execute("INSERT OR REPLACE INTO heartbeat VALUES(1,?)",(json.dumps({"time":stamp.isoformat(),"session":session}),))
        if not session:
            return
        if not paper.LOCK.acquire(False):
            return
        try:
            # Order transitions and account changes share a single SQLite transaction.
            live.execute("ATTACH DATABASE ? AS accountdb", (str(paper.DB),))
            with live:
                ledger = live
                row = live.execute("SELECT body FROM accountdb.state WHERE id=1").fetchone()
                state = json.loads(row[0]) if row else paper.initial_state()
                state["accounts"].setdefault("linkage", {"cash":paper.INITIAL,"positions":{},"orders":[],"curve":[],"trades":[]})
                account = state["accounts"]["linkage"]
                # No overnight catch-up of missed real-time orders.
                codes = set(account["positions"])
                for order in account["orders"] + account.get("watchlist", []):
                    codes.add(order["code"])
                    codes.update(order.get("conditions", {}).get("peers", []))
                    if order.get("linkage"):
                        codes.add(order["linkage"]["leader"])
                batch = {code:q for code,q in quotes(codes).items()
                         if 0 <= (stamp-datetime.fromisoformat(q["stamp"])).total_seconds() <= 30}
                live.execute("INSERT OR REPLACE INTO heartbeat VALUES(1,?)",(json.dumps({"time":stamp.isoformat(),"session":session,"watching":len(codes),"fresh":len(batch),"source":"tencent"}),))
                for q in batch.values():
                    live.execute("INSERT OR IGNORE INTO quotes VALUES(?,?,?,?)",(q["code"],q["stamp"],stamp.isoformat(),json.dumps(q)))
                from paper_features import advance
                from paper_divergence import valid_session
                trackers = {o["date"]+":"+o["code"]:o for o in account.get("watchlist", [])}
                trackers.update({o["date"]+":"+o["code"]:o for o in account["orders"] if o.get("conditions")})
                features = {}
                for tracker_id, tracker in trackers.items():
                    conditions = tracker["conditions"]
                    saved_feature = live.execute("SELECT body FROM feature_states WHERE id=?",(tracker_id,)).fetchone()
                    previous = json.loads(saved_feature[0]) if saved_feature else None
                    if stamp.date().isoformat() <= conditions["signalDate"]:
                        continue
                    if not valid_session(conditions,stamp.date().isoformat()):
                        feature = {"state":"expired","reason":"超出次一交易日","time":stamp.isoformat()}
                    else:
                        feature = advance(conditions,batch.get(tracker["code"]),batch,previous,stamp)
                    feature.update(code=tracker["code"],name=tracker["name"],signalDate=tracker["date"])
                    features[tracker_id]=feature
                    live.execute("INSERT OR REPLACE INTO feature_states VALUES(?,?)",(tracker_id,json.dumps(feature)))
                    if not previous or previous.get("state") != feature["state"]:
                        live.execute("INSERT INTO events VALUES(?,?,?)",(stamp.isoformat(),"feature_change",json.dumps({"id":tracker_id,"before":previous.get("state") if previous else None,"after":feature["state"],"reason":feature["reason"]})))
                # A held position's stop can trigger during the session, subject to T+1.
                for code,pos in account["positions"].items():
                    q=batch.get(code)
                    if (q and pos["date"]<stamp.date().isoformat() and q["last"]<=pos["stop"]
                            and not any(o["code"]==code and o["action"]=="sell" for o in account["orders"])):
                        account["orders"].append({"date":stamp.date().isoformat(),"code":code,"name":pos["name"],
                            "action":"sell","reason":"盘中触发退出参考价","intraday":True})
                remaining=[]
                for order in account["orders"]:
                    order_id = "linkage:"+order["date"]+":"+order["code"]+":"+order["action"]
                    saved = live.execute("SELECT state,body FROM orders WHERE id=?",(order_id,)).fetchone()
                    if saved and saved["state"] in ("filled","cancelled","expired"):
                        # Never replay a terminal order after worker restart.
                        continue
                    if order["date"] >= stamp.date().isoformat() and not order.get("intraday"):
                        remaining.append(order);continue
                    conditions = order.get("conditions")
                    if conditions:
                        from paper_divergence import valid_session
                        if not valid_session(conditions, stamp.date().isoformat()):
                            live.execute("INSERT OR REPLACE INTO orders VALUES(?,?,?)",(order_id,"expired",json.dumps({**order,"event":"仅次一交易日有效"})))
                            continue
                    age = (stamp.date()-datetime.fromisoformat(order["date"]).date()).days
                    if age > 4:
                        live.execute("INSERT OR REPLACE INTO orders VALUES(?,?,?)",(order_id,"expired",json.dumps({**order,"event":"计划超过有效期"})))
                        live.execute("INSERT INTO events VALUES(?,?,?)",(stamp.isoformat(),"expired",json.dumps({"id":order_id,"reason":"计划超过有效期"})))
                        continue
                    if saved and saved["state"] == "submitted" and (stamp-datetime.fromisoformat(json.loads(saved["body"])["submittedAt"])).total_seconds()>60:
                        live.execute("INSERT OR REPLACE INTO orders VALUES(?,?,?)",(order_id,"expired",saved["body"]))
                        live.execute("INSERT INTO events VALUES(?,?,?)",(stamp.isoformat(),"expired",json.dumps({"id":order_id,"reason":"报价中断或委托超时"})))
                        continue
                    quote = batch.get(order["code"])
                    if not quote:
                        remaining.append(order);continue
                    status = saved["state"] if saved else "planned"
                    body = json.loads(saved["body"]) if saved else dict(order)
                    if saved and status == "submitted" and (stamp-datetime.fromisoformat(body["submittedAt"])).total_seconds()>60:
                        status = "expired"
                    if conditions:
                        feature = features.get(order["date"]+":"+order["code"], {})
                        if feature.get("state") == "invalidated" or (status == "submitted" and feature.get("state") != "confirmed"):
                            live.execute("INSERT OR REPLACE INTO orders VALUES(?,?,?)",(order_id,"cancelled",json.dumps({**order,"event":feature.get("reason","确认失效")})))
                            live.execute("INSERT INTO events VALUES(?,?,?)",(stamp.isoformat(),"cancelled",json.dumps({"id":order_id,"reason":feature.get("reason")})))
                            continue
                        if feature.get("state") != "confirmed":
                            remaining.append(order);continue
                    if status == "planned":
                        relation = order.get("linkage")
                        leader = batch.get(relation["leader"]) if relation else None
                        if relation and not leader:
                            remaining.append(order);continue
                        allowed = True
                        if relation:
                            a = leader["last"]/leader["prev"]-1
                            b = quote["last"]/quote["prev"]-1
                            allowed = relation["minLeaderGap"]<=a<=relation["maxLeaderGap"] and relation["minFollowerGap"]<=b<=relation["maxFollowerGap"]
                        if not allowed:
                            remaining.append(order);continue
                        status = "submitted"
                        body["submittedAt"] = quote["stamp"]
                        body["event"] = "分歧突破及行业样本转强触发" if conditions else "A/B实时价格条件触发"
                    elif status == "submitted" and quote["stamp"] > body["submittedAt"]:
                        relation = order.get("linkage")
                        if relation:
                            leader = batch.get(relation["leader"])
                            if not leader:
                                remaining.append(order);continue
                            a=leader["last"]/leader["prev"]-1
                            b=quote["last"]/quote["prev"]-1
                            if not (relation["minLeaderGap"]<=a<=relation["maxLeaderGap"] and relation["minFollowerGap"]<=b<=relation["maxFollowerGap"]):
                                live.execute("INSERT OR REPLACE INTO orders VALUES(?,?,?)",(order_id,"cancelled",json.dumps(body)))
                                live.execute("INSERT INTO events VALUES(?,?,?)",(stamp.isoformat(),"cancelled",json.dumps({"id":order_id,"reason":"成交前A/B条件失效"})))
                                continue
                        price = quote["ask"] if order["action"]=="buy" else quote["bid"]
                        pos = account["positions"].get(order["code"])
                        if price <= 0:
                            remaining.append(order);continue
                        if order["action"]=="buy":
                            if price>=round(quote["prev"]*1.1,2)-.01 or price>order["max_price"] or price<=order["stop"] or pos or len(account["positions"])>=5:
                                status="cancelled"
                            else:
                                price*=1.001
                                qty=int(max(0,min(account["cash"],paper.equity(account)*order["weight"])-5)/(price*1.001))//100*100
                                fee=max(5,qty*price*.001)
                                if qty<=0 or qty*price+fee>account["cash"] or price>order["max_price"]:
                                    status="cancelled"
                                else:
                                    account["cash"]-=qty*price+fee
                                    account["positions"][order["code"]]={"code":order["code"],"name":order["name"],"qty":qty,"cost":price+fee/qty,"mark":price,"date":stamp.date().isoformat(),"stop":order["stop"],"reason":order["reason"]}
                                    status="filled"
                        elif pos and pos["date"]<stamp.date().isoformat() and price>round(quote["prev"]*.9,2)+.01:
                            price*=.999
                            qty=pos["qty"];fee=max(5,qty*price*.001)
                            account["cash"]+=qty*price-fee
                            del account["positions"][order["code"]]
                            status="filled"
                        if status=="filled":
                            account["trades"].append({**order,"filledDate":stamp.isoformat(),"price":price,"qty":qty,"fee":fee,"status":"filled","note":"实时后续报价估算成交"})
                    live.execute("INSERT OR REPLACE INTO orders VALUES(?,?,?)",(order_id,status,json.dumps(body)))
                    if not saved or saved["state"] != status:
                        live.execute("INSERT INTO events VALUES(?,?,?)",(stamp.isoformat(),status,json.dumps({"id":order_id,"quote":quote})))
                    if status not in ("filled","cancelled","expired"):
                        remaining.append(order)
                account["orders"]=remaining
                for code,pos in account["positions"].items():
                    if code in batch: pos["mark"]=batch[code]["last"]
                point={"date":stamp.date().isoformat(),"equity":round(paper.equity(account),2),"stale":[c for c in account["positions"] if c not in batch]}
                account["curve"]=[p for p in account["curve"] if p["date"]!=point["date"]]+[point]
                ledger.execute("INSERT OR REPLACE INTO accountdb.state VALUES(1,?)",(json.dumps(state,ensure_ascii=False),))
        finally:
            paper.LOCK.release()


def loop():
    while True:
        try: tick()
        except Exception as exc:
            with connect() as conn:
                conn.execute("INSERT INTO events VALUES(?,?,?)",(paper.now().isoformat(),"error",json.dumps({"message":"采集或执行失败，停止本轮","type":type(exc).__name__})))
        time.sleep(10)


def status():
    with connect() as conn:
        row=conn.execute("SELECT body FROM heartbeat WHERE id=1").fetchone()
        heartbeat=json.loads(row[0]) if row else None
        if heartbeat:
            heartbeat["alive"] = (paper.now()-datetime.fromisoformat(heartbeat["time"])).total_seconds()<45
        return {"features":[json.loads(r[0]) for r in conn.execute("SELECT body FROM feature_states ORDER BY rowid DESC LIMIT 100")],"heartbeat":heartbeat,"events":[dict(r) for r in conn.execute("SELECT * FROM events ORDER BY rowid DESC LIMIT 20")],"orders":[dict(r) for r in conn.execute("SELECT * FROM orders ORDER BY rowid DESC LIMIT 30")]}


if __name__=="__main__":
    loop()
