r"""Fight ledger: the server's own record of a battle, pulled from a passive capture.

The client never simulates a fight. The fight server sends the whole battle as data: GAME_START carries the
stage, GAME_ENTITY_LIST every entity with its components (each fighter's server-computed props in
PropComponent.FinalProps, HP, faction, cell, skills with rank and level, pet), and then GAME_ROUND messages
whose steps are timestamped server decisions: a skill entity (caster, slot, aim, target), a damage entity
per hit (value, shield taken, crit / block / dodge / blind flags, element), a status entity per applied
status, and modifications (turn queue PreTime/NextTime, whose turn it is, positions, cooldowns, shields,
stacks, HP). PLAYER_GAME_RESULT closes it with the winner, the round count and why the fight ended.

That stream is ground truth for the simulators. This tool turns it into a normalized fight record:

    python tools\liveproto\fights.py extract out\liveproto\capN\decoded.json -o out\fights
    python tools\liveproto\fights.py show out\fights\<gameId>.json
    python tools\liveproto\fights.py fighters out\fights\<gameId>.json -o out\fights\<gameId>.fighters.json

`extract` reads the decoded capture (gproto.py decode), decodes every nested step payload, and writes one
JSON per fight plus out\fights\index.json. `show` prints the fight as a log. `fighters` exports the units in
the team page's fighters.json shape (sheet from FinalProps, skills from the slot table), so the same setup can
be run through the engine and compared step by step. Everything stays under out\ (never committed).
"""
from __future__ import annotations
import json, os, sys, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gproto  # noqa: E402

ROOT = HERE.parents[1]
SCHEMA = HERE / 'schema.json'

# message classes that make up a fight, by their MessagePack class name (opcode -> name via the schema)
START, ENTITIES, COMPLETE, ROUND, PACK, RESULT = ('FightProcessStartMsg', 'FightEntityListMsg', 'FightProcessStartCompleteMsg',
                                                 'FightEntityRoundMsg', 'FightEntityPackMsg', 'FightProcessResultMsg')


def eid(x):
    """EcEntityIdentifier -> its EntityId (the container id is the same for every entity of one fight)."""
    if isinstance(x, dict):
        return x.get('EntityId')
    return x


def pos(p):
    return [p.get('X'), p.get('Y')] if isinstance(p, dict) else None


def comps(entity):
    """{component class name: component dict} for one decoded EcEntity."""
    out = {}
    for c in (entity or {}).get('ComponentList') or []:
        if isinstance(c, dict) and c.get('$type'):
            out[c['$type']] = c
    return out


def unit_of(entity, names):
    """A fighter, pet, summon or grid item as the engine wants to see it."""
    cs = comps(entity)
    fight = cs.get('FightRoleFightComponent')
    if fight is None:
        return None
    ch = cs.get('FightRoleCharacterComponent') or {}
    prop = cs.get('PropComponent') or {}
    grid = cs.get('GridTransformComponent') or {}
    lvl = cs.get('LevelComponent') or {}
    skills = {}
    for slot, d in ((cs.get('FightSkillAgentComponent') or {}).get('SlotSkillItemDatas') or {}).items():
        b = (d or {}).get('BaseInfo') or {}
        skills[int(slot)] = {'item': b.get('SkillItemClassId'), 'ent': b.get('SkillEntClassId'),
                             'rank': b.get('SkillRank'), 'level': b.get('SkillLevel'),
                             'lastRound': (d or {}).get('LastRound'), 'released': (d or {}).get('ReleasedTimes'),
                             'canAi': (d or {}).get('CanAiRelease')}
    passives = {}
    for slot, d in ((cs.get('FightPassiveSkillAgentComponent') or {}).get('SlotPassiveSkillDatas') or {}).items():
        b = (d or {}).get('BaseInfo') or {}
        passives[int(slot)] = {'item': b.get('SkillItemClassId'), 'ent': b.get('SkillEntClassId'),
                               'rank': b.get('SkillRank'), 'level': b.get('SkillLevel'), 'active': (d or {}).get('Active')}
    pet = cs.get('FightRolePetComponent')
    summon = cs.get('FightRoleSummonComponent')
    e = eid(entity.get('Id'))
    return {
        'entity': e, 'classId': entity.get('ClassId'), 'name': names.get(e),
        'characterType': ch.get('CharacterType'), 'master': eid(ch.get('MasterId')),
        'faction': fight.get('Faction'), 'hp': fight.get('Hp'), 'maxHpLast': fight.get('LastMaxHp'),
        'initialHpPercent': fight.get('InitialHpPercent'), 'initiator': fight.get('IsBattleInitiator'),
        'level': lvl.get('Level'), 'subRank': lvl.get('SubRank'),
        'pos': pos(grid.get('MyPos')), 'direction': grid.get('Direction'), 'flipX': grid.get('FlipX'),
        'props': prop.get('FinalProps') or {}, 'baseProps': prop.get('BaseProps') or {},
        'additionProps': prop.get('AdditionProps') or {}, 'element': prop.get('ElementType'),
        'skills': skills, 'passives': passives,
        'pet': ({'classId': pet.get('PetClassId'), 'phase': pet.get('Phase'), 'ability': pet.get('Ability'),
                 'skillRank': pet.get('SkillRank'), 'owner': eid(pet.get('OwnerEntityId'))} if pet else None),
        'summon': summon.get('SummonSkillInfo') if summon else None,
        'components': sorted(cs.keys()),
        'isPlayer': 'FightRolePlayerComponent' in cs, 'isPet': 'FightRolePetEntityComponent' in cs or bool(pet),
        'isGridItem': 'FightRoleGridItemComponent' in cs or 'FightRoleSmartGridItemComponent' in cs,
    }


