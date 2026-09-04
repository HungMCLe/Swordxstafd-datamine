#!/usr/bin/env python3
"""Build the skills dataset: tier -> class -> skills, with per-quality stats.

Writes out/_skills.json  (consumed by the site builder and the client-side
quality stepper) and prints a summary.
"""
from __future__ import annotations
import ast, csv, io, json, struct, sys
from pathlib import Path
import xxhash

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "out"
CFG = OUT / "config_decrypted"

# ---------------- localisation ----------------
_LOC = OUT / "localization" / "text_en_US_b88.bytes"
if not _LOC.exists():
    _LOC = OUT / "localization" / "text_en_US.bytes"
_d = _LOC.read_bytes()
_n = struct.unpack_from("<i", _d, 0)[0]
_st = 4 + _n * 12
_idx = {}
for _i in range(_n):
    _h, _o = struct.unpack_from("<Qi", _d, 4 + _i * 12)
    _idx[_h] = _o

def L(key):
    h = xxhash.xxh64(key.encode("utf-8"), seed=0).intdigest()
    if h not in _idx:
        return None
    o = _st + _idx[h]
    ln = struct.unpack_from("<H", _d, o)[0]
    return _d[o + 2:o + 2 + ln].decode("utf-8", "replace")

def rows(name):
    return list(csv.reader(io.StringIO((CFG / name).read_text(encoding="utf-8-sig", errors="replace"))))

def table(name):
    r = rows(name)
    h = [c.strip() for c in r[0]]
    out = []
    for x in r[2:]:
        if not x or not x[0].strip() or x[0].strip().startswith("#"):
            continue
        out.append({h[i]: (x[i] if i < len(x) else "") for i in range(len(h))})
    return out

def ints(s):
    """Parse a config list like [1,2,3] or {1:2,} into a list of ints."""
    s = (s or "").strip()
    if not s or s in ("[]", "{}"):
        return []
    try:
        v = ast.literal_eval(s)
    except Exception:
        return [int(t) for t in __import__("re").findall(r"\d+", s)]
    if isinstance(v, dict):
        return [int(k) for k in v.keys()]
    if isinstance(v, (list, tuple)):
        return [int(t) for t in v]
    return [int(v)]

# ---------------- quality ladder ----------------
# skill_rank is the game's own ladder: 34 ranks grouped into six qualities, and
# RankAddition ("+ how much", per the config's own comment) is the level the
# game prints beside the quality — Rare +0 .. Immortal +10.
QUALITY_EN = {"Blue": "Rare", "Purple": "Epic", "Orange": "Legendary",
              "Gold": "Mythic", "Red": "Divine", "Rainbow": "Immortal"}
QORDER = ["Rare", "Epic", "Legendary", "Mythic", "Divine", "Immortal"]

rank_quality = {}          # rank -> english quality
rank_label = {}            # rank -> "Divine +3"
quality_first_rank = {}    # english quality -> lowest rank
for r in table("skill_rank"):
    try:
        rk = int(r["Rank"])
    except Exception:
        continue
    q = QUALITY_EN.get(r["Quality"].strip())
    if not q:
        continue
    try:
        add = int(r.get("RankAddition") or 0)
    except Exception:
        add = 0
    rank_quality[rk] = q
    rank_label[rk] = f"{q} +{add}"
    quality_first_rank.setdefault(q, rk)

# ---------------- the game's own prop maths ----------------
# BattleFormulaHandler.CalcSkillProps(rankPropId, levelPropId, rankFactorId,
#                                     propFactors, rank, level):
#     base = levelProp[levelPropId][level]
#     d    = ScaleProps(base, levelProp[rankPropId][rank])    per-prop x/10000
#     d    = ScaleProps(d, propFactors, removeUnscaled=true)  keeps base n factors
#     d    = ScaleSrcProps(d, levelProp[rankFactorId][rank])  when set (passives)
# LevelPropParser is a single lookup across every level_prop_* table, keyed by
# class_id, so the tables below are merged into one (class_id, level) map.
LEVEL_TABLES = ["level_prop_skill", "level_prop_skill_passive",
                "level_prop_skill_passive_main", "level_prop_skill_passive_other",
                "level_prop_skill_scale", "level_prop_status",
                "level_prop_skill_fixed_prop", "level_prop_skill_all_fixed_prop"]
