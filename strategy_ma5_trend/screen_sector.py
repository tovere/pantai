#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按板块筛策略2新突破。默认医药板块。curl后端+低并发,避East Money限流。"""
import json, subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

TODAY="2026-06-29"; MIN_DAYS_ABOVE=3; MIN_AMOUNT=5e7; UA="Mozilla/5.0"
BOARDS={"BK0465":"化学制药","BK0727":"医疗服务","BK1040":"中药","BK1041":"医疗器械",
        "BK1042":"医药商业","BK1044":"生物制品","BK1216":"医药生物"}

def http_get(u, tries=4):
    for _ in range(tries):
        p=subprocess.run(["curl","-s","-m","20","-A",UA,u],capture_output=True,text=True)
        if p.returncode==0 and p.stdout: return p.stdout
    return ""

def board_members():
    out={}
    for bk,nm in BOARDS.items():
        d=json.loads(http_get(f"https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=500&po=1&np=1&fltt=2&invt=2&fs=b:{bk}&fields=f12,f14")).get("data")
        if not d or not d.get("diff"): continue
        for x in d["diff"]:
            c,n=x["f12"],x["f14"]
            if "ST" in n or "退" in n or c.startswith("688") or c.startswith("3"): continue
            if c.startswith("6"): out[c]=(n,f"1.{c}",nm)
            elif c.startswith("0"): out[c]=(n,f"0.{c}",nm)
    return out

def kline(sec):
    d=json.loads(http_get(f"https://push2his.eastmoney.com/api/qt/stock/kline/get?secid={sec}&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57&klt=101&fqt=1&beg=20250401&end=20500101")).get("data")
    return [l.split(",") for l in d["klines"]] if d and d.get("klines") else None

def check(code,name,board,ks):
    if len(ks)<70: return None
    dates=[k[0] for k in ks]; closes=[float(k[2]) for k in ks]; vols=[float(k[5]) for k in ks]; amts=[float(k[6]) for k in ks]
    i=len(ks)-1
    if dates[i]!=TODAY or amts[i]<MIN_AMOUNT: return None
    ma=lambda p,j: sum(closes[j-p+1:j+1])/p
    a=lambda k: closes[k]>=ma(5,k); hold=lambda k: a(k) or (k>0 and a(k-1))
    if not a(i): return None
    s=0;j=i
    while j>=5 and hold(j): s+=1;j-=1
    if s<MIN_DAYS_ABOVE: return None                       # 站上MA5≥3日(新突破+趋势中)
    chg=(closes[i]/closes[i-1]-1)*100
    if chg<-5: return None
    if closes[i]/closes[i-3]-1>=0.20: return None          # 异动
    ma60,ma60p=ma(60,i),ma(60,i-10)
    if not (closes[i]>=ma60 and ma60>ma60p): return None
    ma5=ma(5,i); v20=sum(vols[i-20:i])/20
    return {"code":code,"name":name,"board":board,"close":round(closes[i],2),"chg":round(chg,2),
            "streak":s,"bias5":round((closes[i]/ma5-1)*100,1),"ma5":round(ma5,2),
            "volr":round(vols[i]/v20,2),"amt":round(amts[i]/1e8,1)}

def main():
    M=board_members(); print(f"医药板块主板成分(去重) {len(M)} 只，扫描中...")
    hits=[]
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs={ex.submit(kline,sec):(c,n,b) for c,(n,sec,b) in M.items()}
        for f in as_completed(futs):
            c,n,b=futs[f]
            try:
                ks=f.result()
                if ks:
                    r=check(c,n,b,ks)
                    if r: hits.append(r)
            except Exception: pass
    hits.sort(key=lambda x:(x["streak"],x["bias5"]))      # 新突破(3日)优先,再按贴线
    fresh=sum(1 for h in hits if h["streak"]==3)
    print(f"\n>>> 医药板块·站上MA5+上升趋势+非异动  共 {len(hits)} 只 (其中新突破3日 {fresh} 只)\n")
    print("代码    名称        现价    今日%   距MA5  MA5止损≈   量比   额(亿)  连站MA5  细分")
    for h in hits:
        tag="⚠涨停" if h["chg"]>=9.5 else ""
        print(f"{h['code']}  {h['name'][:6]:<7} {h['close']:>7.2f} {h['chg']:>+6.2f} "
              f"{h['bias5']:>+6.1f}% {h['ma5']:>8.2f} {h['volr']:>6.2f} {h['amt']:>6.1f}  {h['streak']:>4}日  {h['board']} {tag}")

if __name__=="__main__": main()