def event_of(name, d, entity_classes):
    """One decoded step payload -> a compact event record."""
    if name == 'FightEntityAddMsg':
        ent = d.get('Entity') or {}
        cs = comps(ent)
        e = eid(ent.get('Id')); cls = ent.get('ClassId')
        entity_classes[e] = cls
        if 'FightDamageComponent' in cs:
            c = cs['FightDamageComponent']; r = c.get('DamageResult') or {}; t = r.get('DamageTypeData') or {}
            return {'ev': 'damage', 'id': e, 'cls': cls, 'skill': eid(c.get('SkillId')), 'hit': eid(c.get('HitId')),
                    'hitClass': c.get('HitClassId'), 'target': eid(c.get('TargetId')), 'src': eid(c.get('SkillSrcEntityId')),
                    'value': r.get('DamageValue'), 'shield': r.get('ShieldValue'), 'absolute': r.get('AbsoluteDamage'),
                    'crit': t.get('IsCrit'), 'block': t.get('IsBlock'), 'dodge': t.get('IsDodge'), 'blind': t.get('IsBlinding'),
                    'immune': t.get('IsImmunity'), 'trueDmg': t.get('IsTrueDamage'), 'result': r.get('ResultType'),
                    'ele': r.get('SkillElementType') or c.get('SkillElemntType'), 'confront': r.get('ElementConfrontation'),
                    'hitType': c.get('HitDamageType'), 'byStatus': c.get('IsDamageTriggerStatus'), 'at': pos(r.get('Pos'))}
        if 'FightSkillComponent' in cs:
            c = cs['FightSkillComponent']
            return {'ev': 'skill', 'id': e, 'cls': cls, 'who': eid(c.get('SrcEntityId')), 'item': c.get('SrcSkillItemClassId'),
                    'slot': c.get('SkillSlot'), 'aim': pos(c.get('TargetPos')), 'target': eid(c.get('TargetId')),
                    'interrupted': c.get('Interrupted'), 'cost': c.get('CostValue')}
        if 'FightStatusComponent' in cs:
            c = cs['FightStatusComponent']; a = cs.get('ActionComponent') or {}; si = c.get('SourceInfo') or {}
            return {'ev': 'status', 'id': e, 'cls': cls, 'action': a.get('ActionType'), 'apply': eid(a.get('ApplyId')),
                    'stack': c.get('StackedCount'), 'startRound': c.get('StartRound'), 'dur': c.get('CurDurationRound'),
                    'forbidden': c.get('ForbiddenType'), 'src': eid(si.get('Id')), 'srcClass': si.get('ClassId'),
                    'srcSkill': (si.get('SkillInfo') or {}).get('SkillItemClassId'), 'srcFaction': si.get('Faction')}
        for hn in ('FightHitFixedComponent', 'FightHitRandomTargetComponent', 'FightHitBaseComponent', 'FightHitSummonComponent',
                   'FightHitChainedComponent', 'FightHitTriggerSkillComponent'):
            if hn in cs:
                c = cs[hn]
                return {'ev': 'hit', 'id': e, 'cls': cls, 'kind': hn.replace('Fight', '').replace('Component', ''),
                        'skill': eid(c.get('SkillId')), 'index': c.get('HitIndex'), 'delay': c.get('HitDelayTime')}
        if 'ActionComponent' in cs:
            a = cs['ActionComponent']
            return {'ev': 'action', 'id': e, 'cls': cls, 'action': a.get('ActionType'), 'apply': eid(a.get('ApplyId')),
                    'comps': sorted(cs.keys())}
        if 'FightRoleFightComponent' in cs:
            return {'ev': 'unit', 'id': e, 'cls': cls, 'unit': unit_of(ent, {})}
        return {'ev': 'add', 'id': e, 'cls': cls, 'comps': sorted(cs.keys())}
    if name == 'FightEntityRemoveMsg':
        return {'ev': 'remove', 'id': eid(d.get('EntityId'))}
    if name == 'FightRoundAddDataModification' or name == 'FightRoundUpdateDataModification':
        r = d.get('Data') or {}
        return {'ev': 'queue', 'kind': 'add' if name.startswith('FightRoundAdd') else 'update', 'unit': eid(r.get('EntityId')),
                'pre': r.get('PreTime'), 'next': r.get('NextTime'), 'state': d.get('State')}
    if name == 'FightRoundRemoveDataModification':
        return {'ev': 'queue', 'kind': 'remove', 'unit': eid(d.get('RoundEntityId'))}
    if name == 'FightRoundActingDataModification':
        return {'ev': 'acting', 'unit': eid(d.get('RoundEntityId'))}
    if name == 'FightRoundFinishModification':
        return {'ev': 'finish', 'unit': eid(d.get('EntityId'))}
    if name == 'FightRoundNewModification':
        return {'ev': 'globalRound', 'n': d.get('GlobalRound')}
    if name == 'FightPersonalRoundNewModification':
        return {'ev': 'personalRound', 'unit': eid(d.get('EntityId')), 'n': d.get('PersonalRound')}
    if name == 'FightRolePlayerPosModification':
        return {'ev': 'pos', 'unit': eid(d.get('EntityId')), 'to': pos(d.get('Pos'))}
    if name == 'FightHitPosModification':
        return {'ev': 'hitPos', 'id': eid(d.get('EntityId')), 'to': pos(d.get('NewPos'))}
    if name == 'FightSkillChangeCDModification':
        return {'ev': 'cd', 'unit': eid(d.get('EntityId')), 'slots': d.get('SkillSlots'), 'change': d.get('ChangeCD')}
    if name == 'FightSkillResetAllCDModification':
        return {'ev': 'cdReset', 'unit': eid(d.get('EntityId')), 'restart': d.get('Restart')}
    if name == 'FightStatusShieldValueModification':
        return {'ev': 'shield', 'status': eid(d.get('EntityId')), 'type': d.get('ShieldType'), 'max': d.get('MaxValue'),
                'remain': d.get('RemainValue'), 'pre': d.get('PreValue')}
    if name == 'FightStatusStackedUpdateModification':
        return {'ev': 'stack', 'unit': eid(d.get('EntityId')), 'status': eid(d.get('StatusEntId')), 'count': d.get('StackedCount')}
    if name == 'FightStatusDamageModification':
        return {'ev': 'tick', 'status': eid(d.get('EntityId')), 'value': d.get('DamageValue'), 'cure': d.get('IsCure')}
    if name == 'FightSyncDamageModification':
        return {'ev': 'syncDamage', 'unit': eid(d.get('EntityId')),
                'rows': [{'src': eid(x.get('SourceEntityId')), 'real': x.get('RealDamage'), 'value': x.get('DamageValue'),
                          'shield': x.get('ShieldValue')} for x in (d.get('SyncDamageDatas') or []) if isinstance(x, dict)]}
    if name == 'FightRoleHpModification':
        return {'ev': 'hp', 'unit': eid(d.get('EntityId')), 'hp': d.get('Hp')}
    if name == 'FightRootStatusDataModification':
        return {'ev': 'gameStatus', 'status': (d.get('GameStatusData') or {}).get('GameStatus')}
    if name == 'FightRolePetEnergyModification':
        return {'ev': 'petEnergy', 'unit': eid(d.get('EntityId')), 'cur': d.get('CurEnergy'), 'need': d.get('EntityNeedEnergy')}
    if name == 'FightPetUpdateModification':
        return {'ev': 'petUpdate', 'unit': eid(d.get('EntityId')), 'pet': d.get('PetClassId'), 'phase': d.get('PetPhase'),
                'disabled': d.get('IsDisabled'), 'petEntity': eid(d.get('PetEcId'))}
    if name in ('IntData', 'LongData'):
        return {'ev': 'value', 'val': d.get('Val')}
    if name.endswith('Modification'):
        out = {'ev': 'mod', 'type': name}
        for k, v in d.items():
            if k != '$type':
                out[k] = eid(v) if isinstance(v, dict) and 'EntityId' in v and 'ContainerId' in v else v
        return out
    return {'ev': 'other', 'type': name, 'data': d}


