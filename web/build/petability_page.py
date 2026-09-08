"""Fantomon ability trees — every page of every tree drawn from pet_ability_graph, with the
materials to fill it and the stats it grants.

CalculatePetAbilityProps: for each node at level N the game takes the whole row
level_prop_pet_ability[PropId][N] and adds it, each prop scaled by
(1 + pet_ability_prop_scale_factor[PropScaleFactorId][prop]). Costs are pet_ability_prop
CostItemList per node level. Trees 1/2/3 are DPS/Tank/Support; 4/5/6 and 7/8/9 repeat
them for later generations with scale factor 2 (+10%) and 3 (+20%).
"""
from __future__ import annotations
import html, re, collections


def _num(s, d=0):
    try:
        return int(str(s).strip())
    except Exception:
        return d


SHORT = {"MaxHp": "HP", "Attack": "ATK", "Defence": "DEF", "Speed": "SPD", "CritRatePercent": "Crit",
         "BlockPercent": "Block", "CritAvoidPercent": "Crit RES", "BlockAvoidPercent": "Acc",
         "DmgAddPercent": "DMG+", "DmgReducePercent": "RES", "CureAddPercent": "Heal+"}
PCT = {"CritRatePercent", "BlockPercent", "CritAvoidPercent", "BlockAvoidPercent", "DmgAddPercent", "DmgReducePercent",
       "CureAddPercent", "SystemAttackPercent", "SystemDefencePercent", "SystemMaxHpPercent", "SystemSpeedPercent",
       "BaseMaxHpPercent", "BaseAttackPercent", "BaseDefencePercent", "BaseSpeedPercent", "MaxHpPercent", "AttackPercent",
       "DefencePercent", "SpeedPercent"}