levelprop = {}
for _t in LEVEL_TABLES:
    for r in table(_t):
        try:
            _c, _l = int(r["class_id"]), int(r["level"])
        except Exception:
            continue
        d = levelprop.setdefault((_c, _l), {})
        for k, v in r.items():
            if k in ("class_id", "level"):
                continue
            v = (v or "").strip()
            if not v:
                continue
            try:
                d[k] = int(v)
            except Exception:
                pass

_lp_levels = {}
for (_c, _l) in levelprop:
    _lp_levels.setdefault(_c, []).append(_l)
for _c in _lp_levels:
    _lp_levels[_c].sort()


def scale_props(props, scale, remove_unscaled):
    """BattleFormulaHandler.ScaleProps."""
    out = {}
    scale = scale or {}
    for k, v in props.items():
        m = scale.get(k)
        if m is None:
            if not remove_unscaled:
                out[k] = v
        else:
            out[k] = v * (m / 10000.0)
    return out


# ---------------- character level -> subrank -> level curve ----------------
# A skill carries a Rank *and* a Level (PlayerItemParamSkillWrap.EffectiveLevel),
# and the level side reads a growth curve chosen by the character's subrank.
subrank_cap = []
for r in table("player_subrank"):
    sr = (r.get("SubRank") or "").strip()
    try:
        cap = int(r["LevelLimit"])
    except Exception:
        continue
    if sr:
        subrank_cap.append((sr, cap))
MAXLEVEL = max(c for _, c in subrank_cap) if subrank_cap else 100

def subrank_for(level):
    for sr, cap in subrank_cap:
        if level <= cap:
            return sr
    return subrank_cap[-1][0]

group_level = {}
for r in table("entity_prop_group_level"):
    try:
        group_level[(int(r["GroupId"]), (r.get("SubRank") or "").strip())] = int(r["LevelPropId"])
    except Exception:
        pass

# the levels the site's character-level control offers: the game's own subrank caps
LEVELS = [cap for _, cap in subrank_cap]

def curve(group_id, level):
    """levelProp[ entity_prop_group_level[group][subrank(level)] ][level]."""
    lp = group_level.get((group_id, subrank_for(level)))
    if not lp:
        return {}
    row = levelprop.get((lp, level))
    if row is None:
        # some curves are deliberately short — group 14 is flagged
        # "fixed value, does not change" and defines level 1 only.
        below = [l for l in _lp_levels.get(lp, []) if l <= level]
        row = levelprop.get((lp, below[-1])) if below else None
    return row or {}


def parse_factors(s_):
    """{CritRatePercent:5000,CritRatePercentValue:5000} -> dict"""
    out = {}
    for m in __import__("re").finditer(r"(\w+)\s*:\s*(-?\d+)", s_ or ""):
        out[m.group(1)] = int(m.group(2))
    return out

# ---------------- skill coefficients ----------------
eps = {}
for r in table("entity_prop_skill"):
    try:
        eid = int(r["EntityId"])
    except Exception:
        continue
    eps[eid] = r

# ---------------- status (buff/debuff) entities ----------------
status_scale = {}
for r in table("level_prop_status"):
    try:
        cid, rk = int(r["class_id"]), int(r["level"])
    except Exception:
        continue
    d = {}
    for k, v in r.items():
        if k in ("class_id", "level") or not v.strip():
            continue
        try:
            d[k] = int(v)
        except Exception:
            pass
    status_scale[(cid, rk)] = d

status_ent = {}
for r in table("entity_prop_status"):
    try:
        status_ent[int(r["EntityId"])] = r
    except Exception:
        pass

# props we never surface (bookkeeping / duplicated elsewhere)
SKIP = {"EntityId", "Memo", "Memo2", "PvpPropScale", "RankPropId", "GroupLevelPropId",
        "SubRankPropId", "AffectedBySkillRank", "class_id", "level"}

prop_float = {}
for r in table("prop_cfg"):
    pt = (r.get("PropType") or "").strip()
    if pt:
        prop_float[pt] = (r.get("Float") or "").strip().upper() == "TRUE"

def plain(t):
    """Game rich text -> plain text, for tooltips."""
    import re as _r
    t = _r.sub(r"<[^>]+>", "", t or "")
    t = t.replace("\n", " ")
    return _r.sub(r"\s+", " ", t).strip()


