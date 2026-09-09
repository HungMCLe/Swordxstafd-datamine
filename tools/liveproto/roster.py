"""Keep a local roster of every player seen in decoded captures.

  python tools/liveproto/roster.py ingest out/liveproto/cap3/decoded.json [more decoded.json ...]
  python tools/liveproto/roster.py show [name or id ...]
  python tools/liveproto/roster.py fighters Wei Nilee ... -o out/liveproto/fighters.json

The roster lives in out/liveproto/roster.json (gitignored: it holds other players' data). Newer data
replaces older per player; a short history of combat rating and the four main stats is kept.
"""
import sys, os, json, time

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')  # player names are not all cp1252

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
ROSTER = os.path.join(ROOT, 'out', 'liveproto', 'roster.json')

def load():
    if os.path.exists(ROSTER):
        return json.load(open(ROSTER, encoding='utf-8'))
    return dict(players={}, rankings={})

def save(r):
    os.makedirs(os.path.dirname(ROSTER), exist_ok=True)
    json.dump(r, open(ROSTER, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)

def player(r, pid):
    return r['players'].setdefault(str(pid), dict(id=pid, history=[]))

def ingest(files):
    r = load()
    for f in files:
        D = json.load(open(f, encoding='utf-8'))
        ftime = os.path.getmtime(f)
        src = os.path.relpath(f, ROOT)
        for m in D:
            t, d = m['type'], m['data']
            if not isinstance(d, dict):
                continue
            if t == 'PlayerLiteInfoGetResponse':
                for li in d.get('InfoList') or []:
                    p = player(r, li['Id'])
                    for k in ('Name', 'Profession', 'Level', 'SubRank', 'CombatRating', 'NoBlessCombatRating', 'Online', 'Sex', 'EngagePetClassId'):
                        if li.get(k) is not None:
                            p[k[0].lower() + k[1:]] = li[k]
                    p['lastSeen'] = max(p.get('lastSeen', 0), ftime)
            elif t == 'PlayerBriefInfo':
                pid = d['TargetData']['TargetId']
                p = player(r, pid)
                p['name'] = d.get('Name') or p.get('name')
                p['sex'] = d.get('Sex', p.get('sex'))
                snap = d['SnapshotData']
                p['snapshot'] = snap
                p['snapshotTime'] = ftime
                p['snapshotSource'] = src
                p['legionId'] = d.get('LegionId')
                p['equipResonanceProps'] = d.get('EquipResonanceProps')
                for k in ('Level', 'SubRank', 'Profession', 'CombatRating', 'NoBlessCombatRating'):
                    if snap.get(k) is not None:
                        p[k[0].lower() + k[1:]] = snap[k]
                p['lastSeen'] = max(p.get('lastSeen', 0), ftime)
            elif t in ('CharacterLiteStatusInfo', 'RpcResponse251D7A29'):
                items = [d] if t == 'CharacterLiteStatusInfo' else list((d.get('Value') or {}).values())
                for cs in items:
                    if not cs or not cs.get('TargetData'):
                        continue
                    pid = cs['TargetData']['TargetId']
                    p = player(r, pid)
                    ts = (cs.get('Time') or {}).get('ts') or ftime
                    if ts >= p.get('battlePropsTime', 0):
                        p['battleProps'] = cs.get('BattleProps') or {}
                        p['battlePropsTime'] = ts
                        p['battlePropsSource'] = src
                        p['hpPercent'] = cs.get('HpPercentBase')
                        for k in ('Level', 'SubRank', 'CombatRating', 'Online'):
                            if cs.get(k) is not None:
                                p[k[0].lower() + k[1:]] = cs[k]
                        bp = p['battleProps']
                        hist = dict(time=ts, combatRating=cs.get('CombatRating'), attack=bp.get('Attack'), defence=bp.get('Defence'), maxHp=bp.get('MaxHp'), speed=bp.get('Speed'))
                        if not p['history'] or p['history'][-1] != hist:
                            p['history'].append(hist)
                    p['lastSeen'] = max(p.get('lastSeen', 0), ftime)
            elif t == 'PlayerGetPersonalTopContentDataResponse':
                td = d.get('TopData') or {}
                key = f'{src}#{m["seq"]}'
                r['rankings'][key] = dict(time=ftime, ids=td.get('PlayerIds'), scores=[s.get('Value') if isinstance(s, dict) else s for s in td.get('Scores') or []], mine=d.get('TopRankData'))
    save(r)
    print(f'roster: {len(r["players"])} players, {sum(1 for p in r["players"].values() if p.get("battleProps"))} with live battle props, {sum(1 for p in r["players"].values() if p.get("snapshot"))} with full sheets -> {os.path.relpath(ROSTER, ROOT)}')

def find(r, key):
    key = str(key)
    if key in r['players']:
        return r['players'][key]
    for p in r['players'].values():
        if str(p.get('name', '')).lower() == key.lower():
            return p
    return None

def show(keys):
    r = load()
    rows = [find(r, k) or dict(name=k) for k in keys] if keys else sorted(r['players'].values(), key=lambda p: -(p.get('combatRating') or 0))
    print(f'{"name":16s} {"id":13s} {"class":12s} {"lv":>4s} {"rank":8s} {"rating":>10s} {"ATK":>8s} {"DEF":>8s} {"HP":>10s} {"SPD":>8s} sheet')
    for p in rows:
        bp = p.get('battleProps') or {}
        print(f'{str(p.get("name","?")):16s} {str(p.get("id","")):13s} {str(p.get("profession","")):12s} {str(p.get("level","")):>4s} {str(p.get("subRank","")):8s} {str(p.get("combatRating","")):>10s} '
              f'{str(bp.get("Attack","")):>8s} {str(bp.get("Defence","")):>8s} {str(bp.get("MaxHp","")):>10s} {str(bp.get("Speed","")):>8s} {"yes" if p.get("snapshot") else "-"}')

def skills_of(snap):
    """Equipped skills of the current plan: [(skill item id, rank, level, slot)]."""
    out = []
    plans = snap.get('SkillPlanDict') or {}
    cur = str(snap.get('CurSkillPlanIndex', 0))
    plan = plans.get(cur) or (list(plans.values())[0] if plans else None)
    if not plan:
        return out
    for group, slots in (plan.get('EquipedSkills') or {}).items():
        for slot, wrap in (slots or {}).items():
            raw = (wrap or {}).get('RawData') or {}
            ps = ((raw.get('ParamDict') or {}).get('ItemParamSkill')) or {}
            out.append(dict(group=int(group), slot=int(slot), id=raw.get('Id'), rank=ps.get('Rank'), level=ps.get('Level')))
    return sorted(out, key=lambda s: (s['group'], s['slot']))

def fighters(keys, outp):
    r = load()
    res, missing = [], []
    for k in keys:
        p = find(r, k)
        if not p:
            missing.append(k); continue
        snap = p.get('snapshot') or {}
        res.append(dict(id=p['id'], name=p.get('name'), profession=p.get('profession'), level=p.get('level'), subRank=p.get('subRank'),
                        combatRating=p.get('combatRating'), battleProps=p.get('battleProps'), battlePropsTime=p.get('battlePropsTime'),
                        skills=skills_of(snap) if snap else None,
                        passives=[dict(id=w['RawData']['Id'], **(w['RawData'].get('ParamDict', {}).get('ItemParamSkill') or {})) for w in (snap.get('PassiveSkills') or [])] if snap else None,
                        engagePet=p.get('engagePetClassId')))
    json.dump(res, open(outp, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    print(f'wrote {len(res)} fighters -> {outp}; missing: {missing or "none"}')
    for f in res:
        print(f'  {f["name"]:16s} props={"yes" if f["battleProps"] else "NO"} skills={len(f["skills"]) if f["skills"] else "NO"}')

if __name__ == '__main__':
    a = sys.argv[1:]
    if not a:
        print(__doc__)
    elif a[0] == 'ingest':
        ingest(a[1:])
    elif a[0] == 'show':
        show(a[1:])
    elif a[0] == 'fighters':
        o = a[a.index('-o') + 1] if '-o' in a else os.path.join(ROOT, 'out', 'liveproto', 'fighters.json')
        names = [x for x in a[1:] if x != '-o' and x != o]
        fighters(names, o)
