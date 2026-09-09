"""Enrich the duel dataset from the decoded EC prefabs (out/ec_decoded/*.json).

What the prefab tree looks like, and what we take from each layer:

  skill entity ── FightSkillComponent ── HitList[] ──► hit entity
       │            ElementType, SkillType, TargetType,        │  FightHitFixedComponent / FightHitRandomTargetComponent
       │            ResetCDAtStart, LimitedTimes, Ai           │    DamageProp, FixedDamageProp, nested HitList (random targets)
       │                                                        └─ DamageId ──► damage entity
       │                                                                          FightDamageComponent.StatusList[]
       │                                                                            {StatusId, BasePercent, AffectedByProp}
       └── (Charms) PassiveStatusIdList ──► passive status entity
                       FightStatus{HitSkill,RoundStart,DamageSkill,RoundCheckSkill}Component.TriggerSkillCfgs[]

  status entity ── ActionComponent.ActionType (Stun, Frozen, Blinding, Poisoned, Shield, Status ...)
                ── FightStatusComponent (DurationRound, RoundTarget, RoundUpdateTiming, StatusType, stacking)
                ── FightStatusPropComponent           -> stat props from entity_prop_status, rank/level scaled
                ── FightStatusDamageFalloffComponent  -> per-hit decay for the source skill
                ── FightStatusShieldPersistentComponent
                ── FightStatusRoundStartComponent     -> trigger skills each round (DoT, regen)
                ── StatusEndComponent                 -> trigger skills on expiry
                ── FightStatusSkillStopCdComponent    -> cooldowns frozen while it lasts
                ── FightStatusHitDmgAddPerComponent   -> DurationSkillCount: lasts N of the holder's skills

"Applicator" in these prefabs is the entity the status sits on; "Creator" is whoever put it there.
"""
from __future__ import annotations
import glob, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_ENTS = None


def ents():
    global _ENTS
    if _ENTS is None:
        _ENTS = {}
        for f in glob.glob(str(ROOT / "out" / "ec_decoded" / "*.json")):
            for e in json.load(open(f, encoding="utf-8")):
                _ENTS[e["id"]] = e
    return _ENTS


def comp(eid, name):
    e = ents().get(eid)
    if not e:
        return None
    for c in e["components"]:
        if c["type"] == name:
            return c.get("info") or {}
    return None


def comps(eid):
    e = ents().get(eid)
    return {c["type"]: (c.get("info") or {}) for c in e["components"]} if e else {}


def _trigger_cfgs(cfgs):
    out = []
    for t in cfgs or []:
        if not t or not t.get("SkillId"):
            continue
        out.append({"skill": t["SkillId"], "chance": t.get("BasePercent", 1.0),
                    "byProp": bool(t.get("AffectedByProp")), "target": t.get("Target"),
                    "source": t.get("Source")})
    return out


