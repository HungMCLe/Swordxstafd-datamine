"""Skills page: tier -> class -> skill cards with a per-skill quality stepper."""
from __future__ import annotations
import html, json, os


def render(layout, data, iconset):
    """iconset: set of filenames present in dist/assets/skills."""
    qualities = data["qualities"]
    statlabel = {s["key"]: s["label"] for s in data["stats"]}
    ispct = {s["key"]: s["pct"] for s in data["stats"]}

    # ---- tier nav ----
    tiernav = "".join(
        f'<a href="#tier{t["tier"]}">Tier {t["tier"]}</a>' for t in data["tiers"])

    sections = []
    for t in data["tiers"]:
        classes = []
        for c in t["classes"]:
            cicon = os.path.basename(c.get("icon") or "")
            cimg = (f'<img class="cls-icon" src="../assets/skills/class_{html.escape(cicon)}.png" '
                    f'alt="" width="34" height="34">'
                    if f"class_{cicon}.png" in iconset else '')
            cards = []
            for s in c["skills"]:
                sid = s["id"]
                icon = (f'<img src="../assets/skills/skill_{sid}.png" alt="" width="44" height="44" loading="lazy">'
                        if f"skill_{sid}.png" in iconset else '<span class="sk-noicon"></span>')
                qs = s.get("qualities") or {}
                have = [q for q in qualities if q in qs]
                desc = (s.get("desc") or "").strip()
                # strip the game's rich-text markup for a clean summary line
                import re as _re
                desc = _re.sub(r"<[^>]+>", "", desc)
                desc = _re.sub(r"\s+", " ", desc).strip()
                if len(desc) > 190:
                    desc = desc[:187].rstrip() + "…"
                kind = s.get("kind", "active")
                pill = f'<span class="sk-kind {kind}">{kind}</span>'
                if have:
                    stepper = (
                        '<div class="qstep">'
                        '<button type="button" class="qbtn" data-dir="-1" aria-label="Lower quality">&lsaquo;</button>'
                        '<span class="qname"></span>'
                        '<button type="button" class="qbtn" data-dir="1" aria-label="Higher quality">&rsaquo;</button>'
                        '</div>')
                    stats = '<dl class="sk-stats"></dl>'
                    payload = html.escape(json.dumps(
                        {"q": {q: qs[q] for q in have},
                         "order": have,
                         "labels": {k: statlabel.get(k, k) for k in
                                    {kk for q in have for kk in qs[q]["vals"]}},
                         "pct": {k: ispct.get(k, False) for k in
                                 {kk for q in have for kk in qs[q]["vals"]}}},
                        ensure_ascii=False), quote=True)
                    dataattr = f' data-skill="{payload}"'
                else:
                    stepper = ''
                    stats = ('<p class="sk-flat">Does not scale with quality — this one scales with '
                             'character level instead.</p>' if kind == "passive"
                             else '<p class="sk-flat">No per-quality coefficients in the config.</p>')
                    dataattr = ''
                cards.append(
                    f'<article class="skill"{dataattr}>'
                    f'<div class="sk-head">{icon}<div class="sk-id"><h4>{html.escape(s["name"])}</h4>'
                    f'<span class="sk-meta">{pill}<span class="sk-num">#{sid}</span></span></div>{stepper}</div>'
                    + (f'<p class="sk-desc">{html.escape(desc)}</p>' if desc else '')
                    + stats + '</article>')
            classes.append(
                f'<section class="cls"><h3>{cimg}{html.escape(c["name"])}'
                f'<span class="cls-n">{len(c["skills"])} skills</span></h3>'
                f'<div class="skillgrid">{"".join(cards)}</div></section>')
        sections.append(
            f'<section class="tier-sec" id="tier{t["tier"]}">'
            f'<h2>Tier {t["tier"]}<span class="tier-cls">'
            f'{" · ".join(html.escape(c["name"]) for c in t["classes"])}</span></h2>'
            f'{"".join(classes)}</section>')

    body = f"""
<div class="wrap">
<p class="eyebrow">Skills</p>
<h1>Every skill, at every quality</h1>
<p class="lede">Classes branch into four lines, each promoting through seven tiers. Pick any skill and
step it through the quality ladder to see exactly how its numbers change.</p>

<div class="qglobal">
  <span class="qglabel">Set every skill to</span>
  <div class="qallrow">
    {"".join(f'<button type="button" class="qall q-{q.lower()}" data-q="{q}">{q}</button>' for q in qualities)}
  </div>
</div>

<div class="note">
<p><b>How the numbers are produced.</b> A skill's value is its base coefficient multiplied by a rank
scale: <code>value = base &times; rankScale(RankPropId, rank)</code>. Quality is a band of ranks, so each
step below shows the value at the <i>first</i> rank of that quality — the moment you reach it.
Damage coefficients are shown as a percentage of ATK; flat values are raw.</p>
</div>

<nav class="tiernav">{tiernav}</nav>

{"".join(sections)}

<h2>What did not make this page</h2>
<p>Of 328 class skills, <b>170</b> have per-quality numbers in the config. The rest split two ways:
passives whose effect is a flat stat rather than a percentage do not scale with quality at all — the
rank table has no entry for them, so they grow with character level instead; and some actives resolve
their damage through status entities rather than direct coefficients, which is a separate system.
Both are marked on their cards rather than guessed at.</p>
</div>
<script src="../assets/skills.js" defer></script>
"""
    return layout("Skills", "Every Sword x Staff class skill by tier, with exact numbers at Rare, Epic, Legendary, Mythic, Divine and Immortal quality.", body, "skills", 1)
