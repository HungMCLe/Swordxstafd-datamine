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
QUALITY_EN = {"Blue": "Rare", "Purple": "Epic", "Orange": "Legendary",
              "Gold": "Mythic", "Red": "Divine", "Rainbow": "Immortal"}
QORDER = ["Rare", "Epic", "Legendary", "Mythic", "Divine", "Immortal"]

rank_quality = {}          # rank -> english quality
quality_first_rank = {}    # english quality -> lowest rank
for r in table("skill_rank"):
    rk = int(r["Rank"])
    q = QUALITY_EN.get(r["Quality"].strip())
    if not q:
        continue
    rank_quality[rk] = q
    quality_first_rank.setdefault(q, rk)

# ---------------- rank scaling ----------------
# level_prop_skill: class_id = RankPropId, level = rank, values are x10000 multipliers
rank_scale = {}
for r in table("level_prop_skill"):
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
    rank_scale[(cid, rk)] = d

# ---------------- passive rank scaling (percent props; level = rank) ----------
passive_rank_scale = {}
for r in table("level_prop_skill_passive"):
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
    passive_rank_scale[(cid, rk)] = d

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

def nice(k):
    lab = L(f"PropType.{k}")
    if not lab:
        import re as _r
        lab = _r.sub(r"(?<!^)(?=[A-Z])", " ", k)
    lab = (lab.replace("Status Fixed Add", "Flat status effect ")
              .replace("StatusFixedAdd", "Flat status effect ")
              .replace("Status Add", "Status effect "))
    return lab.strip()

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
    factors = parse_factors(s.get("PassivePropFactors"))
    try:
        p_rankprop = int(s.get("PassiveRankPropId") or 0)
    except Exception:
        p_rankprop = 0
    try:
        maxrank = int(s.get("MaxRankLimit") or 0)
    except Exception:
        maxrank = 0
    entry = {
        "id": cid, "name": name, "desc": desc, "cn": s.get("Name", "").strip(),
        "tag": (s.get("OuterTag") or "").strip(),
        "sort": (s.get("SkillSortTypes") or "").strip(),
        "maxRank": maxrank, "entity": eid, "kind": "active", "qualities": {},
    }
    # buff/debuff skills: numbers live on the status entities the skill points at
    view = [v for v in ints(s.get("ViewPropEntities")) if v in status_ent]
    if view:
        sbase, srank = {}, 0
        for vid in view:
            row = status_ent[vid]
            try:
                srank = int(row.get("RankPropId") or 0) or srank
            except Exception:
                pass
            for k, v in row.items():
                if k in SKIP or not str(v).strip() or str(v).strip() == "0":
                    continue
                try:
                    sbase[k] = int(v)
                except Exception:
                    pass
        if sbase and srank:
            avail = [rk for (c_, rk) in status_scale if c_ == srank]
            smax = max(avail) if avail else 0
            entry["kind"] = "buff"
            entry["statusBase"] = sbase
            entry["maxRank"] = entry["maxRank"] or smax
            for q in QORDER:
                rk = quality_first_rank.get(q)
                if rk is None or rk > smax:
                    continue
                sc = status_scale.get((srank, rk), {})
                vals = dict(entry["qualities"].get(q, {}).get("vals", {}))
                labels = {}
                for k, bv in sbase.items():
                    mult = sc.get(k)
                    if mult is None:
                        continue
                    if prop_float.get(k, True):          # percentage-style prop
                        vals["ST:" + k] = round(bv / 10000.0 * (mult / 10000.0) * 100, 2)
                    else:                                 # flat value
                        vals["ST:" + k] = round(bv * (mult / 10000.0), 1)
                    labels[k] = nice(k)
                if vals:
                    entry["qualities"][q] = {"rank": rk, "vals": vals}
            entry["statusLabels"] = {("ST:" + k): nice(k) for k in sbase}
            entry["statusPct"] = {("ST:" + k): prop_float.get(k, True) for k in sbase}

    if not ep:
        # passive: value = PassivePropFactors x passive rank scale
        if factors and p_rankprop:
            avail = [rk for (c_, rk) in passive_rank_scale if c_ == p_rankprop]
            pmax = max(avail) if avail else 0
            entry["maxRank"] = pmax
            entry["kind"] = "passive"
            entry["base"] = factors
            for q in QORDER:
                rk = quality_first_rank.get(q)
                if rk is None or rk > pmax:
                    continue
                sc = passive_rank_scale.get((p_rankprop, rk), {})
                vals = {}
                for key, fv in factors.items():
                    mult = sc.get(key)
                    if mult is None:
                        continue
                    vals[key] = round(fv / 10000.0 * (mult / 10000.0) * 100, 2)
                if vals:
                    entry["qualities"][q] = {"rank": rk, "vals": vals}
        return entry
    try:
        rankprop = int(ep.get("RankPropId") or 0)
    except Exception:
        rankprop = 0
    # MaxRankLimit is blank for most skills; fall back to the highest rank the
    # scaling table actually defines for this RankPropId.
    if maxrank <= 0:
        avail = [rk for (cid_, rk) in rank_scale if cid_ == rankprop]
        maxrank = max(avail) if avail else 0
        entry["maxRank"] = maxrank
    base = {}
    for key, _label in STATS:
        v = (ep.get(key) or "").strip()
        if v and v != "0":
            try:
                base[key] = int(v)
            except Exception:
                pass
    if not base:
        return entry
    entry["base"] = base
    for q in QORDER:
        rk = quality_first_rank.get(q)
        if rk is None or rk > maxrank:
            continue
        sc = rank_scale.get((rankprop, rk), {})
        # keep anything the status merge already put here
        vals = dict(entry["qualities"].get(q, {}).get("vals", {}))
        for key in base:
            mult = sc.get(key)
            eff = base[key] * (mult / 10000.0) if mult is not None else float(base[key])
            vals[key] = round(eff, 1)
        entry["qualities"][q] = {"rank": rk, "vals": vals}
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

    data = {
        "qualities": QORDER,
        "qualityRanks": {q: quality_first_rank.get(q) for q in QORDER},
        "stats": [{"key": k, "label": lb, "pct": k in PCT} for k, lb in STATS],
        "tiers": [{"tier": t, "classes": tiers[t]} for t in sorted(tiers)],
    }
    (OUT / "_skills.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    nsk = sum(len(c["skills"]) for t in data["tiers"] for c in t["classes"])
    withstats = sum(1 for t in data["tiers"] for c in t["classes"] for s in c["skills"] if s.get("qualities"))
    print(f"tiers {len(data['tiers'])}, classes "
          f"{sum(len(t['classes']) for t in data['tiers'])}, skills {nsk}, with per-quality stats {withstats}")
    for t in data["tiers"]:
        names = ", ".join(c["name"] for c in t["classes"])
        print(f"  tier {t['tier']}: {names}")
    # sample
    for t in data["tiers"]:
        for c in t["classes"]:
            for s in c["skills"]:
                if s.get("qualities"):
                    print(f"\nsample — {c['name']} / {s['name']} (rank cap {s['maxRank']})")
                    for q, v in s["qualities"].items():
                        print(f"   {q:<10} rank {v['rank']:<3} {v['vals']}")
                    return


if __name__ == "__main__":
    main()
