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
            walk_hits(info["HitList"], out, depth + 1, at)
            continue
        dmg = comp(info.get("DamageId"), "FightDamageComponent") or {}
        on = [{"status": s["StatusId"], "chance": s.get("BasePercent", 1.0),
               "byProp": bool(s.get("AffectedByProp")), "target": s.get("TargetType")}
              for s in (dmg.get("StatusList") or []) if s.get("StatusId")]
        out.append({"prop": info.get("DamageProp"), "fixed": info.get("FixedDamageProp"),
                    "type": info.get("DamageType"), "kind": name.replace("Fight", "").replace("Component", ""),
                    "scope": len(info.get("Scope") or []), "on": on, "at": at,
                    "true": bool(info.get("IsTrueDamage")), "ignoreShield": bool(info.get("DamageIgnoreShield"))})


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
            "resetCdAtStart": bool(fsc.get("ResetCDAtStart")),
            "limitedTimes": fsc.get("LimitedTimes", -1), "aiPriority": ai,
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
         "stack": bool(fs.get("IsOpenStack")), "maxStack": fs.get("MaxStackedCount", 0)}
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
                sts = _status_cfgs(info.get("StatusCfgs") or info.get("TriggerStatusCfgs"))
                if not trig and not sts:
                    unmodelled.append(_human(cname))
                    continue
                pv = dict(base, kind=kind, triggers=trig, statuses=sts)
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

    def note_hits(hits):
        for h in hits:
            for o in h.get("on", []):
                pending_status.add(o["status"])

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
                     "r": skill_rows(eid), "ec": ec, "pvp": pvp}
            if ec:
                note_hits(ec["hits"])
            trig[str(sk)] = entry
        for sid in list(pending_status - set(int(k) for k in statuses)):
            summ = status_summary(sid, SD, status_rows)
            if summ:
                statuses[str(sid)] = summ
                for key in ("roundStart", "onEnd"):
                    for t in summ.get(key, []):
                        pending_skill.add(t["skill"])
            else:
                statuses[str(sid)] = {"id": sid, "action": "Unknown", "dur": -1}
        if not (pending_skill - seen_skill) and not (pending_status - set(int(k) for k in statuses)):
            break

    duel["statuses"] = statuses
    duel["trig"] = trig
    return duel
