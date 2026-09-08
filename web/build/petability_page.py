"""Fantomon ability trees — each page drawn as the game lays it out (pet_ability_graph for
positions, NextNodes for the links, the client's PetAbility_* sprites for the symbols), with
the materials to fill it, what a full page grants, and the power that is worth.

Stats: a node at level N adds the whole row level_prop_pet_ability[PropId][N], scaled per prop
by pet_ability_prop_scale_factor[PropScaleFactorId] (CalculatePetAbilityProps); System*Percent
then multiplies the Fantomon's own stat (HandleSystemPercentProps). Power: prop_cfg.Score per
stat (CalcCombatRatingByProps): ATK 2.5, HP 0.5, DEF 2.5, SPD 3.125; the crit / damage nodes
score against your own base stats and are left out of the number.
Materials merge 4 -> 1 up a tier (item_merge); Wool, Egg and Essence never convert into each
other except by choosing from the material boxes.
"""
from __future__ import annotations
import html, re, os, shutil, collections


def _num(s, d=0):
    try:
        return int(str(s).strip())
    except Exception:
        return d


SHORT = {"MaxHp": "HP", "Attack": "ATK", "Defence": "DEF", "Speed": "SPD", "CritRatePercent": "Crit Rate",
         "BlockPercent": "Block Rate", "CritAvoidPercent": "Crit RES", "BlockAvoidPercent": "Accuracy",
         "DmgAddPercent": "DMG Boost", "DmgReducePercent": "DMG RES", "CureAddPercent": "Healing Boost",
         "SystemAttackPercent": "ATK", "SystemDefencePercent": "DEF", "SystemMaxHpPercent": "HP", "SystemSpeedPercent": "SPD"}
PCT = {k for k in SHORT if k.endswith("Percent")}
ICON = {"Attack": "PetAbility_Attack", "MaxHp": "PetAbility_MaxHp", "Defence": "PetAbility_Defence", "Speed": "PetAbility_Speed"}
SCORE = {"Attack": 2.5, "MaxHp": 0.5, "Defence": 2.5, "Speed": 3.125}
SYS = {"SystemAttackPercent": "Attack", "SystemDefencePercent": "Defence", "SystemMaxHpPercent": "MaxHp", "SystemSpeedPercent": "Speed"}
REF_LEVELS = (100, 150, 200)