def decode_steps(dec, step_list, entity_classes):
    out = []
    for st in step_list or []:
        if not isinstance(st, dict):
            continue
        raw = st.get('Data')
        body = bytes.fromhex(raw) if isinstance(raw, str) else (raw if isinstance(raw, (bytes, bytearray)) else None)
        rec = {'t': st.get('Time'), 'msg': st.get('MsgType')}
        if body:
            name, obj, rest = dec.message(body)
            rec['type'] = name
            if rest:
                rec['rest'] = rest
            rec.update(event_of(name, obj if isinstance(obj, dict) else {'value': obj}, entity_classes))
        out.append(rec)
    return out


def extract(decoded_path, out_dir, roster_path=None):
    schema = json.load(open(SCHEMA, encoding='utf-8'))
    dec = gproto.Decoder(schema)
    msgs = json.load(open(decoded_path, encoding='utf-8'))
    names = {}
    if roster_path and os.path.exists(roster_path):
        R = json.load(open(roster_path, encoding='utf-8'))
        for pid, p in (R.get('players') or {}).items():
            names[int(pid)] = p.get('name')
    fights, cur = [], None

    def new_fight(start):
        return {'stage': start.get('StageId'), 'viewerFaction': start.get('Faction'), 'created': str(start.get('CreateTime')),
                'source': start.get('GameSource'), 'gameId': None, 'players': {}, 'units': [], 'rounds': [], 'preRounds': [],
                'result': None, 'captured': datetime.datetime.now().isoformat(timespec='seconds'), 'from': str(decoded_path)}

    entity_classes = {}
    for m in msgs:
        if m.get('dir') != 's2c':
            continue
        t, d = m.get('type'), m.get('data')
        if not isinstance(d, dict):
            continue
        if t == START:
            if cur:
                fights.append(cur)
            cur = new_fight(d); entity_classes = {}
            continue
        if cur is None:
            continue
        if t == ENTITIES:
            cur['gameId'] = d.get('GameId') or cur['gameId']
            for ent in d.get('EntityList') or []:
                if not isinstance(ent, dict):
                    continue
                entity_classes[eid(ent.get('Id'))] = ent.get('ClassId')
                u = unit_of(ent, {})
                if u:
                    cur['units'].append(u)
                else:
                    cs = comps(ent)
                    if 'FightRoundDriverComponent' in cs:
                        drv = cs['FightRoundDriverComponent']
                        cur['queue0'] = [{'unit': eid(x.get('EntityId')), 'pre': x.get('PreTime'), 'next': x.get('NextTime')}
                                         for x in (drv.get('DataList') or []) if isinstance(x, dict)]
                        cur['round0'] = drv.get('Round')
                    if 'FightComponent' in cs:
                        fc = cs['FightComponent']
                        cur['speed'] = fc.get('Speed'); cur['createMode'] = fc.get('FightCreateMode')
                        cur['stage'] = fc.get('StageId') or cur['stage']
        elif t == COMPLETE:
            cur['gameId'] = d.get('GameId') or cur['gameId']
            cur['state'] = d.get('GameState')
            for pid, ident in (d.get('PlayerId2EntityId') or {}).items():
                cur['players'][str(pid)] = eid(ident)
            for u in cur['units']:
                for pid, e in cur['players'].items():
                    if e == u['entity']:
                        u['playerId'] = int(pid); u['name'] = names.get(int(pid))
        elif t == ROUND:
            cur['rounds'].append({'gameId': d.get('GameId'), 'steps': decode_steps(dec, d.get('StepList'), entity_classes)})
        elif t == PACK:
            for rm in d.get('RoundList') or []:
                if isinstance(rm, dict):
                    cur['rounds'].append({'gameId': rm.get('GameId'), 'steps': decode_steps(dec, rm.get('StepList'), entity_classes)})
        elif t == RESULT:
            r = d.get('GameResult') or {}
            rep = r.get('Report') or {}
            cur['result'] = {'win': r.get('Win'), 'winFaction': r.get('WinFaction'), 'round': r.get('Round'),
                             'end': r.get('GameBattleEndType'), 'stage': r.get('StageId'), 'gameClass': r.get('GameClassId'),
                             'roundCount': rep.get('RoundCount'), 'personalRound': rep.get('PersonaRound')}
            fights.append(cur); cur = None
        elif t.endswith('Modification') or t in ('FightEntityAddMsg', 'FightEntityRemoveMsg'):
            # steps that arrive outside a round message (the PlayStart phase and setup)
            cur['preRounds'].append(dict({'t': None, 'msg': None, 'type': t}, **event_of(t, d, entity_classes)))
    if cur:
        fights.append(cur)
    for f in fights:
        f['entityClasses'] = {str(k): v for k, v in entity_classes.items()}
        # name every unit as best we can
        for u in f['units']:
            if not u.get('name'):
                u['name'] = names.get(u.get('playerId')) or (f'pet {u["pet"]["classId"]}' if u.get('pet') else f'entity {u["entity"]} (class {u["classId"]})')
    if dec.problems:
        print('decode problems:', *dec.problems[:10], sep='\n  ')
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    index_path = out_dir / 'index.json'
    index = json.load(open(index_path, encoding='utf-8')) if index_path.exists() else []
    written = []
    for f in fights:
        gid = f.get('gameId') or f['captured'].replace(':', '')
        dst = out_dir / f'{gid}.json'
        json.dump(f, open(dst, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
        written.append(dst)
        index = [x for x in index if x.get('gameId') != gid]
        index.append({'gameId': gid, 'file': dst.name, 'stage': f.get('stage'), 'units': [u['name'] for u in f['units'] if u.get('isPlayer')],
                      'rounds': len(f['rounds']), 'steps': sum(len(r['steps']) for r in f['rounds']),
                      'result': f.get('result'), 'captured': f['captured']})
    json.dump(index, open(index_path, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    print(f'{len(fights)} fight(s) in {decoded_path}')
    for f, dst in zip(fights, written):
        print(f'  {dst}: stage {f.get("stage")}, {len(f["units"])} units, {len(f["rounds"])} rounds, '
              f'{sum(len(r["steps"]) for r in f["rounds"])} steps, result {f.get("result")}')
    return written


def show(path):
    f = json.load(open(path, encoding='utf-8'))
    byid = {u['entity']: u for u in f['units']}
    def nm(e):
        u = byid.get(e)
        return u['name'] if u else (f'#{e}' if e is not None else '-')
    print(f'fight {f.get("gameId")}  stage {f.get("stage")}  speed {f.get("speed")}  viewer faction {f.get("viewerFaction")}  result {f.get("result")}')
    print('units:')
    for u in f['units']:
        sk = ', '.join(f'{v["item"]} r{v["rank"]} L{v["level"]}' for k, v in sorted(u['skills'].items()))
        print(f'  #{u["entity"]:<4} f{u["faction"]} {str(u["name"]):<16} class {u["classId"]} lvl {u["level"]} {u["subRank"]} hp {u["hp"]} at {u["pos"]} '
              f'{"pet" if u.get("isPet") else "player" if u.get("isPlayer") else u.get("characterType")}  skills: {sk}')
    if f.get('queue0'):
        print('initial queue:', ', '.join(f'{nm(q["unit"])} next {q["next"]:.1f}' for q in f['queue0']))
    for pre in f.get('preRounds') or []:
        print('  [setup]', line(pre, nm))
    for i, r in enumerate(f['rounds']):
        print(f'-- round message {i + 1} ({len(r["steps"])} steps)')
        for s in r['steps']:
            print(f'  {s.get("t", 0) or 0:7.2f}s  {line(s, nm)}')


def line(s, nm):
    ev = s.get('ev')
    if ev == 'skill':
        return f'{nm(s["who"])} casts item {s["item"]} (slot {s["slot"]}) aim {s["aim"]} target {nm(s.get("target"))}'
    if ev == 'damage':
        flags = ' '.join(k for k in ('crit', 'block', 'dodge', 'blind', 'immune', 'trueDmg') if s.get(k))
        return (f'{nm(s["src"])} -> {nm(s["target"])}: {s["result"]} {s["value"]} (shield {s["shield"]}, abs {s["absolute"]}) '
                f'{s.get("ele")} {s.get("hitType")} hit#{s.get("hitClass")} {flags}')
    if ev == 'status':
        return f'status {s["cls"]} ({s["action"]}) on {nm(s["apply"])} from {nm(s.get("src"))} via {s.get("srcSkill")} x{s["stack"]} dur {s["dur"]}'
    if ev == 'hit':
        return f'hit {s["kind"]} #{s["cls"]} index {s["index"]} delay {s["delay"]}'
    if ev == 'queue':
        return f'queue {s["kind"]} {nm(s["unit"])} pre {s.get("pre")} next {s.get("next")} {s.get("state") or ""}'
    if ev == 'acting':
        return f'*** {nm(s["unit"])} acts'
    if ev == 'finish':
        return f'{nm(s["unit"])} finishes turn'
    if ev == 'pos':
        return f'{nm(s["unit"])} moves to {s["to"]}'
    if ev == 'cd':
        return f'{nm(s["unit"])} cooldown slots {s["slots"]} {s["change"]:+d}'
    if ev == 'globalRound':
        return f'global round {s["n"]}'
    if ev == 'personalRound':
        return f'{nm(s["unit"])} round {s["n"]}'
    if ev == 'gameStatus':
        return f'game status {s["status"]}'
    if ev == 'shield':
        return f'shield status #{s["status"]} {s["remain"]}/{s["max"]} (was {s["pre"]})'
    if ev == 'tick':
        return f'status #{s["status"]} {"heals" if s.get("cure") else "deals"} {s["value"]}'
    if ev == 'stack':
        return f'{nm(s["unit"])} status #{s["status"]} stacks {s["count"]}'
    if ev == 'hp':
        return f'{nm(s["unit"])} hp {s["hp"]}'
    if ev == 'remove':
        return f'remove #{s["id"]}'
    if ev == 'action':
        return f'action {s["action"]} #{s["cls"]} on {nm(s.get("apply"))}'
    if ev == 'unit':
        return f'unit added #{s["id"]} class {s["cls"]}'
    if ev == 'add':
        return f'entity #{s["id"]} class {s["cls"]} {s.get("comps")}'
    if ev == 'syncDamage':
        return f'{nm(s["unit"])} damage sync {s["rows"]}'
    if ev == 'value':
        return f'{s.get("type")} {s.get("val")}'
    if ev == 'mod':
        return f'{s["type"]} ' + ' '.join(f'{k}={v}' for k, v in s.items() if k not in ('ev', 'type', 't', 'msg'))
    return f'{s.get("type")} {json.dumps(s.get("data"))[:120]}'


def fighters(path, out):
    """The fight's player units in the team page's fighters.json shape."""
    sys.path.insert(0, str(ROOT / 'web' / 'build'))
    import team_data  # noqa
    f = json.load(open(path, encoding='utf-8'))
    out_list = []
    for u in f['units']:
        if not u.get('isPlayer'):
            continue
        techs = [{'id': v['item'], 'rank': v['rank'] or 1, 'level': v['level'] or 1} for k, v in sorted(u['skills'].items())]
        charms = [{'id': v['item'], 'rank': v['rank'] or 1, 'level': v['level'] or 1} for k, v in sorted(u['passives'].items())]
        out_list.append({'id': u.get('playerId') or u['entity'], 'name': u['name'], 'cls': u.get('classId'), 'level': u.get('level'),
                         'subRank': u.get('subRank'), 'rank': 0, 'rating': None, 'rankPos': None,
                         'sheet': team_data.sheet_of(u['props']), 'techs': techs[:4], 'charms': charms[:4],
                         'pet': (u.get('pet') or {}).get('classId'), 'faction': u['faction'], 'pos': u['pos'], 'entity': u['entity']})
    json.dump(out_list, open(out, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    print(f'wrote {out}: {len(out_list)} players')


def main():
    a = sys.argv[1:]
    if not a or a[0] not in ('extract', 'show', 'fighters'):
        print(__doc__); return
    if a[0] == 'extract':
        src = a[1]; out = 'out/fights'; roster = str(ROOT / 'out' / 'liveproto' / 'roster.json')
        if '-o' in a: out = a[a.index('-o') + 1]
        if '--roster' in a: roster = a[a.index('--roster') + 1]
        extract(src, out, roster)
    elif a[0] == 'show':
        show(a[1])
    elif a[0] == 'fighters':
        dst = a[a.index('-o') + 1] if '-o' in a else a[1].replace('.json', '.fighters.json')
        fighters(a[1], dst)


if __name__ == '__main__':
    main()
