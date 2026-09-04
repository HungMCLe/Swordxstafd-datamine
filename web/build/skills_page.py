"""Skills page: a class tree you pick from, plus the selected class's skills."""
from __future__ import annotations
import html, json, os, re
from richtext import richtext


def _lines(data):
    """Return (roots, chains). chains = list of lists of class dicts, one per line."""
    byid, tier_of = {}, {}
    for t in data["tiers"]:
        for c in t["classes"]:
            byid[c["id"]] = c
            tier_of[c["id"]] = t["tier"]
    roots = [c for c in byid.values() if tier_of[c["id"]] == 1]
    chains = []
    for r in roots:
        for c in byid.values():
            if c.get("prePro") == r["id"]:
                chain, cur = [c], c
                while True:
                    nxt = next((x for x in byid.values() if x.get("prePro") == cur["id"]), None)
                    if not nxt:
                        break
                    chain.append(nxt)
                    cur = nxt
                chains.append({"root": r, "chain": chain})
    return roots, chains, tier_of


def render(layout, data, iconset):
    qualities = data["qualities"]
    statlabel = {s["key"]: s["label"] for s in data["stats"]}
    ispct = {s["key"]: s["pct"] for s in data["stats"]}
    roots, chains, tier_of = _lines(data)
    en_of = {c["id"]: c["name"] for t in data["tiers"] for c in t["classes"]}

    def cicon(c, size=26):
        b = os.path.basename(c.get("icon") or "")
        if f"class_{b}.png" in iconset:
            return (f'<img src="../assets/skills/class_{html.escape(b)}.png" alt="" '
                    f'width="{size}" height="{size}">')
        return ''

    def node(c, extra=""):
        return (f'<button type="button" class="cnode{extra}" data-cls="{html.escape(c["id"])}">'
                f'{cicon(c)}<span>{html.escape(c["name"])}</span>'
                f'<em>T{tier_of[c["id"]]}</em></button>')

    # ---- tree ----
    cols = []
    for ch in chains:
        cells = "".join(f'<li>{node(c)}</li>' for c in ch["chain"])
        cols.append(f'<ol class="line" data-root="{html.escape(ch["root"]["id"])}">{cells}</ol>')
    rootrow = "".join(
        f'<div class="rootcell">{node(r, " root")}</div>' for r in roots)
    tree = (f'<div class="tree">'
            f'<div class="rootrow">{rootrow}</div>'
            f'<div class="lines">{"".join(cols)}</div>'
            f'</div>')

    # ---- skill panels ----
    panels = []
    for t in data["tiers"]:
        for c in t["classes"]:
            cards = []
            for s in c["skills"]:
                sid = s["id"]
                icon = (f'<img src="../assets/skills/skill_{sid}.png" alt="" width="44" height="44" loading="lazy">'
                        if f"skill_{sid}.png" in iconset else '<span class="sk-noicon"></span>')
                qs = s.get("qualities") or {}
                have = [q for q in qualities if q in qs]
                desc = richtext((s.get("desc") or "").strip())
                kind = s.get("kind", "active")
                pill = f'<span class="sk-kind {kind}">{kind}</span>'
                if have:
                    keys = {k for q in have for k in qs[q]["vals"]}
                    labels = {}
                    for k in keys:
                        labels[k] = (s.get("statusLabels", {}).get(k)
                                     or statlabel.get(k)
                                     or re.sub(r"(?<!^)(?=[A-Z])", " ", k.replace("ST:", ""))
                                       .replace("Status Fixed Add", "Flat status effect ")
                                       .replace("Status Add", "Status effect "))
                    payload = html.escape(json.dumps(
                        {"q": {q: qs[q] for q in have}, "order": have, "labels": labels,
                         "pct": {k: ispct.get(k, False) for k in keys},
                         "direct": {k: bool(s.get("statusPct", {}).get(k, False)) for k in keys}},
                        ensure_ascii=False), quote=True)
                    stepper = ('<div class="qstep">'
                               '<button type="button" class="qbtn" data-dir="-1" aria-label="Lower quality">&lsaquo;</button>'
                               '<span class="qname"></span>'
                               '<button type="button" class="qbtn" data-dir="1" aria-label="Higher quality">&rsaquo;</button>'
                               '</div>')
                    stats = '<dl class="sk-stats"></dl>'
                    attr = f' data-skill="{payload}"'
                else:
                    stepper = ''
                    stats = ('<p class="sk-flat">Flat-stat passive — scales with character level, '
                             'not with quality.</p>' if kind == "passive"
                             else '<p class="sk-flat">No per-quality values in the config for this one.</p>')
                    attr = ''
                cards.append(
                    f'<article class="skill"{attr}>'
                    f'<div class="sk-head">{icon}<div class="sk-id"><h4>{html.escape(s["name"])}</h4>'
                    f'<span class="sk-meta">{pill}<span class="sk-num">#{sid}</span></span></div>{stepper}</div>'
                    + (f'<p class="sk-desc">{desc}</p>' if desc else '')
                    + stats + '</article>')
            withn = sum(1 for s in c["skills"] if s.get("qualities"))
            panels.append(
                f'<section class="panel" id="cls-{html.escape(c["id"])}" hidden>'
                f'<div class="panel-head">{cicon(c, 40)}<div><h2>{html.escape(c["name"])}</h2>'
                f'<p class="panel-sub">Tier {tier_of[c["id"]]}'
                + (f' · promotes from {html.escape(en_of.get(c["prePro"], c["prePro"]))}'
                   if c.get("prePro") and c["prePro"] != "None" else '')
                + f' · {len(c["skills"])} skills, {withn} with per-quality values</p></div></div>'
                f'<div class="skillgrid">{"".join(cards)}</div></section>')

    body = f"""
<div class="wrap">
<p class="eyebrow">Skills</p>
<h1>Every skill, at every quality</h1>
<p class="lede">Two base classes branch into four lines, each promoting through seven tiers.
Pick a class, then step any skill from Rare to Immortal — the values move, and take the colour of the
quality you are on.</p>

{tree}

<div class="qglobal">
  <span class="qglabel">Set every skill to</span>
  <div class="qallrow">
    {"".join(f'<button type="button" class="qall q-{q.lower()}" data-q="{q}">{q}</button>' for q in qualities)}
  </div>
</div>

{"".join(panels)}

<div class="note">
<p><b>Where the numbers come from.</b> Damage skills use their base coefficient times a rank scale
(<code>level_prop_skill</code>); buffs and debuffs read the status entity the skill points at through
<code>ViewPropEntities</code>, scaled by <code>level_prop_status</code>. Quality is a band of ranks, so each
step shows the value at the <i>first</i> rank of that quality. Coefficients are a percentage of ATK;
flat values are raw.</p>
<p><b>Descriptions are the game's own.</b> All 328 are shown exactly as the client renders them, keeping
its colour markup — element names in their element colour, and game keywords like <span class="kw">grid</span>
or <span class="kw">base chance</span> highlighted. Fixed figures written into the text (chances, ranges,
hit counts) are picked out in bold; those do not change with quality. The values that <i>do</i> change are the
ones in the stat list, which take the colour of the quality you have selected.</p>
<p><b>241 of 328 skills</b> have per-quality values. The rest are flat-stat passives, which the rank tables
do not scale at all — they grow with character level instead. Those say so on the card.</p>
</div>
</div>
<script src="../assets/skills.js" defer></script>
"""
    return layout("Skills", "Every Sword x Staff class skill by tier and class line, with exact values at Rare, Epic, Legendary, Mythic, Divine and Immortal.", body, "skills", 1)