# ---------------------------------------------------------------- hits
def walk_hits(hitlist, out, depth=0, t0=0.0):
    """Flatten a skill's hit tree into one entry per landed hit, in order, each
    stamped with the moment it lands (HitCfg.Delay, seconds from the cast)."""
    if depth > 4:
        return
    for h in hitlist or []:
        hid = h.get("ClassId")
        at = round(t0 + float(h.get("Delay") or 0.0), 3)
        cs = comps(hid)
        hitc = None
        for name, info in cs.items():
            if name.startswith("FightHit"):
                hitc = (name, info)
                break
        if not hitc:
            continue
        name, info = hitc
        if info.get("HitList"):                       # random-target fan-out: the sub-hits are the hits
            sub = []
            for pi, hc in enumerate(info["HitList"]):       # one pick per HitCfg; each may expand to several hits
                s0 = len(sub)
                walk_hits([hc], sub, depth + 1, at)
                for x in sub[s0:]:
                    x["pick"] = pi
            if name == "FightHitRandomTargetComponent":
                # FightHitRandomTargetComponentInfo: one pick per HitCfg, with replacement, from the (unsorted)
                # Scope cells around the hit centre; empty cells allowed unless AllowEmptyScope is false;
                # MiniHitTargetCount picks must land on a unit
                rnd = {"g": f"{hid}", "cells": [list(c.get("Pos") or [0, 0]) for c in (info.get("Scope") or [])],
                       "onSource": bool(h.get("ActOnSouce")), "n": len(info["HitList"]),
                       "allowEmpty": bool(info.get("AllowEmptyScope", True)), "minHits": info.get("MiniHitTargetCount", 0) or 0,
                       "notSameTarget": bool(info.get("NotSameTarget")), "notSameGrid": bool(info.get("NotSameGrid")),
                       "notSameEmpty": bool(info.get("NotSameEmptyScope")), "notAllowEmpty": bool(info.get("NotAllowHitEmpty"))}
                for x in sub:
                    x["rnd"] = rnd
            out.extend(sub)
            continue
        dmg = comp(info.get("DamageId"), "FightDamageComponent") or {}
        mv = dmg.get("MoveCfg") or {}
        move = None
        if mv.get("MoveBehaviourId"):
            # FightSKillMoveCfg on the damage: the victim's forced move (Drag / Knockback)
            move = {"offset": list(mv.get("Offset") or [0, 0]), "towards": bool(mv.get("TowardsTargetPos")),
                    "dir": mv.get("SkillMoveDirection"), "distance": mv.get("Distance", -1), "delay": mv.get("Delay", 0),
                    "expand": bool(mv.get("CanExpandOffset")), "chance": mv.get("BasePercent", 1.0),
                    "byProp": bool(mv.get("AffectedByProp")), "cancelDiag": bool(mv.get("CancelDiagonally"))}
        on = [{"status": s["StatusId"], "chance": s.get("BasePercent", 1.0),
               "byProp": bool(s.get("AffectedByProp")), "target": s.get("TargetType")}
              for s in (dmg.get("StatusList") or []) if s.get("StatusId")]
        scope_cells = [list(c.get("Pos") or [0, 0]) for c in (info.get("Scope") or [])]
        summon = None
        if name == "FightHitSummonComponent":
            # FightHitSummonComponentInfo: the hit acts on SummonScope (BaseScopes = each entry's Base HitScopCfg);
            # every cell rolls its own Rate to spawn the grid item (SummonGridItemId + SummonGridItemStatus) or
            # the creature (SummonId / SummonPoolSetting)
            sc = [c for c in (info.get("SummonScope") or []) if c]
            scope_cells = [list(((c.get("Base") or {}).get("Pos")) or [0, 0]) for c in sc]
            pools = [(pl.get("SummonPoolCfg") or {}).get("SummonId") for pl in ((info.get("SummonPoolSetting") or {}).get("SummonPools") or [])]
            summon = {"gridItem": info.get("SummonGridItemId") or 0, "gridStatuses": [x for x in (info.get("SummonGridItemStatus") or []) if x],
                      "creature": info.get("SummonId") or 0, "pools": [x for x in pools if x],
                      "rates": [c.get("Rate", 1.0) for c in sc], "rate": info.get("Rate", 1.0),
                      "lifespan": info.get("LifespanStatusId") or 0}
        out.append({"prop": info.get("DamageProp"), "fixed": info.get("FixedDamageProp"),
                    "type": info.get("DamageType"), "kind": name.replace("Fight", "").replace("Component", ""),
                    "scope": len(scope_cells), "on": on, "at": at,
                    "true": bool(info.get("IsTrueDamage")), "ignoreShield": bool(info.get("DamageIgnoreShield")),
                    # the area: cell offsets from the hit centre (HitScopCfg.Pos), and whether that centre is
                    # the caster's own cell (HitCfg.ActOnSouce) rather than the skill's aim point
                    "cells": scope_cells, "summon": summon,
                    "onSource": bool(h.get("ActOnSouce")),
                    "chained": ({"repeat": bool(info.get("Repeat")), "back": bool(info.get("Back")), "preferUnvisited": bool(info.get("PreferUnvisited"))}
                                if name == "FightHitChainedComponent" else None),
                    "move": move})
        # FightDamageComponentInfo.ChildSkillCfg: a skill cast on every unit this hit damages (its own coefficients,
        # statuses and forced move); its hits are appended right after, marked as children of this hit
        ch = dmg.get("ChildSkillCfg") or {}
        if ch.get("SkillId") and depth < 4:
            sub = []
            walk_hits((comp(ch["SkillId"], "FightSkillComponent") or {}).get("HitList"), sub, depth + 1, at)
            for x in sub:
                x["child"] = {"of": len(out) - 1, "eid": ch["SkillId"], "chance": ch.get("Rate", 1.0), "hpBelow": ch.get("LessThanHpPer", -1)}
            out.extend(sub)


