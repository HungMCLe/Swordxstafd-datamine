"""Equipment reference — every piece by season and slot, with the stat formula from
BattleFormulaHandler.CalcEquipMainProps / CalcEquipSecProps and the set bonuses.

    main = curve[MainPropId][level][type] x (1 + upgrade[+N]) x (1 + rankFactor)
    (+ bless[b] on top, only while your promotion matches the piece's)

level = clamp(player level, piece level, piece level + LevelExtension)  (EquipInfo.GetLevel);
every piece in the table has LevelExtension 0, so a levelled piece is fixed at its own level
and a "-1" piece takes the level it dropped at.
"""
from __future__ import annotations
import html, json, re, collections


def _num(s, d=0):
    try:
        return int(str(s).strip())
    except Exception:
        return d


def _jsonish_list(s):
    return re.findall(r'"([A-Za-z0-9_]+)"', s or "")


def _pct(v, digits=0):
    p = v / 100.0
    return f"{p:.{digits}f}%" if digits else f"{p:g}%"


def render(layout, base_tables):
    import build as _b
    L = _b.L
    ladder, _B, _BA, _BC, sr, grp, name = base_tables()

    # ---- localisation helpers
    def loc(key, fallback):
        v = L(key)
        return (v or fallback).strip()
    def prop_name(p):
        return loc(f"PropType.{p}", p)

    # ---- tables
    eq = _b.csvrows("equip"); eh = [c.strip() for c in eq[0]]; ei = {c: i for i, c in enumerate(eh)}
    it = _b.csvrows("item"); ih = [c.strip() for c in it[0]]; ii = {c: i for i, c in enumerate(ih)}
    items = {r[0].strip(): r for r in it[2:] if r and r[0].strip().isdigit()}
    et = _b.csvrows("equip_type"); th = [c.strip() for c in et[0]]; ti = {c: i for i, c in enumerate(th)}
    types = {r[0].strip(): r for r in et[2:] if r and r[0].strip() and not r[0].startswith("#")}

    def curve(table):
        rows = _b.csvrows(table); h = [c.strip() for c in rows[0]]
        out = {}
        for r in rows[2:]:
            if len(r) > 2 and r[0].strip().isdigit() and r[1].strip().lstrip("-").isdigit():
                out.setdefault(int(r[0]), {})[int(r[1])] = {h[i]: _num(r[i]) for i in range(2, min(len(h), len(r)))}
        return out
    main_c = curve("level_prop_equip_main")
    sec_c = curve("level_prop_equip_second")
    rank_c = curve("level_prop_equip_rank")
    upg_c = curve("level_prop_equip_upgrade")
    bless_c = curve("level_prop_equip_bless_level")

    def rank_factor(rid, level=130, typ="Attack"):
        row = rank_c.get(rid, {})
        r = row.get(level) or (row[max(row)] if row else {})
        return r.get(typ, 0) / 10000.0

    # ---- quality words, from the item table
    QUAL_ORDER = ["White", "Blue", "Purple", "Orange", "Gold", "Red", "Rainbow"]
    qword = {q: loc(f"Quality.{q}", q) for q in QUAL_ORDER}

    # ---- seasons: astrological_season_config, and the promotion cap that gear level matches
    fam_cap = {}
    for Ld in ladder:
        fam = Ld["internal"].split("_")[0]
        fam = fam if fam.startswith(("Godtouched", "Demigod")) else fam.rstrip("123")
        fam_cap[fam] = max(fam_cap.get(fam, 0), Ld["cap"])
        fam_cap.setdefault(fam + "_name", Ld["rank"].rsplit(" ", 1)[0])
    seasons = []
    for r in _b.csvrows("astrological_season_config")[2:]:
        if r and r[0].strip().isdigit():
            fam = r[1].strip()
            seasons.append({"n": int(r[0]), "family": fam, "name": loc(f"astrological_season_{r[0]}_name", f"Season {r[0]}"),
                            "cap": fam_cap.get(fam, 0), "promotion": fam_cap.get(fam + "_name", fam)})
    season_by_cap = {s["cap"]: s for s in seasons}

    # ---- suits and their bonuses
    ea = _b.csvrows("equip_attributes"); ah = [c.strip() for c in ea[0]]; ai = {c: i for i, c in enumerate(ah)}
    attrs = {r[0].strip(): r for r in ea[2:] if r and r[0].strip().isdigit()}
    ap = _b.csvrows("equip_attributes_props")
    aprops = {r[0].strip(): r[1] for r in ap[2:] if r and r[0].strip().isdigit()}
    ps = _b.csvrows("equip_attributes_passive_skill"); ph = [c.strip() for c in ps[0]]; pi = {c: i for i, c in enumerate(ph)}
    pskill = {r[0].strip(): r for r in ps[2:] if r and r[0].strip().isdigit()}

    def bonus_text(aid):
        a = attrs.get(aid)
        if not a:
            return f"attribute {aid}"
        tpl = loc(f"equip_attributes_{aid}_desc", a[ai["Desc"]])
        typ = a[ai["Type"]].strip()
        props = re.findall(r"([A-Za-z0-9_]+):(-?\d+)", aprops.get(aid, ""))
        for k, (p, v) in enumerate(props, 1):
            val = int(v)
            tpl = tpl.replace(f"{{PropType{k}}}", prop_name(p)).replace(f"{{SignedPropValue{k}}}", ("+" if val >= 0 else "") + _pct(val)) \
                     .replace(f"{{PropValue{k}}}", _pct(val))
        row = pskill.get(aid)
        if row:
            sk = row[pi["SkillId"]].strip()
            sname = loc(f"item_{sk}_name", f"skill {sk}") if sk and sk != "0" else ""
            vals = re.findall(r"Values'\s*:\s*\[(-?\d+)", row[pi["Props"]])
            for k, v in enumerate(vals, 1):
                tpl = tpl.replace(f"{{PropValue{k}}}", _pct(int(v)))
            if sname:
                tpl = tpl.replace("{Skill}", f"<b>{html.escape(sname)}</b>")
        # what the config leaves unfilled sits on the skill's prefab, not in a table: say so rather than invent it
        tpl = re.sub(r"\s*\{PropValue\d\}", " <i>(the skill's own value)</i>", tpl)
        tpl = tpl.replace("{Skill}", "<i>its skill</i>")
        return tpl

    suits = {}
    for r in _b.csvrows("equip_suit")[2:]:
        if r and r[0].strip().isdigit():
            sid = r[0].strip()
            pieces = dict(re.findall(r"(\d+)\s*:\s*(\d+)", r[2]))
            suits[sid] = {"id": sid, "name": loc(f"equip_suit_{sid}", r[1]),
                          "bonus": [(int(c), bonus_text(a)) for c, a in sorted(pieces.items(), key=lambda x: int(x[0]))]}

    # ---- the pieces
    pieces = []
    for r in eq[2:]:
        if not r or not r[0].strip().isdigit():
            continue
        cid = r[0].strip()
        irow = items.get(cid)
        if not irow:
            continue
        typ = irow[ii["ItemType"]].strip()
        trow = types.get(typ)
        if not trow:
            continue
        level = _num(r[ei["Level"]], -1)
        main_t = r[ei["MainPropType"]].strip()
        main_id = _num(r[ei["MainPropId"]]); sec_id = _num(r[ei["SecPropId"]])
        rank_id = _num(r[ei["MainRankPropId"]])
        rf = rank_factor(rank_id, level if level > 0 else 130, main_t)
        sec_types = _jsonish_list(r[ei["SecPropTypes"]])
        suit_ids = re.findall(r"(\d+)\s*:", r[ei["SuitId"]])
        def at(lv, main_id=main_id, sec_id=sec_id, main_t=main_t, sec_types=sec_types):
            m = main_c.get(main_id, {}).get(lv, {}).get(main_t, 0)
            s = {t: sec_c.get(sec_id, {}).get(lv, {}).get(t, 0) for t in sec_types}
            return m, s
        pieces.append({
            "id": cid, "name": loc(f"item_{cid}_name", cid), "type": typ,
            "slot": loc(f"ItemType.{typ}", typ), "pos": loc(f"EquipPos.{trow[ti['EquipPos']]}", trow[ti["EquipPos"]]),
            "quality": irow[ii["Quality"]].strip(), "level": level, "main_t": main_t, "main_id": main_id,
            "sec_id": sec_id, "sec_types": sec_types, "rank_id": rank_id, "rf": rf, "suits": suit_ids, "at": at,
            "line": ("Warrior line" if "Zhanshi" in trow[ti["Professions"]] else "Mage line" if "Fashi" in trow[ti["Professions"]]
                     else "Warrior line" if typ in ("Shield", "Glove") else "Mage line"),
        })

    SLOT_ORDER = ["Sword", "Wand", "Shield", "Glove", "Book", "Ball", "Helmet", "Clothes", "Boot"]
    def slot_key(p):
        return SLOT_ORDER.index(p["type"]) if p["type"] in SLOT_ORDER else 99
    def q_key(p):
        return QUAL_ORDER.index(p["quality"]) if p["quality"] in QUAL_ORDER else 99

    def fmt(v):
        v = int(v)
        return f"{v:,}"

    # ---- one season block: per slot, the pieces at that level
    def piece_row(p, lv):
        m, s = p["at"](lv)
        main_v = int(m * (1 + p["rf"]))
        secs = ", ".join(f"{prop_name(t)} {fmt(int(v * (1 + p['rf'])))}" for t, v in s.items())
        sets = ", ".join(f'<a href="#suit-{sid}">{html.escape(suits[sid]["name"])}</a>' for sid in p["suits"] if sid in suits)
        return (f'<tr><td><b>{html.escape(p["name"])}</b><br><span class="hint">{p["slot"]} &middot; {p["line"]}</span></td>'
                f'<td><span class="q-{p["quality"].lower()}">{qword.get(p["quality"], p["quality"])}</span></td>'
                f'<td class="num">{prop_name(p["main_t"])} <b>{fmt(main_v)}</b></td>'
                f'<td>{secs}</td><td>{sets or "&mdash;"}</td></tr>')

    def block(title, sub, plist, lv):
        out = [f'<h2 id="{re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")}">{html.escape(title)}</h2><p>{sub}</p>']
        by_slot = collections.OrderedDict()
        for p in sorted(plist, key=lambda p: (slot_key(p), q_key(p), p["name"])):
            by_slot.setdefault(p["slot"], []).append(p)
        for slot, ps_ in by_slot.items():
            out.append(f'<h3>{html.escape(slot)} <span class="hint">{html.escape(ps_[0]["pos"])} &middot; {len(ps_)}</span></h3>')
            out.append('<div class="tablewrap"><table class="equip"><thead><tr><th>Piece</th><th>Quality</th>'
                       '<th class="num">Main stat</th><th>Secondary (one rolls)</th><th>Set</th></tr></thead><tbody>')
            out.extend(piece_row(p, lv) for p in ps_)
            out.append('</tbody></table></div>')
        return "\n".join(out)

    sections = []
    levelled = [p for p in pieces if p["level"] > 0]
    caps = sorted(set(p["level"] for p in levelled))
    season_caps = [c for c in caps if c in season_by_cap]
    early = [p for p in levelled if p["level"] not in season_by_cap]
    if early:
        parts = ['<h2 id="early">Before the seasons</h2><p>Starter and levelling pieces, each at its own level.</p>']
        for lv in sorted(set(p["level"] for p in early)):
            plist = [p for p in early if p["level"] == lv]
            parts.append(block(f"Level {lv}", f"{len(plist)} pieces.", plist, lv).replace("<h2", "<h3", 1).replace("</h2>", "</h3>", 1))
        sections.append("\n".join(parts))
    KINGDOM_MAP = {100: 13, 130: 14, 160: 17, 190: 19, 220: 21}   # gear level -> map id, from the table's source memos
    for cap in season_caps:
        s = season_by_cap[cap]
        plist = [p for p in levelled if p["level"] == cap]
        kingdom = loc(f"ui_map_{KINGDOM_MAP.get(cap, 0)}", "")
        sections.append(block(f"Season {s['n']} · {s['name']}" + (f" — {kingdom}" if kingdom else ""),
                              f"Level {cap} gear, the cap of {html.escape(s['promotion'])} &mdash; the promotion this season's "
                              f"<code>astrological_season_config</code> row names. {len(plist)} pieces.", plist, cap))

    # ---- drops that take the level they fall at: one line per name and quality, at each season cap
    scaled = [p for p in pieces if p["level"] < 0]
    scaled_rows = []
    seen = set()
    for p in sorted(scaled, key=lambda p: (slot_key(p), q_key(p), p["name"], p["id"])):
        key = (p["name"], p["quality"], p["main_id"])
        if key in seen:
            continue
        seen.add(key)
        cells = "".join(f'<td class="num">{fmt(int(p["at"](c)[0] * (1 + p["rf"])))}</td>' for c in season_caps)
        scaled_rows.append(f'<tr><td><b>{html.escape(p["name"])}</b><br><span class="hint">{p["slot"]}</span></td>'
                           f'<td><span class="q-{p["quality"].lower()}">{qword.get(p["quality"], p["quality"])}</span></td>'
                           f'<td>{prop_name(p["main_t"])}</td>{cells}<td>{", ".join(prop_name(t) for t in p["sec_types"])}</td></tr>')
    scaled_head = "".join(f'<th class="num">Lv {c}</th>' for c in season_caps)

    # ---- multiplier tables
    qf_rows = "".join(
        f'<tr><td><span class="q-{q.lower()}">{qword[q]}</span></td><td class="num">+{_pct(int(rank_factor(rid, 130) * 10000))}</td></tr>'
        for q, rid in (("White", 1210), ("Blue", 1211), ("Purple", 1212), ("Orange", 1213), ("Gold", 1214), ("Red", 1215)))
    upg = upg_c.get(1200, {})
    upg_rows = "".join(f'<tr><td class="num">+{n}</td><td class="num">+{_pct(upg.get(n, {}).get("Attack", 0))}</td></tr>'
                       for n in (1, 5, 10, 20, 30, 50, 100, 150, 200, 250) if n in upg)
    bl = bless_c.get(1154, {})
    bless_rows = "".join(f'<tr><td class="num">{n}</td><td class="num">+{_pct(bl.get(n, {}).get("Attack", 0), 1)}</td></tr>'
                         for n in (1, 5, 10, 20, 30, 50, 100) if n in bl)

    # ---- sets
    set_rows = []
    used = collections.defaultdict(set)
    for p in levelled:
        for sid in p["suits"]:
            used[sid].add(p["level"])
    for sid, s in sorted(suits.items(), key=lambda x: int(x[0])):
        where = ", ".join(f"Lv {lv}" for lv in sorted(used.get(sid, [])))
        bon = "".join(f'<li><b>{c} pieces</b> &mdash; {t}</li>' for c, t in s["bonus"])
        set_rows.append(f'<div class="suit" id="suit-{sid}"><h3>{html.escape(s["name"])} <span class="hint">{where or "not on a levelled piece"}</span></h3><ul>{bon}</ul></div>')

    season_list = "".join(f'<li><b>Season {s["n"]}</b> {html.escape(s["name"])} &mdash; {html.escape(s["promotion"])}, gear level {s["cap"]}</li>' for s in seasons)

    body = f"""
<div class="wrap">
<p class="eyebrow">Reference</p>
<h1>Equipment</h1>
<p class="lede">Every piece in the game's equipment table, by the season it belongs to and the slot it fills, with its
main stat from the level curve, the secondary stats it can roll and the set it counts toward. Names, qualities, slots
and set bonuses are the game's own text.</p>

<h2>How a piece is valued</h2>
<p><code>CalcEquipMainProps</code> reads the piece's main stat off its level curve and multiplies it twice: once by the
upgrade level (the <b>+N</b> you pay materials for) and once by a fixed <b>quality factor</b>. <b>Season Enhancement</b>
goes on top of that &mdash; the game's tooltip: <i>"Gear Enhancement Level {0} + Season Level {1}"</i>, <i>"Season
Enhancement provides gear power boosts beyond your current Rank's cap"</i> &mdash; and only counts while your promotion
matches the piece's (the config calls it "bless").</p>
<pre><code>main = curve[level] x (1 + upgrade[+N]) x (1 + quality)   (+ season enhancement[b] while the promotion matches)</code></pre>
<p>The secondary stat uses the same shape on its own curve. The piece's level is your level clamped to the piece's own
level (<code>EquipInfo.GetLevel</code>); every piece here has no level extension, so a levelled piece is fixed at its
level and a drop that scales takes the level it fell at.</p>
<div class="threecol">
<div class="tablewrap"><table><thead><tr><th>Quality</th><th class="num">Factor</th></tr></thead><tbody>{qf_rows}</tbody></table>
<caption>From <code>level_prop_equip_rank</code>; constant across levels.</caption></div>
<div class="tablewrap"><table><thead><tr><th class="num">Upgrade</th><th class="num">Factor</th></tr></thead><tbody>{upg_rows}</tbody></table>
<caption>From <code>level_prop_equip_upgrade</code>. The material table runs to +250.</caption></div>
<div class="tablewrap"><table><thead><tr><th class="num">Season Enh.</th><th class="num">Factor</th></tr></thead><tbody>{bless_rows}</tbody></table>
<caption>Season Enhancement, from <code>level_prop_equip_bless_level</code>, the common curve; a few pieces use their own.</caption></div>
</div>

<h2>The seasons</h2>
<p>Each row of <code>astrological_season_config</code> names a season and a promotion family, and the gear levels in the
equipment table land exactly on those families' level caps. That is the grouping below: a season's gear is the gear
at its promotion's cap.</p>
<ul class="plain">{season_list}</ul>

{"".join(sections)}

<h2 id="scaling">Drops that take the level they fall at</h2>
<p>These pieces are stored with level &minus;1 and get the level of the character they drop for. The main stat below is
shown at each season's gear level, quality factor included.</p>
<div class="tablewrap"><table class="equip"><thead><tr><th>Piece</th><th>Quality</th><th>Main</th>{scaled_head}<th>Secondary pool</th></tr></thead>
<tbody>{"".join(scaled_rows)}</tbody></table></div>

<h2 id="sets">Sets</h2>
<p>Two pieces of a set give the stat pair; four give the effect. Where a bonus fires a skill, the value that skill uses
sits on its prefab rather than in the equipment tables, and the line says so instead of guessing.</p>
<div class="suits">{"".join(set_rows)}</div>
</div>
"""
    return layout("Equipment", "Every Sword x Staff equipment piece by season and slot, with the stat formula, quality, "
                  "upgrade and bless factors, and every set bonus.", body, "equipment", 0)
