#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""新浪源:成交额最大的主板股里,筛"放量新高→缩量回踩不破昨阳线低点"。绕东财限流。"""
import json, subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
UA="Mozilla/5.0"; REF="https://finance.sina.com.cn"
def get(u,tries=5):
    for _ in range(tries):
        p=subprocess.run(["curl","-s","-m","15","-H",f"Referer: {REF}","-A",UA,u],capture_output=True,text=True)
        if p.returncode==0 and p.stdout.strip().startswith(("[","{")): return p.stdout
    return ""
def universe(top=500):
    out=[]; page=1
    while len(out)<top and page<=12:
        r=get(f"https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData?page={page}&num=80&sort=amount&asc=0&node=hs_a")
        if not r: break
        try: arr=json.loads(r)
        except Exception: break
        if not arr: break
        for x in arr:
            sym=x["symbol"]; nm=x["name"]; code=sym[2:]
            if sym.startswith("bj") or code.startswith("688") or code.startswith("3"): continue
            if "ST" in nm or "退" in nm: continue
            out.append((sym,nm,float(x.get("amount",0))))
        page+=1
    return out[:top]
def kl(sym):
    r=get(f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={sym}&scale=240&datalen=250")
    if not r: return None
    try: d=json.loads(r)
    except Exception: return None
    return d if len(d)>40 else None
def check(sym,nm,amt,d):
    O=[float(x['open']) for x in d]; C=[float(x['close']) for x in d]
    H=[float(x['high']) for x in d]; L=[float(x['low']) for x in d]; V=[float(x['volume']) for x in d]
    i=len(d)-1
    prehi=max(H[:i]); hidx=max(k for k in range(i) if H[k]==prehi)
    if hidx< i-2: return None                       # 新高须在昨/前天
    if hidx<6 or V[hidx] < sum(V[hidx-5:hidx])/5: return None   # 新高日放量
    if C[i-1]<=O[i-1]: return None                  # 昨日阳线
    protect=L[i-1]
    chg=(C[i]/C[i-1]-1)*100
    if V[i]>=V[i-1] or V[i]<0.4*(sum(V[i-6:i-1])/5): return None # 缩量但不过小
    if C[i]<protect or chg>5 or chg<-5: return None # 回踩不破+今日小幅
    if C[i]/C[i-3]-1>=0.30: return None             # 排加速
    return {"sym":sym,"nm":nm,"px":round(C[i],2),"chg":round(chg,1),"date":d[i]['day'][5:],
            "nhago":i-hidx,"shrink":round(V[i]/V[i-1],2),"protect":round(protect,2),
            "toprot":round((C[i]/protect-1)*100,1),"amt":round(amt/1e8,1)}
def main():
    U=universe(500); print(f"成交额前 {len(U)} 只主板,扫描中...")
    hits=[]; done=0; fail=0
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs={ex.submit(kl,s):(s,n,a) for s,n,a in U}
        for f in as_completed(futs):
            done+=1; s,n,a=futs[f]
            try:
                d=f.result()
                if d:
                    r=check(s,n,a,d)
                    if r: hits.append(r)
                else: fail+=1
            except Exception: fail+=1
            if done%150==0: print(f"  {done}/{len(U)} 命中{len(hits)} 失败{fail}")
    hits.sort(key=lambda x:x["toprot"])
    dd=hits[0]['date'] if hits else '?'
    print(f"\n>>> 放量新高→缩量回踩候选 {len(hits)} 只 (数据截至{dd},失败{fail})\n")
    print("代码      名称      现价   涨跌% 新高 缩量 保护位 距保护 成交额")
    for h in hits[:40]:
        print(f"{h['sym']}  {h['nm'][:6]:<6} {h['px']:>7.2f} {h['chg']:>+5.1f}% {h['nhago']}天 {h['shrink']:>4.2f} {h['protect']:>7.2f} {h['toprot']:>+5.1f}% {h['amt']:>5.1f}亿")
if __name__=="__main__": main()
