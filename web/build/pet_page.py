"""Pets — every pet with its skills as a baby and as an adult, from pet / pet_evolution,
with the shared growth curve, potential and skill-rank tables."""
from __future__ import annotations
import html, re, os, shutil, collections


def _num(s, d=0):
    try:
        return int(str(s).strip())
    except Exception:
        return d


def _ids(s):
    return [x for x in re.findall(r"\d+", s or "")]


def clean_rich(s):
    """The game's own rich text, flattened: colour and link tags stripped, breaks kept."""
    s = s or ""
    s = re.sub(r"<link=\d+>", "", s).replace("</link>", "")
    s = re.sub(r"<color=#?[0-9a-fA-F]+>", "", s).replace("</color>", "")
    s = s.replace("<u>", "").replace("</u>", "").replace("\\n", "\n")
    return html.escape(s).replace("\n", "<br>")


def render(layout, dist, out):
    import build as _b
    L = _b.L

    def loc(key, fallback=""):
        v = L(key)
        return (v or fallback).strip()

    def rows_of(name):
        r = _b.csvrows(name); h = [c.strip() for c in r[0]]
        return h, [x for x in r[2:] if x and x[0].strip() and not x[0].startswith("#")]

    h, pets = rows_of("pet"); pi = {c: i for i, c in enumerate(h)}
    h, evo = rows_of("pet_evolution"); ei = {c: i for i, c in enumerate(h)}
    h, skills = rows_of("skill"); si = {c: i for i, c in enumerate(h)}
    skill_row = {r[0].strip(): r for r in skills}
    h, pot = rows_of("pet_potential"); poi = {c: i for i, c in enumerate(h)}
    h, prank = rows_of("pet_skill_rank"); pri = {c: i for i, c in enumerate(h)}
    h, pb = rows_of("pet_battle"); pbi = {c: i for i, c in enumerate(h)}
    battle = {r[0].strip(): r for r in pb}
    h, lpp = rows_of("level_prop_pet"); lpi = {c: i for i, c in enumerate(h)}
    curve = collections.defaultdict(dict)
    for r in lpp:
        curve[r[0].strip()][_num(r[1])] = {h[i]: _num(r[i]) for i in range(2, min(len(h), len(r)))}

    # ---- art: baby/adult icons and skill icons
    def copy_dir(sub, prefix, dest):
        src = os.path.join(out, sub); d = os.path.join(dist, "assets", dest); os.makedirs(d, exist_ok=True)
        have = set()
        if os.path.isdir(src):
            for f in os.listdir(src):
                if f.startswith(prefix) and f.endswith(".png"):
                    shutil.copy2(os.path.join(src, f), os.path.join(d, f)); have.add(f[:-4])
        return have
    have_pet = copy_dir("pet_icons", "pet_", "pets")
    have_sk = copy_dir("pet_skill_icons", "petskill_", "petskills")

    QW = {q: loc(f"Quality.{q}", q) for q in ("Blue", "Purple", "Orange", "Gold", "Red", "Rainbow")}

    def skill_card(sid, promotable, quality=None):
        r = skill_row.get(sid)
        name = loc(f"item_{sid}_name", (r[si["Name"]] if r else f"skill {sid}"))
        desc = clean_rich(loc(f"item_{sid}_func_desc", ""))
        tag = r[si["OuterTag"]].strip() if r else ""
        icon = (f'<img src="assets/petskills/petskill_{sid}.png" alt="" loading="lazy">' if f"petskill_{sid}" in have_sk
                else '<span class="noimg small"></span>')
        bits = []
        if tag:
            bits.append(html.escape(tag))
        if quality:
            bits.append(f"reaches {html.escape(QW.get(quality, quality))} on evolution")
        if promotable:
            bits.append("ranks up with shards")
        return (f'<div class="petskill">{icon}<div><b>{html.escape(name)}</b>'
                f'{" <span class=hint>" + " &middot; ".join(bits) + "</span>" if bits else ""}'
                f'<p>{desc or "<i>no card text in the localisation</i>"}</p></div></div>')

    def phase_block(e, title):
        promo = set(_ids(e[ei["PromotableSkills"]]))
        equal = dict(re.findall(r"(\d+)\s*:\s*'?([A-Za-z]+)'?", e[ei["EvolutionSkillQuality"]]))
        groups = [("Field skill", _ids(e[ei["EntitySkill"]])), ("Battle skills", _ids(e[ei["EntityActiveSkills"]])),
                  ("Support", _ids(e[ei["SupportSkills"]])), ("Active", _ids(e[ei["ActiveSkills"]])),
                  ("Passive", _ids(e[ei["PassiveSkills"]]))]
        seen, out_ = set(), []
        for label, ids in groups:
            ids = [i for i in ids if i not in seen]
            if not ids:
                continue
            seen.update(ids)
            out_.append(f'<h5>{label}</h5>' + "".join(skill_card(i, i in promo, equal.get(i)) for i in ids))
        lvl = e[ei["EvolutionLevel"]].strip()
        return (f'<div class="phase"><h4>{title}' + (f' <span class="hint">from Lv {lvl}</span>' if lvl else "") + "</h4>"
                + ("".join(out_) or "<p class='hint'>no skills listed</p>") + "</div>")

    cards = []
    placeholders = []
    for p in pets:
        cid = p[0].strip()
        name = loc(f"ui_pet_name_{cid}", "") or loc(f"pet_name_{cid}", "") or loc(f"item_{cid}_name", "") or p[pi["Name"]]
        if re.match(r"^DNT", name):
            placeholders.append((cid, name)); continue
        ptype = loc(f"PetType.{p[pi['Type']].strip()}", p[pi["Type"]].strip())
        move = p[pi["MovementType"]].strip()
        shard_id = p[pi["PetPieceId"]].strip()
        shard = loc(f"item_{shard_id}_name", shard_id)
        merge = _num(p[pi["PieceMergeCount"]])
        phases = sorted([e for e in evo if e[0].strip() == cid], key=lambda e: 0 if e[ei["EvolutionPhase"]].strip() == "Childhood" else 1)
        baby = f'<img class="baby" src="assets/pets/pet_{cid}.png" alt="">' if f"pet_{cid}" in have_pet else '<span class="noimg"></span>'
        adult_id = str(_num(cid) + 100)
        adult = f'<img class="adult" src="assets/pets/pet_{adult_id}.png" alt="">' if f"pet_{adult_id}" in have_pet else ""
        stat = ""
        b = battle.get(cid)
        if b:
            stat = " &middot; ".join(f"{k} {_num(b[pbi[k]]) / 100:g}%" for k in ("MaxHp", "Attack", "Defence", "Speed") if k in pbi)
            stat = f"<dt>Battle base</dt><dd>{stat.replace('MaxHp', 'HP').replace('Attack', 'ATK').replace('Defence', 'DEF').replace('Speed', 'SPD')}</dd>"
        blocks = "".join(phase_block(e, loc(f"PetEvolutionPhase.{e[ei['EvolutionPhase']].strip()}", e[ei["EvolutionPhase"]].strip())) for e in phases)
        cards.append(f'''<article class="pet" id="pet-{cid}">
  <div class="pethead">{baby}{adult}<div><h3>{html.escape(name)}</h3>
    <dl><dt>Role</dt><dd>{html.escape(ptype)}</dd><dt>Moves</dt><dd>{html.escape(move)}</dd>
    <dt>Shard</dt><dd>{html.escape(shard)} &times;{merge} to summon</dd>{stat}</dl></div></div>
  <div class="phases">{blocks}</div>
</article>''')

    # ---- shared growth curve
    cid0 = re.findall(r"\d+", pets[0][pi["LevelPropId"]])
    curve_id = cid0[1] if len(cid0) > 1 else (cid0[0] if cid0 else "")
    c = curve.get(curve_id, {})
    lv_rows = "".join(f"<tr><td class='num'>{lv}</td>" + "".join(f"<td class='num'>{c[lv].get(k, 0):,}</td>" for k in ("MaxHp", "Attack", "Defence", "Speed")) + "</tr>"
                      for lv in (1, 20, 50, 80, 100, 120, 150, 200) if lv in c)
    pot_rows = ""
    byq = collections.defaultdict(list)
    for r in pot:
        byq[r[0].strip()].append(r)
    for q in ("Blue", "Purple", "Orange", "Gold"):
        rs = sorted(byq.get(q, []), key=lambda r: _num(r[poi["Level"]]))
        if not rs:
            continue
        top = rs[-1]
        cost = sum(_num(r[poi["SkillPieceCost"]]) for r in rs)
        pot_rows += f"<tr><td>{html.escape(QW.get(q, q))}</td><td class='num'>{len(rs)}</td><td class='num'>{cost:,}</td><td class='num'>{_num(top[poi['PropValue']]) / 100:g}%</td></tr>"
    rank_rows = "".join(f"<tr><td>{html.escape(QW.get(r[pri['Quality']].strip(), r[pri['Quality']].strip()))}</td><td class='num'>{_num(r[pri['Piece']]):,}</td></tr>"
                        for r in prank if r[pri["Quality"]].strip() not in ("None",))

    ph_txt = ""
    if placeholders:
        ph_txt = ("<p class='hint'>Two more pet ids exist in the table with placeholder names rather than localised ones (" +
                  ", ".join(html.escape(c) for c, _ in placeholders) + "), so they are not shown as pets.</p>")

    body = f"""
<div class="wrap">
<p class="eyebrow">Reference</p>
<h1>Pets</h1>
<p class="lede">Every pet in the game's table, with the skills it has as a baby and the ones it gains as an adult,
straight from the evolution table. Names, roles, stages and skill text are the game's own.</p>
{ph_txt}
<div class="petgrid">{"".join(cards)}</div>

<h2>How pets grow</h2>
<p>Every pet shares one growth curve, <code>level_prop_pet</code> {html.escape(curve_id)}, and evolves at level 100. The four
pets with a <code>pet_battle</code> row scale that curve by the percentages on their card.</p>
<div class="threecol">
<div class="tablewrap"><table><thead><tr><th class="num">Level</th><th class="num">HP</th><th class="num">ATK</th><th class="num">DEF</th><th class="num">SPD</th></tr></thead><tbody>{lv_rows}</tbody></table>
<caption>The shared curve.</caption></div>
<div class="tablewrap"><table><thead><tr><th>Potential</th><th class="num">Steps</th><th class="num">Shards, total</th><th class="num">Top bonus</th></tr></thead><tbody>{pot_rows}</tbody></table>
<caption><code>pet_potential</code>: shards spent per quality tier, and the stat bonus at the last step.</caption></div>
<div class="tablewrap"><table><thead><tr><th>Skill rank</th><th class="num">Shards</th></tr></thead><tbody>{rank_rows}</tbody></table>
<caption><code>pet_skill_rank</code>: what each skill quality costs.</caption></div>
</div>
</div>
"""
    return layout("Pets", "Every Sword x Staff pet with its baby and adult skills, the shared growth curve, potential and "
                  "skill-rank costs.", body, "pets", 0)
