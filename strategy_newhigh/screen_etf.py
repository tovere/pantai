import json, subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
UA="Mozilla/5.0"
def get(u,tries=5):
    for _ in range(tries):
        p=subprocess.run(["curl","-s","-m","15","-A",UA,u],capture_output=True,text=True)
        if p.returncode==0 and '"data"' in p.stdout and p.stdout[:40].find('null')<0: return p.stdout
    return ""
def universe(top=250):
    out=[]; pn=1
    while len(out)<top and pn<=4:
        r=get(f"https://push2.eastmoney.com/api/qt/clist/get?pn={pn}&pz=100&po=1&np=1&fltt=2&invt=2&fid=f6&fs=b:MK0021&fields=f12,f14,f6")
        if not r: break
        d=json.loads(r).get("data")
        if not d or not d.get("diff"): break
        for x in d["diff"]:
            c,nm=x["f12"],x["f14"]
            if any(w in nm for w in ["货币","债","国债","政金"]): continue
            out.append((c,nm,float(x.get("f6") or 0)))
        pn+=1
    return out[:top]
def kl(c):
    sec=f"1.{c}" if c.startswith("5") else f"0.{c}"
    r=get(f"https://push2his.eastmoney.com/api/qt/stock/kline/get?secid={sec}&fields1=f1&fields2=f51,f52,f53,f54,f55,f56&klt=101&fqt=1&beg=20200101&end=20500101")
    if not r: return None
    d=json.loads(r).get("data")
    return [x.split(",") for x in d["klines"]] if d and d.get("klines") else None
def check(c,nm,amt,ks):
    if len(ks)<60: return None
    dt=[x[0] for x in ks];O=[float(x[1]) for x in ks];C=[float(x[2]) for x in ks]
    H=[float(x[3]) for x in ks];L=[float(x[4]) for x in ks];V=[float(x[5]) for x in ks]
    i=len(ks)-1
    gmax=max(H[:i]); ghidx=max(k for k in range(i) if H[k]==gmax)
    if ghidx<i-2: return None
    if sum(1 for k in range(i-10,i) if H[k]==max(H[:k+1]))>2: return None  # 首次突破:近10日新高≤2天(非连续加速)                               # 历史新高在昨/前天
    if ghidx<6 or V[ghidx]<sum(V[ghidx-5:ghidx])/5: return None
    if C[i-1]<=O[i-1]: return None
    protect=L[i-1]; chg=(C[i]/C[i-1]-1)*100
    if V[i]>=V[i-1] or V[i]<0.4*(sum(V[i-6:i-1])/5): return None
    if C[i]<protect or chg>5 or chg<-5: return None
    rng=H[i]-L[i]
    if rng>0 and C[i]<L[i]+rng*0.5: return None             # 承接
    for k in range(i-9,i+1):
        if C[k]/C[k-1]-1<=-0.06: return None                # 排妖
    ma20=sum(C[i-19:i+1])/20; bias20=(C[i]/ma20-1)*100
    return {"c":c,"nm":nm,"px":round(C[i],3),"chg":round(chg,1),"nh":i-ghidx,
            "sh":round(V[i]/V[i-1],2),"pr":round(protect,3),"tp":round((C[i]/protect-1)*100,1),
            "b20":round(bias20,1),"amt":round(amt/1e8,1)}
def main():
    U=universe(250); print(f"东财ETF·成交额前{len(U)}只,严格扫...")
    hits=[]
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs={ex.submit(kl,c):(c,n,a) for c,n,a in U}
        for f in as_completed(futs):
            c,n,a=futs[f]
            try:
                ks=f.result()
                if ks:
                    r=check(c,n,a,ks)
                    if r: hits.append(r)
            except: pass
    hits.sort(key=lambda x:x["tp"])
    print(f"\n>>> ETF严格版(历史新高+缩量回踩+承接+排妖+排加速) {len(hits)}只\n")
    print("代码    名称            现价   涨跌% 新高 缩量 保护位 距保护 乖离MA20 成交额")
    for h in hits:
        print(f"{h['c']}  {h['nm'][:10]:<10} {h['px']:>6.3f} {h['chg']:>+5.1f}% {h['nh']}天 {h['sh']:>4.2f} {h['pr']:>6.3f} {h['tp']:>+5.1f}% {h['b20']:>+5.1f}% {h['amt']:>5.1f}亿")
main()
