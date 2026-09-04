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
                ranks = s.get("ranks") or []
                desc = richtext((s.get("desc") or "").strip(), s.get("links"))
                tname = s.get("type") or "Technique"
                pill = f'<span class="sk-kind {tname.lower()}">{tname}</span>'
                if ranks:
                    payload = html.escape(json.dumps(
                        {"ranks": ranks, "vals": s["vals"], "lmult": s["lmult"],
                         "lgroup": s["lgroup"], "labels": s["labels"], "pct": s["pct"],
                         "order": s["order"], "pair": s["pair"], "lkey": s["lkey"]},
                        ensure_ascii=False), quote=True)
                    stepper = ('<div class="qstep">'
                               '<button type="button" class="qbtn" data-dir="-1" aria-label="Lower rank">&lsaquo;</button>'
                               '<span class="qname"></span>'
                               '<button type="button" class="qbtn" data-dir="1" aria-label="Higher rank">&rsaquo;</button>'
                               '</div>')
                    stats = '<dl class="sk-stats"></dl>'
                    attr = f' data-skill="{payload}"'
                else:
                    stepper = ''
                    stats = ('<p class="sk-flat">The game&rsquo;s own scaling chain defines no '
                             'value for this one — its effect is written into the description.</p>')
                    attr = ''
                cards.append(
                    f'<article class="skill"{attr}>'
                    f'<div class="sk-head">{icon}<div class="sk-id"><h4>{html.escape(s["name"])}</h4>'
                    f'<span class="sk-meta">{pill}<span class="sk-num">#{sid}</span></span></div>{stepper}</div>'
                    + (f'<p class="sk-desc">{desc}</p>' if desc else '')
                    + stats + '</article>')
            withn = sum(1 for s in c["skills"] if s.get("ranks"))
            panels.append(
                f'<section class="panel" id="cls-{html.escape(c["id"])}" hidden>'
                f'<div class="panel-head">{cicon(c, 40)}<div><h2>{html.escape(c["name"])}</h2>'
                f'<p class="panel-sub">Tier {tier_of[c["id"]]}'
                + (f' · promotes from {html.escape(en_of.get(c["prePro"], c["prePro"]))}'
                   if c.get("prePro") and c["prePro"] != "None" else '')
                + f' · {len(c["skills"])} skills, {withn} with per-rank values</p></div></div>'
                f'<div class="skillgrid">{"".join(cards)}</div></section>')

    maxlv = data["levels"][-1]
    import build as _b
    from build import DIST
    (DIST / "assets").mkdir(parents=True, exist_ok=True)
    (DIST / "assets" / "curves.json").write_text(
        json.dumps(data["curves"], separators=(",", ":")), encoding="utf-8")
    globaljson = json.dumps(dict({k: data[k] for k in
                             ("rankLabels", "rankQuality", "qualityRanks",
                              "lpidOf", "defaultLevel", "defaultSubrank")}, v=_b.asset_v()),
                            ensure_ascii=False).replace("</", "<\/")
    subopts = "".join(
        f'<option value="{html.escape(sr["id"])}"'
        f'{" selected" if sr["id"] == data["defaultSubrank"] else ""}>'
        f'{html.escape(sr["name"])} &middot; to level {sr["cap"]}</option>'
        for sr in data["subranks"])

    body = f"""
<div class="wrap">
<p class="eyebrow">Skills</p>
<h1>Every skill, at every rank</h1>
<p class="lede">A skill carries a quality <i>and</i> a level inside it — the game writes them
together as <b>Divine&nbsp;+3</b>. There are 34 steps from Rare&nbsp;+0 to Immortal&nbsp;+10.
Pick a class, then step any skill one rank at a time and watch the numbers move.</p>

{tree}

<div class="controls">
  <div class="ctl">
    <span class="ctl-label">Set every skill to</span>
    <div class="qallrow">
      {"".join(f'<button type="button" class="qall q-{q.lower()}" data-q="{q}">{q}</button>' for q in qualities)}
    </div>
  </div>
  <div class="ctl">
    <span class="ctl-label">Skill level</span>
    <input type="number" id="lvl" min="1" max="{maxlv}" value="{data['defaultLevel']}"
           inputmode="numeric" aria-label="Skill level">
  </div>
  <div class="ctl">
    <span class="ctl-label">Character rank</span>
    <select id="subrank" aria-label="Character rank">{subopts}</select>
  </div>
  <p class="ctl-note">A skill's own level indexes a growth curve; your character rank picks which
  curve. Flat figures move with both &mdash; coefficients move with rank alone.</p>
</div>

<script type="application/json" id="skilldata">{globaljson}</script>

{"".join(panels)}

<div class="note">
<p><b>Rank and level are two different things.</b> <code>skill_rank</code> lists 34 ranks grouped into six
qualities, and its <code>RankAddition</code> column is the number the game prints after the quality name.
Rare spans 2 ranks, Epic 3, Legendary 4, Mythic 6, Divine 8 and Immortal 11 — so Divine&nbsp;+7 is a real
step above Divine&nbsp;+0, not a relabelling.</p>
<p><b>Where the numbers come from.</b> The game's own
<code>BattleFormulaHandler.CalcSkillProps</code>. It reads a base from the growth curve that
<code>entity_prop_group_level</code> picks for your character rank, indexed by the <i>skill's</i> own level;
scales it per-property by the rank table; then by the skill's own factors; and for Charms once more by a
rank factor. The columns in <code>entity_prop_skill</code> are factors on that curve, not amounts.</p>
<p><b>Which tables count.</b> <code>LevelPropParser</code> reads one baked binary, and
<code>level_prop_files</code> is the game's own list of what goes into it &mdash; merging anything else
gives wrong numbers, because a prop missing from the rank table passes through unscaled rather than being
multiplied. Rows follow <code>prop_cfg</code>: <code>SkillPanelShowOrder</code> for order, and a prop marked
<code>SkillHide</code> is folded into its percent partner, which is why damage reads as one
<b>204.4%&nbsp;+&nbsp;494,887</b> line. Values truncate at each step the way the game's
<code>(long)</code> casts do.</p>
<p><b>Checked against a live client.</b> Three cards at skill level 127, character rank Expert&nbsp;II:
Rapid Cast at Immortal&nbsp;+1 &rarr; <b>25,444</b> (game: 25.4K). Divine Wrath at Divine&nbsp;+6 &rarr;
<b>CD 2</b> and <b>204.4% + 494,887</b> (game: 204.4%+494K). Frost Guard at Divine&nbsp;+1 &rarr;
<b>31.2% + 34,916</b> and <b>2.7% + 75,542</b> (game: 31.2%+34.9K, 2.7%+75.5K). Eight figures, eight
matches.</p>
<p><b>Two kinds, as the game splits them:</b> 166 <b>Techniques</b> and 162 <b>Charms</b>.
Descriptions are the client's own text, colour markup intact, and every highlighted keyword carries the
game's explanation on hover — all 393 resolve, including the units named by summon skills.</p>
<p><b>322 of 328 skills</b> have per-rank values. For the rest the config's scaling chain produces nothing
at all — their effect is described in words rather than a scaled number — and those cards say so.</p>
</div>
</div>
<script src="../assets/skills.js?v={_b.asset_v()}" defer></script>
"""
    return layout("Skills", "Every Sword x Staff class skill at all 34 ranks, from Rare +0 to Immortal +10, with the values the game's own formula produces.", body, "skills", 1)
