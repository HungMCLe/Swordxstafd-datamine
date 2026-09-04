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
# level_prop_files is the game's own manifest of which CSVs are baked into
# Assets/Config/Binary/level_prop.bytes — the single table LevelPropParser reads.
# Merging anything else is wrong: level_prop_skill_passive_other holds
# ElementMaster for class 2001 but is NOT in the binary, so GetProps(2001, rank)
# has no ElementMaster and flat stats pass through the rank step unscaled.
LEVEL_TABLES = [ln.strip()[:-4] for ln in
                (CFG / "level_prop_files").read_text(encoding="utf-8-sig").splitlines()
                if ln.strip().endswith(".csv") and ln.strip().startswith("level_prop")]
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

# Two independent inputs, as CalcSkillPassiveProps takes them: the skill item's
# own level indexes the curve, the character's subrank picks which curve.
# a skill's level only ever indexes a growth curve that some group points at
_skill_lpids = set(group_level.values())
MAXSKILLLEVEL = max((l for (c, l) in levelprop if c in _skill_lpids), default=200)
LEVELS = list(range(1, MAXSKILLLEVEL + 1))


def group_lpids(group_id):
    """The distinct growth curves a group uses, one per character rank band."""
    return sorted({v for (g, _), v in group_level.items() if g == group_id})


def curve_at(lpid, level):
    """LevelPropParser.GetConfigProps: exact row, else the top of the range."""
    row = levelprop.get((lpid, level))
    if row is None:
        avail = _lp_levels.get(lpid, [])
        if not avail:
            return {}
        row = levelprop.get((lpid, avail[-1] if level > avail[-1] else avail[0]))
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

# prop_cfg drives the skill panel: SkillPanelShowOrder is the row order,
# SkillHide marks a prop that is not a row of its own — the game appends it to
# its percent partner instead, which is how "204.4%+494K" is one line.
prop_order = {}
prop_skillhide = {}
prop_float = {}
for r in table("prop_cfg"):
    pt = (r.get("PropType") or "").strip()
    if pt:
        prop_float[pt] = (r.get("Float") or "").strip().upper() == "TRUE"
        prop_skillhide[pt] = (r.get("SkillHide") or "").strip().upper() == "TRUE"
        try:
            prop_order[pt] = int((r.get("SkillPanelShowOrder") or "0").strip())
        except Exception:
            prop_order[pt] = 0

# A hidden flat prop belongs to the percent row it partners; the names carry the
# relationship. prop_cfg's own RelativeProp column pairs character stats, not
# these skill-panel rows, so the mapping is spelled out.
PAIRED = {
    "SkillAttack1": "SkillFixedAttack1", "SkillAttack2": "SkillFixedAttack2",
    "SkillAttack3": "SkillFixedAttack3", "SkillAttack4": "SkillFixedAttack4",
    "SkillCureByHp": "SkillFixedCure", "SkillCureByAttack": "SkillFixedCure",
    "ShieldByAttack": "SkillFixedShield",
    "StatusDmgReducePer": "FixedStatusDmgReduce",
    "StatusAdd1": "StatusFixedAdd1", "StatusAdd2": "StatusFixedAdd2",
    "StatusAdd3": "StatusFixedAdd3", "StatusAdd4": "StatusFixedAdd4",
    "StatusShieldAddPercent": "StatusFixedShieldAdd",
}

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


def _trunc(factor, mult, pct):
    """ScaleProps casts to long at each step: (long)(value * Long2Double(scale))."""
    v = int(factor * (mult / 10000.0))
    return round(v / 10000.0 * 100, 4) if pct else v


def _acc(entry, prop, label, pct, level_dep, group, per_rank, curve_key=None):
    """Record one stat: either a finished number per rank, or a per-rank
    multiplier that the page applies to the level curve."""
    entry["labels"][prop] = label
    entry["pct"][prop] = pct
    if level_dep:
        ck = curve_key or prop
        entry["lgroup"][prop] = group
        entry["lkey"][prop] = ck
        needed_curve.add((group, ck))
        for rk, v in per_rank.items():
            entry["lmult"].setdefault(str(rk), {})[prop] = v
    else:
        for rk, v in per_rank.items():
            entry["vals"].setdefault(str(rk), {})[prop] = v