def link_targets(row):
    """Resolve <link=N> to {name, desc} using HyperLinkTypes/HyperLinkDatas."""
    import re as _r, ast as _a
    def arr(v):
        v = (v or "").strip()
        if not v or v == "[]":
            return []
        try:
            out = _a.literal_eval(v)
            return list(out) if isinstance(out, (list, tuple)) else []
        except Exception:
            return _r.findall(r"'([^']*)'", v)
    types = arr(row.get("HyperLinkTypes"))
    datas = arr(row.get("HyperLinkDatas"))
    out = []
    for i, ty in enumerate(types):
        item = None
        tyy = str(ty).strip()
        if tyy == "Monster" and i < len(datas):
            m = _r.search(r"MonsterId\s*:\s*(\d+)", str(datas[i]))
            if m:
                nm = L(f"monster_{m.group(1)}")
                if nm:
                    item = {"name": nm, "desc": "A unit summoned by this skill."}
        elif tyy == "Entry" and i < len(datas):
            m = _r.search(r"EntryId\s*:\s*(\d+)", str(datas[i]))
            if m:
                eid = m.group(1)
                nm = L(f"entry_{eid}_name")
                ds = L(f"entry_{eid}_desc")
                if nm:
                    item = {"name": nm, "desc": plain(ds)}
        out.append(item)
    return out


def nice(k):
    lab = L(f"PropType.{k}")
    if not lab:
        import re as _r
        lab = _r.sub(r"(?<!^)(?=[A-Z])", " ", k)
    lab = (lab.replace("Status Fixed Add", "Flat status effect ")
              .replace("StatusFixedAdd", "Flat status effect ")
              .replace("Status Add", "Status effect "))
    return lab.strip()

# ---------------- item type: the game has exactly two, Technique and Charm ----
item_type = {}
for r in table("item"):
    try:
        item_type[int(r["ClassId"])] = (r.get("ItemType") or "").strip()
    except Exception:
        pass
TYPE_EN = {"ActiveSkill": "Technique", "PassiveSkill": "Charm"}

# ---------------- skills ----------------
skills = {}
for r in table("skill"):
    try:
        cid = int(r["ClassId"])
    except Exception:
        continue
    skills[cid] = r

# stat columns we surface, in display order
STATS = [
    ("SkillAttack1", "Damage coefficient"),
    ("SkillAttack2", "Damage coefficient 2"),
    ("SkillAttack3", "Damage coefficient 3"),
    ("SkillFixedAttack1", "Flat damage"),
    ("SkillCureByAttack", "Heal (from ATK)"),
    ("SkillCureByHp", "Heal (from max HP)"),
    ("SkillFixedCure", "Flat heal"),
    ("ShieldByAttack", "Shield (from ATK)"),
    ("SkillFixedShield", "Flat shield"),
    ("BreakResilience", "Poise break"),
    ("CD", "Cooldown"),
]
PCT = {"SkillAttack1", "SkillAttack2", "SkillAttack3", "SkillCureByAttack",
       "SkillCureByHp", "ShieldByAttack"}

# (group, prop) pairs whose level curve the page has to ship
needed_curve = set()


def _acc(entry, prop, label, pct, level_dep, group, per_rank):
    """Record one stat: either a finished number per rank, or a per-rank
    multiplier that the page applies to the level curve."""
    entry["labels"][prop] = label
    entry["pct"][prop] = pct
    if level_dep:
        entry["lgroup"][prop] = group
        needed_curve.add((group, prop))
        for rk, v in per_rank.items():
            entry["lmult"].setdefault(str(rk), {})[prop] = v
    else:
        for rk, v in per_rank.items():
            entry["vals"].setdefault(str(rk), {})[prop] = v


def _curve_props(group):
    """Every prop the level curve for this group ever defines."""
    keys = set()
    for lv in LEVELS:
        keys |= set(curve(group, lv))
    return keys


