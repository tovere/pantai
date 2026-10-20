"""Auditable evidence evolution. Watch states never grant trading authority."""
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent / 'data_cache' / 'divergence_evidence'


def history_changes(item, day):
    prior = None
    if ROOT.exists():
        for path in sorted(ROOT.glob('*.json'), reverse=True):
            if path.stem >= day:
                continue
            found = json.loads(path.read_text()).get(item['code'])
            if found:
                prior = found
                break
    ev = item['evidence']
    current = {'date': day, 'volumeRatio': ev['priceVolume']['volumeRatio'],
               'supportIntact': ev['priceVolume']['supportIntact'],
               'pivot': ev['chan']['latestPivot'], 'boxRetest': ev['wyckoff']['breakoutRetest'],
               'industry': ev['sector']['match'], 'trigger': ev['entry']['triggerPrice'],
               'stop': ev['entry']['stop']}
    changes = []
    if prior:
        for field in ('volumeRatio','supportIntact','pivot','boxRetest','industry','trigger','stop'):
            if current[field] != prior.get(field):
                changes.append({'feature':field,'before':prior.get(field),'after':current[field]})
    return current, {'previousDate':prior['date'] if prior else None, 'changes':changes,
                     'note':'与此前最近一次真实候选证据比较；无前值不推断改善，非连续日比较不称单日变化'}


def advance(condition, quote, batch, previous, now):
    """Three distinct, synchronized samples over >=20s; restart retains counters.

    Source gaps, missing peers, or a false condition reset the confirmation window.
    All quotes used by a confirmation must advance, so polling repeats don't count.
    """
    from paper_divergence import triggered
    old = previous or {}
    state = dict(old)
    if old.get('state') in ('invalidated','expired'):
        return state
    if old.get('sessionDate') != now.date().isoformat():
        state = {}
    state['sessionDate'] = now.date().isoformat()
    recent = lambda q: q and 0 <= (now-datetime.fromisoformat(q['stamp'])).total_seconds() <= 30
    peers = [batch.get(c) for c in condition['peers']]
    if quote and recent(quote) and quote['last'] <= condition['invalidateBelow']:
        state.update(state='invalidated', reason='跌破结构失效位', count=0, since=None)
    elif not recent(quote) or not all(recent(q) for q in peers):
        state.update(state='data_wait', reason='个股或行业样本报价缺失/过期', count=0, since=None)
    elif not triggered(condition, quote, batch):
        state.update(state='waiting', reason='价格突破或行业转强未同时成立', count=0, since=None)
    else:
        stamps = {quote['code']:quote['stamp'], **{q['code']:q['stamp'] for q in peers}}
        earlier = state.get('sampleStamps', {})
        advanced = all(stamp > earlier.get(code, '') for code,stamp in stamps.items())
        gap = (now-datetime.fromisoformat(state['observedAt'])).total_seconds() if state.get('observedAt') else None
        if gap is not None and gap > 30:
            state.update(count=0, since=None)
        if advanced:
            state['count'] = state.get('count',0)+1
            state['since'] = state.get('since') or now.isoformat()
            state['sampleStamps'] = stamps
            state['observedAt'] = now.isoformat()
        seconds = (now-datetime.fromisoformat(state['since'])).total_seconds() if state.get('since') else 0
        confirmed = state.get('count',0)>=3 and seconds>=20
        state.update(state='confirmed' if confirmed else 'confirming',
                     reason='连续报价确认通过' if confirmed else '等待至少3组新报价、持续20秒')
    state['time'] = now.isoformat()
    return state


def save_evidence(items, day):
    ROOT.mkdir(parents=True,exist_ok=True)
    records = {}
    for item in items:
        record, changes = history_changes(item,day)
        item['evidence']['evolution'] = changes
        records[item['code']] = record
    target = ROOT/(day+'.json')
    temp = target.with_suffix('.tmp')
    temp.write_text(json.dumps(records,ensure_ascii=False))
    temp.replace(target)