def _curve_props(group):
    """Every prop any of this group's curves ever defines."""
    keys = set()
    for lpid in group_lpids(group):
        for lv in LEVELS:
            keys |= set(curve_at(lpid, lv))
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
        "vals": {}, "lmult": {}, "lgroup": {}, "lkey": {}, "labels": {}, "pct": {},
        "links": link_targets(s),
    }

    def ranks_of(rank_prop_id):
        # a skill's rank ladder is skill_rank's 34 steps; some scaling tables
        # carry extra rows past that (level_prop_skill_passive_other runs to 200)
        return sorted(l for l in _lp_levels.get(rank_prop_id, []) if l in rank_quality)

    # ---- damage / heal / shield: entity_prop_skill ----
    def add_skill_entity(e):
        try:
            rankprop = int(e.get("RankPropId") or 0)
            group = int(e.get("GroupLevelPropId") or 0)
        except Exception:
            return []
        rks = ranks_of(rankprop)
        curve_keys = _curve_props(group)
        for key, label in STATS:
            label = L(f"PropType.{key}") or label
            v = (e.get(key) or "").strip()
            if not v or v == "0" or key in entry["labels"]:
                continue
            try:
                fac = int(v)
            except Exception:
                continue
            if key in curve_keys:
                # the entity column is a factor on the character-level curve
                _acc(entry, key, label, False, True, group,
                     {rk: (levelprop.get((rankprop, rk), {}).get(key, 10000) / 10000.0)
                          * (fac / 10000.0) for rk in rks})
            else:
                pct = key in PCT
                _acc(entry, key, label, pct, False, 0,
                     {rk: _trunc(fac, levelprop.get((rankprop, rk), {})
                                       .get(key, 10000), pct) for rk in rks})
        return rks

    if ep:
        entry["ranks"] = add_skill_entity(ep)

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
                          * (fac / 10000.0) * (0.01 if is_pct else 1) for rk in rks},
                     curve_key=k)
            else:
                _acc(entry, prop, nice(k), is_pct, False, 0,
                     {rk: _trunc(fac, levelprop.get((srank, rk), {})
                                       .get(k, 10000), is_pct) for rk in rks})
        if entry["kind"] == "active" and not ep:
            entry["kind"] = "buff"
        entry["ranks"] = sorted(set(entry.get("ranks") or []) | set(rks))

    # a skill can also point at further skill entities for its side effects —
    # Frost Guard's heal is one, and it is where "Healing Power" comes from
    for vid in ints(s.get("ViewPropEntities")):
        if vid in eps and vid != eid:
            rks = add_skill_entity(eps[vid])
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

    # how the game lays the rows out: order by prop_cfg, and fold each hidden
    # flat prop into its percent partner so one row reads "204.4% + 494K"
    def bare(k):
        return k[3:] if k.startswith("ST:") else k
    entry["order"] = {k: prop_order.get(bare(k), 0) for k in entry["labels"]}
    pair = {}
    for k in list(entry["labels"]):
        flat = PAIRED.get(bare(k))
        if not flat:
            continue
        for cand in (flat, "ST:" + flat):
            if cand in entry["labels"] and prop_skillhide.get(flat):
                pair[k] = cand
    entry["pair"] = pair
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

    curves, lpid_of = {}, {}
    for g, prop in sorted(needed_curve):
        lpid_of.setdefault(str(g), {})
        for sr, _cap in subrank_cap:
            lp_ = group_level.get((g, sr))
            if lp_:
                lpid_of[str(g)][sr] = lp_
        for lp_ in group_lpids(g):
            by = curves.setdefault(str(lp_), {})
            for lv in LEVELS:
                v = curve_at(lp_, lv).get(prop)
                if v is not None:
                    by.setdefault(str(lv), {})[prop] = v

    data = {
        "qualities": QORDER,
        "qualityRanks": {q: quality_first_rank.get(q) for q in QORDER},
        "rankLabels": {str(rk): rank_label[rk] for rk in sorted(rank_label)},
        "rankQuality": {str(rk): rank_quality[rk] for rk in sorted(rank_quality)},
        "levels": LEVELS,
        "subranks": [{"id": sr, "cap": cap, "name": L(f"SubRank.{sr}") or sr}
                     for sr, cap in subrank_cap],
        "defaultSubrank": "Silver3",
        "defaultLevel": 100,
        "lpidOf": lpid_of,
        "curves": curves,
        "stats": [{"key": k, "label": lb, "pct": k in PCT} for k, lb in STATS],
        "tiers": [{"tier": t, "classes": tiers[t]} for t in sorted(tiers)],
    }
    def charm_props(sk):
        """Per-rank stat contributions of a Charm, in the shape the sim applies."""
        out = {}
        for rk in sk["ranks"]:
            row = {}
            for pr, v in sk["vals"].get(str(rk), {}).items():
                row[pr.replace("ST:", "")] = {"v": v, "pct": bool(sk["pct"].get(pr))}
            for pr, m in sk["lmult"].get(str(rk), {}).items():
                row[pr.replace("ST:", "")] = {"m": m, "g": sk["lgroup"][pr],
                                              "k": sk["lkey"].get(pr, pr.replace("ST:", "")),
                                              "pct": bool(sk["pct"].get(pr))}
            if row:
                out[str(rk)] = row
        return out

    # ---- compact dataset for the duel simulator -------------------------------
    # element is not in any CSV (it lives in the binary EC prefabs), but the
    # client's own description names it inside a colour tag; no element means
    # Physical, which is exactly the SourceEleType == None branch in Damage().
    import re as _re
    ELE = ["Wind", "Water", "Fire", "Light", "Dark"]
    _epat = _re.compile(r"<color=#[0-9a-fA-F]{3,8}>\s*(" + "|".join(ELE) + r")\s*</color>")
    _hpat = _re.compile(r"DMG\s+(?:(\d+)\s+times|(once|twice))", _re.I)
    duel = []
    for t in data["tiers"]:
        for c in t["classes"]:
            for sk in c["skills"]:
                if not sk.get("ranks"):
                    continue
                desc = sk.get("desc") or ""
                m = _epat.search(desc)
                hm = _hpat.search(_re.sub(r"<[^>]+>", "", desc))
                hits = 1
                if hm:
                    hits = int(hm.group(1)) if hm.group(1) else (2 if (hm.group(2) or "").lower() == "twice" else 1)
                per = {}
                for rk in sk["ranks"]:
                    v = sk["vals"].get(str(rk), {})
                    lm = sk["lmult"].get(str(rk), {})
                    row = {}
                    for key in ("SkillAttack1", "SkillAttack2", "SkillAttack3", "CD"):
                        if key in v:
                            row[key] = v[key]
                    if "SkillFixedAttack1" in lm:
                        row["fx"] = lm["SkillFixedAttack1"]
                        row["fg"] = sk["lgroup"]["SkillFixedAttack1"]
                    if row:
                        per[str(rk)] = row
                duel.append({"id": sk["id"], "name": sk["name"], "cls": c["name"],
                             "tier": t["tier"], "ele": m.group(1) if m else "Physical",
                             "hits": max(1, min(hits, 20)), "r": per,
                             "kind": sk["type"], "props": charm_props(sk)})
    (OUT / "_duel.json").write_text(json.dumps({"skills": duel, "lpidOf": lpid_of},
                                               ensure_ascii=False, separators=(",", ":")),
                                    encoding="utf-8")
    print(f"  duel dataset: {len(duel)} techniques")

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
                                lp_ = data["lpidOf"].get(g, {}).get("Silver3")
                                base = data["curves"].get(str(lp_), {}).get("100", {}).get(pr)
                                if base is not None:
                                    out[pr] = round(base * m, 2)
                            print(f"   {data['rankLabels'][str(rk)]:<14} {out}")
                        return
    show("Edge Strike")
    show("Rapid Cast")
    show("Formation Breaker")


if __name__ == "__main__":
    main()