def skill_entry(cid):
    s = skills.get(cid)
    if not s:
        return None
    name = L(f"item_{cid}_name") or s.get("Name", "").strip() or f"Skill {cid}"
    desc = L(f"item_{cid}_func_desc") or ""
    try:
        eid = int(s.get("EcEntityId") or 0)
    except Exception:
        eid = 0
    ep = eps.get(eid)
    entry = {
        "id": cid, "name": name, "desc": desc, "cn": s.get("Name", "").strip(),
        "tag": (s.get("OuterTag") or "").strip(),
        "sort": (s.get("SkillSortTypes") or "").strip(),
        "entity": eid, "kind": "active",
        "type": TYPE_EN.get(item_type.get(cid, ""), ""),
        "vals": {}, "lmult": {}, "lgroup": {}, "labels": {}, "pct": {},
        "links": link_targets(s),
    }

    def ranks_of(rank_prop_id):
        # a skill's rank ladder is skill_rank's 34 steps; some scaling tables
        # carry extra rows past that (level_prop_skill_passive_other runs to 200)
        return sorted(l for l in _lp_levels.get(rank_prop_id, []) if l in rank_quality)

    # ---- damage / heal / shield: entity_prop_skill ----
    if ep:
        try:
            rankprop = int(ep.get("RankPropId") or 0)
            group = int(ep.get("GroupLevelPropId") or 0)
        except Exception:
            rankprop = group = 0
        rks = ranks_of(rankprop)
        curve_keys = _curve_props(group)
        for key, label in STATS:
            v = (ep.get(key) or "").strip()
            if not v or v == "0":
                continue
            try:
                fac = int(v)
            except Exception:
                continue
            if key in curve_keys:
                # base comes from the character-level curve; the entity column
                # is a factor on it, exactly as CalcSkillProps applies it
                _acc(entry, key, label, False, True, group,
                     {rk: (levelprop.get((rankprop, rk), {}).get(key, 10000) / 10000.0)
                          * (fac / 10000.0) for rk in rks})
            else:
                pct = key in PCT
                _acc(entry, key, label, pct, False, 0,
                     {rk: round(fac * (levelprop.get((rankprop, rk), {}).get(key, 10000) / 10000.0)
                                * (100 / 10000.0 if pct else 1), 2) for rk in rks})
        entry["ranks"] = rks

    # ---- buffs and debuffs: the status entities the skill points at ----
    view = [v for v in ints(s.get("ViewPropEntities")) if v in status_ent]
    for vid in view:
        row = status_ent[vid]
        try:
            srank = int(row.get("RankPropId") or 0)
            sgroup = int(row.get("GroupLevelPropId") or 0)
        except Exception:
            continue
        rks = ranks_of(srank)
        if not rks:
            continue
        curve_keys = _curve_props(sgroup)
        for k, v in row.items():
            if k in SKIP or not str(v).strip() or str(v).strip() == "0":
                continue
            try:
                fac = int(v)
            except Exception:
                continue
            prop = "ST:" + k
            is_pct = prop_float.get(k, True)
            if k in curve_keys:
                _acc(entry, prop, nice(k), is_pct, True, sgroup,
                     {rk: (levelprop.get((srank, rk), {}).get(k, 10000) / 10000.0)
                          * (fac / 10000.0) * (0.01 if is_pct else 1) for rk in rks})
            else:
                _acc(entry, prop, nice(k), is_pct, False, 0,
                     {rk: round(fac * (levelprop.get((srank, rk), {}).get(k, 10000) / 10000.0)
                                * (100 / 10000.0 if is_pct else 1), 2) for rk in rks})
        if entry["kind"] == "active" and not ep:
            entry["kind"] = "buff"
        entry["ranks"] = sorted(set(entry.get("ranks") or []) | set(rks))

    # ---- flat-stat Charms: CalcSkillPassiveProps ----
    factors = parse_factors(s.get("PassivePropFactors"))
    if factors:
        try:
            p_rank = int(s.get("PassiveRankPropId") or 0)
            p_group = int(s.get("PassiveGroupLevelPropId") or 0)
            p_fac = int(s.get("PassiveRankFactorId") or 0)
        except Exception:
            p_rank = p_group = p_fac = 0
        rks = ranks_of(p_rank)
        curve_keys = _curve_props(p_group)
        if not ep:
            entry["kind"] = "passive"
        for k, fac in factors.items():
            # the game's chain keeps only props the level curve defines
            if k not in curve_keys:
                continue
            is_pct = prop_float.get(k, False)
            per = {}
            for rk in rks:
                m = (levelprop.get((p_rank, rk), {}).get(k, 10000) / 10000.0) * (fac / 10000.0)
                if p_fac > 0:
                    m *= levelprop.get((p_fac, rk), {}).get(k, 10000) / 10000.0
                per[rk] = m * (0.01 if is_pct else 1)
            _acc(entry, k, nice(k), is_pct, True, p_group, per)
        entry["ranks"] = sorted(set(entry.get("ranks") or []) | set(rks))

    rks = entry.get("ranks") or []
    entry["ranks"] = rks
    entry["maxRank"] = max(rks) if rks else 0
    if not entry["labels"]:
        entry["ranks"] = []
    return entry


