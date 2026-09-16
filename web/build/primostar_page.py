"""Primostar planner: the season Progression score and what it costs in Material Realm swings.

Score (destiny_score_Bless_RuleDesc, the game's rule card): for each season level of a category you get that
season's rate from astrological_season_config (BlessPlayerLevelScoreRate, BlessEquipLevelScoreRate,
BlessTreasureLevelScoreRate, BlessSkillLevelScoreRate, BlessPetLevelScoreRate); Primostars at season end =
floor(total score / SourceStarRateMatrial) + BaseBlessAwardCount. Grades D..SSS: destiny_score_award (Type Bless).

Season levels are levels past the promotion cap (system_level_limit base columns), buyable only at the top
sub-rank of the season's promotion family and gated by the character's own season level (the rows of
system_level_limit for that sub-rank: SkillBlessLevel, EquipBlessLevel, TreasureBlessLevel, PetBlessLevel).
Costs: skill_slot_upgrade_bless (Battle Essence, per slot; 4 active + 4 passive slots = game_settings.SkillTypes),
equip_upgrade_bless (Raw Ore, Refined Ore, Rolla, per piece; 5 pieces), treasure_bless (Chrono Sand grades + Rolla,
per relic; TreasureMaxSlotCount 4), pet_upgrade_bless (cumulative Fantomon XP), level_bless (cumulative XP, score).
Normal ladders to reach the cap first: equip_upgrade_material, skill_slot_upgrade_material,
treasure_levelup_material, level_exp (player column 1, Fantomon column 2).

Swings: one tool per swing (quick_buy: 5 tools per purchase, price tiers per day), yields per swing from the
mop-up tables at each promotion (see realms_page.py). Sand grades merge 5 -> 1 (item_merge).
"""
from __future__ import annotations
import html, re, collections, math, json


def _num(s, d=0):
    try:
        return int(str(s).strip())
    except Exception:
        try:
            return float(str(s).strip())
        except Exception:
            return d


def _items(s):
    return {int(a): int(c) for a, c in re.findall(r"(\d+)\s*:\s*(\d+)", s or "")}


def _list(s):
    return [int(x) for x in re.findall(r"-?\d+", s or "")]