def skill_ec(ec_entity_id):
    fsc = comp(ec_entity_id, "FightSkillComponent")
    if fsc is None:
        return None
    hits = []
    walk_hits(fsc.get("HitList"), hits)
    ai = (fsc.get("Ai") or {}).get("AiPriorityTypes") or []
    # how long the cast takes on screen: the prefab's own duration, else the last hit plus a beat
    dur = max(float(fsc.get("Duration") or 0), float(fsc.get("ActionDuration") or 0),
              (max([h["at"] for h in hits]) + 0.4) if hits else 0.8)
    return {"ele": fsc.get("ElementType") or "None", "skillType": fsc.get("SkillType"),
            "target": fsc.get("TargetType"), "hits": hits, "dur": round(dur, 2),
            # where the aim point may be placed: offsets from the caster, near to far (FightSkillComponentInfo.Range)
            "range": [list(r) for r in (fsc.get("Range") or [])], "rangeType": fsc.get("RangeType"),
            "targetKind": fsc.get("SkillTargetType"),
            # FightSkillComponentInfo.SourceMoveList: the caster's displacement (dashes, leaps), ascending Delay
            "sourceMove": sorted([{"offset": list(m.get("Offset") or [0, 0]), "towards": bool(m.get("TowardsTargetPos")),
                                   "dir": m.get("SkillMoveDirection"), "distance": m.get("Distance", -1), "delay": m.get("Delay", 0),
                                   "expand": bool(m.get("CanExpandOffset")), "aiMust": bool(m.get("AiMustMoveTo"))}
                                  for m in (fsc.get("SourceMoveList") or []) if m and m.get("MoveBehaviourId")], key=lambda m: m["delay"]),
            "flipSource": fsc.get("FlipSource", True),
            # FightSkillComponentInfo.CanTriggerChild: whether this skill's hits may set off child skills and
            # status hooks (a Burn tick has it off, so it cannot chain into Radiant Sear and the like)
            "canTriggerChild": fsc.get("CanTriggerChild", True),
            "canTriggerStatuses": fsc.get("CanTriggerStatusEntityIds") or [],
            "resetCdAtStart": bool(fsc.get("ResetCDAtStart")),
            "limitedTimes": fsc.get("LimitedTimes", -1), "aiPriority": ai,
            # the AI's ordering for the last skill of a turn, and whether a ranged caster backs off (SkillAiCfg)
            "aiLast": (fsc.get("Ai") or {}).get("LastAIPriorityTypes") or [],
            "dontKeepDistance": bool((fsc.get("Ai") or {}).get("DontKeepDistance")),
            "needCondition": bool(fsc.get("NeedConditionStatusMeetToRelease"))}


# ---------------------------------------------------------------- statuses
ACTION_SKIP = {"Stun", "Frozen"}                 # the holder loses its action
ACTION_FLAG = {"Blinding", "Poisoned", "Restrict", "Fear", "Confusion", "Ridicule", "Damp",
               "Immobilize", "SlowAction", "Chill", "Burn", "SuperArmor", "Invincible"}


