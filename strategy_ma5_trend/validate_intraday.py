#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用真实分钟数据验证做T假设：高开日卖在开盘价后，盘中能否接回更低？
  5分钟K线(klt=5, 近~1.5月) 跑大样本；1分钟分时(trends2, 近5天) 交叉验证。
指标：卖飞率(开盘≈全天最低,接不回)、可接回幅度、低点出现在上午还是下午。
"""
import json, urllib.request, statistics
from concurrent.futures import ThreadPoolExecutor, as_completed

UA="Mozilla/5.0"
def http_get(u):
    return urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":UA}),timeout=20).read().decode("utf-8","ignore")

def fetch_universe():
    out,pn=[],1
    while True:
        u=(f"https://push2.eastmoney.com/api/qt/clist/get?pn={pn}&pz=100&po=1&np=1"
           "&fltt=2&invt=2&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23&fields=f12,f14")
        d=json.loads(http_get(u)).get("data")
        if not d or not d.get("diff"): break
        for it in d["diff"]:
            c,nm=it["f12"],it["f14"]
            if "ST" in nm or "退" in nm or "PT" in nm or c.startswith("688"): continue
            s=f"1.{c}" if c.startswith("6") else (f"0.{c}" if c.startswith(("0","3")) else None)
            if s: out.append(s)
        if pn*100>=d.get("total",0): break
        pn+=1
    return out

def k5(secid):
    u=("https://push2his.eastmoney.com/api/qt/stock/kline/get"
       f"?secid={secid}&fields1=f1&fields2=f51,f52,f53,f54,f55,f56&klt=5&fqt=1&beg=20200101&end=20500101")
    d=json.loads(http_get(u)).get("data")
    if not d or not d.get("klines"): return None
    # 时间,开,收,高,低,量
    days={}
    for ln in d["klines"]:
        p=ln.split(","); dt=p[0][:10]
        days.setdefault(dt,[]).append((float(p[1]),float(p[2]),float(p[4])))  # open,close,low
    return days

def trends1(secid):
    u=("https://push2his.eastmoney.com/api/qt/stock/trends2/get"
       f"?secid={secid}&fields1=f1&fields2=f51,f53,f56&ndays=5&iscr=0&iscca=0")
    d=json.loads(http_get(u)).get("data")
    if not d or not d.get("trends"): return None
    days={}
    for ln in d["trends"]:
        p=ln.split(","); dt=p[0][:10]
        days.setdefault(dt,[]).append(float(p[1]))   # 分时价
    return days

def eval_5min(days):
    """每个高开日：open=首bar开, low=全天最低, close=末bar收"""
    recs=[]; ds=sorted(days)
    for k in range(1,len(ds)):
        prev=days[ds[k-1]]; cur=days[ds[k]]
        if not prev or not cur: continue
        prev_close=prev[-1][1]; op=cur[0][0]
        low=min(b[2] for b in cur); close=cur[-1][1]
        if op>prev_close and op>0:
            rng=(op-low)/op
            # 低点出现在哪个bar(占比)
            lows=[b[2] for b in cur]; lowpos=lows.index(min(lows))/len(lows)
            recs.append({"rng":rng,"fly":rng<0.005,"up":close>op,"lowpos":lowpos})
    return recs

def eval_1min(days):
    recs=[]; ds=sorted(days)
    for k in range(1,len(ds)):
        prev=days[ds[k-1]]; cur=days[ds[k]]
        if not prev or not cur: continue
        prev_close=prev[-1]; op=cur[0]; low=min(cur); close=cur[-1]
        if op>prev_close and op>0:
            rng=(op-low)/op
            lowpos=cur.index(min(cur))/len(cur)
            recs.append({"rng":rng,"fly":rng<0.005,"up":close>op,"lowpos":lowpos})
    return recs

def report(name, recs):
    n=len(recs)
    if not n: print(f"{name}: 无样本"); return
    fly=sum(1 for r in recs if r["fly"])
    catch=[r for r in recs if not r["fly"]]
    avg_rng=statistics.mean(r["rng"] for r in recs)*100
    avg_catch=statistics.mean(r["rng"] for r in catch)*100 if catch else 0
    up=[r for r in recs if r["up"]]; down=[r for r in recs if not r["up"]]
    fly_up=sum(1 for r in up if r["fly"])/len(up)*100 if up else 0
    fly_dn=sum(1 for r in down if r["fly"])/len(down)*100 if down else 0
    am=sum(1 for r in catch if r["lowpos"]<0.5)/len(catch)*100 if catch else 0
    print(f"\n===== {name}  高开样本 {n} 个 =====")
    print(f"  卖飞率(开盘≈全天最低,接不回): {fly/n*100:.1f}%")
    print(f"  其中 高开冲高日卖飞率 {fly_up:.1f}%  /  高开回落日卖飞率 {fly_dn:.1f}%")
    print(f"  全部高开日 平均可接回幅度(开盘→最低): {avg_rng:.2f}%")
    print(f"  能接回的日子 平均幅度: {avg_catch:.2f}%  (现实吃一半≈{avg_catch/2:.2f}%)")
    print(f"  能接回的日子里 最低点出现在上午的占比: {am:.1f}%")

def main():
    uni=fetch_universe()
    s5=uni[::9]; s1=uni[::30]      # 5分钟大样本 / 1分钟小样本
    print(f"全市场 {len(uni)} 只 → 5分钟取样 {len(s5)} 只, 1分钟取样 {len(s1)} 只")

    r5=[]
    def pull5(s):
        try:
            d=k5(s); return eval_5min(d) if d else []
        except Exception: return []
    def pull1(s):
        try:
            d=trends1(s); return eval_1min(d) if d else []
        except Exception: return []
    with ThreadPoolExecutor(max_workers=24) as ex:
        for recs in ex.map(pull5, s5): r5.extend(recs)
    print(f"5分钟 高开日样本累计 {len(r5)}")
    report("5分钟K线(近~1.5月)", r5)

    r1=[]
    with ThreadPoolExecutor(max_workers=24) as ex:
        for recs in ex.map(pull1, s1): r1.extend(recs)
    report("1分钟分时(近5天)", r1)

if __name__=="__main__": main()
