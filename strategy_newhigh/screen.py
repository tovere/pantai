#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
强势股缩量回踩选股(用户盘感法的日线可量化部分):
  近期(昨/前天)放量创区间新高 + 成交额大 + 今日缩量回踩不破昨阳线低点(保护位)
分时承接/择时靠人。curl后端+低并发。
"""
import json, subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
TODAY="2026-06-30"; UA="Mozilla/5.0"; BIGAMT=2e8
def get(u,tries=5):
    for _ in range(tries):
        p=subprocess.run(["curl","-s","-m","20","-A",UA,u],capture_output=True,text=True)
        if p.returncode==0 and p.stdout and '"klines"' in p.stdout: return p.stdout
    return ""
def uni():
    out,pn=[],1
    while True:
        r=get(f"https://push2.eastmoney.com/api/qt/clist/get?pn={pn}&pz=100&po=1&np=1&fltt=2&invt=2&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23&fields=f12,f14")
        if not r: break
        d=json.loads(r).get("data")
        if not d or not d.get("diff"): break
        for it in d["diff"]:
            c,nm=it["f12"],it["f14"]
            if "ST" in nm or "退" in nm or "PT" in nm or c.startswith("688") or c.startswith("3"): continue
            out.append((c,nm))
        if pn*100>=d.get("total",0): break
        pn+=1
    return out
def kl(c):
    sec=f"1.{c}" if c.startswith("6") else f"0.{c}"
    r=get(f"https://push2his.eastmoney.com/api/qt/stock/kline/get?secid={sec}&fields1=f1&fields2=f51,f52,f53,f54,f55,f56,f57&klt=101&fqt=1&beg=20250101&end=20500101")
    if not r: return None
    d=json.loads(r).get("data")
    if not d or not d.get("klines"): return None
    return [x.split(",") for x in d["klines"]]  # 日期,开,收,高,低,量,额
def check(c,nm,ks):
    if len(ks)<40: return None
    dt=[x[0] for x in ks]; O=[float(x[1]) for x in ks]; C=[float(x[2]) for x in ks]
    H=[float(x[3]) for x in ks]; L=[float(x[4]) for x in ks]; V=[float(x[5]) for x in ks]; A=[float(x[6]) for x in ks]
    i=len(ks)-1
    if dt[i]!=TODAY: return None
    # 区间新高在 昨(i-1)或前天(i-2)
    prehi=max(H[:i]); hidx=max(k for k in range(i) if H[k]==prehi)
    if hidx< i-2: return None
    # 新高日放量
    if hidx<6 or V[hidx] < sum(V[hidx-5:hidx])/5: return None
    # 昨日阳线 → 保护位=昨低
    if C[i-1]<=O[i-1]: return None
    protect=L[i-1]
    # 今日: 缩量 + 回踩不破保护 + 涨幅不大(承接) + 成交额大
    chg=(C[i]/C[i-1]-1)*100
    if V[i]>=V[i-1]: return None                  # 缩量
    if V[i] < 0.4*(sum(V[i-6:i-1])/5): return None # 量不过小
    if C[i]<protect: return None                   # 回踩不破保护
    if chg>5 or chg<-5: return None                # 今天涨幅不大(小承接/下杀捞起)
    if A[i]<BIGAMT: return None                    # 成交额大
    if C[i]/C[i-3]-1>=0.30: return None            # 排加速/异动
    return {"c":c,"nm":nm,"px":round(C[i],2),"chg":round(chg,1),
            "nhago":i-hidx,"shrink":round(V[i]/V[i-1],2),
            "protect":round(protect,2),"toprot":round((C[i]/protect-1)*100,1),
            "amt":round(A[i]/1e8,1)}
def main():
    U=uni(); print(f"主板 {len(U)} 只,扫描中...")
    hits=[]; done=0; fail=0
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs={ex.submit(kl,c):(c,n) for c,n in U}
        for f in as_completed(futs):
            done+=1; c,n=futs[f]
            try:
                ks=f.result()
                if ks:
                    r=check(c,n,ks)
                    if r: hits.append(r)
                else: fail+=1
            except Exception: fail+=1
            if done%600==0: print(f"  {done}/{len(U)} 命中{len(hits)} 拉取失败{fail}")
    hits.sort(key=lambda x:x["toprot"])  # 离保护位越近越好(止损近)
    print(f"\n>>> 放量新高后缩量回踩候选 {len(hits)} 只 (拉取失败{fail}只,覆盖不全)\n")
    print("代码    名称      现价   今日% 新高 缩量 保护位(昨低) 距保护 成交额")
    for h in hits[:40]:
        print(f"{h['c']}  {h['nm'][:6]:<6} {h['px']:>6.2f} {h['chg']:>+5.1f}% {h['nhago']}天前 {h['shrink']:>4.2f} {h['protect']:>7.2f}   {h['toprot']:>+5.1f}% {h['amt']:>5.1f}亿")
if __name__=="__main__": main()