def status_summary(sid, SD, rank_rows):
    """Everything the simulator needs to know about one status entity."""
    cs = comps(sid)
    fs = cs.get("FightStatusComponent")
    if fs is None:
        return None
    act = (cs.get("ActionComponent") or {}).get("ActionType") or "Status"
    s = {"id": sid, "action": act,
         "dur": fs.get("DurationRound", -1), "holder": fs.get("RoundTarget"),
         "timing": fs.get("RoundUpdateTiming"), "type": fs.get("StatusType"),
         "stack": bool(fs.get("IsOpenStack")), "maxStack": fs.get("MaxStackedCount", 0),
         "ele": fs.get("ElementType") or "None"}
    fo = cs.get("FightStatusDamageFalloffComponent")
    if fo:
        s["falloff"] = {"pct": (fo.get("FalloffPercent") or 0) / 10000.0,
                        "start": fo.get("NumOfStart", 1), "max": fo.get("MaxFalloffCount", -1)}
    if "FightStatusShieldPersistentComponent" in cs:
        s["shield"] = True
    if "FightStatusSkillStopCdComponent" in cs:
        s["cdFreeze"] = True
    hd = cs.get("FightStatusHitDmgAddPerComponent")
    if hd:
        s["skillCount"] = hd.get("DurationSkillCount", -1)
        s["onlyAttack"] = hd.get("OnlySkillType") == "Attack"
    rs = cs.get("FightStatusRoundStartComponent")
    if rs:
        s["roundStart"] = _trigger_cfgs(rs.get("StatusTriggerSkillCfgs"))
    se = cs.get("StatusEndComponent")
    if se:
        s["onEnd"] = _trigger_cfgs(se.get("StatusTriggerSkillCfgs"))
    ar = cs.get("FightStatusAgentRateComponent")
    if ar:
        s["boosts"] = {"actions": ar.get("LimitActionTypes") or [], "prop": ar.get("AddPropType")}
    mn = cs.get("FightStatusMoveNearComponent")
    if mn:
        # FightStatusMoveNearComponentInfo: fires its skills on units in Range when the status starts
        # (TryAtStart), when a unit steps in from outside (TryAtEnterRange), or when a unit standing inside
        # starts its own round (TryAtStandRound); a Burn cell is exactly this on a grid item
        s["moveNear"] = {"rate": mn.get("Rate", 1.0), "cells": [list(c) for c in (mn.get("Range") or [])],
                         "onStart": bool(mn.get("TryAtStart")), "onEnter": bool(mn.get("TryAtEnterRange")),
                         "onStand": bool(mn.get("TryAtStandRound")), "onInRangeMove": bool(mn.get("TryAtInRangeMove")),
                         "onRound": bool(mn.get("TryAtRound")), "onMoved": bool(mn.get("TryAtMoved")),
                         "target": mn.get("TargetType"), "maxCount": mn.get("MaxCount", -1),
                         "onlyFirst": mn.get("OnlyFirstInPosition", True),
                         "skills": _trigger_cfgs(mn.get("Skills")) + _direct_skill(mn)}
    sar = cs.get("StatusAutoRemoveComponent")
    if sar:
        s["removeAtRoundTargetDie"] = bool(sar.get("RemoveAtRoundTargetDie"))
        s["removeAtCreatorDie"] = bool(sar.get("RemoveAtCreatorDie"))
    # Rapid Cast's marker: a one-shot status whose only behaviour is a global-round
    # hook. The prefab fixes the timing (battle start, self); the amount — one
    # turn off every Technique — is the skill's own text, since the hook's effect
    # lives in code rather than in a prop.
    if "FightStatusGlobalRoundUpdateComponent" in cs and not cs.get("FightStatusPropComponent"):
        pass
    if "FightStatusGlobalRoundUpdateComponent" in cs:
        s["cdStart"] = -1
    # whatever numbers the status carries — stat changes, shield size, block value —
    # sit on its entity_prop_status row, scaled by the caster's rank and level
    rows = rank_rows(sid)
    if rows:
        s["props"] = rows                        # {rank: {prop: {v|m,g,k,pct}}}
    return s


# ---------------------------------------------------------------- charms
PASSIVE_KINDS = {"FightStatusHitSkillComponent": "hit",
                 "FightStatusRoundStartComponent": "roundStart",
                 "FightStatusDamageSkillComponent": "damaged",
                 "FightStatusRoundCheckSkillComponent": "roundCheck",
                 "FightStatusSkillStartComponent": "skillStart"}


def _status_cfgs(cfgs):
    out = []
    for c in cfgs or []:
        if not c or not c.get("StatusId"):
            continue
        out.append({"status": c["StatusId"], "chance": c.get("BasePercent", 1.0),
                    "target": c.get("ApplyTarget") or c.get("TargetType") or "Applicator"})
    return out


def _direct_skill(info):
    """Some components name their skill straight on the component (Counter Blade's
    FightStatusDamageSkillComponent.SkillId = 11210) rather than in a cfg list."""
    sid = info.get("SkillId")
    return [{"skill": sid, "chance": 1.0, "byProp": False, "target": "TriggerSource",
             "source": "Applicator"}] if sid else []


# components every status carries, or that the sheet already covers (the always-on props)
BOILERPLATE = {"ActionComponent", "FightStatusComponent", "FightStatusPropComponent", "FightStatusStartComponent"}


def _human(cname):
    return re.sub(r"([a-z])([A-Z])", r"\1 \2", cname.replace("FightStatus", "").replace("Component", "")).lower()


