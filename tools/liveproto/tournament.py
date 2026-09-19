"""Tournament (Team Challenge) bracket from a decoded capture: divisions, their teams and members, the fight tree.

  python tools/liveproto/tournament.py extract out/liveproto/cap11/decoded.json -o out/liveproto/tournament.json
  python tools/liveproto/tournament.py show out/liveproto/tournament.json

The client receives, while the Bracket screen is open, TeamChallengeDivision (DivisionId, Round, TeamIdList,
FightingTree {progress: [[teamA, teamB], ...]}, GameRecord of played duels), TeamChallengeTeam (TeamId, Name, LeaderId,
Players, Status, CombatRatingRank), TeamChallengePlayerMatchData (Id, Name, Level, SubRank, CombatRating) and, for
teams whose panel is opened, TeamChallengePlayerEquipedSkills (PlayerId, Skills per slot, CurPetData). Objects are
found by their decoded `$type` wherever they sit inside a message. The Domain (cross-server) tournament uses the
DomainTeamChallenge* classes with the same shape.
"""
import sys, os, json, collections

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

WANT = {'TeamChallengeDivision', 'DomainTeamChallengeDivisionData', 'TeamChallengeTeam', 'DomainTeamChallengeTeamData',
        'TeamChallengePlayerMatchData', 'TeamChallengePlayerMatchInfo', 'TeamChallengePlayerEquipedSkills',
        'TeamChallengeSeason', 'TeamChallengePlayer', 'DomainTeamChallengePlayerData', 'TeamChallengeDuelResult',
        'TeamChallengeDivisionGameRecord', 'DomainTeamChallengeDivisionGameRecord'}


def walk(o, found, depth=0):
    if depth > 12:
        return
    if isinstance(o, dict):
        t = o.get('$type')
        if t in WANT:
            found[t].append(o)
        for v in o.values():
            walk(v, found, depth + 1)
    elif isinstance(o, list):
        for v in o:
            walk(v, found, depth + 1)


def skills_of(sk):
    """TeamChallengePlayerEquipedSkills.Skills: {ItemType: {slot: PlayerItemDataWrap}} -> [(id, rank, level, slot, type)]"""
    out = []
    for itype, slots in (sk or {}).items():
        for slot, wrap in (slots or {}).items():
            raw = (wrap or {}).get('RawData') or wrap or {}
            ps = ((raw.get('ParamDict') or {}).get('ItemParamSkill')) or {}
            if raw.get('Id'):
                out.append(dict(type=itype, slot=int(slot) if str(slot).isdigit() else slot, id=raw.get('Id'), rank=ps.get('Rank'), level=ps.get('Level')))
    return out


