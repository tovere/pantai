import json, subprocess
from concurrent.futures import ThreadPoolExecutor
exec(open("backtest.py").read().split("def backtest")[0])
pool=etf_pool(); series={}
with ThreadPoolExecutor(max_workers=8) as ex:
    for c,r in zip(pool, ex.map(kl,pool)):
        if r and len(r)>80: series[c]=r
alld=sorted(set(d for s in series.values() for d,_ in s))
idx={c:{d:i for i,(d,_) in enumerate(s)} for c,s in series.items()}
cl ={c:[x[1] for x in s] for c,s in series.items()}
def runcfg(FILT, STEP, N=3, WIN=20):
    eq=1.0; daily=[]
    for t in range(60,len(alld)-1,STEP):
        d=alld[t]; sc=[]
        for c,s in series.items():
            i=idx[c].get(d)
            if i is None or i<WIN: continue
            maf=sum(cl[c][i-FILT+1:i+1])/FILT
            if cl[c][i]>=maf: sc.append((cl[c][i]/cl[c][i-WIN]-1,c))
        sc.sort(reverse=True); picks=[c for _,c in sc[:N]]
        seg=alld[t:min(t+STEP,len(alld)-1)+1]
        if not picks:
            for _ in seg[1:]: daily.append(eq)
            continue
        base={c:idx[c].get(d) for c in picks}
        for k in range(1,len(seg)):
            rr=[cl[c][idx[c][seg[k]]]/cl[c][base[c]]-1 for c in picks if base[c] is not None and seg[k] in idx[c]]
            daily.append(eq*(1+sum(rr)/len(rr)) if rr else eq)
        rr=[cl[c][idx[c][seg[-1]]]/cl[c][base[c]]-1 for c in picks if base[c] is not None and seg[-1] in idx[c]]
        if rr: eq*=(1+sum(rr)/len(rr))
    peak=daily[0]; mdd=0
    for v in daily: peak=max(peak,v); mdd=max(mdd,(peak-v)/peak)
    return (daily[-1]-1)*100, mdd*100
print("护盘线/调仓频率   收益 / 日盯市最大回撤   (持3只,20日动量)")
for filt,lab in [(20,"MA20(慢/现用)"),(10,"MA10(中)"),(5,"MA5(快/早走)")]:
    tot,mdd=runcfg(filt,5); print(f"  {lab:<14} 周调  {tot:>+7.1f}% / 回撤{mdd:4.1f}%")
print("  --- 同MA20、调仓更勤(=更早反应) ---")
for step,lab in [(5,"周调"),(2,"两日调"),(1,"每日调")]:
    tot,mdd=runcfg(20,step); print(f"  MA20 {lab:<10} {tot:>+7.1f}% / 回撤{mdd:4.1f}%")
