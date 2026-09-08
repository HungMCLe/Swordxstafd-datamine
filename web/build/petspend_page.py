"""Fantomon ability trees — where the material goes: rate of return per page and slot,
diminishing returns, strategy curves, the optimal order, and an optimiser.

Power = sum(stat x prop_cfg.Score) (CalcCombatRatingByProps); percent nodes multiply the
Fantomon's own stat first (HandleSystemPercentProps); the Fantomon's whole prop set is then
scaled by its slot (ConvertPropsByPetSlot: PetFormationPropChangeFactor [1, .5, .5, .5], idle
PetIdlePropChangeFactor 0.2). Costs in the family's base material via item_merge (4 -> 1).
"""
from __future__ import annotations
import html, re, json, collections


def _num(s, d=0):
    try:
        return int(str(s).strip())
    except Exception:
        return d


SCORE = {"Attack": 2.5, "MaxHp": 0.5, "Defence": 2.5, "Speed": 3.125}
SYS = {"SystemAttackPercent": "Attack", "SystemDefencePercent": "Defence", "SystemMaxHpPercent": "MaxHp", "SystemSpeedPercent": "Speed"}
LEVELS = (100, 150, 200)
ROLE_TREE = {"DPS": "7", "Tank": "8", "Support": "9"}     # the Mythic trees
COL = {"main": "#a3603f", "side": "#3d6ea8", "idle": "#8a8fa6", "focus": "#a3603f", "spread": "#3d6ea8", "even": "#4e8a5c", "flat": "#9a938a"}


