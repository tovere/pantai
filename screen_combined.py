#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
合并每晚选股器：策略2(突破·沿MA5) + 策略3(回踩·MA20低吸) 一次扫出。
收盘后(或14:50后)跑。输出两张清单，按贴线(止损近)排序。curl后端+低并发。
"""
import json, subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
TODAY="2026-06-30"; MIN_AMOUNT=5e7; UA="Mozilla/5.0"
def get(u,tries=6):
    for _ in range(tries):
        p=subprocess.run(["curl","-s","-m","12","-A",UA,u],capture_output=True,text=True)
        if p.returncode==0 and p.stdout: return p.stdout
    return ""
def uni():
    out,pn=[],1
    while True:
        d=json.loads(get(f"https://push2.eastmoney.com/api/qt/clist/get?pn={pn}&pz=100&po=1&np=1&fltt=2&invt=2&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23&fields=f12,f14")).get("data")
        if not d or not d.get("diff"): break
        for it in d["diff"]:
            c,nm=it["f12"],it["f14"]
            if "ST" in nm or "退" in nm or "PT" in nm or c.startswith("688") or c.startswith("3"): continue
            out.append((c,nm, f"1.{c}" if c.startswith("6") else f"0.{c}"))
        if pn*100>=d.get("total",0): break
        pn+=1
    return out
def kl(s):
    d=json.loads(get(f"https://push2his.eastmoney.com/api/qt/stock/kline/get?secid={s}&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57&klt=101&fqt=1&beg=20250401&end=20500101")).get("data")
    return [l.split(",") for l in d["klines"]] if d and d.get("klines") else None
def check(code,name,ks):
    if len(ks)<70: return None
    dt=[k[0] for k in ks]; O=[float(k[1]) for k in ks]; C=[float(k[2]) for k in ks]
    L=[float(k[4]) for k in ks]; V=[float(k[5]) for k in ks]; A=[float(k[6]) for k in ks]
    i=len(ks)-1
    if dt[i]!=TODAY or A[i]<MIN_AMOUNT: return None
    ma=lambda p,k: sum(C[k-p+1:k+1])/p
    chg=(C[i]/C[i-1]-1)*100; v20=sum(V[i-20:i])/20
    m5,m10,m20,m60,m60p=ma(5,i),ma(10,i),ma(20,i),ma(60,i),ma(60,i-10)
    res=[]
    # 策略2 突破: 新突破(B,streak==3)+MA60上行+非异动+今日在MA5上
    above=lambda k: C[k]>=ma(5,k); hold=lambda k: above(k) or above(k-1)
    s=0;k=i
    while k>=5 and hold(k): s+=1;k-=1
    if (above(i) and s==3 and chg>=-5 and C[i]>=m60 and m60>m60p and C[i]/C[i-3]-1<0.20):
        res.append({"type":"突破","code":code,"name":name,"close":round(C[i],2),"chg":round(chg,2),
                    "bias":round((C[i]/m5-1)*100,1),"stop":round(m5,2),"line":"MA5",
                    "volr":round(V[i]/v20,2),"amt":round(A[i]/1e8,1),"limit":chg>=9.5})
    # 策略3 回踩: 趋势(C>MA20>MA60,MA60上行)+近10日有过上涨+回踩MA20不破+缩量
    if (C[i]>m20>m60 and m60>m60p and max(C[i-9:i+1])>=m20*1.05
        and L[i]<=m20*1.02 and C[i]>=m20 and V[i]<sum(V[i-5:i])/5 and chg>=-5):
        res.append({"type":"回踩","code":code,"name":name,"close":round(C[i],2),"chg":round(chg,2),
                    "bias":round((C[i]/m20-1)*100,1),"stop":round(m20,2),"line":"MA20",
                    "volr":round(V[i]/v20,2),"amt":round(A[i]/1e8,1),"limit":chg>=9.5})
    return res or None
def main():
    U=uni(); print(f"主板 {len(U)} 只，扫描中...")
    hits=[]
    with ThreadPoolExecutor(max_workers=12) as ex:
        futs={ex.submit(kl,s):(c,n) for c,n,s in U}
        for f in as_completed(futs):
            c,n=futs[f]
            try:
                r=f.result()
                if r:
                    rr=check(c,n,r)
                    if rr: hits.extend(rr)
            except Exception: pass
    for typ in ("突破","回踩"):
        g=sorted([h for h in hits if h["type"]==typ], key=lambda x:x["bias"])
        print(f"\n===== 【{typ}】 {len(g)}只  (止损线={'MA5' if typ=='突破' else 'MA20'}, 按贴线排序) =====")
        print("代码    名称        现价    今日%   距线   止损位    量比   额(亿)")
        for h in g[:25]:
            tag="⚠涨停买不进" if h["limit"] else ""
            print(f"{h['code']}  {h['name'][:6]:<7} {h['close']:>7.2f} {h['chg']:>+6.2f} "
                  f"{h['bias']:>+5.1f}% {h['stop']:>8.2f} {h['volr']:>6.2f} {h['amt']:>6.1f}  {tag}")

if __name__=="__main__": main()
