"""NPC friendship — every friendable NPC by the map they live on, in season order,
with their gifts, the stats their friendship grants, and the friendship ladder."""
from __future__ import annotations
import html, json, re, collections, os, shutil


def _num(s, d=0):
    try:
        return int(str(s).strip())
    except Exception:
        return d


def render(layout, base_tables, dist, out):
    import build as _b
    L = _b.L
    ladder, *_ = base_tables()

    def loc(key, fallback=""):
        v = L(key)
        return (v or fallback).strip()

    def rows_of(name):
        r = _b.csvrows(name); h = [c.strip() for c in r[0]]
        return h, [x for x in r[2:] if x and x[0].strip() and not x[0].startswith("#")]

    # ---- maps in season order, with the season alignment used on the Equipment page
    fam_cap, fam_name = {}, {}
    for Ld in ladder:
        fam = Ld["internal"].split("_")[0]
        fam = fam if fam.startswith(("Godtouched", "Demigod")) else fam.rstrip("123")
        fam_cap[fam] = max(fam_cap.get(fam, 0), Ld["cap"]); fam_name.setdefault(fam, Ld["rank"].rsplit(" ", 1)[0])
    season_of_cap = {}
    for r in _b.csvrows("astrological_season_config")[2:]:
        if r and r[0].strip().isdigit():
            fam = r[1].strip()
            season_of_cap[fam_cap.get(fam, 0)] = (int(r[0]), loc(f"astrological_season_{r[0]}_name", f"Season {r[0]}"), fam_name.get(fam, fam))
    # gear level per kingdom, from the equipment table's source memos (see equip page)
    MAP_CAP = {13: 100, 14: 130, 17: 160, 19: 190, 21: 220}
    MAP_ORDER = [9, 10, 11, 12, 13, 14, 17, 19, 21]

    def map_title(m):
        nm = loc(f"ui_map_{m}", "")
        if m == 9 and not nm:
            return "Crossover guests"
        s = season_of_cap.get(MAP_CAP.get(m, -1))
        if s:
            return f"Season {s[0]} · {html.escape(s[1])} — {html.escape(nm)}" if nm else f"Season {s[0]} · {html.escape(s[1])}"
        return html.escape(nm) if nm else f"Map {m}"

    # ---- tables
    h, npcs = rows_of("npc"); ni = {c: i for i, c in enumerate(h)}
    h, fl = rows_of("npc_friendship_level"); fi = {c: i for i, c in enumerate(h)}
    h, tags = rows_of("npc_friendship_tag"); tgi = {c: i for i, c in enumerate(h)}
    h, gifts = rows_of("npc_gift"); gi = {c: i for i, c in enumerate(h)}
    h, prof = rows_of("npc_profile"); pri = {c: i for i, c in enumerate(h)}
    h, lp = rows_of("level_prop_npc_friendship"); li = {c: i for i, c in enumerate(h)}
    curve = collections.defaultdict(dict)
    for r in lp:
        curve[r[0].strip()][_num(r[1])] = {h[i]: _num(r[i]) for i in range(2, min(len(h), len(r))) if _num(r[i])}

    by_npc = collections.defaultdict(list)
    for r in fl:
        by_npc[r[0].strip()].append(r)
    prof_by = collections.defaultdict(list)
    for r in prof:
        prof_by[r[0].strip()].append(r)
    gift_name = {g[0].strip(): loc(f"item_{g[0].strip()}_name", g[gi['Memo']]) for g in gifts}
    gift_exp = {g[0].strip(): _num(g[gi["Friendship"]]) for g in gifts}

    # ---- art
    src = os.path.join(out, "npc_icons"); dst = os.path.join(dist, "assets", "npc")
    os.makedirs(dst, exist_ok=True)
    have = set()
    if os.path.isdir(src):
        for f in os.listdir(src):
            if f.startswith("npc_icon_") and f.endswith(".png"):
                shutil.copy2(os.path.join(src, f), os.path.join(dst, f)); have.add(f[len("npc_icon_"):-4])

    PROP_LABEL = {"Attack": "ATK", "MaxHp": "HP", "Defence": "DEF", "Speed": "SPD", "BaseSpeedPercent": "SPD",
                  "BaseAttackPercent": "ATK", "BaseMaxHpPercent": "HP", "BaseDefencePercent": "DEF",
                  "CritRatePercent": "Crit Rate", "CritAvoidPercent": "Crit RES", "BlockPercent": "Block Rate",
                  "BlockAvoidPercent": "Accuracy", "DmgAddPercent": "DMG Boost",
                  "TravelNpcBaseRewardAddPercent": "travel reward", "TravelNpcExtraRewardAddProbability": "travel bonus chance"}
    PCT = {"BaseSpeedPercent", "BaseAttackPercent", "BaseMaxHpPercent", "BaseDefencePercent", "CritRatePercent",
           "CritAvoidPercent", "BlockPercent", "BlockAvoidPercent", "DmgAddPercent",
           "TravelNpcBaseRewardAddPercent", "TravelNpcExtraRewardAddProbability"}

    def grants(cid, lv):
        row = curve.get(cid, {}).get(lv, {})
        parts = []
        for k, v in row.items():
            if k.endswith("DmgAddScale"):
                continue
            lab = PROP_LABEL.get(k) or loc(f"PropType.{k}", k)
            parts.append(f"+{v / 100:g}% {lab}" if (k in PCT or k.endswith("Percent") or k.endswith("Probability")) else f"+{v:,} {lab}")
        return ", ".join(parts)

    def gate_name(sr):
        return loc(f"SubRank.{sr}", sr)

    # ---- one NPC card
    def card(r):
        cid = r[0].strip()
        name = loc(r[ni["NameKey"]], r[ni["Memo"]])
        levels = by_npc.get(cid, [])
        total = max((_num(x[fi["FriendshipExp"]]) for x in levels), default=0)
        gates = []
        last = None
        for x in sorted(levels, key=lambda x: _num(x[fi["Level"]])):
            g = x[fi["SubRankLimit"]].strip()
            if g != last:
                gates.append((_num(x[fi["Level"]]), g)); last = g
        gate_txt = ", ".join(f"Lv {lv}+ needs {html.escape(gate_name(g))}" for lv, g in gates if g and g != "Norank")
        pref = dict(re.findall(r"(\d+)\s*:\s*([\d.]+)", r[ni["GiftPreferenceDict"]]))
        favs = sorted(((gift_name.get(i, loc(f"item_{i}_name", i)), float(m)) for i, m in pref.items()), key=lambda x: -x[1])
        excl = [loc(f"item_{i}_name", i) for i in re.findall(r"\d+", r[ni["ExclusiveGiftIds"]])]
        fav_txt = ", ".join(f"{html.escape(n)} <span class='hint'>&times;{m:g}</span>" for n, m in favs[:8])
        gtype = r[ni["PreferenceGiftType"]].strip()
        prof_rows = sorted(prof_by.get(cid, []), key=lambda p: _num(p[pri["ProfileId"]]))
        prof_txt = ", ".join(
            f"Lv {m.group(1)}" for p in prof_rows for m in [re.search(r"FriendshipLevel:(\d+)", p[pri["UnlockConditionParam"]])] if m)
        prof_reward = ""
        if prof_rows:
            m = re.search(r"(\d+):(\d+)", prof_rows[0][pri["Reward"]])
            if m:
                prof_reward = f" — each gives {loc(f'item_{m.group(1)}_name', m.group(1))} &times;{m.group(2)}"
        lpid = r[ni["LevelPropId"]].strip()
        g50, g100 = grants(lpid, 50), grants(lpid, 100)
        travel = loc(f"Profession.{r[ni['TravelProfession']].strip()}", "")
        img = f'<img src="assets/npc/npc_icon_{cid}.png" alt="" loading="lazy">' if cid in have else '<span class="noimg"></span>'
        meta = [html.escape(r[ni["NpcRoleType"]].strip()), html.escape(loc(f"Sex.{r[ni['Sex']].strip()}", r[ni["Sex"]].strip()))]
        if travel:
            meta.append(f"travels as a {html.escape(travel)}")
        if r[ni["CanDuel"]].strip().upper() == "TRUE":
            meta.append("can be duelled")
        rows = ""
        if gtype and gtype != "None":
            rows += f"<dt>Likes</dt><dd>{html.escape(gtype)}</dd>"
        if excl:
            rows += f"<dt>Exclusive gift</dt><dd>{html.escape(', '.join(excl))}</dd>"
        if fav_txt:
            rows += f"<dt>Best gifts</dt><dd>{fav_txt}</dd>"
        if levels:
            rows += f"<dt>To Lv 100</dt><dd>{total:,} friendship</dd>"
            if gate_txt:
                rows += f"<dt>Gates</dt><dd>{gate_txt}</dd>"
        if g50 or g100:
            rows += f"<dt>Grants at Lv 50</dt><dd>{g50 or '—'}</dd><dt>Grants at Lv 100</dt><dd>{g100 or '—'}</dd>"
        if prof_txt:
            rows += f"<dt>Profile pages</dt><dd>unlock at {prof_txt}{prof_reward}</dd>"
        return (f'<article class="npc" id="npc-{cid}">{img}<div><h3>{html.escape(name)}</h3>'
                f'<p class="meta">{" &middot; ".join(meta)}</p><dl>{rows}</dl></div></article>')

    # ---- group by map
    groups = collections.defaultdict(list)
    placeholders = []
    for r in npcs:
        if re.match(r"^DNT", loc(r[ni["NameKey"]], "")):
            placeholders.append(r[0].strip()); continue
        m = re.search(r"Map_(\d+)", r[ni["Icon"]])
        mid = int(m.group(1)) if m else _num(r[ni["MapGroupId"]], 0)
        groups[mid].append(r)
    sections = []
    for mid in MAP_ORDER:
        rs = groups.pop(mid, [])
        if not rs:
            continue
        rs.sort(key=lambda r: (r[ni["NpcRoleType"]] != "Special", _num(r[0])))
        friendable = [r for r in rs if r[0].strip() in by_npc]
        sections.append(f'<h2 id="map-{mid}">{map_title(mid)} <span class="hint">{len(rs)} NPCs, {len(friendable)} with a friendship ladder</span></h2>'
                        f'<div class="npcgrid">{"".join(card(r) for r in rs)}</div>')
    rest = [r for rs in groups.values() for r in rs]
    if rest:
        rest.sort(key=lambda r: _num(r[0]))
        sections.append(f'<h2 id="events">Event and crossover NPCs <span class="hint">{len(rest)}, no home map</span></h2>'
                        f'<div class="npcgrid">{"".join(card(r) for r in rest)}</div>')
    if placeholders:
        sections.append(f"<p class='hint'>{len(placeholders)} more NPC ids carry placeholder names rather than localised ones and are not shown.</p>")

    # ---- the ladder: tags, exp per band, gates (all NPCs share the same ladder)
    sample = next(iter(by_npc.values()))
    sample.sort(key=lambda x: _num(x[fi["Level"]]))
    exp_at = {_num(x[fi["Level"]]): _num(x[fi["FriendshipExp"]]) for x in sample}
    gate_at = {_num(x[fi["Level"]]): x[fi["SubRankLimit"]].strip() for x in sample}
    tag_rows = ""
    for t in tags:
        lo, hi = [int(v) for v in re.findall(r"\d+", t[tgi["LevelRanges"]])[:2]]
        nm = loc(f"npc_friendship_tag_{t[0].strip()}_name", t[tgi["TagName"]])
        gates_in = sorted({gate_at.get(l, "") for l in range(lo, hi + 1)} - {"", "Norank"})
        tag_rows += (f"<tr><td>{lo}–{hi}</td><td><b>{html.escape(nm)}</b></td><td class='num'>{exp_at.get(hi, 0):,}</td>"
                     f"<td>{', '.join(html.escape(gate_name(g)) for g in gates_in) or '—'}</td></tr>")
    talk_rows = "".join(f"<li>Lv {lv}: “{html.escape(loc(f'npc_talk_{i}', ''))}”</li>"
                        for lv, i in ((1, 1), (2, 2), (4, 3)) if loc(f"npc_talk_{i}", ""))

    # ---- gifts
    excl_owner = {}
    for g in gifts:
        o = g[gi["ExclusiveNpc"]].strip()
        if o:
            excl_owner[g[0].strip()] = loc(f"ui_npc_name_{o}", o)
    gift_rows = "".join(
        f"<tr><td>{html.escape(gift_name[g[0].strip()])}</td><td class='num'>{gift_exp[g[0].strip()]:,}</td>"
        f"<td>{html.escape(excl_owner.get(g[0].strip(), ''))}</td></tr>"
        for g in sorted(gifts, key=lambda g: (-gift_exp[g[0].strip()], gift_name[g[0].strip()])))

    body = f"""
<div class="wrap">
<p class="eyebrow">Reference</p>
<h1>NPC friendship</h1>
<p class="lede">Every NPC in the game's table, by the map they live on and in the order the seasons open them, with
the gifts they like, the friendship ladder and what each friendship level grants you. Names, maps, tags and gift
reactions are the game's own text; the season labels follow the same alignment as the Equipment page.</p>

<p class="hint">Map 9 has no name in the localisation; its residents are the crossover guests, so that is what the section is called.</p>
<h2>The ladder</h2>
<p>Every NPC climbs the same 100 levels. The friendship total to reach each band, the title the game gives the bond
there, and the promotion you must hold before the band opens:</p>
<div class="tablewrap"><table><thead><tr><th>Levels</th><th>Bond</th><th class="num">Friendship to reach</th><th>Needs</th></tr></thead>
<tbody>{tag_rows}</tbody></table></div>
<p>Gifts get a warmer line as the bond grows:</p><ul class="plain">{talk_rows}</ul>
<p>Friendship also pays in stats: each NPC has a bonus curve, and the cards below show what it grants at Lv 50 and
Lv 100. Flat ATK, HP, DEF and SPD stack across every NPC you befriend.</p>

{"".join(sections)}

<h2 id="gifts">Gifts</h2>
<p>Friendship per gift before an NPC's own multiplier. A journal is exclusive to one NPC.</p>
<div class="tablewrap"><table><thead><tr><th>Gift</th><th class="num">Friendship</th><th>Only for</th></tr></thead>
<tbody>{gift_rows}</tbody></table></div>
</div>
"""
    return layout("NPC friendship", "Every Sword x Staff NPC by map and season, with gifts, the friendship ladder and the "
                  "stats each friendship level grants.", body, "npcs", 0)
