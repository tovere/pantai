import json, subprocess
from concurrent.futures import ThreadPoolExecutor
exec(open("backtest.py").read().split("def backtest")[0])  # 复用 get/SECTORS/etf_pool/kl
pool=etf_pool()
series={}
with ThreadPoolExecutor(max_workers=8) as ex:
    for c,r in zip(pool, ex.map(kl,pool)):
        if r and len(r)>80: series[c]=r
N,WIN,STEP=3,20,5
alld=sorted(set(d for s in series.values() for d,_ in s))
idx={c:{d:i for i,(d,_) in enumerate(s)} for c,s in series.items()}
cl ={c:[x[1] for x in s] for c,s in series.items()}
eq=1.0; daily=[]; cashdays=0; total=0
for t in range(60,len(alld)-1,STEP):
    d=alld[t]; sc=[]
    for c,s in series.items():
        i=idx[c].get(d)
        if i is None or i<WIN: continue
        if cl[c][i]>=sum(cl[c][i-19:i+1])/20: sc.append((cl[c][i]/cl[c][i-WIN]-1,c))
    sc.sort(reverse=True); picks=[c for _,c in sc[:N]]
    # 持有到下一个调仓日,每天盯市
    seg=alld[t:min(t+STEP,len(alld)-1)+1]
    if not picks:
        for _ in seg[1:]: daily.append(eq); cashdays+=1; total+=1
        continue
    base={c:idx[c].get(d) for c in picks}
    for dd_i in range(1,len(seg)):
        rr=[]
        for c in picks:
            i0=base[c]; j=idx[c].get(seg[dd_i])
            if i0 is not None and j is not None: rr.append(cl[c][j]/cl[c][i0]-1)
        mark=eq*(1+sum(rr)/len(rr)) if rr else eq
        daily.append(mark); total+=1
    # 周末结算
    rr=[]
    for c in picks:
        i0=base[c]; j=idx[c].get(seg[-1])
        if i0 is not None and j is not None: rr.append(cl[c][j]/cl[c][i0]-1)
    if rr: eq*=(1+sum(rr)/len(rr))
peak=daily[0]; mdd=0
for v in daily: peak=max(peak,v); mdd=max(mdd,(peak-v)/peak)
print(f"持3只/20日/周调  ETF轮动")
print(f"  最终净值 {daily[-1]:.2f} (总收益{(daily[-1]-1)*100:+.1f}%)")
print(f"  按【每日盯市】最大回撤: {mdd*100:.1f}%   (之前按周采样是16.1%)")
print(f"  空仓天数占比: {cashdays/total*100:.1f}%")