JS = r"""
(function () {
  var D = PRIMO, $ = function (id) { return document.getElementById(id); };
  var fmt = function (v, d) { return Number(v).toLocaleString("en-US", { maximumFractionDigits: d == null ? 0 : d }); };
  var val = function (id) { var el = $(id); return el ? (Number(el.value) || 0) : 0; };
  var MAT = { ore: D.names.ore, refined: D.names.refined, rolla: D.names.rolla, essence: D.names.essence, sand: D.names.sand + " (plain-sand equivalent)", petxp: "Fantomon XP", xp: "Character XP" };
  var REALMS = [["ironvein", "Ironvein Pit", D.names.toolOre], ["gilded", "Gilded Depths", D.names.toolRolla], ["dread", "Dread Hollow", D.names.toolEssence], ["dustfall", "Dustfall Dune", D.names.toolSand]];
  var PIECES = D.pieces;                     /* [key, name] x 5 */

  function season() { return D.seasons[$("p_season").value]; }
  function fam() { return season().family; }
  function tier() { return $("p_tier").value; }
  function ladder(sys) { return (D.ladders[fam()] || {})[sys] || []; }
  function gateFor(sl) {
    var g = season().gates, out = { skill: 0, equip: 0, relic: 0, pet: 0 };
    for (var i = 0; i < g.length; i++) if (sl >= g[i][0]) out = g[i][1];
    return out;
  }
  function yields() { var y = D.yields[fam()]; return y[tier()] || y[season().top]; }
  function swingsFor(cost) {
    var y = yields(), sw = { ironvein: 0, gilded: 0, dread: 0, dustfall: 0 };
    if (cost.ore) sw.ironvein += cost.ore / y.ore;
    if (cost.refined) sw.ironvein += cost.refined / y.refined;
    if (cost.rolla) sw.gilded += cost.rolla / y.rolla;
    if (cost.essence) sw.dread += cost.essence / y.essence;
    if (cost.sand) sw.dustfall += cost.sand / y.sand;
    return sw;
  }
  function total(sw) { return sw.ironvein + sw.gilded + sw.dread + sw.dustfall; }
  function addCost(a, b, mult) { mult = mult == null ? 1 : mult; for (var k in b) a[k] = (a[k] || 0) + b[k] * mult; return a; }
  function ignoreRefined() { return $("p_norefined").checked; }
  function levelCost(sys, k) {
    var c = ladder(sys)[k - 1]; if (!c) return null;
    var out = {}; for (var key in c) out[key] = c[key];
    if (ignoreRefined()) delete out.refined;
    return out;
  }
  function normalCost(sys, from, to) {
    var lad = D.normal[sys] || {}, out = {};
    for (var l = from + 1; l <= to; l++) { var c = lad[l]; if (c) addCost(out, c); }
    if (ignoreRefined()) delete out.refined;
    return out;
  }
  function tierCaps() { return season().capsBy[tier()] || season().caps; }
  function prefill() {
    var c = tierCaps();
    PIECES.forEach(function (p) { $("lvl_equip_" + p[0]).value = c.equip; });
    $("lvl_skill").value = c.skill; $("lvl_relic").value = c.relic; $("lvl_pet").value = c.pet;
    $("p_prefill").textContent = "Normal levels pre-filled with the " + (season().tiers.filter(function (t) { return t[0] === tier(); })[0] || [0, tier()])[1] + " caps: gear " + c.equip + ", skills " + c.skill + ", relics " + c.relic + ", Fantomon " + c.pet + ". Edit them if you are below the cap.";
  }
  function fillTiers() {
    var s = season(), sel = $("p_tier"), cur = sel.value; sel.innerHTML = "";
    s.tiers.forEach(function (t) { var o = document.createElement("option"); o.value = t[0]; o.textContent = t[1] + " (x" + t[2] + ")"; sel.appendChild(o); });
    sel.value = s.tiers.some(function (t) { return t[0] === cur; }) ? cur : s.top;
    $("p_caps").textContent = "Season " + s.n + " (" + s.name + "): season levels open at " + s.topName + ". Caps there: character " + s.caps.player + ", gear " + s.caps.equip + ", skills " + s.caps.skill + ", relics " + s.caps.relic + ", Fantomon " + s.caps.pet + ". Points per season level: character " + s.rates.player + ", gear " + s.rates.equip + ", skills " + s.rates.skill + ", Fantomon " + s.rates.pet + ", relics " + s.rates.relic + ". Primostars = score / " + s.divisor + " (rounded down) + " + s.fixed + ".";
    ["equip", "skill", "relic", "pet", "player"].forEach(function (sys) { var el = $("cap_" + sys); if (el) el.textContent = s.caps[sys]; });
  }
  function grade(score) {
    var g = season().grades, out = g[0][1];
    for (var i = 0; i < g.length; i++) if (score >= g[i][0]) out = g[i][1];
    return out;
  }
  function pactLevels(stars) { var n = 0; while (n < D.pact.length && D.pact[n] <= stars) n++; return n; }
  function dawniumFor(buys) {
    var left = buys, d = 0;
    for (var i = 0; i < D.tools.tiers.length && left > 0; i++) { var n = Math.min(left, D.tools.tiers[i][1]); d += n * D.tools.tiers[i][0]; left -= n; }
    return d;
  }
  function buysOf(r) { return Math.max(0, Math.min(D.tools.max, val("buy_" + r))); }
  function toolsTable(sw) {
    var trs = "", worst = 0, worstName = "", dawDay = 0, totalDaw = 0, totalSw = 0, buysTotal = 0;
    REALMS.forEach(function (r) {
      var n = sw[r[0]], b = buysOf(r[0]), tools = b * D.tools.pack, daw = dawniumFor(b); buysTotal += b;
      if (!n) { if (b) dawDay += 0; return; }
      totalSw += n;
      var days = tools ? Math.ceil(n / tools) : Infinity; if (days > worst) { worst = days; worstName = r[1]; }
      dawDay += daw; totalDaw += (isFinite(days) ? days : 0) * daw;
      trs += "<tr><th>" + r[1] + "</th><td class=num>" + fmt(Math.ceil(n)) + " " + r[2] + "</td><td class=num>" + b + " &times; " + D.tools.pack + " = " + tools + "</td><td class=num>" + (isFinite(days) ? fmt(days) + " days" : "never (0 bought)") + "</td><td class=num>" + fmt(daw) + "</td><td class=num>" + (isFinite(days) ? fmt(days * daw) : "&mdash;") + "</td></tr>";
    });
    $("out_tools").innerHTML = trs || "<tr><td colspan=6>No realm materials needed.</td></tr>";
    if (!trs) { $("out_days").innerHTML = ""; return; }
    /* a balanced split: the same number of purchases a day, shared in proportion to the swings each realm needs */
    var need = REALMS.map(function (r) { return sw[r[0]] || 0; }), tot = need.reduce(function (a, b) { return a + b; }, 0);
    var split = need.map(function (n) { return n > 0 ? Math.max(1, Math.round(buysTotal * n / tot)) : 0; });
    var over = split.reduce(function (a, b) { return a + b; }, 0) - buysTotal;
    while (over > 0) { var i = split.indexOf(Math.max.apply(null, split)); if (split[i] > 1) { split[i]--; over--; } else break; }
    while (over < 0) { var j = -1, best = -1; need.forEach(function (n, k) { if (n > 0) { var d = n / ((split[k] + 1) * D.tools.pack); var cur = n / (split[k] * D.tools.pack); if (cur - d > best) { best = cur - d; j = k; } } }); if (j < 0) break; split[j]++; over++; }
    var bDays = 0, bDaw = 0; need.forEach(function (n, k) { if (n > 0) { var d = Math.ceil(n / (split[k] * D.tools.pack)); if (d > bDays) bDays = d; bDaw += dawniumFor(split[k]); } });
    var same = REALMS.every(function (r, k) { return split[k] === buysOf(r[0]); });
    $("out_days").innerHTML = "With your split you finish in <b>" + fmt(worst) + " days</b> (" + worstName + " is the slowest) at " + fmt(dawDay) + " " + D.names.dawnium + " a day, about " + fmt(totalDaw) + " in all." +
      (same ? " That split is already balanced." : " Same " + buysTotal + " purchases a day, balanced to finish together: " + REALMS.map(function (r, k) { return split[k] + " " + r[2]; }).join(", ") + " &rarr; <b>" + fmt(bDays) + " days</b> at " + fmt(bDaw) + " " + D.names.dawnium + " a day. <button type=\"button\" class=\"pickbtn\" id=\"p_usesplit\">Use this split</button>");
    var btn = $("p_usesplit"); if (btn) btn.addEventListener("click", function () { REALMS.forEach(function (r, k) { $("buy_" + r[0]).value = split[k]; }); compute(); showPlan(); });
  }
  /* the units the planner walks: 5 gear pieces, skills x slots, relics x count */
  function unitsList() {
    var list = PIECES.map(function (p) { return { sys: "equip", key: p[0], name: p[1], mult: 1, cur: val("cur_equip_" + p[0]), lvl: $("lvl_equip_" + p[0]).value, tgtId: "tgt_equip_" + p[0] }; });
    list.push({ sys: "skill", key: "skill", name: "Skills", mult: val("n_skill"), cur: val("cur_skill"), lvl: $("lvl_skill").value, tgtId: "tgt_skill" });
    list.push({ sys: "relic", key: "relic", name: "Relics", mult: val("n_relic"), cur: val("cur_relic"), lvl: $("lvl_relic").value, tgtId: "tgt_relic" });
    return list;
  }
  function compute() {
    var s = season(), tl = val("tgt_player"), gate = gateFor(tl), notes = [], pts = 0, cost = {}, rows = "";
    unitsList().forEach(function (u) {
      var tgt = val(u.tgtId), lad = ladder(u.sys), max = Math.min(gate[u.sys], lad.length);
      if (tgt > max) { notes.push(u.name + ": target " + tgt + " cut to " + max + " (gate at character season level " + tl + ": " + gate[u.sys] + "; ladder " + lad.length + ")"); tgt = max; }
      if (tgt < u.cur) tgt = u.cur;
      var c = {};
      for (var k = u.cur + 1; k <= tgt; k++) { var lc = levelCost(u.sys, k); if (lc) addCost(c, lc, u.mult); }
      var nlv = Number(u.lvl);
      if (u.lvl !== "" && !isNaN(nlv) && nlv < s.caps[u.sys]) addCost(c, normalCost(u.sys, nlv, s.caps[u.sys]), u.mult);
      var p = (tgt - u.cur) * s.rates[u.sys] * u.mult; pts += p; addCost(cost, c);
      var sw = swingsFor(c), mats = Object.keys(c).filter(function (k) { return c[k] > 0; }).map(function (k) { return fmt(c[k]) + " " + MAT[k]; }).join(", ");
      rows += "<tr><th>" + u.name + "</th><td class=num>" + u.cur + " &rarr; " + tgt + (u.mult > 1 ? " &times; " + u.mult : "") + "</td><td class=num>" + fmt(p) + "</td><td>" + (mats || "&mdash;") + "</td><td class=num>" + (total(sw) ? fmt(total(sw)) : "&mdash;") + "</td></tr>";
    });
    /* Fantomon and character: XP, not swings */
    var pc = val("cur_pet"), pt = Math.min(val("tgt_pet"), Math.min(gate.pet, ladder("pet").length)), pn = val("n_pet");
    if (val("tgt_pet") > pt) notes.push("Fantomon: target cut to " + pt + " by the gate or ladder");
    if (pt < pc) pt = pc;
    var pl = ladder("pet"), pxp = ((pl[pt - 1] || 0) - (pc > 0 ? (pl[pc - 1] || 0) : 0)) * pn, pp = (pt - pc) * s.rates.pet * pn; pts += pp;
    rows += "<tr><th>Fantomon</th><td class=num>" + pc + " &rarr; " + pt + (pn > 1 ? " &times; " + pn : "") + "</td><td class=num>" + fmt(pp) + "</td><td>" + (pxp ? fmt(pxp) + " Fantomon XP" : "&mdash;") + "</td><td class=num>&mdash;</td></tr>";
    var cc = val("cur_player"), sc = D.playerScore[fam()] || [], cl = ladder("player");
    if (tl < cc) tl = cc;
    var cp = (sc[tl - 1] || 0) - (cc > 0 ? (sc[cc - 1] || 0) : 0), cxp = (cl[tl - 1] || 0) - (cc > 0 ? (cl[cc - 1] || 0) : 0); pts += cp;
    rows += "<tr><th>Character</th><td class=num>" + cc + " &rarr; " + tl + "</td><td class=num>" + fmt(cp) + "</td><td>" + (cxp ? fmt(cxp) + " Character XP" : "&mdash;") + "</td><td class=num>&mdash;</td></tr>";
    var stars = Math.floor(pts / s.divisor) + s.fixed;
    $("out_rows").innerHTML = rows;
    $("out_sum").innerHTML = "<b>" + fmt(pts) + " points</b> &rarr; Progression grade <b>" + grade(pts) + "</b> &rarr; <b>" + fmt(stars) + " " + D.names.star + "</b> (" + fmt(pts) + " / " + s.divisor + " + " + s.fixed + "), enough for Astral Pact level " + pactLevels(stars) + " of " + D.pact.length + " from zero.";
    toolsTable(swingsFor(cost));
    $("out_notes").innerHTML = notes.length ? "<li>" + notes.join("</li><li>") + "</li>" : "";
    bestNext(gate);
  }
  function bestNext(gate) {
    var s = season(), list = [];
    unitsList().forEach(function (u) {
      var lad = ladder(u.sys);
      for (var k = u.cur + 1; k <= Math.min(u.cur + 40, lad.length); k++) {
        var c = levelCost(u.sys, k); if (!c) break;
        var sw = total(swingsFor(c));
        list.push({ name: u.name, k: k, pts: s.rates[u.sys], sw: sw, ppw: s.rates[u.sys] / sw, open: k <= gate[u.sys] });
      }
    });
    list.sort(function (a, b) { return b.ppw - a.ppw; });
    var h = "";
    list.slice(0, 12).forEach(function (x) {
      h += "<tr" + (x.open ? "" : " class=dim") + "><th>" + x.name + " +" + x.k + "</th><td class=num>" + x.pts + "</td><td class=num>" + fmt(x.sw, 1) + "</td><td class=num>" + x.ppw.toFixed(2) + "</td><td>" + (x.open ? "open" : "needs a higher character season level") + "</td></tr>";
    });
    $("out_best").innerHTML = h;
  }
  /* greedy plan: from the current season levels, buy the level with the most points per swing until the goal */
  function plan() {
    var s = season(), tl = val("tgt_player"), gate = gateFor(tl);
    var goal = val("p_goal"), need = $("p_goalkind").value === "stars" ? Math.max(0, (goal - s.fixed) * s.divisor) : goal;
    var units = unitsList().map(function (u) { u.bought = 0; return u; });
    /* points already in hand or promised by the Fantomon and character fields */
    var have = 0;
    units.forEach(function (u) { have += u.cur * s.rates[u.sys] * u.mult; });
    var pc = val("cur_pet"), pt = Math.max(pc, Math.min(val("tgt_pet"), gate.pet)), cc = val("cur_player"), sc = D.playerScore[fam()] || [];
    have += pt * s.rates.pet * val("n_pet") + (sc[Math.max(tl, cc) - 1] || 0);
    var cost = {}, guard = 0;
    while (have < need && guard++ < 20000) {
      var best = null;
      units.forEach(function (u) {
        var k = u.cur + u.bought + 1; if (k > gate[u.sys] || u.mult <= 0) return;
        var c = levelCost(u.sys, k); if (!c) return;
        var sw = total(swingsFor(c)) * u.mult, ppw = s.rates[u.sys] * u.mult / sw;
        if (!best || ppw > best.ppw) best = { u: u, c: c, ppw: ppw };
      });
      if (!best) break;
      best.u.bought++; have += s.rates[best.u.sys] * best.u.mult; addCost(cost, best.c, best.u.mult);
    }
    return { units: units, have: have, need: need, cost: cost, reached: have >= need };
  }
  function showPlan() {
    var s = season(), p = plan(), sw = swingsFor(p.cost);
    if (p.need <= 0) { $("out_goal").innerHTML = "Enter a goal above."; return; }
    var parts = p.units.filter(function (u) { return u.bought > 0; }).map(function (u) { return u.name + " to +" + (u.cur + u.bought) + (u.mult > 1 ? " on " + u.mult : ""); });
    $("out_goal").innerHTML = (p.reached ? "Reachable: " : "Not reachable at the target character season level (the gates cap it): ") + (parts.join(", ") || "nothing to buy") +
      " &rarr; " + fmt(p.have) + " points (" + fmt(Math.floor(p.have / s.divisor) + s.fixed) + " " + D.names.star + ") for about " + fmt(total(sw)) + " swings: " +
      REALMS.filter(function (r) { return sw[r[0]] > 0; }).map(function (r) { return fmt(Math.ceil(sw[r[0]])) + " in " + r[1]; }).join(", ") + ". Press Recommend to write these targets into the fields above.";
  }
  function recommend() {
    var p = plan();
    p.units.forEach(function (u) { $(u.tgtId).value = u.cur + u.bought; });
    compute(); showPlan();
    $("out_sum").scrollIntoView({ behavior: "smooth", block: "center" });
  }
  function init() {
    fillTiers(); prefill();
    $("p_season").addEventListener("change", function () { fillTiers(); prefill(); compute(); showPlan(); });
    $("p_tier").addEventListener("change", function () { prefill(); compute(); showPlan(); });
    document.querySelectorAll("#primo input, #primo select").forEach(function (el) {
      if (el.id === "p_season" || el.id === "p_tier") return;
      el.addEventListener("input", function () { compute(); showPlan(); }); el.addEventListener("change", function () { compute(); showPlan(); });
    });
    $("p_reco").addEventListener("click", recommend);
    compute(); showPlan();
  }
  init();
})();
"""