def main():
    prof_en = {}
    tiers = {}
    for p in table("profession_base"):
        pid = p["Profession"].strip()
        if pid in ("", "None"):
            continue
        try:
            tier = int(p["Rank"])
        except Exception:
            continue
        en = L(f"Profession.{pid}") or pid
        prof_en[pid] = en
        sk = [skill_entry(c) for c in ints(p.get("Skills"))]
        sk = [s for s in sk if s]
        tiers.setdefault(tier, []).append({
            "id": pid, "name": en, "prePro": p.get("PrePro", "").strip(),
            "icon": (p.get("Icon1") or "").strip(),
            "skills": sk,
        })

    curves = {}
    for g, prop in sorted(needed_curve):
        by = curves.setdefault(str(g), {})
        for lv in LEVELS:
            v = curve(g, lv).get(prop)
            if v is not None:
                by.setdefault(str(lv), {})[prop] = v

    data = {
        "qualities": QORDER,
        "qualityRanks": {q: quality_first_rank.get(q) for q in QORDER},
        "rankLabels": {str(rk): rank_label[rk] for rk in sorted(rank_label)},
        "rankQuality": {str(rk): rank_quality[rk] for rk in sorted(rank_quality)},
        "levels": LEVELS,
        "subranks": {str(cap): L(f"SubRank.{sr}") or sr for sr, cap in subrank_cap},
        "defaultLevel": 100 if 100 in LEVELS else LEVELS[len(LEVELS) // 2],
        "curves": curves,
        "stats": [{"key": k, "label": lb, "pct": k in PCT} for k, lb in STATS],
        "tiers": [{"tier": t, "classes": tiers[t]} for t in sorted(tiers)],
    }
    (OUT / "_skills.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    nsk = sum(len(c["skills"]) for t in data["tiers"] for c in t["classes"])
    withstats = sum(1 for t in data["tiers"] for c in t["classes"]
                    for s in c["skills"] if s.get("ranks"))
    kinds = {}
    for t in data["tiers"]:
        for c in t["classes"]:
            for s in c["skills"]:
                kinds[s.get("type") or "?"] = kinds.get(s.get("type") or "?", 0) + 1
    print(f"tiers {len(data['tiers'])}, classes "
          f"{sum(len(t['classes']) for t in data['tiers'])}, skills {nsk}, "
          f"with per-rank values {withstats}")
    print(f"  {kinds}  ranks 1-{max(rank_label)}  levels {LEVELS[0]}-{LEVELS[-1]} "
          f"({len(LEVELS)} steps)  curve groups {len(data['curves'])}")
    for t in data["tiers"]:
        print(f"  tier {t['tier']}: " + ", ".join(c["name"] for c in t["classes"]))

    def show(want):
        for t in data["tiers"]:
            for c in t["classes"]:
                for s in c["skills"]:
                    if s["name"] == want:
                        print(f"\nsample - {c['name']} / {s['name']} "
                              f"({s['type']}, ranks {s['ranks'][:1]}..{s['ranks'][-1:]})")
                        for rk in (s["ranks"][:1] + s["ranks"][-1:]):
                            out = dict(s["vals"].get(str(rk), {}))
                            for pr, m in s["lmult"].get(str(rk), {}).items():
                                g = str(s["lgroup"][pr])
                                base = data["curves"].get(g, {}).get("100", {}).get(pr)
                                if base is not None:
                                    out[pr] = round(base * m, 2)
                            print(f"   {data['rankLabels'][str(rk)]:<14} {out}")
                        return
    show("Edge Strike")
    show("Rapid Cast")
    show("Formation Breaker")


if __name__ == "__main__":
    main()