def charm_passive(status_ids):
    """The behaviours a Charm's passive statuses carry, as the simulator's trigger
    kinds, plus the component types it has no model for, so the page can say so.

    Kinds: hit / damaged / roundStart / roundEnd / roundCheck / skillStart fire
    skills and apply statuses; skillEnd applies a status every N Techniques
    (Blazing Clash); hpUnit applies one per UnitHpPer of max HP lost (Frame of
    Battles); hpBelow fires when HP crosses under a fraction (Pure Protection);
    deathSave floors a lethal hit (Indomitable Will). A hit status that carries a
    StatusStackCountComponent pays out at that count with the Charm's own
    numbers (Blade of Judgment's Mark)."""
    out, unmodelled = [], []
    for pid in status_ids:
        cs = comps(pid)
        for cname, info in cs.items():
            if cname in BOILERPLATE:
                continue
            kind = PASSIVE_KINDS.get(cname)
            base = {"status": pid, "rate": info.get("Rate", 1.0),
                    "maxCount": info.get("MaxCount", info.get("MaxInvokeCount", -1)),
                    "onlyAttack": info.get("OnlySkillType") == "Attack"}
            if kind:
                trig = _trigger_cfgs(info.get("TriggerSkillCfgs") or info.get("SkillCfgs")
                                     or info.get("StatusTriggerSkillCfgs")) + _direct_skill(info)
                sts = _status_cfgs(info.get("StatusCfgs") or info.get("TriggerStatusCfgs") or info.get("StatusTriggerStatusCfgs"))
                # FightStatusDamageSkillComponent: StatusId goes on the damage target (the wearer), SourceStatusId on the attacker
                if info.get("StatusId"):
                    sts.append({"status": info["StatusId"], "chance": 1.0, "byProp": False, "target": "Applicator"})
                if info.get("SourceStatusId"):
                    sts.append({"status": info["SourceStatusId"], "chance": 1.0, "byProp": False, "target": "TriggerSource"})
                if not trig and not sts:
                    unmodelled.append(_human(cname))
                    continue
                pv = dict(base, kind=kind, triggers=trig, statuses=sts)
                if cname in ("FightStatusDamageSkillComponent", "FightStatusHitSkillComponent"):
                    # each true flag restricts the event: Block = only a blocked hit, Crit = only a crit,
                    # Damage = only when damage landed, Cure = only a heal; ConditionCount = every Nth event
                    pv["onBlock"] = bool(info.get("Block"))
                    pv["onCrit"] = bool(info.get("Crit"))
                    pv["onDamage"] = bool(info.get("Damage", True))
                    pv["onCure"] = bool(info.get("Cure"))
                    pv["conditionCount"] = info.get("ConditionCount", 1) or 1
                    pv["elements"] = info.get("ElementTypes") or info.get("HitSkillElementTypes") or []
                    if cname == "FightStatusDamageSkillComponent":
                        pv["eachRoundMax"] = info.get("EachRoundMaxCount", -1)
                        pv["skillTargetType"] = info.get("SkillTargetType") or "All"
                        pv["isAttackerTarget"] = bool(info.get("IsAttackerTarget"))
                        pv["greaterThanMaxHpPer"] = info.get("GreaterThanMaxHpPer", -1.0)
                    else:
                        pv["hitSkillTypes"] = info.get("HitSkillTypes") or []
                        pv["onlySkills"] = info.get("HitSkillEntityClassIds") or []
                        pv["roundReset"] = info.get("RoundResetCount", -1)
                        pv["hitSource"] = info.get("HitSourceType") or "Applicator"
                for st in sts:
                    scc = comp(st["status"], "StatusStackCountComponent")
                    if scc and scc.get("StackCount"):
                        pv["stackTrigger"] = {"status": st["status"], "count": scc["StackCount"]}
                out.append(pv)
            elif cname == "FightStatusRoundEndComponent":
                trig = _trigger_cfgs(info.get("TriggerSkillCfgs"))
                sts = _status_cfgs(info.get("TriggerStatusCfgs"))
                if trig or sts:
                    out.append(dict(base, kind="roundEnd", rate=1.0, triggers=trig, statuses=sts))
                else:
                    unmodelled.append(_human(cname))
            elif cname == "FightStatusSkillEndComponent" and info.get("StatusEntClassId"):
                out.append(dict(base, kind="skillEnd", rate=1.0, every=info.get("MetCount") or 1, triggers=[],
                                statuses=[{"status": info["StatusEntClassId"], "chance": 1.0, "target": "Applicator"}]))
            elif cname == "FightStatusHpDecreaseUnitComponent":
                sts = _status_cfgs(info.get("StatusList"))
                trig = _trigger_cfgs(info.get("Skills"))
                if sts or trig:
                    out.append(dict(base, kind="hpUnit", rate=1.0, unit=info.get("UnitHpPer") or 0.15,
                                    triggers=trig, statuses=sts))
                else:
                    unmodelled.append(_human(cname))
            elif cname == "FightStatusHpLessThanComponent":
                sts = [{"status": x, "chance": 1.0, "target": "Applicator"} for x in (info.get("StatusList") or []) if x]
                sts += _status_cfgs(info.get("StatusCfgs"))
                trig = _trigger_cfgs(info.get("SkillCfgs")) + _direct_skill(info)
                if sts or trig:
                    out.append(dict(base, kind="hpBelow", rate=1.0, pct=info.get("HpLessThanPercentage") or 0.5,
                                    triggers=trig, statuses=sts))
                else:
                    unmodelled.append(_human(cname))
            elif cname == "FightStatusHpLimitComponent":
                # LowerLimit and MaxCount are "replaceable entry parameters"
                # (ConfigLowerLimit / ConfigMaxCount) and decode as defaults here;
                # the card says 1 HP, the first time
                out.append(dict(base, kind="deathSave", rate=1.0, maxCount=info.get("MaxCount") or 1,
                                limit=info.get("LowerLimit") or 1,
                                triggers=_trigger_cfgs(info.get("SkillList")),
                                statuses=_status_cfgs(info.get("StatusList"))))
            elif cname == "StatusApplyTargetHandleComponent":
                # a hook on statuses the wearer applies: when the applied status carries the filtered gameplay tag
                # (bit 19 = Status.Type.Poisoned, the Erosion family), add another status to the same target
                hs = [h for h in (info.get("HandleSettings") or []) if isinstance(h, dict)]
                flt = info.get("FilterCondition") or {}
                tag = None
                try:
                    q = flt.get("Query") or []
                    words = q[0][0][0] if q and isinstance(q[0], list) and q[0] and isinstance(q[0][0], list) else None
                    if isinstance(words, list) and words and words[0] & (1 << 19):
                        tag = "Poisoned"
                except Exception:
                    tag = None
                sts = []
                for h in hs:
                    res = h.get("StatusIdResolver") or {}
                    if res.get("StatusClassId"):
                        sts.append({"status": res["StatusClassId"], "chance": h.get("Rate", 1.0), "byProp": bool(h.get("AffectedByProp")), "target": "TriggerTarget"})
                if sts:
                    out.append(dict(base, kind="statusApplied", rate=1.0, when=tag, perTarget=info.get("MaxCountPerTargetOnceTrigger", 1),
                                    triggers=[], statuses=sts))
                else:
                    unmodelled.append(_human(cname))
            elif cname == "FightStatusDoDamageHandleComponent":
                # on damage the wearer deals (filtered by the damaging skill's element), apply statuses to the victim
                sts = [{"status": c["StatusId"], "chance": c.get("BasePercent", 1.0), "byProp": bool(c.get("AffectedByProp")), "target": "TriggerTarget"}
                       for c in (info.get("StatusCfgs") or []) if c and c.get("StatusId")]
                trig = _trigger_cfgs(info.get("SkillCfgs"))
                if sts or trig:
                    out.append(dict(base, kind="hit", elements=info.get("HitSkillElementTypes") or [], ignoreSkills=info.get("IgnoreHitSkills") or [],
                                    maxCount=info.get("MaxTriggerCount", -1), triggers=trig, statuses=sts))
                else:
                    unmodelled.append(_human(cname))
            elif cname == "FightStatusHitDmgAddPerComponent":
                # an outgoing-damage bonus on the wearer's hits, sized by the Charm's own StatusDmgAddPer row and,
                # when ScalePropByStatusTypeCount, multiplied by how many matching statuses the target carries
                st = info.get("StatusType") or {}
                out.append(dict(base, kind="dmgAdd", rate=info.get("Rate", 1.0), onlyAttack=info.get("OnlySkillType") == "Attack",
                                needTargetStatus=bool(st.get("IsCondition")), anyTypes=st.get("AnyStatusTypes") or [],
                                scaleByCount=bool(info.get("ScalePropByStatusTypeCount")), countType=st.get("CountType"),
                                maxCount=st.get("MaxStatusCount", -1), unit=st.get("Unit", 1.0), isAddition=bool(st.get("IsAdditionCount")),
                                triggers=[], statuses=[]))
            elif cname == "FightStatusRoleDieComponent":
                trig = _trigger_cfgs(info.get("SkillCfgs"))
                sts = _status_cfgs(info.get("StatusCfgs"))
                out.append(dict(base, kind="revive", rate=1.0, maxCount=info.get("MaxCount", 0), sameFaction=info.get("SameFaction", True),
                                characterTypes=info.get("CharacterTypes") or [], triggers=trig, statuses=sts))
            elif cname == "FightStatusDamageCustomComponent":
                # a strike back at the attacker when the wearer takes skill damage; magnitude = the Charm's DamageByDamage row
                out.append(dict(base, kind="reflect", rate=info.get("Rate", 1.0), needShield=bool(info.get("NeedShield")),
                                bySkill=info.get("CheckTriggerBySkill", True), valueType=info.get("ConditionDamageValueType"),
                                triggers=[{"skill": info["SkillId"], "chance": 1.0, "byProp": False, "target": "TriggerSource"}] if info.get("SkillId") else [],
                                statuses=[]))
            elif cname == "FightStatusMoveNearComponent":
                trig = _trigger_cfgs(info.get("Skills")) + _direct_skill(info)
                out.append(dict(base, kind="proximity", rate=info.get("Rate", 1.0), cells=[list(c) for c in (info.get("Range") or [])],
                                onEnter=bool(info.get("TryAtEnterRange")), onStandRound=bool(info.get("TryAtStandRound")),
                                onInRangeMove=bool(info.get("TryAtInRangeMove")), target=info.get("TargetType"),
                                characterTypes=info.get("CharacterTypes") or [], triggers=trig, statuses=[]))
            elif cname == "FightStatusActionEndComponent":
                trig = _trigger_cfgs(info.get("Skills"))
                out.append(dict(base, kind="actionEnd", rate=info.get("Rate", 1.0), actions=info.get("ActionTypes") or [],
                                allEnd=bool(info.get("IsTargetTypeAllEnd")), triggers=trig, statuses=[]))
            elif cname == "FightStatusHitCustomCureComponent":
                # lifesteal on the wearer's damaging hits; magnitude = the Charm's SuckHpByDamage / FixedSuckHp row
                out.append(dict(base, kind="lifesteal", rate=info.get("Rate", 1.0), onlyAttack=info.get("OnlySkillType") == "Attack",
                                maxCount=info.get("MaxInvokeCount", -1), triggers=[], statuses=[]))
            elif cname == "FightStatusKillSkillComponent":
                cd = info.get("CustomDamageInfo") or {}
                out.append(dict(base, kind="kill", rate=info.get("Rate", 1.0), atDiePos=bool(info.get("IsSkillTargetDiePos")),
                                overflow=bool(info.get("IsCustomOverflowDamage")), customProp=cd.get("DamageProp"),
                                maxCount=info.get("MaxCount", -1),
                                triggers=[{"skill": info["SkillEntId"], "chance": 1.0, "byProp": False, "target": "TriggerTarget"}] if info.get("SkillEntId") else [],
                                statuses=[]))
            elif cname == "FightStatusActionExistComponent":
                out.append(dict(base, kind="whileAction", rate=1.0, actions=info.get("Conditions") or [],
                                triggers=[], statuses=[{"status": info["StatusId"], "chance": 1.0, "target": "Applicator"}] if info.get("StatusId") else []))
            elif cname == "FightStatusHpIncreaseUnitComponent":
                pass                                    # the mirror of hpUnit: stacks come off as HP climbs back; handled with hpUnit
            else:
                unmodelled.append(_human(cname))
    return out, sorted(set(unmodelled))