def render(layout, base_tables):
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

    def prop_name(k):
        base = k.replace("System", "")
        return loc(f"PropType.{k}", "") or loc(f"PropType.{base}", "") or k

    def fmt_prop(k, v):
        lab = SHORT.get(k) or prop_name(k)
        if k in PCT:
            return f"+{v / 100:g}% {lab}"
        return f"+{v:,} {lab}"

    # ---- tables
    h, pets = rows_of("pet"); pi = {c: i for i, c in enumerate(h)}
    h, ab = rows_of("pet_ability"); ai = {c: i for i, c in enumerate(h)}
    h, ap = rows_of("pet_ability_prop"); api = {c: i for i, c in enumerate(h)}
    h, gr = rows_of("pet_ability_graph")
    h, lpa = rows_of("level_prop_pet_ability"); lh = h
    h, sf = rows_of("pet_ability_prop_scale_factor")
    curve = collections.defaultdict(dict)
    for r in lpa:
        curve[r[0].strip()][_num(r[1])] = {lh[i]: _num(r[i]) for i in range(2, len(lh)) if _num(r[i])}
    scale = {r[0].strip(): {h[i]: _num(r[i]) for i in range(1, len(h))} for r in sf}

    nodes = collections.defaultdict(dict)          # tree -> node -> row
    for r in ab:
        nodes[r[0].strip()][r[ai["NodeId"]].strip()] = r
    levels = collections.defaultdict(list)         # (tree, node) -> rows by level
    for r in ap:
        levels[(r[0].strip(), r[api["NodeId"]].strip())].append(r)
    for k in levels:
        levels[k].sort(key=lambda r: _num(r[api["NodeLevel"]]))
    graph = collections.defaultdict(dict)          # (tree, page) -> row -> [ids]
    for r in gr:
        graph[(r[0].strip(), r[1].strip())][_num(r[2])] = [_num(x) for x in re.findall(r"-?\d+", r[3])]

    pets_by_tree = collections.defaultdict(list)
    ptype = {}
    for p in pets:
        name = loc(f"item_{p[0].strip()}_name", "")
        if not name or name.startswith("DNT"):
            continue
        pets_by_tree[p[pi["AbilityId"]].strip()].append(name)
        ptype[p[pi["AbilityId"]].strip()] = loc(f"PetType.{p[pi['Type']].strip()}", p[pi["Type"]].strip())

    def scaled(row, sid):
        s = scale.get(sid, {})
        return {k: int(v * (1 + s.get(k, 0) / 10000.0)) for k, v in row.items()}

    def node_total(tree, nid, lv=10):
        lvrows = levels.get((tree, nid), [])
        r = next((x for x in lvrows if _num(x[api["NodeLevel"]]) == lv), None)
        if not r:
            return {}, "1"
        return scaled(curve.get(r[api["PropId"]].strip(), {}).get(lv, {}), r[api["PropScaleFactorId"]].strip()), r[api["PropScaleFactorId"]].strip()

    # ---- one page of one tree
    def page_block(tree, pg, compact=False):
        ids = [n for n, r in nodes[tree].items() if r[ai["PageCode"]].strip() == pg]
        if not ids:
            return "", None
        # gate
        gate = ""
        for n in ids:
            r = nodes[tree][n]
            if r[ai["UnlockConditionType"]].strip() == "SubRank":
                m = re.search(r"SubRank\W+(\w+)", r[ai["UnlockConditionParam"]])
                if m:
                    gate = disp.get(m.group(1), m.group(1))
        # costs per node level (uniform within a page) and page totals
        per_level = []
        totals = collections.Counter()
        for n in ids:
            for lv in levels.get((tree, n), []):
                pairs = [(i, _num(c)) for i, c in re.findall(r"(\d+),(\d+)", lv[api["CostItemList"]])]
                for i, c in pairs:
                    totals[i] += c
                if n == ids[0]:
                    per_level.append((_num(lv[api["NodeLevel"]]), pairs))
        # stats at a full page, and per node type
        page_sum = collections.Counter()
        by_type = collections.OrderedDict()
        for n in ids:
            show = re.search(r"Prop:'(\w+)'", nodes[tree][n][ai["NodeShowParams"]])
            show = show.group(1) if show else "?"
            tot, sid = node_total(tree, n)
            for k, v in tot.items():
                page_sum[k] += v
            if show not in by_type:
                per_lv = []
                for lv in range(1, 11):
                    t, _ = node_total(tree, n, lv)
                    per_lv.append(t)
                by_type[show] = (n, per_lv)
        # the grid
        rows_ = graph.get((tree, pg), {})
        width = max((len(v) for v in rows_.values()), default=7)
        cells = ""
        for rn in sorted(rows_, reverse=True):
            for x in rows_[rn]:
                if x <= 0:
                    cells += "<i></i>"
                    continue
                r = nodes[tree].get(str(x))
                show = re.search(r"Prop:'(\w+)'", r[ai["NodeShowParams"]]).group(1) if r else "?"
                tot, _ = node_total(tree, str(x))
                title = f"node {x}: at Lv 10 " + ", ".join(fmt_prop(k, v) for k, v in tot.items())
                gated = r and r[ai["UnlockConditionType"]].strip() == "SubRank"
                cells += (f'<b class="nd st-{show.lower()}{" gate" if gated else ""}" title="{html.escape(title)}">'
                          f'{html.escape(SHORT.get(show, show))}</b>')
        grid = f'<div class="abtree" style="grid-template-columns:repeat({width},1fr)">{cells}</div>'
        cost_row = "".join(
            f"<tr><td class='num'>Lv {lv}</td><td>{', '.join(html.escape(loc('item_' + i + '_name', i)) + ' &times;' + str(c) for i, c in pairs)}</td></tr>"
            for lv, pairs in per_level)
        total_txt = ", ".join(f"<b>{html.escape(loc('item_' + i + '_name', i))}</b> &times;{c:,}" for i, c in totals.most_common())
        sum_txt = ", ".join(fmt_prop(k, v) for k, v in sorted(page_sum.items(), key=lambda kv: -kv[1]))
        type_rows = ""
        for show, (n, per_lv) in by_type.items():
            cells_ = "".join(f"<td>{', '.join(fmt_prop(k, v) for k, v in t.items()) or '&mdash;'}</td>" for t in per_lv)
            type_rows += f"<tr><th>{html.escape(prop_name(show))} node</th>{cells_}</tr>"
        if compact:
            return (f"<li><b>Page {pg}</b>" + (f" (opens at {html.escape(gate)})" if gate else "") + f": {sum_txt}</li>"), totals
        block = (f'<details class="page"><summary><b>Page {pg}</b> &middot; {len(ids)} nodes'
                 + (f" &middot; opens at {html.escape(gate)}" if gate else "")
                 + f" &middot; to fill: {total_txt}</summary>"
                 f"<div class='pagebody'>{grid}"
                 f"<p><b>Full page grants</b> {sum_txt}.</p>"
                 f"<div class='twocol'><div class='tablewrap'><table><thead><tr><th class='num'>Level</th><th>Cost per node</th></tr></thead><tbody>{cost_row}</tbody></table>"
                 f"<caption>Every node on this page costs the same per level.</caption></div>"
                 f"<div class='tablewrap'><table class='nodecurve'><thead><tr><th>Node</th>" + "".join(f"<th>Lv {i}</th>" for i in range(1, 11)) +
                 f"</tr></thead><tbody>{type_rows}</tbody></table><caption>What one node of each kind is worth at each level (its whole row, not just its headline stat).</caption></div></div></div></details>")
        return block, totals

    # ---- trees, grouped by type then generation
    gens = {"1": ("1", 1), "2": ("2", 1), "3": ("3", 1), "4": ("1", 2), "5": ("2", 2), "6": ("3", 2), "7": ("1", 3), "8": ("2", 3), "9": ("3", 3)}
    sections = []
    for base in ("1", "2", "3"):
        typ = ptype.get(base, "")
        for tree, (b, gen) in gens.items():
            if b != base or tree not in nodes:
                continue
            names = ", ".join(pets_by_tree.get(tree, [])) or "no released Fantomon yet"
            sid = levels.get((tree, "1"), [[None] * 6])[0]
            sid = sid[api["PropScaleFactorId"]].strip() if sid and sid[0] else "1"
            bonus = scale.get(sid, {}).get("Attack", 0)
            grand = collections.Counter()
            blocks = []
            compact = gen > 1
            for pg in sorted({r[ai["PageCode"]].strip() for r in nodes[tree].values()}, key=int):
                blk, tot = page_block(tree, pg, compact)
                blocks.append(blk)
                if tot:
                    grand.update(tot)
            grand_txt = ", ".join(f"<b>{html.escape(loc('item_' + i + '_name', i))}</b> &times;{c:,}" for i, c in grand.most_common())
            intro = (f'Every node here is worth <b>{bonus // 100}% more</b> than the <a href="#tree-{base}">first-generation {html.escape(typ)} tree</a>; '
                     f'the layout, gates and costs are identical, so only what each full page grants is listed. ' if bonus else '')
            body_ = ("<ul class='plain'>" + "".join(blocks) + "</ul>") if compact else "".join(blocks)
            sections.append(
                f'<h2 id="tree-{tree}">{html.escape(typ)} tree, generation {gen} <span class="hint">{html.escape(names)}</span></h2>'
                f"<p>{intro}All ten pages filled: {grand_txt}.</p>" + body_)

    types_txt = ", ".join(f"{html.escape(ptype.get(t, t))} ({html.escape(', '.join(pets_by_tree.get(t, [])))})" for t in ("1", "2", "3"))
    body = f"""
<div class="wrap">
<p class="eyebrow">Reference</p>
<h1>Fantomon ability trees</h1>
<p class="lede">Every page of every Fantomon's ability tree, drawn the way the game lays it out, with what it costs to fill
the page and what a full page grants. There are three trees, one per Fantomon role, and each later generation of
Fantomon gets the same tree with a bonus on every node.</p>

<h2>How it works</h2>
<p>A tree has ten pages; page one has 19 nodes and the rest 34, and each node has ten levels. A node at level N grants
its <i>whole</i> row for that level (<code>CalculatePetAbilityProps</code> adds the full <code>level_prop_pet_ability</code>
row), so an ATK node also carries small HP, DEF and SPD amounts and, from level 5, a percent bonus. The headline stat
is what the node shows. Costs come from <code>pet_ability_prop</code> and are the same for every node on a page; each
role pays in its own material family. Pages open in order, and some need a promotion: page 2 at Expert I, page 4 at
Champion I, page 6 at Master I, page 8 at Paragon I, page 9 at Saint I. Second-generation Fantomon get +10% on every
node's stats and third-generation +20%, from <code>pet_ability_prop_scale_factor</code>.</p>
<p>Roles and who uses each tree: {types_txt}.</p>

{"".join(sections)}
</div>
"""
    return layout("Fantomon ability trees", "Every page of every Sword x Staff Fantomon ability tree: layout, materials to fill "
                  "each page, and the stats a full page grants.", body, "pettrees", 0)
