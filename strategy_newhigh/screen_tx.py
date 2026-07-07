#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
策略·新高后缩量回踩 —— 腾讯源版(当日30号数据)
东财行情接口被限流时的备份方案：
  池子: 新浪 getHQNodeData 按成交额排序
  历史K线: 腾讯 web.ifzq.gtimg.cn/kline (不复权, 到T-1)
  当日T根: 腾讯实时 qt.gtimg.cn (不复权, 含当天) → 拼到历史末尾
全程不复权、成交量单位均为"手", 口径一致。
"""
import json, subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
UA="Mozilla/5.0"; SREF="https://finance.sina.com.cn"
TOP=2000

def get(u, ref="", tries=5):
    cmd=["curl","-s","-m","15","-A",UA]
    if ref: cmd+=["-H",f"Referer: {ref}"]
    cmd.append(u)
    for _ in range(tries):
        p=subprocess.run(cmd,capture_output=True,text=True,errors="replace")
        if p.returncode==0 and p.stdout.strip(): return p.stdout
    return ""

def universe(top=TOP):
    out=[]; page=1
    while len(out)<top and page<=30:
        r=get(f"https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData?page={page}&num=80&sort=amount&asc=0&node=hs_a",SREF)
        try: arr=json.loads(r) if r.strip().startswith("[") else None
        except: arr=None
        if not arr: print(f"  ⚠池子页{page}空,跳过"); page+=1; continue
        for x in arr:
            sym=x["symbol"]; nm=x["name"]; code=sym[2:]
            if sym.startswith("bj") or code.startswith("688") or code.startswith("3"): continue
            if "ST" in nm or "退" in nm: continue
            out.append((sym,nm,float(x.get("amount",0))))
        page+=1
    return out[:top]

def realtime_batch(syms):
    """腾讯实时, 60只一批; 返回 {sym:{o,c,h,l,v,d}}"""
    bars={}
    for i in range(0,len(syms),60):
        r=get("https://qt.gtimg.cn/q="+",".join(syms[i:i+60]))
        for line in r.split(";"):
            line=line.strip()
            if not line.startswith("v_") or '="' not in line: continue
            sym=line[2:line.index("=")]
            f=line[line.index('"')+1:line.rindex('"')].split("~")
            if len(f)<35: continue
            try:
                bars[sym]={"o":float(f[5]),"c":float(f[3]),"h":float(f[33]),
                           "l":float(f[34]),"v":float(f[6]),"d":f[30][:8]}
            except: pass
    return bars

def kl(sym):
    r=get(f"https://web.ifzq.gtimg.cn/appstock/app/kline/kline?param={sym},day,,,1500")
    try:
        d=json.loads(r)["data"][sym]
        k=d.get("day") or d.get("qfqday")
    except: return None
    return k if k and len(k)>60 else None

def check(sym,nm,amt,k,tb):
    O=[float(x[1]) for x in k]; C=[float(x[2]) for x in k]
    H=[float(x[3]) for x in k]; L=[float(x[4]) for x in k]; V=[float(x[5]) for x in k]
    dt=[x[0].replace("-","") for x in k]
    # 仅当K线还没更新到当日时, 才用实时补一根(避免重复)
    if tb and dt[-1]!=tb["d"]:
        O.append(tb["o"]); C.append(tb["c"]); H.append(tb["h"]); L.append(tb["l"]); V.append(tb["v"]); dt.append(tb["d"])
    i=len(C)-1
    # 1. 真历史新高(本serie≈6年)落在昨/前天
    gmax=max(H[:i]); ghidx=max(k0 for k0 in range(i) if H[k0]==gmax)
    if ghidx<i-2: return None
    if sum(1 for k0 in range(i-10,i) if H[k0]==max(H[:k0+1]))>2: return None  # 首次突破:近10日新高≤2天
    if ghidx<6 or V[ghidx]<sum(V[ghidx-5:ghidx])/5: return None              # 新高日放量
    # 2. 昨日阳线→保护位
    if C[i-1]<=O[i-1]: return None
    protect=L[i-1]; chg=(C[i]/C[i-1]-1)*100
    # 3. 今日缩量回踩不破 + 小幅 + 承接(收盘在振幅上半段)
    if V[i]>=V[i-1] or V[i]<0.4*(sum(V[i-6:i-1])/5): return None
    if C[i]<protect or chg>5 or chg<-5: return None
    rng=H[i]-L[i]
    if rng>0 and C[i]<L[i]+rng*0.5: return None
    # 4. 排妖:近10日无单日-6%
    for k0 in range(i-9,i+1):
        if C[k0]/C[k0-1]-1<=-0.06: return None
    # 5. 排加速
    if C[i]/C[i-3]-1>=0.30: return None
    return {"sym":sym,"nm":nm,"date":dt[i],"px":round(C[i],2),"chg":round(chg,1),
            "nh":i-ghidx,"sh":round(V[i]/V[i-1],2),"pr":round(protect,2),
            "tp":round((C[i]/protect-1)*100,1),"amt":round(amt/1e8,1)}

def main():
    U=universe(); print(f"新浪·成交额前 {len(U)} 只")
    syms=[s for s,_,_ in U]
    print("拉腾讯实时(当日30号)...")
    rt=realtime_batch(syms)
    td=max((b["d"] for b in rt.values()), default="?")
    print(f"  实时拿到 {len(rt)} 只, 最新日={td}")
    hits=[]
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs={ex.submit(kl,s):(s,n,a) for s,n,a in U if s in rt}
        for f in as_completed(futs):
            s,n,a=futs[f]
            try:
                k=f.result()
                if k:
                    r=check(s,n,a,k,rt[s])
                    if r: hits.append(r)
            except: pass
    hits.sort(key=lambda x:x["tp"])
    print(f"\n>>> 腾讯源·严格版(真历史新高+放量+缩量回踩+今日承接+排妖) {len(hits)}只 截至{td}\n")
    print("代码      名称      现价   涨跌% 新高 缩量 保护位 距保护 成交额")
    for h in hits:
        print(f"{h['sym']}  {h['nm'][:6]:<6} {h['px']:>7.2f} {h['chg']:>+5.1f}% {h['nh']}天 {h['sh']:>4.2f} {h['pr']:>7.2f} {h['tp']:>+5.1f}% {h['amt']:>5.1f}亿")
if __name__=="__main__": main()