def render(layout, base_tables, dist, out):
    import build as _b
    L = _b.L
    ladder, *_ = base_tables()
    disp = {Ld["internal"]: Ld["rank"] for Ld in ladder}

    def loc(key, fallback=""):
        v = L(key)
        return (v or fallback).strip()

    def rows_of(name):
        r = _b.csvrows(name); h = [c.strip() for c in r[0]]
        return h, [x for x in r[2:] if x and x[0].strip() and not x[0].startswith("#")]

    # ---- tables
    h, pets = rows_of("pet"); pi = {c: i for i, c in enumerate(h)}
    h, ab = rows_of("pet_ability"); ai = {c: i for i, c in enumerate(h)}
    h, ap = rows_of("pet_ability_prop"); api = {c: i for i, c in enumerate(h)}
    h, gr = rows_of("pet_ability_graph")
    h, lpa = rows_of("level_prop_pet_ability"); lh = h
    h, sf = rows_of("pet_ability_prop_scale_factor")
    h, pc = rows_of("prop_cfg"); pci = {c: i for i, c in enumerate(h)}
    score = {}
    for r in pc:
        try:
            score[r[0].strip()] = float(r[pci["Score"]]) if r[pci["Score"]].strip() else 0.0
        except Exception:
            pass
    for k in SCORE:
        if score.get(k):
            SCORE[k] = score[k]
    h, mg = rows_of("item_merge"); mi = {c: i for i, c in enumerate(h)}
    merge = {r[0].strip(): (r[mi["Material1"]].strip(), _num(r[mi["Count1"]])) for r in mg if r[mi["Material1"]].strip()}
    h, lpp = rows_of("level_prop_pet"); lpi = {c: i for i, c in enumerate(h)}
    petcurve = {}
    for r in lpp:
        if r[0].strip() == "5080":
            petcurve[_num(r[1])] = {k: _num(r[lpi[k]]) for k in ("MaxHp", "Attack", "Defence", "Speed")}

    curve = collections.defaultdict(dict)
    for r in lpa:
        curve[r[0].strip()][_num(r[1])] = {lh[i]: _num(r[i]) for i in range(2, len(lh)) if _num(r[i])}
    scale = {r[0].strip(): {h[i]: _num(r[i]) for i in range(1, len(h))} for r in sf}
    nodes = collections.defaultdict(dict)
    for r in ab:
        nodes[r[0].strip()][r[ai["NodeId"]].strip()] = r
    levels = collections.defaultdict(list)
    for r in ap:
        levels[(r[0].strip(), r[api["NodeId"]].strip())].append(r)
    for k in levels:
        levels[k].sort(key=lambda r: _num(r[api["NodeLevel"]]))
    graph = collections.defaultdict(dict)
    for r in gr:
        graph[(r[0].strip(), r[1].strip())][_num(r[2])] = [_num(x) for x in re.findall(r"-?\d+", r[3])]

    pets_by_tree = collections.defaultdict(list); ptype = {}
    for p in pets:
        name = loc(f"item_{p[0].strip()}_name", "")
        if not name or name.startswith("DNT"):
            continue
        pets_by_tree[p[pi["AbilityId"]].strip()].append(name)
        ptype[p[pi["AbilityId"]].strip()] = loc(f"PetType.{p[pi['Type']].strip()}", p[pi["Type"]].strip())

    # ---- art
    def copy_dir(sub, dest, prefix=""):
        src = os.path.join(out, sub); d = os.path.join(dist, "assets", dest); os.makedirs(d, exist_ok=True); have = set()
        if os.path.isdir(src):
            for f in os.listdir(src):
                if f.endswith(".png") and f.startswith(prefix):
                    shutil.copy2(os.path.join(src, f), os.path.join(d, f)); have.add(f[:-4])
        return have
    have_mat = copy_dir("petmat_icons", "petmat")
    have_node = copy_dir("stat_icons", "petnodes", "PetAbility_")

    def mat(i, n):
        nm = html.escape(loc(f"item_{i}_name", i))
        img = f'<img src="assets/petmat/item_{i}.png" alt="{nm}" title="{nm}">' if f"item_{i}" in have_mat else nm + " "
        return f'<span class="mat">{img}<b>{n:,}</b></span>'

    def base_equiv(cost):
        """Everything expressed in the family's base material through the 4:1 merges."""
        total = collections.Counter()
        for i, n in cost.items():
            k, mult = i, 1
            while k in merge:
                k2, c = merge[k]; mult *= c; k = k2
            total[k] += n * mult
        return total

    def top_of(base):
        """The family's highest tier and how many base units make one of it."""
        up = {m: (prod, c) for prod, (m, c) in merge.items()}
        k, mult = base, 1
        while k in up:
            k, c = up[k]; mult *= c
        return k, mult

    def top_equiv(eq):
        out = {}
        for base, n in eq.items():
            top, mult = top_of(base)
            out[top] = n / mult
        return out

    def mat_f(i, v):
        nm = html.escape(loc(f"item_{i}_name", i))
        img = f'<img src="assets/petmat/item_{i}.png" alt="{nm}" title="{nm}">' if f"item_{i}" in have_mat else nm + " "
        return f'<span class="mat">{img}<b>{v:,.1f}</b></span>'

    def cost_cell(cost, eq):
        top = top_equiv(eq)
        return (f'<span class="c-as">{" ".join(mat(i, n) for i, n in cost.most_common())}</span>'
                f'<span class="c-base">{" + ".join(mat(i, n) for i, n in eq.items())}</span>'
                f'<span class="c-top">{" + ".join(mat_f(i, v) for i, v in top.items())}</span>')

    def scaled(row, sid):
        s = scale.get(sid, {})
        return {k: int(v * (1 + s.get(k, 0) / 10000.0)) for k, v in row.items()}

    def node_total(tree, nid, lv=10):
        r = next((x for x in levels.get((tree, nid), []) if _num(x[api["NodeLevel"]]) == lv), None)
        if not r:
            return {}
        return scaled(curve.get(r[api["PropId"]].strip(), {}).get(lv, {}), r[api["PropScaleFactorId"]].strip())

    def show_prop(tree, nid):
        m = re.search(r"Prop:'(\w+)'", nodes[tree][nid][ai["NodeShowParams"]])
        return m.group(1) if m else "?"

    def fmt(k, v):
        return f"+{v / 100:g}% {SHORT.get(k, k)}" if k in PCT else f"+{v:,} {SHORT.get(k, k)}"

    def power(sum_):
        """Flat stats by their Score, then the System% part against a Fantomon of each reference level."""
        flat = sum(v * SCORE[k] for k, v in sum_.items() if k in SCORE)
        by_lv = {}
        for lv in REF_LEVELS:
            base = petcurve.get(lv, {})
            extra = sum((v / 10000.0) * base.get(SYS[k], 0) * SCORE[SYS[k]] for k, v in sum_.items() if k in SYS)
            by_lv[lv] = int(flat + extra)
        return int(flat), by_lv

    # ---- the drawing
    def tree_svg(tree, pg):
        rows_ = graph.get((tree, pg), {})
        if not rows_:
            return ""
        W, H, R = 64, 60, 20
        cols = max(len(v) for v in rows_.values()); nrows = max(rows_)
        pos = {}
        for rn, ids in rows_.items():
            for c, x in enumerate(ids):
                if x > 0:
                    pos[str(x)] = (c * W + W / 2, (nrows - rn) * H + H / 2)
        lines, dots = [], []
        for nid, (x, y) in pos.items():
            r = nodes[tree].get(nid)
            if not r:
                continue
            for nx in re.findall(r"\d+", r[ai["NextNodes"]]):
                if nx in pos:
                    x2, y2 = pos[nx]
                    lines.append(f'<line x1="{x:.0f}" y1="{y:.0f}" x2="{x2:.0f}" y2="{y2:.0f}"/>')
        for nid, (x, y) in pos.items():
            r = nodes[tree].get(nid)
            sp = show_prop(tree, nid)
            icon = ICON.get(sp) or ("PetAbility_OtherPercent" if sp in PCT else "PetAbility_Other")
            gated = r and r[ai["UnlockConditionType"]].strip() == "SubRank"
            tot = node_total(tree, nid)
            tip = f"Node {nid} · {SHORT.get(sp, sp)} · at Lv 10: " + ", ".join(fmt(k, v) for k, v in tot.items())
            ring = f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{R + 3}" class="gate"/>' if gated else ""
            img = (f'<image href="assets/petnodes/{icon}.png" x="{x - R:.0f}" y="{y - R:.0f}" width="{2 * R}" height="{2 * R}"/>'
                   if icon in have_node else f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{R}" class="nd"/><text x="{x:.0f}" y="{y + 4:.0f}">{html.escape(SHORT.get(sp, sp)[:4])}</text>')
            dots.append(f'<g><title>{html.escape(tip)}</title>{ring}{img}</g>')
        return (f'<svg class="abtree" viewBox="0 0 {cols * W} {nrows * H}" role="img" aria-label="Page {pg} layout">'
                f'<g class="links">{"".join(lines)}</g>{"".join(dots)}</svg>')

    # ---- one page
    def page(tree, pg):
        ids = [n for n, r in nodes[tree].items() if r[ai["PageCode"]].strip() == pg]
        gate = ""
        for n in ids:
            r = nodes[tree][n]
            if r[ai["UnlockConditionType"]].strip() == "SubRank":
                m = re.search(r"SubRank\W+(\w+)", r[ai["UnlockConditionParam"]])
                if m:
                    gate = disp.get(m.group(1), m.group(1))
        cost = collections.Counter()
        per_level = {}
        for n in ids:
            for lv in levels.get((tree, n), []):
                pairs = [(i, _num(c)) for i, c in re.findall(r"(\d+),(\d+)", lv[api["CostItemList"]])]
                for i, c in pairs:
                    cost[i] += c
                per_level.setdefault(_num(lv[api["NodeLevel"]]), pairs)
        total = collections.Counter()
        for n in ids:
            for k, v in node_total(tree, n).items():
                total[k] += v
        flat_p, lv_p = power(total)
        eq = base_equiv(cost)
        return {
            "pg": pg, "n": len(ids), "gate": gate, "cost": cost, "eq": eq, "per_level": per_level,
            "grants": ", ".join(fmt(k, v) for k, v in sorted(total.items(), key=lambda kv: (kv[0] in PCT, -kv[1]))),
            "flat_p": flat_p, "lv_p": lv_p, "svg": tree_svg(tree, pg),
            "cost_txt": " ".join(mat(i, n) for i, n in cost.most_common()),
            "eq_txt": " + ".join(mat(i, n) for i, n in eq.items()),
        }

    # ---- trees
    gens = {"1": ("1", 1), "2": ("2", 1), "3": ("3", 1), "4": ("1", 2), "5": ("2", 2), "6": ("3", 2), "7": ("1", 3), "8": ("2", 3), "9": ("3", 3)}
    sections = []
    for base in ("1", "2", "3"):
        typ = ptype.get(base, "")
        gen_names = {g: ", ".join(pets_by_tree.get(t, [])) for t, (b, g) in gens.items() if b == base}
        pages = [page(base, pg) for pg in sorted({r[ai["PageCode"]].strip() for r in nodes[base].values()}, key=int)]
        grand = collections.Counter(); grand_eq = collections.Counter()
        for p in pages:
            grand.update(p["cost"]); grand_eq.update(p["eq"])
        fam_base = next(iter(grand_eq))
        rows_html = ""
        for p in pages:
            rows_html += (f"<tr><td><b>Page {p['pg']}</b><br><span class='hint'>{p['n']} nodes{(' · ' + html.escape(p['gate'])) if p['gate'] else ''}</span></td>"
                          f"<td class='costs'>{cost_cell(p['cost'], p['eq'])}</td>"
                          f"<td class='num'><b>{p['flat_p']:,}</b><br><span class='hint'>" + " / ".join(f"Lv {lv}: {v:,}" for lv, v in p['lv_p'].items()) + "</span></td>"
                          f"<td class='small'>{p['grants']}</td></tr>")
        cost_pattern = "".join(
            f"<tr><td class='num'>Lv {lv}</td>" + "".join(f"<td>{' '.join(mat(i, n) for i, n in p['per_level'].get(lv, []))}</td>" for p in pages) + "</tr>"
            for lv in range(1, 11))
        drawings = "".join(
            f"<figure class='pagefig'><figcaption><b>Page {p['pg']}</b>" + (f" · opens at {html.escape(p['gate'])}" if p['gate'] else "") +
            f"</figcaption>{p['svg']}</figure>" for p in pages)
        gen_txt = "".join(
            f"<li><b>Generation {g}</b> ({html.escape(gen_names.get(g, '') or 'none released yet')}): " +
            (f"the same tree, costs and gates, with every node and so every power figure <b>+{g * 10 - 10}%</b>." if g > 1 else "the numbers below.") + "</li>"
            for g in (1, 2, 3))
        sections.append(f"""
<h2 id="tree-{base}">{html.escape(typ)} tree <span class="hint">{html.escape(gen_names.get(1, ''))}</span></h2>
<ul class="plain">{gen_txt}</ul>
<p class="costs">All ten pages: {cost_cell(grand, grand_eq)}</p>
<div class="tablewrap"><table class="pages"><thead><tr><th>Page</th><th>To fill it</th><th class="num">Power</th><th>A full page grants</th></tr></thead>
<tbody>{rows_html}</tbody></table>
<caption>Power counts the flat stats by the game's own weights; the second line adds the percent nodes' worth for a Fantomon of that level.
The crit, accuracy and damage nodes score against your own base stats and are not in the figure.</caption></div>
<details><summary>The pages, drawn</summary><div class="pagefigs">{drawings}</div></details>
<details><summary>What each level of a node costs, page by page</summary>
<div class="tablewrap"><table class="pages"><thead><tr><th class="num">Level</th>{"".join(f"<th>Page {p['pg']}</th>" for p in pages)}</tr></thead><tbody>{cost_pattern}</tbody></table>
<caption>Every node on a page costs the same per level.</caption></div></details>
""")

    m4 = " &middot; ".join(f"4 &times; {mat(m, 1)} &rarr; {mat(p, 1)}" for p, (m, c) in merge.items() if p in ("1541", "1542", "1551", "1552", "1531", "1532"))
    body = f"""
<div class="wrap">
<p class="eyebrow">Reference</p>
<h1>Fantomon ability trees</h1>
<p class="lede">Three trees, one per Fantomon role. Each has ten pages of nodes drawn the way the game lays them out, and
every node has ten levels. The table gives, for each page, what it costs to fill, what that is worth in power, and
what a full page grants. Later generations of Fantomon use the same tree with a bonus on every node.</p>

<h2>Materials and power</h2>
<p>Each role pays in its own family, and within a family four of a tier merge into one of the next
(<code>item_merge</code>): {m4}. Wool, Egg and Essence do not convert into each other; the only way across is the
self-choose material boxes.</p>
<p class="costmode">Show costs <span class="seg" role="group" aria-label="Cost display">
<button type="button" data-mode="as" class="on">as listed</button><button type="button" data-mode="base">in the base material</button>
<button type="button" data-mode="top">in the top tier</button></span>
<span class="hint">sixteen of the base make one of the top tier; the top-tier figure is not rounded</span></p>
<p>The game scores stats with fixed weights (<code>prop_cfg</code>): ATK and DEF {SCORE['Attack']:g} per point, SPD
{SCORE['Speed']:g}, HP {SCORE['MaxHp']:g}. A node's percent bonus multiplies the Fantomon's own stat, so its worth depends on the
Fantomon's level; the table shows the flat part and the total for a Fantomon at level {", ".join(str(l) for l in REF_LEVELS)}.
Pages open in order and some need a promotion: page 2 at Expert I, 4 at Champion I, 6 at Master I, 8 at Paragon I,
9 at Saint I.</p>
{"".join(sections)}
</div>
"""
    body += """
<script>
(function () {
  var wrap = document.querySelector(".wrap"), btns = document.querySelectorAll(".costmode button");
  function set(m) {
    wrap.setAttribute("data-costs", m);
    btns.forEach(function (b) { b.classList.toggle("on", b.getAttribute("data-mode") === m); });
    try { localStorage.setItem("pw_costmode", m); } catch (e) {}
  }
  btns.forEach(function (b) { b.addEventListener("click", function () { set(b.getAttribute("data-mode")); }); });
  var saved = null; try { saved = localStorage.getItem("pw_costmode"); } catch (e) {}
  set(saved || "as");
})();
</script>"""
    return layout("Fantomon ability trees", "Every page of every Sword x Staff Fantomon ability tree: drawn layout, materials to fill "
                  "each page with merges counted, power, and stats granted.", body, "pettrees", 0)