# ---------------------------------------------------------------- driver
def enrich(duel, SD):
    """Mutates the duel dict: per-skill ec / passive, plus statuses and trigger skills."""
    skills_cfg = SD.skills                       # ClassId -> skill row
    prop_float = SD.prop_float

    def ranks_of(rank_prop_id):
        return sorted(l for l in SD._lp_levels.get(rank_prop_id, []) if l in SD.rank_quality)

    def status_rows(sid):
        """entity_prop_status row -> per-rank stat rows, same maths as the skills page."""
        row = SD.status_ent.get(sid)
        if not row:
            return {}
        try:
            srank = int(row.get("RankPropId") or 0); sgroup = int(row.get("GroupLevelPropId") or 0)
        except Exception:
            return {}
        rks = ranks_of(srank)
        curve_keys = SD._curve_props(sgroup)
        out = {}
        for rk in rks:
            d = {}
            for k, v in row.items():
                if k in SD.SKIP or not str(v).strip() or str(v).strip() == "0":
                    continue
                try:
                    fac = int(v)
                except Exception:
                    continue
                mult = SD.levelprop.get((srank, rk), {}).get(k, 10000) / 10000.0
                is_pct = prop_float.get(k, True)
                if k in curve_keys:
                    d[k] = {"m": mult * (fac / 10000.0) * (0.01 if is_pct else 1), "g": sgroup, "k": k, "pct": is_pct}
                else:
                    d[k] = {"v": SD._trunc(fac, SD.levelprop.get((srank, rk), {}).get(k, 10000), is_pct), "pct": is_pct}
            if d:
                out[str(rk)] = d
        return out

    def skill_rows(eid):
        """A trigger skill's per-rank numbers, the way a Technique's are built."""
        e = SD.eps.get(eid)
        if not e:
            return {}
        try:
            rankprop = int(e.get("RankPropId") or 0); group = int(e.get("GroupLevelPropId") or 0)
        except Exception:
            return {}
        rks = ranks_of(rankprop)
        curve_keys = SD._curve_props(group)
        out = {}
        for rk in rks:
            d = {}
            for key, _label in SD.STATS:
                v = (e.get(key) or "").strip()
                if not v or v == "0":
                    continue
                fac = int(v)
                mult = SD.levelprop.get((rankprop, rk), {}).get(key, 10000)
                if key in curve_keys:
                    d["fx" if key == "SkillFixedAttack1" else key] = (mult / 10000.0) * (fac / 10000.0)
                    if key == "SkillFixedAttack1":
                        d["fg"] = group
                    else:
                        d[key + "_g"] = group
                else:
                    d[key] = SD._trunc(fac, mult, key in SD.PCT)
            if d:
                out[str(rk)] = d
        return out

    statuses, trig = {}, {}
    pending_status, pending_skill = set(), set()

    def child_rows(ec):
        """A child skill's own per-rank numbers, PvP scale and governor gate, on each of its hits."""
        for h in ec.get("hits", []):
            c = h.get("child")
            if not c:
                continue
            eid = c["eid"]
            h["childRows"] = skill_rows(eid)
            ep = SD.eps.get(eid) or {}
            try:
                h["childPvp"] = int((ep.get("PvpPropScale") or "10000").strip() or 10000)
            except Exception:
                h["childPvp"] = 10000
            h["childGov"] = (ep.get("AffectedBySkillRank") or "").strip().upper() == "TRUE"
            fsc = comp(eid, "FightSkillComponent") or {}
            h["childEle"] = fsc.get("ElementType") or "None"

    def note_hits(hits):
        for h in hits:
            for o in h.get("on", []):
                pending_status.add(o["status"])
            for sid in ((h.get("summon") or {}).get("gridStatuses") or []):
                pending_status.add(sid)

    for s in duel["skills"]:
        row = skills_cfg.get(s["id"])
        if not row:
            continue
        try:
            eid = int(row.get("EcEntityId") or 0)
        except Exception:
            eid = 0
        ec = skill_ec(eid) if eid else None
        if ec:
            s["ec"] = ec
            if ec["ele"] not in ("None", None):
                s["ele"] = ec["ele"]
            elif ec["hits"]:
                s["ele"] = "Physical"
            note_hits(ec["hits"])
            child_rows(ec)
        if s["kind"] == "Charm":
            ids = [int(x) for x in re.findall(r"\d+", row.get("PassiveStatusIdList") or "")]
            pas, unmod = charm_passive(ids)
            if pas:
                s["passive"] = pas
                for p in pas:
                    for t in p["triggers"]:
                        pending_skill.add(t["skill"])
                    for o in p.get("statuses", []):
                        pending_status.add(o["status"])
                # a Charm whose numbers belong to the status or the strike it
                # produces, not to the standing sheet
                if any(p["kind"] in ("skillEnd", "hpUnit", "hpBelow", "deathSave") or p.get("stackTrigger") for p in pas):
                    s["condProps"] = True
            if unmod:
                s["unmodelled"] = unmod

    # trigger skills can apply statuses, whose triggers can fire skills: close over both
    seen_skill = set()
    for _ in range(4):
        for sk in list(pending_skill - seen_skill):
            seen_skill.add(sk)
            skrow = skills_cfg.get(sk)
            eid = int(skrow["EcEntityId"]) if skrow and skrow.get("EcEntityId") else sk
            ec = skill_ec(eid)
            try:
                pvp = int(((SD.eps.get(eid) or {}).get("PvpPropScale") or "10000").strip() or 10000)
            except Exception:
                pvp = 10000
            entry = {"id": sk, "name": (SD.L(f"item_{sk}_name") if skrow else None) or f"skill {sk}",
                     "r": skill_rows(eid), "ec": ec, "pvp": pvp,
                     "gov": ((SD.eps.get(eid) or {}).get("AffectedBySkillRank") or "").strip().upper() == "TRUE"}
            if ec:
                note_hits(ec["hits"])
                child_rows(ec)
            trig[str(sk)] = entry
        for sid in list(pending_status - set(int(k) for k in statuses)):
            summ = status_summary(sid, SD, status_rows)
            if summ:
                statuses[str(sid)] = summ
                for key in ("roundStart", "onEnd"):
                    for t in summ.get(key, []):
                        pending_skill.add(t["skill"])
                for t in (summ.get("moveNear") or {}).get("skills", []):
                    pending_skill.add(t["skill"])
            else:
                statuses[str(sid)] = {"id": sid, "action": "Unknown", "dur": -1}
        if not (pending_skill - seen_skill) and not (pending_status - set(int(k) for k in statuses)):
            break

    duel["statuses"] = statuses
    duel["trig"] = trig
    return duel
