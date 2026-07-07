import json, subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
UA="Mozilla/5.0"
def get(u,tries=5):
    for _ in range(tries):
        p=subprocess.run(["curl","-s","-m","15","-A",UA,u],capture_output=True,text=True)
        if p.returncode==0 and '"data"' in p.stdout and 'null' not in p.stdout[:40]: return p.stdout
    return ""
def universe(top=2000):
    out=[]; total=None
    for pn in range(1,22):
        if total and (pn-1)*100>=total: break
        r=get(f"https://push2.eastmoney.com/api/qt/clist/get?pn={pn}&pz=100&po=1&np=1&fltt=2&invt=2&fid=f6&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23&fields=f12,f14,f6",tries=10)
        if not r: print(f"  ⚠页{pn}取数失败,跳过"); continue   # 空页跳过,不中断
        try: d=json.loads(r).get("data")
        except: print(f"  ⚠页{pn}解析失败,跳过"); continue
        if not d or not d.get("diff"): continue
        if total is None: total=d.get("total",0)
        for x in d["diff"]:
            c,nm=x["f12"],x["f14"]
            if "ST" in nm or "退" in nm or c.startswith("688") or c.startswith("3"): continue
            out.append((c,nm,float(x.get("f6") or 0)))
        if len(out)>=top: break
    return out[:top]
def kl(c):
    sec=f"1.{c}" if c.startswith("6") else f"0.{c}"
    r=get(f"https://push2his.eastmoney.com/api/qt/stock/kline/get?secid={sec}&fields1=f1&fields2=f51,f52,f53,f54,f55,f56,f57&klt=101&fqt=1&beg=20170101&end=20500101")
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
    if sum(1 for k in range(i-10,i) if H[k]==max(H[:k+1]))>2: return None  # 首次突破:近10日新高≤2天(非连续加速)
    if ghidx<6 or V[ghidx]<sum(V[ghidx-5:ghidx])/5: return None
    if C[i-1]<=O[i-1]: return None
    protect=L[i-1]; chg=(C[i]/C[i-1]-1)*100
    if V[i]>=V[i-1] or V[i]<0.4*(sum(V[i-6:i-1])/5): return None
    if C[i]<protect or chg>5 or chg<-5: return None
    rng=H[i]-L[i]
    if rng>0 and C[i]<L[i]+rng*0.5: return None
    for k in range(i-9,i+1):
        if C[k]/C[k-1]-1<=-0.06: return None
    if C[i]/C[i-3]-1>=0.30: return None
    return {"c":c,"nm":nm,"date":dt[i][5:],"px":round(C[i],2),"chg":round(chg,1),
            "nh":i-ghidx,"sh":round(V[i]/V[i-1],2),"pr":round(protect,2),
            "tp":round((C[i]/protect-1)*100,1),"amt":round(amt/1e8,1)}
def main():
    U=universe(2000); print(f"东财·成交额前{len(U)}只,严格扫{('当日' )}...")
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
    dd=hits[0]['date'] if hits else '?'
    print(f"\n>>> 严格版(真历史新高+放量+缩量回踩+今日承接+排妖) {len(hits)}只 截至{dd}\n")
    print("代码    名称      现价   涨跌% 新高 缩量 保护位 距保护 成交额")
    for h in hits:
        print(f"{h['c']}  {h['nm'][:6]:<6} {h['px']:>7.2f} {h['chg']:>+5.1f}% {h['nh']}天 {h['sh']:>4.2f} {h['pr']:>7.2f} {h['tp']:>+5.1f}% {h['amt']:>5.1f}亿")
main()