def render(layout, charts):
    import build as _b
    L = _b.L

    def loc(key, fallback=""):
        v = L(key)
        return (v or fallback).strip()

    def rows_of(name):
        r = _b.csvrows(name); h = [c.strip() for c in r[0]]
        return h, [x for x in r[2:] if x and x[0].strip() and not x[0].startswith("#")]

    # ---- settings: slot factors
    gs = open(_b.OUT / "config_decrypted" / "game_settings", encoding="utf-8", errors="ignore").read()
    seg = gs[gs.find('"PetSetting"'):][:4000]
    m = re.search(r'PetFormationPropChangeFactor"?\s*:\s*\[([^\]]*)\]', seg)
    slots = [float(x) for x in re.findall(r"[\d.]+", m.group(1))] if m else [1.0, 0.5, 0.5, 0.5]
    m = re.search(r'PetIdlePropChangeFactor"?\s*:\s*([\d.]+)', seg)
    idle_f = float(m.group(1)) if m else 0.2

    # ---- tables
    h, ab = rows_of("pet_ability"); ai = {c: i for i, c in enumerate(h)}
    h, ap = rows_of("pet_ability_prop"); api = {c: i for i, c in enumerate(h)}
    h, lpa = rows_of("level_prop_pet_ability"); lh = h
    h, sf = rows_of("pet_ability_prop_scale_factor"); scale = {r[0].strip(): {h[i]: _num(r[i]) for i in range(1, len(h))} for r in sf}
    h, pc = rows_of("prop_cfg"); pci = {c: i for i, c in enumerate(h)}
    for r in pc:
        k = r[0].strip()
        if k in SCORE and r[pci["Score"]].strip():
            SCORE[k] = float(r[pci["Score"]])
    h, mg = rows_of("item_merge"); mi = {c: i for i, c in enumerate(h)}
    merge = {r[0].strip(): (r[mi["Material1"]].strip(), _num(r[mi["Count1"]])) for r in mg if r[mi["Material1"]].strip()}
    h, lpp = rows_of("level_prop_pet"); lpi = {c: i for i, c in enumerate(h)}
    petcurve = {_num(r[1]): {k: _num(r[lpi[k]]) for k in ("MaxHp", "Attack", "Defence", "Speed")} for r in lpp if r[0].strip() == "5080"}
    curve = collections.defaultdict(dict)
    for r in lpa:
        curve[r[0].strip()][_num(r[1])] = {lh[i]: _num(r[i]) for i in range(2, len(lh)) if _num(r[i])}
    lv10 = {}
    for r in ap:
        if r[api["NodeLevel"]].strip() == "10":
            lv10[(r[0].strip(), r[api["NodeId"]].strip())] = r
    costs_by = collections.defaultdict(collections.Counter)
    for r in ap:
        for i, c in re.findall(r"(\d+),(\d+)", r[api["CostItemList"]]):
            costs_by[(r[0].strip(), r[api["NodeId"]].strip())][i] += _num(c)

    def base_eq(cost):
        tot = 0
        for i, n in cost.items():
            k, mult = i, 1
            while k in merge:
                k2, c = merge[k]; mult *= c; k = k2
            tot += n * mult
        return tot

    def base_of(tree):
        for (t, n), c in costs_by.items():
            if t == tree:
                k = next(iter(c))
                while k in merge:
                    k = merge[k][0]
                return k

    # ---- per role: pages with cost, stats, power by level
    roles = {}
    for role, tree in ROLE_TREE.items():
        nodes = {r[ai["NodeId"]].strip(): r for r in ab if r[0].strip() == tree}
        pages = []
        for pg in range(1, 11):
            ids = [n for n, r in nodes.items() if r[ai["PageCode"]].strip() == str(pg)]
            cost = collections.Counter()
            tot = collections.Counter()
            for n in ids:
                cost.update(costs_by[(tree, n)])
                r = lv10.get((tree, n))
                if not r:
                    continue
                row = curve[r[api["PropId"]].strip()][10]; s = scale.get(r[api["PropScaleFactorId"]].strip(), {})
                for k, v in row.items():
                    tot[k] += int(v * (1 + s.get(k, 0) / 10000.0))
            flat = sum(v * SCORE[k] for k, v in tot.items() if k in SCORE)
            plv = {L_: flat + sum((v / 10000.0) * petcurve[L_][SYS[k]] * SCORE[SYS[k]] for k, v in tot.items() if k in SYS) for L_ in LEVELS}
            pages.append({"pg": pg, "cost": base_eq(cost), "flat": flat, "p": plv, "stats": dict(tot), "n": len(ids)})
        roles[role] = {"tree": tree, "base": base_of(tree), "pages": pages}

    # ---- simulations (DPS tree, level 150) for the charts
    def simulate(pages, budget, level, idle_n, strategy):
        pets = [("main", slots[0])] + [(f"side{k}", slots[k + 1]) for k in range(min(3, len(slots) - 1))] + [(f"idle{k}", idle_f) for k in range(idle_n)]
        state = collections.defaultdict(int); spent = 0; gained = 0.0
        pw = lambda pg: pages[pg]["flat"] if level == "flat" else pages[pg]["p"][level]
        def buy(who, f):
            nonlocal spent, gained
            pg = state[who]
            if pg >= 10 or spent + pages[pg]["cost"] > budget:
                return False
            state[who] = pg + 1; spent += pages[pg]["cost"]; gained += f * pw(pg)
            return True
        if strategy == "spread":
            for who, f in pets:
                buy(who, f)
        if strategy == "even":
            progress = True
            while progress:
                progress = False
                for who, f in pets:
                    if buy(who, f):
                        progress = True
            return gained, spent, dict(state)
        while True:
            best = None
            for who, f in pets:
                pg = state[who]
                if pg >= 10 or spent + pages[pg]["cost"] > budget:
                    continue
                eff = f * pw(pg) / pages[pg]["cost"]
                if best is None or eff > best[0]:
                    best = (eff, who, f)
            if not best:
                break
            buy(best[1], best[2])
        return gained, spent, dict(state)

    dps = roles["DPS"]["pages"]
    LV = 150
    # rate of return per page and slot
    rr_rows = "".join(
        f"<tr><td class='num'>{p['pg']}</td><td class='num'>{p['cost']:,}</td><td class='num'>{sum(q['cost'] for q in dps[:p['pg']]):,}</td>"
        f"<td class='num'>{p['flat']:,.0f}</td><td class='num'>{p['p'][LV]:,.0f}</td>"
        f"<td class='num'><b>{100 * slots[0] * p['p'][LV] / p['cost']:,.0f}</b></td><td class='num'>{100 * slots[1] * p['p'][LV] / p['cost']:,.0f}</td><td class='num'>{100 * idle_f * p['p'][LV] / p['cost']:,.0f}</td>"
        f"<td class='num'>{100 * p['stats'].get('Attack', 0) / p['cost']:,.1f}</td><td class='num'>{100 * p['stats'].get('Defence', 0) / p['cost']:,.1f}</td>"
        f"<td class='num'>{100 * p['stats'].get('MaxHp', 0) / p['cost']:,.1f}</td><td class='num'>{100 * p['stats'].get('Speed', 0) / p['cost']:,.1f}</td></tr>"
        for p in dps)
    bar = charts.bar_chart(
        [{"label": f"Page {p['pg']}", "value": round(100 * p["p"][LV] / p["cost"]), "colour": COL["main"] if p["pg"] == 1 else COL["side"]} for p in dps],
        fmt=lambda v: f"{v:,.0f}", caption=f"Power per 100 base material by page, main slot, Fantomon level {LV}. Page 1 is the only cheap page.")
    cum_c, cum_p, cum_f = [0], [0], [0]
    for p in dps:
        cum_c.append(cum_c[-1] + p["cost"]); cum_p.append(cum_p[-1] + p["p"][LV]); cum_f.append(cum_f[-1] + p["flat"])
    dim = charts.line_chart(
        [{"name": f"one Fantomon, main slot, level {LV}", "colour": COL["main"], "points": list(zip(cum_c, cum_p))},
         {"name": "flat stats only (level-independent)", "colour": COL["flat"], "dash": True, "points": list(zip(cum_c, cum_f))}],
        xlabel="base material spent on one Fantomon", ylabel="power gained",
        xfmt=lambda v: f"{v / 1000:.0f}K", yfmt=lambda v: f"{v / 1000:.0f}K",
        marks=[{"x": cum_c[1], "label": "page 1"}, {"x": cum_c[3], "label": "page 3"}, {"x": cum_c[6], "label": "page 6"}],
        caption="Diminishing returns on one Fantomon: the curve is steepest across page 1 and nearly straight after page 6.")
    budgets = list(range(0, 62001, 1000))
    series = []
    for key, name in (("focus", "focus the formation (best page anywhere, by return)"), ("spread", "page 1 on everyone first, then by return"), ("even", "spread evenly, page by page across all")):
        pts = [(b, simulate(dps, b, LV, 12, key)[0]) for b in budgets]
        series.append({"name": name, "colour": COL[key], "points": pts, "dash": key == "even"})
    strat = charts.line_chart(series, xlabel="base material available", ylabel="power gained",
                              xfmt=lambda v: f"{v / 1000:.0f}K", yfmt=lambda v: f"{v / 1000:.0f}K",
                              caption=f"Three ways to spend the same material: 1 main, 3 sides, 12 idle Fantomon, level {LV}, DPS tree. "
                                      "Focusing wins at every budget until everything is filled.")
    # the ladder
    ladder = []
    state = collections.defaultdict(int); spent = 0
    pets = [("main", slots[0])] + [(f"side {k + 1}", slots[k + 1]) for k in range(3)] + [(f"idle {k + 1}", idle_f) for k in range(12)]
    for _ in range(24):
        best = None
        for who, f in pets:
            pg = state[who]
            if pg >= 10:
                continue
            eff = f * dps[pg]["p"][LV] / dps[pg]["cost"]
            if best is None or eff > best[0]:
                best = (eff, who, pg, f)
        eff, who, pg, f = best
        state[who] = pg + 1; spent += dps[pg]["cost"]
        ladder.append((who, pg + 1, dps[pg]["cost"], spent, eff * 100, f * dps[pg]["p"][LV]))
    ladder_rows = "".join(
        f"<tr><td class='num'>{i + 1}</td><td>{html.escape(who)}</td><td class='num'>{pg}</td><td class='num'>{c:,}</td><td class='num'>{s:,}</td><td class='num'>{g:,.0f}</td><td class='num'>{e:,.0f}</td></tr>"
        for i, (who, pg, c, s, e, g) in enumerate(ladder))
    # budget comparison table
    cmp_rows = ""
    for b in (dps[0]["cost"] * 16, 20000, sum(p["cost"] for p in dps), 100000):
        a = simulate(dps, b, LV, 12, "focus")[0]; s2 = simulate(dps, b, LV, 12, "spread")[0]; e = simulate(dps, b, LV, 12, "even")[0]
        cmp_rows += f"<tr><td class='num'>{b:,}</td><td class='num'><b>{a:,.0f}</b></td><td class='num'>{s2:,.0f} <span class='hint'>({100 * (s2 / a - 1):+.0f}%)</span></td><td class='num'>{e:,.0f} <span class='hint'>({100 * (e / a - 1):+.0f}%)</span></td></tr>"

    data = {"slots": slots, "idle": idle_f, "levels": list(LEVELS), "merge": {k: v for k, v in merge.items()},
            "roles": {role: {"base": d["base"], "baseName": loc(f"item_{d['base']}_name", d["base"]),
                             "tiers": [], "cost": [p["cost"] for p in d["pages"]], "flat": [p["flat"] for p in d["pages"]],
                             "p": {str(L_): [p["p"][L_] for p in d["pages"]] for L_ in LEVELS}} for role, d in roles.items()}}
    for role, d in roles.items():
        k = d["base"]; tiers = [k]
        up = {m: prod for prod, (m, c) in merge.items()}
        while k in up:
            k = up[k]; tiers.append(k)
        data["roles"][role]["tiers"] = [{"id": t, "name": loc(f"item_{t}_name", t)} for t in tiers[:3]]
    cfg = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")

    role_opts = "".join(f'<option value="{r}">{r}</option>' for r in ROLE_TREE)
    body = f"""
<div class="wrap">
<p class="eyebrow">Reference</p>
<h1>Where the material goes</h1>
<p class="lede">A statistical look at the Fantomon ability trees: what each page returns per material, how fast the
returns fall, what focusing on the formation buys against spreading, the exact order that maximises power per
material, and a calculator for your own stock. Numbers are the Mythic DPS tree at Fantomon level {LV} unless a
control says otherwise; the other roles and qualities scale every figure by a constant and keep the same order.</p>

<h2>The model</h2>
<p>Power is the game's combat rating: each stat times its weight from <code>prop_cfg</code> (ATK {SCORE['Attack']:g}, DEF
{SCORE['Defence']:g}, SPD {SCORE['Speed']:g}, HP {SCORE['MaxHp']:g}). A percent node multiplies the Fantomon's own stat
before scoring, so its worth grows with the Fantomon's level. The Fantomon's whole stat set is then scaled by where it
sits: the main slot counts {slots[0]:g}, each side slot {slots[1]:g}, and every idle Fantomon {idle_f:g} (from
<code>game_settings</code>). Material is counted in the family's base unit, four of a tier making one of the next.
Crit, accuracy and damage nodes score against your own base stats and are excluded; they sit on every page alike and
do not change any ranking below.</p>

<h2>Rate of return by page</h2>
<div class="tablewrap"><table class="xp"><thead><tr><th class="num">Page</th><th class="num">Cost</th><th class="num">Cumulative</th>
<th class="num">Power, flat</th><th class="num">Power, Lv {LV}</th><th class="num">per 100 · main</th><th class="num">side</th><th class="num">idle</th>
<th class="num">ATK /100</th><th class="num">DEF /100</th><th class="num">HP /100</th><th class="num">SPD /100</th></tr></thead>
<tbody>{rr_rows}</tbody></table>
<caption>Cost in base material. "per 100" is power gained per 100 base material spent on that page, by slot. The last four
columns are flat stat per 100 material, before the slot factor.</caption></div>
{bar}

<h2>Diminishing returns</h2>
{dim}

<h2>Focus or spread</h2>
{strat}
<div class="tablewrap"><table><thead><tr><th class="num">Budget</th><th class="num">Focus</th><th class="num">Page 1 on everyone first</th><th class="num">Even spread</th></tr></thead>
<tbody>{cmp_rows}</tbody></table><caption>Power gained at fixed budgets, 1 main + 3 sides + 12 idle, level {LV}. Percentages against focusing.</caption></div>

<h2>The order that maximises power per material</h2>
<p>Greedy by return: at every step, buy the page anywhere that returns the most power per material. Because pages
must be filled in order and slots differ, this is the sequence:</p>
<div class="tablewrap"><table class="xp"><thead><tr><th class="num">#</th><th>Fantomon</th><th class="num">Page</th><th class="num">Cost</th><th class="num">Spent so far</th><th class="num">Power gained</th><th class="num">per 100</th></tr></thead>
<tbody>{ladder_rows}</tbody></table></div>

<h2>Your material</h2>
<section class="calc" id="petcalc">
  <div class="calc-grid">
    <div class="calc-side">
      <label>Role <select id="pc_role">{role_opts}</select></label>
      <label>Fantomon level <select id="pc_level">{"".join(f'<option value="{l}"{" selected" if l == LV else ""}>{l}</option>' for l in LEVELS)}<option value="flat">flat stats only</option></select></label>
      <label>Idle Fantomon of this role <input type="number" id="pc_idle" value="4" min="0" max="12" class="short"></label>
    </div>
    <div class="calc-side" id="pc_mats"></div>
  </div>
  <p class="verdict" id="pc_verdict"></p>
  <div class="tablewrap"><table><thead><tr><th>Fantomon</th><th class="num">Pages</th><th class="num">Material</th><th class="num">Power</th></tr></thead><tbody id="pc_rows"></tbody></table></div>
  <p class="note" id="pc_note"></p>
</section>
</div>
<script>var PET_SPEND = {cfg};</script>
<script>
(function () {{
  var C = PET_SPEND, $ = function (id) {{ return document.getElementById(id); }};
  function fmt(v) {{ return Math.round(v).toLocaleString("en-US"); }}
  function matsUI() {{
    var role = C.roles[$("pc_role").value], h = "";
    role.tiers.forEach(function (t, i) {{
      h += '<label>' + t.name + ' <input type="number" class="short" id="pc_t' + i + '" value="' + (i === 0 ? 2000 : i === 1 ? 300 : 20) + '" min="0"></label>';
    }});
    $("pc_mats").innerHTML = h;
    for (var i = 0; i < role.tiers.length; i++) $("pc_t" + i).addEventListener("input", compute);
  }}
  function budgetOf() {{
    var role = C.roles[$("pc_role").value], b = 0, mult = 1;
    role.tiers.forEach(function (t, i) {{ b += (Number(($("pc_t" + i) || {{}}).value) || 0) * mult; mult *= 4; }});
    return b;
  }}
  function powerArr(role, level) {{ return level === "flat" ? role.flat : role.p[level]; }}
  function sim(role, budget, level, idleN, strategy) {{
    var pets = [["main", C.slots[0]], ["side 1", C.slots[1]], ["side 2", C.slots[2]], ["side 3", C.slots[3]]];
    for (var i = 0; i < idleN; i++) pets.push(["idle " + (i + 1), C.idle]);
    var pw = powerArr(role, level), st = {{}}, spent = 0, gained = 0, mat = {{}}, pow = {{}};
    pets.forEach(function (p) {{ st[p[0]] = 0; mat[p[0]] = 0; pow[p[0]] = 0; }});
    function buy(p) {{
      var pg = st[p[0]]; if (pg >= 10 || spent + role.cost[pg] > budget) return false;
      st[p[0]] = pg + 1; spent += role.cost[pg]; mat[p[0]] += role.cost[pg]; gained += p[1] * pw[pg]; pow[p[0]] += p[1] * pw[pg]; return true;
    }}
    if (strategy === "spread") pets.forEach(buy);
    if (strategy === "even") {{ var prog = true; while (prog) {{ prog = false; pets.forEach(function (p) {{ if (buy(p)) prog = true; }}); }} return {{ gained: gained, spent: spent, st: st, mat: mat, pow: pow, pets: pets }}; }}
    while (true) {{
      var best = null;
      pets.forEach(function (p) {{ var pg = st[p[0]]; if (pg >= 10 || spent + role.cost[pg] > budget) return; var e = p[1] * pw[pg] / role.cost[pg]; if (!best || e > best[0]) best = [e, p]; }});
      if (!best) break; buy(best[1]);
    }}
    return {{ gained: gained, spent: spent, st: st, mat: mat, pow: pow, pets: pets }};
  }}
  function compute() {{
    var role = C.roles[$("pc_role").value], level = $("pc_level").value, idleN = Math.max(0, Math.min(12, parseInt($("pc_idle").value, 10) || 0));
    var b = budgetOf(), r = sim(role, b, level, idleN, "focus"), s = sim(role, b, level, idleN, "spread"), e = sim(role, b, level, idleN, "even");
    var rows = "";
    r.pets.forEach(function (p) {{ if (!r.st[p[0]]) return; rows += "<tr><td>" + p[0] + " <span class=hint>x" + p[1] + "</span></td><td class=num>" + r.st[p[0]] + "</td><td class=num>" + fmt(r.mat[p[0]]) + "</td><td class=num>" + fmt(r.pow[p[0]]) + "</td></tr>"; }});
    $("pc_rows").innerHTML = rows || "<tr><td colspan=4>Not enough for page 1 on the main.</td></tr>";
    $("pc_verdict").innerHTML = "With <b>" + fmt(b) + "</b> " + role.baseName + " (merges counted) the best spend gains <b>" + fmt(r.gained) + "</b> power" +
      (level === "flat" ? " from flat stats" : " at Fantomon level " + level) + ", using " + fmt(r.spent) + " and leaving " + fmt(b - r.spent) + ".";
    $("pc_note").innerHTML = "Page 1 on everyone first would gain " + fmt(s.gained) + " (" + (100 * (s.gained / r.gained - 1)).toFixed(0) + "%), an even spread " + fmt(e.gained) + " (" + (100 * (e.gained / r.gained - 1)).toFixed(0) + "%).";
  }}
  $("pc_role").addEventListener("change", function () {{ matsUI(); compute(); }});
  ["pc_level", "pc_idle"].forEach(function (id) {{ $(id).addEventListener("input", compute); $(id).addEventListener("change", compute); }});
  matsUI(); compute();
}})();
</script>
"""
    return layout("Where the material goes", "Rate of return per page and slot of the Sword x Staff Fantomon ability trees, "
                  "diminishing returns, focus against spread, the optimal order and a calculator.", body, "pettrees", 0)