def extract(files, outp):
    found = collections.defaultdict(list)
    types = collections.Counter()
    for f in files:
        D = json.load(open(f, encoding='utf-8'))
        for m in D:
            types[m['type']] += 1
            walk(m.get('data'), found)
            # top-level messages of a wanted type carry no $type of their own
            if m['type'] in WANT and isinstance(m.get('data'), dict):
                found[m['type']].append(dict(m['data'], **{'$type': m['type']}))
    print('message types seen:', ', '.join(f'{k}x{v}' for k, v in types.most_common(25)))
    print('tournament objects:', {k: len(v) for k, v in found.items()})

    season = {}
    for s in found['TeamChallengeSeason']:
        season = dict(seasonId=s.get('SeasonId'), round=s.get('Round'), progress=s.get('FightingProcess'), divisionId=s.get('DivisionId'),
                      playMode=s.get('PlayMode'), planesRank=s.get('PlanesRank'), periodStart=s.get('PeriodStartTime'))
    teams = {}
    for t in found['TeamChallengeTeam'] + found['DomainTeamChallengeTeamData']:
        tid = t.get('TeamId')
        if tid is None:
            continue
        cur = teams.setdefault(str(tid), dict(id=str(tid)))      # team ids exceed 2^53: strings everywhere
        for k in ('Name', 'LeaderId', 'Players', 'Status', 'CombatRatingRank', 'FinalRound', 'PlaneId', 'SupportedCount', 'Catalog'):
            if t.get(k) is not None:
                cur[k[0].lower() + k[1:]] = t[k]
    players = {}
    for p in found['TeamChallengePlayerMatchData'] + found['TeamChallengePlayerMatchInfo']:
        pid = p.get('Id') or p.get('PlayerId')
        if pid is None:
            continue
        cur = players.setdefault(str(pid), dict(id=pid))
        for k in ('Name', 'Level', 'SubRank', 'CombatRating', 'NoBlessCombatRating', 'PlanesRank', 'Online', 'ServerId'):
            if p.get(k) is not None:
                cur[k[0].lower() + k[1:]] = p[k]
    # member names, levels and ratings come as ordinary lite-info responses while the bracket is open
    for f in files:
        for m in json.load(open(f, encoding='utf-8')):
            if m['type'] == 'PlayerLiteInfoGetResponse' and isinstance(m.get('data'), dict):
                for li in m['data'].get('InfoList') or []:
                    if li.get('Id') is None:
                        continue
                    cur = players.setdefault(str(li['Id']), dict(id=li['Id']))
                    for k in ('Name', 'Profession', 'Level', 'SubRank', 'CombatRating', 'NoBlessCombatRating', 'Online', 'ServerId'):
                        if li.get(k) is not None:
                            cur[k[0].lower() + k[1:]] = li[k]
    for e in found['TeamChallengePlayerEquipedSkills']:
        pid = e.get('PlayerId')
        if pid is None:
            continue
        cur = players.setdefault(str(pid), dict(id=pid))
        cur['equipped'] = skills_of(e.get('Skills'))
        pet = e.get('CurPetData') or {}
        if pet:
            cur['pet'] = dict(classId=pet.get('ClassId'), level=pet.get('Level'))
        if e.get('CombatRating') is not None:
            cur['combatRating'] = e['CombatRating']
    for p in found['TeamChallengePlayer'] + found['DomainTeamChallengePlayerData']:
        pid = p.get('PlayerId')
        if pid is None:
            continue
        cur = players.setdefault(str(pid), dict(id=pid))
        if p.get('TeamId') is not None:
            cur['teamId'] = str(p['TeamId'])
        if p.get('CombatRating') is not None:
            cur['combatRating'] = p['CombatRating']
        if p.get('SnapshotData'):
            cur['snapshot'] = p['SnapshotData']       # a full PlayerSnapshotData (own player, usually)
    divisions = {}
    for d in found['TeamChallengeDivision'] + found['DomainTeamChallengeDivisionData']:
        did = d.get('DivisionId')
        if did is None:
            continue
        tree = {}
        for prog, pairs in (d.get('FightingTree') or {}).items():
            pl = pairs if isinstance(pairs, list) else [pairs[k] for k in sorted(pairs, key=lambda x: int(x))]
            tree[str(prog)] = [[str(x) for x in (pr if isinstance(pr, list) else [pr])] for pr in pl]
        divisions[str(did)] = dict(id=did, seasonId=d.get('SeasonId'), round=d.get('Round'), teamIds=[str(x) for x in (d.get('TeamIdList') or [])],
                                   top1=str(d.get('Top1TeamId') or 0), top2=str(d.get('Top2TeamId') or 0), tree=tree,
                                   games=[dict(gameId=g.get('GameId'), win=str(g.get('WinTeam')), lost=str(g.get('LostTeam')), winScore=g.get('WinScore'), lostScore=g.get('LostScore'))
                                          for g in (d.get('GameRecord') or []) if isinstance(g, dict)])
    for d in divisions.values():
        for tid in d['teamIds']:
            teams.setdefault(tid, dict(id=tid))['divisionId'] = d['id']
    out = dict(season=season, divisions=divisions, teams=teams, players=players)
    json.dump(out, open(outp, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    print(f'tournament: {len(divisions)} divisions, {len(teams)} teams, {len(players)} players '
          f'({sum(1 for p in players.values() if p.get("equipped"))} with equipped skills, {sum(1 for p in players.values() if p.get("snapshot"))} with snapshots) -> {outp}')


def show(path):
    T = json.load(open(path, encoding='utf-8'))
    print('season:', T['season'])
    for d in sorted(T['divisions'].values(), key=lambda x: x['id']):
        print(f"division {d['id']} round {d['round']} teams {len(d['teamIds'])} top1 {d['top1']} games {len(d['games'])}")
        for prog, pairs in d['tree'].items():
            print(f'  {prog}: ' + ', '.join(f"{T['teams'].get(str(a), {}).get('name', a)} v {T['teams'].get(str(b), {}).get('name', b)}" for a, b in [(p[0], p[1]) if isinstance(p, list) and len(p) >= 2 else (p, None) for p in pairs]))
    for t in sorted(T['teams'].values(), key=lambda x: (x.get('divisionId') or 0, x.get('combatRatingRank') or 0)):
        names = [T['players'].get(str(pid), {}).get('name', pid) for pid in (t.get('players') or [])]
        print(f"  team {t.get('name', t['id'])} (div {t.get('divisionId')}, rank {t.get('combatRatingRank')}): {', '.join(map(str, names))}")


if __name__ == '__main__':
    a = sys.argv[1:]
    if not a:
        print(__doc__)
    elif a[0] == 'extract':
        o = a[a.index('-o') + 1] if '-o' in a else os.path.join(ROOT, 'out', 'liveproto', 'tournament.json')
        files = [x for x in a[1:] if x not in ('-o', o)]
        extract(files, o)
    elif a[0] == 'show':
        show(a[1])