def render(layout, base_tables):
    import build as _b
    L = _b.L
    ladder, *_ = base_tables()
    esc = html.escape

    def loc(key, fallback=""):
        v = L(key)
        return (v or fallback).strip()

    def rows_of(name):
        r = _b.csvrows(name); h = [c.strip() for c in r[0]]
        return h, [x for x in r[2:] if x and x[0].strip() and not x[0].startswith("#")]

    def item_name(i):
        return loc(f"item_{i}_name", f"item {i}")

    n = lambda v: f"{int(v):,}"

    # ---- promotions
    h, ps = rows_of("player_subrank")
    order = [r[0].strip() for r in ps]
    ordinal = {name: i + 1 for i, name in enumerate(order)}
    disp = {}
    for name in order:
        site = next((Ld["rank"] for Ld in ladder if Ld["internal"] == name), None)
        disp[name] = loc(f"SubRank.{name}") or site or name

    def family(internal):
        base = internal.split("_")[0]
        return base if base.startswith(("Godtouched", "Demigod", "Truegod", "Lordgod")) else base.rstrip("123")

    fam_subs = collections.defaultdict(list)
    for s in order:
        fam_subs[family(s)].append(s)

    # ---- level_number and reward rules (for yields)
    h, ln = rows_of("level_number")
    numbers = {}
    for r in ln:
        for ci, c in enumerate(h[1:], 1):
            if ci < len(r) and r[ci].strip():
                try:
                    numbers[(int(c), int(r[0]))] = float(r[ci])
                except Exception:
                    pass
    h, rr = rows_of("reward_rule"); ri = {c: i for i, c in enumerate(h)}
    rules = collections.defaultdict(list)
    for r in rr:
        ids = _list(r[ri["IdList"]]); cnt = [float(x) for x in re.findall(r"[\d.]+", r[ri["CountList"]])]
        wts = _list(r[ri["WeightList"]]); sub = _list(r[ri["SubRankCountId"]])
        for j, i in enumerate(ids):
            rules[_num(r[0])].append((i, cnt[j] if j < len(cnt) else 0, wts[j] if j < len(wts) else 1, sub[j] if j < len(sub) else 0))

    def pay(rids, s):
        out = collections.Counter()
        for rid in rids:
            for i, c, w, sid in rules[rid]:
                out[i] += int(c * (numbers.get((sid, ordinal[s]), 1) if sid else 1))
        return out

    h, md = rows_of("mop_up_dungeon"); mi = {c: i for i, c in enumerate(h)}
    h, mm = rows_of("mop_up_material"); oi = {c: i for i, c in enumerate(h)}
    obj = {_num(r[0]): (_list(r[oi["AttackRewardIds"]]), _list(r[oi["BreakRewardIds"]]), _num(r[oi["Durability"]])) for r in mm}
    tools = {r[mi["Type"]].strip(): list(_items(r[mi["CostDict"]]).keys())[0] for r in md}
    ED = 11.0                                    # expected durability per swing (10 attack, +-10%, 20% crit x1.5)
    SAND = {41400: 1, 41401: 5, 41402: 25}

    def yield_at(s):
        out = {}
        for r in md:
            t = r[mi["Type"]].strip(); gen = _num(r[mi["GenerateMaterialRuleId"]])
            pool = [(i, w) for i, c, w, _ in rules[gen]]; tot = sum(w for _, w in pool)
            exp = collections.Counter(); esw = 0.0
            for iid, w in pool:
                a, brk, dur = obj[iid]; w = w / tot
                for i, c in pay(a, s).items():
                    exp[i] += w * c * dur
                for i, c in pay(brk, s).items():
                    exp[i] += w * c
                esw += w * (dur / ED if dur > 0 else 0)
            per = {i: v / esw for i, v in exp.items()}
            if t == "RoughRefineStone":
                out["ore"] = per.get(41300, 0); out["refined"] = per.get(41301, 0)
            elif t == "SilverCoin":
                out["rolla"] = per.get(1, 0); out["dawnium"] = per.get(2, 0)
            elif t == "SkillSeniorMaterial":
                out["essence"] = per.get(42200, 0)
            elif t == "SandsOfTime":
                out["sand"] = sum(v * SAND.get(i, 0) for i, v in per.items())
        return {k: round(v, 2) for k, v in out.items()}

    # ---- seasons, caps and gates
    h, sc = rows_of("astrological_season_config"); si = {c: i for i, c in enumerate(h)}
    h, da = rows_of("destiny_score_award")
    grades = collections.defaultdict(list)
    for r in da:
        if r[0].strip() == "Bless":
            grades[_num(r[1])].append((_num(r[3]), r[5].strip() or f"grade {r[2]}"))
    h, sl = rows_of("system_level_limit"); li = {c: i for i, c in enumerate(h)}
    base_caps, gates = {}, collections.defaultdict(list)
    for r in sl:
        s = r[0].strip()
        if not r[li["PlayerLevel"]].strip():
            continue
        bc = base_caps.setdefault(s, {"player": 0, "skill": 0, "equip": 0, "pet": 0, "relic": 0})
        for key, col in (("player", "PlayerLevel"), ("skill", "SkillLevel"), ("equip", "EquipLevel"), ("pet", "PetLevel"), ("relic", "TreasureLevel")):
            bc[key] = max(bc[key], _num(r[li[col]]))
        g = (_num(r[li["PlayerBlessLevel"]]), {"skill": _num(r[li["SkillBlessLevel"]]), "equip": _num(r[li["EquipBlessLevel"]]), "relic": _num(r[li["TreasureBlessLevel"]]), "pet": _num(r[li["PetBlessLevel"]])})
        if not gates[s] or gates[s][-1][1] != g[1]:
            gates[s].append(g)

    seasons, yields = [], {}
    for r in sc:
        sn = _num(r[si["Season"]]); famn = r[si["Rank"]].strip()
        subs = fam_subs.get(famn, []); top = subs[-1] if subs else None
        tiers = [(s, disp[s], f"{numbers.get((6, ordinal[s]), 1):g}") for s in subs if numbers.get((6, ordinal[s])) is not None]
        yields[famn] = {s: yield_at(s) for s, _d, _f in tiers}
        seasons.append({
            "n": sn, "family": famn, "name": loc(f"astrological_season_{sn}_name", f"Season {sn}"),
            "rates": {"player": _num(r[si["BlessPlayerLevelScoreRate"]]), "equip": _num(r[si["BlessEquipLevelScoreRate"]]), "relic": _num(r[si["BlessTreasureLevelScoreRate"]]),
                      "skill": _num(r[si["BlessSkillLevelScoreRate"]]), "pet": _num(r[si["BlessPetLevelScoreRate"]])},
            "divisor": _num(r[si["SourceStarRateMatrial"]]) or 1, "fixed": _num(r[si["BaseBlessAwardCount"]]),
            "grades": sorted(grades.get(sn, [(0, "D")])), "top": top, "topName": disp.get(top, top),
            "caps": base_caps.get(top, {"player": 0, "skill": 0, "equip": 0, "pet": 0, "relic": 0}),
            "capsBy": {s: base_caps.get(s, {}) for s, _d, _f in tiers},
            "gates": [[g[0], g[1]] for g in gates.get(top, [])], "tiers": tiers,
        })

    # ---- ladders per family
    ladders = collections.defaultdict(lambda: {"skill": [], "equip": [], "relic": [], "pet": [], "player": []})
    player_score = collections.defaultdict(list)
    for r in rows_of("skill_slot_upgrade_bless")[1]:
        ladders[r[0].strip()]["skill"].append({"essence": _items(r[2]).get(42200, 0)})
    for r in rows_of("equip_upgrade_bless")[1]:
        c = _items(r[3]); ladders[r[0].strip()]["equip"].append({"ore": c.get(41300, 0), "refined": c.get(41301, 0), "rolla": c.get(1, 0)})
    for r in rows_of("treasure_bless")[1]:
        c = _items(r[2]); ladders[r[0].strip()]["relic"].append({"sand": sum(v * SAND.get(i, 0) for i, v in c.items()), "rolla": c.get(1, 0)})
    for r in rows_of("pet_upgrade_bless")[1]:
        ladders[r[0].strip()]["pet"].append(_num(r[2]))
    for r in rows_of("level_bless")[1]:
        ladders[r[0].strip()]["player"].append(_num(r[2])); player_score[r[0].strip()].append(_num(r[3]))
    normal = {"equip": {}, "skill": {}, "relic": {}}
    for r in rows_of("equip_upgrade_material")[1]:
        c = _items(r[2]); normal["equip"][_num(r[0])] = {"ore": c.get(41300, 0), "refined": c.get(41301, 0), "rolla": c.get(1, 0)}
    for r in rows_of("skill_slot_upgrade_material")[1]:
        normal["skill"][_num(r[0])] = {"essence": _items(r[1]).get(42200, 0)}
    for r in rows_of("treasure_levelup_material")[1]:
        c = _items(r[1]); normal["relic"][_num(r[0])] = {"sand": sum(v * SAND.get(i, 0) for i, v in c.items()), "rolla": c.get(1, 0)}

    # ---- tools, pact, gear pieces
    h, qb = rows_of("quick_buy"); qi = {c: i for i, c in enumerate(h)}
    q = next(r for r in qb if r[0].strip() == "100")
    prices = _list(q[qi["PriceList"]]); counts = _list(q[qi["PriceBuyCount"]])
    tool_cfg = {"pack": _num(q[qi["BaseCount"]]), "tiers": list(zip(prices, counts)), "max": sum(counts), "currency": item_name(_num(q[qi["CurrencyId"]]))}
    pact_cum, acc = [], 0
    for r in rows_of("astrological_level")[1]:
        acc += _num(r[1]); pact_cum.append(acc)
    poses = re.findall(r'"(\w+)"', rows_of("equip_upgrade_bless")[1][0][2])
    pieces = [(p, loc(f"EquipPos.{p}", p)) for p in poses]

    data = {"seasons": seasons, "ladders": ladders, "playerScore": player_score, "normal": normal, "yields": yields, "tools": tool_cfg, "pact": pact_cum, "pieces": pieces,
            "names": {"star": item_name(61), "ore": item_name(41300), "refined": item_name(41301), "rolla": item_name(1), "essence": item_name(42200),
                      "sand": item_name(41400), "dawnium": item_name(2), "toolOre": item_name(tools["RoughRefineStone"]), "toolRolla": item_name(tools["SilverCoin"]),
                      "toolEssence": item_name(tools["SkillSeniorMaterial"]), "toolSand": item_name(tools["SandsOfTime"])}}

    # ---- static reference tables
    rate_rows = "".join(f"<tr><th>Season {s['n']} &middot; {esc(s['name'])}</th><td>{esc(s['topName'])}</td><td class=num>{s['rates']['player']}</td><td class=num>{s['rates']['equip']}</td>"
                        f"<td class=num>{s['rates']['skill']}</td><td class=num>{s['rates']['pet']}</td><td class=num>{s['rates']['relic']}</td><td class=num>{s['divisor']}</td><td class=num>{s['fixed']}</td>"
                        f"<td>{', '.join(f'{g[1]} {n(g[0])}' for g in s['grades'][1:])}</td></tr>" for s in seasons)
    gate_rows = ""
    for s in seasons:
        if not s["gates"]:
            continue
        gate_rows += f"<tr><th rowspan={len(s['gates'])}>Season {s['n']}</th>" + "".join(
            ("<tr>" if i else "") + f"<td class=num>{g[0]}</td><td class=num>{g[1]['equip']}</td><td class=num>{g[1]['skill']}</td><td class=num>{g[1]['relic']}</td><td class=num>{g[1]['pet']}</td></tr>"
            for i, g in enumerate(s["gates"]))
    tier_rows = ""
    for s in seasons:
        for t in s["tiers"]:
            y = yields[s["family"]][t[0]]
            tier_rows += f"<tr><th>{esc(t[1])}</th><td class=num>{t[2]}&times;</td><td class=num>{n(y['ore'])}</td><td class=num>{y['refined']:.0f}</td><td class=num>{n(y['rolla'])}</td><td class=num>{n(y['essence'])}</td><td class=num>{n(y['sand'])}</td></tr>"
    tool_txt = ", then ".join(f"{c} at {p}" for p, c in tool_cfg["tiers"])
    s2 = next((s for s in seasons if s["n"] == 2), seasons[0])
    tier_opts = "".join(f'<option value="{t[0]}"{" selected" if t[0] == s2["top"] else ""}>{esc(t[1])} (&times;{t[2]})</option>' for t in s2["tiers"])
    season_opts = "".join(f'<option value="{i}"{" selected" if s["n"] == 2 else ""}>Season {s["n"]} &middot; {esc(s["name"])} ({esc(s["topName"])})</option>' for i, s in enumerate(seasons))

    def lab(text, inp):
        return f"<label>{text} {inp}</label>"

    def num(id_, v, ph=""):
        return f'<input type="number" id="{id_}" value="{v}" min="0"{f" placeholder=\"{ph}\"" if ph else ""}>'

    gear_rows = "".join(f'<tr><th>{esc(name)}</th><td>{num(f"lvl_equip_{key}", "")}</td><td>{num(f"cur_equip_{key}", 0)}</td><td>{num(f"tgt_equip_{key}", 20)}</td></tr>' for key, name in pieces)

    body = f"""
<div class="wrap">
<p class="eyebrow">Season planner</p>
<h1>{esc(item_name(61))} planner</h1>
<p class="lede">Set the season, where you stand and where you want to be; the planner returns the Progression score,
the grade, the {esc(item_name(61))}s at season end, and the Material Realm swings, tools, days and {esc(item_name(2))} it takes &mdash;
gear piece by piece, skills, relics, Fantomon and character levels all counted with the game's own rates. Give it a goal and
press <b>Recommend</b> to have it pick the cheapest levels for you.</p>

<p class="calcnote">The rule card: <i>"For each Season Character Level gained, you receive {{1}} pts. For each Total Season Gear
Enhancement Level gained, {{2}} pts. For each Total Season Skill Level gained, {{3}} pts. For each Total Season Fantomon Level
gained, {{4}} pts. For each Total Season Relic Level gained, {{5}} pts. The conversion rate of {esc(item_name(61))} is your total season
progression score divided by {{6}}, rounded down. In addition to this conversion, you'll also receive a fixed amount."</i>
Season levels are the levels past your promotion's cap; they are sold only at the top tier of the season's promotion and
each ladder opens further as your own season level rises (the gate table below).</p>

<section class="calc" id="primo">
  <div class="conv">
    <label>Season <select id="p_season">{season_opts}</select></label>
    <label>Your promotion <select id="p_tier">{tier_opts}</select></label>
    <label>{esc(item_name(tools["RoughRefineStone"]))} buys/day <input type="number" id="buy_ironvein" value="4" min="0" max="{tool_cfg['max']}"></label>
    <label>{esc(item_name(tools["SilverCoin"]))} buys/day <input type="number" id="buy_gilded" value="2" min="0" max="{tool_cfg['max']}"></label>
    <label>{esc(item_name(tools["SkillSeniorMaterial"]))} buys/day <input type="number" id="buy_dread" value="2" min="0" max="{tool_cfg['max']}"></label>
    <label>{esc(item_name(tools["SandsOfTime"]))} buys/day <input type="number" id="buy_dustfall" value="4" min="0" max="{tool_cfg['max']}"></label>
    <label><input type="checkbox" id="p_norefined" checked> ignore {esc(item_name(41301))} costs (untick if you have to mine it)</label>
    <div class="out" id="p_caps"></div>
    <div class="out hint" id="p_prefill"></div>
  </div>

  <h3>Goal</h3>
  <div class="conv"><label>I want <input type="number" id="p_goal" value="200" min="0"></label><label>&nbsp;<select id="p_goalkind"><option value="stars">{esc(item_name(61))}</option><option value="score">points</option></select></label>
  <label>&nbsp;<button type="button" id="p_reco" class="pickbtn">Recommend for me</button></label>
  <div class="out" id="out_goal"></div></div>
  <p class="calcnote">Recommend starts from your current season levels and buys gear, skill and relic levels in order of points per
  swing until the goal is met, within the gates of your target character season level, then writes those targets into the fields
  below. Fantomon and character levels come from your own fields, since they are XP, not realm materials.</p>

  <h3>Where you are and where you want to be</h3>
  <div class="pgrid">
    <div class="pfield"><b>Character</b> <span class=hint>cap <span id="cap_player"></span></span>
      {lab("Season level now", num("cur_player", 0))}{lab("Target season level", num("tgt_player", 10))}</div>
    <div class="pfield"><b>Skills</b> <span class=hint>cap <span id="cap_skill"></span>, per slot</span>
      {lab("Current normal level", num("lvl_skill", ""))}{lab("Season levels now", num("cur_skill", 0))}{lab("Target season level", num("tgt_skill", 30))}{lab("Slots", num("n_skill", 8))}</div>
    <div class="pfield"><b>Relics</b> <span class=hint>cap <span id="cap_relic"></span>, per relic</span>
      {lab("Current normal level", num("lvl_relic", ""))}{lab("Season levels now", num("cur_relic", 0))}{lab("Target season level", num("tgt_relic", 3))}{lab("Relics", num("n_relic", 4))}</div>
    <div class="pfield"><b>Fantomon</b> <span class=hint>cap <span id="cap_pet"></span>, per Fantomon</span>
      {lab("Current normal level", num("lvl_pet", ""))}{lab("Season levels now", num("cur_pet", 0))}{lab("Target season level", num("tgt_pet", 30))}{lab("Fantomon levelled", num("n_pet", 1))}</div>
  </div>
  <div class="pfield" style="margin:0 0 14px"><b>Gear</b> <span class=hint>cap <span id="cap_equip"></span>, each piece on its own ladder</span>
    <div class="tablewrap" style="margin:6px 0 0"><table class="xp small"><thead><tr><th>Piece</th><th>Current normal level</th><th>Season levels now</th><th>Target season level</th></tr></thead><tbody>{gear_rows}</tbody></table></div></div>

  <p class="verdict" id="out_sum"></p>
  <div class="tablewrap"><table class="xp small"><thead><tr><th>Category</th><th class=num>Season levels</th><th class=num>Points</th><th>Materials</th><th class=num>Swings</th></tr></thead><tbody id="out_rows"></tbody></table></div>
  <ul class="calcnote" id="out_notes"></ul>
  <h3>Tools and days</h3>
  <div class="tablewrap"><table class="xp small"><thead><tr><th>Realm</th><th class=num>Tools needed</th><th class=num>Buys &times; pack a day</th><th class=num>Days</th><th class=num>{esc(item_name(2))} a day</th><th class=num>{esc(item_name(2))} in all</th></tr></thead><tbody id="out_tools"></tbody></table></div>
  <p class="verdict" id="out_days"></p>
  <p class="calcnote">Shop: {tool_cfg['pack']} tools per purchase; purchases per day cost {tool_txt} {esc(tool_cfg['currency'])}, {tool_cfg['max']} purchases a day at most
  (<code>quick_buy</code>). Swings are averages over the swing roll and the node odds; Refined Ore comes flat from the Refined Ore Mine and is the slow part of gear.</p>
  <h3>Best next levels</h3>
  <p>Points per swing of the next levels open to you, best first. Greyed rows wait for a higher character season level.</p>
  <div class="tablewrap"><table class="xp small"><thead><tr><th>Level</th><th class=num>Points</th><th class=num>Swings</th><th class=num>Points per swing</th><th>Gate</th></tr></thead><tbody id="out_best"></tbody></table></div>
</section>

<h2>Reference</h2>
<h3>Rates and conversion by season</h3>
<div class="tablewrap"><table class="xp small"><thead><tr><th>Season</th><th>Season levels at</th><th class=num>Character</th><th class=num>Gear</th><th class=num>Skill</th><th class=num>Fantomon</th><th class=num>Relic</th><th class=num>Score per {esc(item_name(61))}</th><th class=num>Fixed</th><th>Progression grades</th></tr></thead><tbody>{rate_rows}</tbody></table></div>
<h3>Gates: how many season levels each character season level opens</h3>
<div class="tablewrap"><table class="xp small"><thead><tr><th>Season</th><th class=num>Character season level</th><th class=num>Gear</th><th class=num>Skills</th><th class=num>Relics</th><th class=num>Fantomon</th></tr></thead><tbody>{gate_rows}</tbody></table></div>
<h3>Realm yield per swing by promotion</h3>
<div class="tablewrap"><table class="xp small"><thead><tr><th>Promotion</th><th class=num>Factor</th><th class=num>{esc(item_name(41300))}</th><th class=num>{esc(item_name(41301))}</th><th class=num>{esc(item_name(1))}</th><th class=num>{esc(item_name(42200))}</th><th class=num>{esc(item_name(41400))} equiv.</th></tr></thead><tbody>{tier_rows}</tbody></table></div>
<details class="statbox"><summary>Where this comes from</summary>
<p class="calcnote">Rates, divisor and fixed amount: <code>astrological_season_config</code>; grades: <code>destiny_score_award</code> (Bless);
caps and gates: <code>system_level_limit</code>; ladders: <code>equip_upgrade_bless</code> (one ladder, every piece), <code>skill_slot_upgrade_bless</code>
(4 active + 4 passive slots, <code>game_settings.SkillTypes</code>), <code>treasure_bless</code> (<code>TreasureMaxSlotCount</code> 4),
<code>pet_upgrade_bless</code> and <code>level_bless</code> (cumulative XP); normal ladders <code>equip_upgrade_material</code>,
<code>skill_slot_upgrade_material</code>, <code>treasure_levelup_material</code>; gear slot names <code>EquipPos.*</code>; sand grades <code>item_merge</code>;
yields from the mop-up tables as on the Realms page; shop <code>quick_buy</code>; Astral Pact <code>astrological_level</code>. Fantomon and character
XP are shown as XP, since they do not come from the realms. Season 6 has no season ladders in this client build.</p></details>
</div>
<script>var PRIMO = {json.dumps(data)};</script>
<script>{JS}</script>
"""
    return layout(f"{item_name(61)} planner",
                  f"Season Progression score, grade and {item_name(61)}s for any season, with the Material Realm swings, tools and days each target costs, and a recommender for the cheapest mix.",
                  body, "primostars", 0)
