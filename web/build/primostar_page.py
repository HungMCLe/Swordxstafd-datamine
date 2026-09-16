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
  var PIECES = D.pieces, dirty = {};

  function season() { return D.seasons[$("p_season").value]; }
  function fam() { return season().family; }
  function caps() { return season().caps; }
  function ladder(sys) { return (D.ladders[fam()] || {})[sys] || []; }
  function gateFor(sl) { var g = season().gates, out = { skill: 0, equip: 0, relic: 0, pet: 0 }; for (var i = 0; i < g.length; i++) if (sl >= g[i][0]) out = g[i][1]; return out; }
  function yields() { var y = D.yields[fam()]; return y[$("p_tier").value] || y[season().top]; }
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
  function addCost(a, b, m) { m = m == null ? 1 : m; for (var k in b) a[k] = (a[k] || 0) + b[k] * m; return a; }
  function levelCost(sys, k) { var c = ladder(sys)[k - 1]; if (!c) return null; var o = {}; for (var key in c) o[key] = c[key]; if ($("p_norefined").checked) delete o.refined; return o; }
  function normalCost(sys, from, to) { var lad = D.normal[sys] || {}, o = {}; for (var l = from + 1; l <= to; l++) if (lad[l]) addCost(o, lad[l]); if ($("p_norefined").checked) delete o.refined; return o; }
  function grade(score) { var g = season().grades, out = g[0][1]; for (var i = 0; i < g.length; i++) if (score >= g[i][0]) out = g[i][1]; return out; }
  function stars(score) { var s = season(); return Math.floor(score / s.divisor) + s.fixed; }
  function pactLevels(st) { var n = 0; while (n < D.pact.length && D.pact[n] <= st) n++; return n; }
  function dawniumFor(b) { var left = b, d = 0; for (var i = 0; i < D.tools.tiers.length && left > 0; i++) { var n = Math.min(left, D.tools.tiers[i][1]); d += n * D.tools.tiers[i][0]; left -= n; } return d; }
  function buysOf(r) { return Math.max(0, Math.min(D.tools.max, val("buy_" + r))); }
  function uneven() { return $("p_uneven").checked; }

  /* --- where you are: from the Progression panel (season-level totals), or from per-item shown levels in the fold --- */
  function units() {
    var c = caps(), list = [], g = val("pan_equip"), n = PIECES.length;
    PIECES.forEach(function (p, i) {
      var curS = Math.floor(g / n) + (i < g % n ? 1 : 0), curN = c.equip;
      if (uneven()) { var sh = val("now_equip_" + p[0]); curN = Math.min(sh, c.equip); curS = Math.max(0, sh - c.equip); }
      list.push({ sys: "equip", name: p[1], mult: 1, curS: curS, curN: curN, tgtId: "tgt_equip_" + p[0] });
    });
    [["skill", "Skills", "n_skill", "pan_skill", "now_skill"], ["relic", "Relics", "n_relic", "pan_relic", "now_relic"]].forEach(function (x) {
      var m = Math.max(1, val(x[2])), curS = Math.round(val(x[3]) / m), curN = c[x[0]];
      if (uneven()) { var sh = val(x[4]); curN = Math.min(sh, c[x[0]]); curS = Math.max(0, sh - c[x[0]]); }
      list.push({ sys: x[0], name: x[1], mult: m, curS: curS, curN: curN, tgtId: "tgt_" + x[0] });
    });
    return list;
  }
  function petNow() { var m = Math.max(1, val("n_pet")), c = caps().pet; if (uneven()) { var sh = val("now_pet"); return [Math.min(sh, c), Math.max(0, sh - c), m]; } return [c, Math.round(val("pan_pet") / m), m]; }
  function charNow() { var c = caps().player; if (uneven()) { var sh = val("now_player"); return [Math.min(sh, c), Math.max(0, sh - c)]; } return [c, val("pan_player")]; }
  function nowPoints() {
    var s = season(), p = 0, sc = D.playerScore[fam()] || [];
    units().forEach(function (u) { p += u.curS * s.rates[u.sys] * u.mult; });
    var pn = petNow(); p += pn[1] * s.rates.pet * pn[2];
    var cn = charNow(); p += sc[cn[1] - 1] || 0;
    return p;
  }
  function setDefaultTargets() {          /* targets follow "now" until the user edits them */
    var c = caps();
    units().forEach(function (u) { if (!dirty[u.tgtId]) $(u.tgtId).value = c[u.sys] + u.curS; });
    var pn = petNow(); if (!dirty.tgt_pet) $("tgt_pet").value = c.pet + pn[1];
    var cn = charNow(); if (!dirty.tgt_player) $("tgt_player").value = c.player + cn[1];
  }

  function compute() {
    var s = season(), c = caps(), now = nowPoints();
    $("now_sum").innerHTML = "Now: <b>" + fmt(now) + " points</b>, grade <b>" + grade(now) + "</b>, <b>" + fmt(stars(now)) + " " + D.names.star + "</b> at season end.";
    var tgtChar = Math.max(val("tgt_player"), c.player + charNow()[1]), gate = gateFor(Math.max(0, tgtChar - c.player)), notes = [], gain = 0, cost = {}, rows = "";
    units().forEach(function (u) {
      var tgt = Math.max(val(u.tgtId), c[u.sys] + u.curS), tS = Math.max(0, tgt - c[u.sys]), tN = Math.min(tgt, c[u.sys]), maxS = Math.min(gate[u.sys], ladder(u.sys).length);
      if (tS > maxS) { notes.push(u.name + " " + tgt + " needs season level " + tS + "; at character level " + tgtChar + " the gate allows " + gate[u.sys] + ", so it is cut to " + (c[u.sys] + maxS)); tS = maxS; tgt = c[u.sys] + maxS; }
      var cc = {}; if (tN > u.curN) addCost(cc, normalCost(u.sys, u.curN, tN), u.mult);
      for (var k = u.curS + 1; k <= tS; k++) { var lc = levelCost(u.sys, k); if (lc) addCost(cc, lc, u.mult); }
      var p = (tS - u.curS) * s.rates[u.sys] * u.mult; gain += p; addCost(cost, cc);
      var sw = swingsFor(cc), mats = Object.keys(cc).filter(function (k) { return cc[k] > 0; }).map(function (k) { return fmt(cc[k]) + " " + MAT[k]; }).join(", ");
      rows += "<tr><th>" + u.name + (u.mult > 1 ? " <span class=hint>&times;" + u.mult + "</span>" : "") + "</th><td class=num>" + (c[u.sys] + u.curS) + " &rarr; " + tgt + "</td><td class=num>" + ((tS - u.curS) * u.mult) + "</td><td class=num>" + fmt(p) + "</td><td>" + (mats || "&mdash;") + "</td><td class=num>" + (total(sw) ? fmt(total(sw)) : "&mdash;") + "</td></tr>";
    });
    var pn = petNow(), pl = ladder("pet"), pt = Math.max(val("tgt_pet"), c.pet + pn[1]), ptS = Math.max(0, pt - c.pet), ptN = Math.min(pt, c.pet), pmax = Math.min(gate.pet, pl.length);
    if (ptS > pmax) { notes.push("Fantomon " + pt + " cut to " + (c.pet + pmax) + " by the gate or the ladder"); ptS = pmax; pt = c.pet + pmax; }
    var pxp = ((D.xp.pet[ptN] || 0) - (D.xp.pet[pn[0]] || 0) + (pl[ptS - 1] || 0) - (pn[1] > 0 ? pl[pn[1] - 1] : 0)) * pn[2], pp = (ptS - pn[1]) * s.rates.pet * pn[2]; gain += pp;
    rows += "<tr><th>Fantomon" + (pn[2] > 1 ? " <span class=hint>&times;" + pn[2] + "</span>" : "") + "</th><td class=num>" + (c.pet + pn[1]) + " &rarr; " + pt + "</td><td class=num>" + ((ptS - pn[1]) * pn[2]) + "</td><td class=num>" + fmt(pp) + "</td><td>" + (pxp > 0 ? fmt(pxp) + " Fantomon XP" : "&mdash;") + "</td><td class=num>&mdash;</td></tr>";
    var cn = charNow(), sc = D.playerScore[fam()] || [], cl = ladder("player"), ctS = Math.max(0, tgtChar - c.player), ctN = Math.min(tgtChar, c.player);
    var cp = (sc[ctS - 1] || 0) - (cn[1] > 0 ? sc[cn[1] - 1] || 0 : 0), cxp = (D.xp.player[ctN] || 0) - (D.xp.player[cn[0]] || 0) + (cl[ctS - 1] || 0) - (cn[1] > 0 ? cl[cn[1] - 1] : 0); gain += cp;
    rows += "<tr><th>Character</th><td class=num>" + (c.player + cn[1]) + " &rarr; " + tgtChar + "</td><td class=num>" + (ctS - cn[1]) + "</td><td class=num>" + fmt(cp) + "</td><td>" + (cxp > 0 ? fmt(cxp) + " Character XP" : "&mdash;") + "</td><td class=num>&mdash;</td></tr>";
    var tot = now + gain;
    $("out_rows").innerHTML = rows;
    $("out_sum").innerHTML = "Target: <b>" + fmt(tot) + " points</b> (+" + fmt(gain) + "), grade <b>" + grade(tot) + "</b>, <b>" + fmt(stars(tot)) + " " + D.names.star + "</b> at season end, worth Astral Pact level " + pactLevels(stars(tot)) + " of " + D.pact.length + " from zero.";
    $("out_notes").innerHTML = notes.length ? "<li>" + notes.join("</li><li>") + "</li>" : "";
    toolsTable(swingsFor(cost));
  }
  function toolsTable(sw) {
    var days = val("p_days"), trs = "", worst = 0, worstName = "", dawDay = 0, totalDaw = 0, buysTotal = 0, late = [];
    REALMS.forEach(function (r) {
      var n = Math.max(0, sw[r[0]] - val("bag_" + r[0])), b = buysOf(r[0]), tools = b * D.tools.pack, daw = dawniumFor(b); buysTotal += b;
      if (n <= 0) { if (sw[r[0]] > 0) trs += "<tr><th>" + r[1] + "</th><td class=num>" + fmt(Math.ceil(sw[r[0]])) + " " + r[2] + "</td><td colspan=4>covered by the tools in your bag</td></tr>"; return; }
      var d = tools ? Math.ceil(n / tools) : Infinity; if (d > worst) { worst = d; worstName = r[1]; }
      dawDay += daw; totalDaw += (isFinite(d) ? d : 0) * daw;
      var nb = days > 0 ? Math.ceil(n / (days * D.tools.pack)) : Infinity;
      if (days > 0 && (!isFinite(d) || d > days)) late.push(r[1] + " needs " + (nb <= D.tools.max ? nb + " buys a day (" + fmt(dawniumFor(nb)) + " " + D.names.dawnium + ")" : "more than the shop sells"));
      trs += "<tr><th>" + r[1] + "</th><td class=num>" + fmt(Math.ceil(sw[r[0]])) + " " + r[2] + "</td><td class=num>" + b + " &times; " + D.tools.pack + " = " + tools + "</td><td class=num>" + (isFinite(d) ? fmt(d) + " days" : "never (0 bought)") + (days > 0 && isFinite(d) && d > days ? " <span class=warn>late</span>" : "") + "</td><td class=num>" + fmt(daw) + "</td><td class=num>" + (isFinite(d) ? fmt(d * daw) : "&mdash;") + "</td></tr>";
    });
    $("out_tools").innerHTML = trs || "<tr><td colspan=6>Nothing to mine for these targets.</td></tr>";
    if (!worst) { $("out_days").innerHTML = trs ? "Everything is covered by the tools in your bag." : ""; return; }
    var need = REALMS.map(function (r) { return Math.max(0, (sw[r[0]] || 0) - val("bag_" + r[0])); }), tot = need.reduce(function (a, b) { return a + b; }, 0);
    var sp = need.map(function (n) { return n > 0 ? Math.max(1, Math.round(buysTotal * n / tot)) : 0; }), over = sp.reduce(function (a, b) { return a + b; }, 0) - buysTotal;
    while (over > 0) { var i = sp.indexOf(Math.max.apply(null, sp)); if (sp[i] > 1) { sp[i]--; over--; } else break; }
    while (over < 0) { var j = -1, best = -1; need.forEach(function (n, k) { if (n > 0) { var g = n / (sp[k] * D.tools.pack) - n / ((sp[k] + 1) * D.tools.pack); if (g > best) { best = g; j = k; } } }); if (j < 0) break; sp[j]++; over++; }
    var bDays = 0, bDaw = 0; need.forEach(function (n, k) { if (n > 0) { var d = Math.ceil(n / (sp[k] * D.tools.pack)); if (d > bDays) bDays = d; bDaw += dawniumFor(sp[k]); } });
    var same = REALMS.every(function (r, k) { return sp[k] === buysOf(r[0]); });
    var txt = "With your split you finish in <b>" + fmt(worst) + " days</b> (" + worstName + " is the slowest) at " + fmt(dawDay) + " " + D.names.dawnium + " a day, about " + fmt(totalDaw) + " in all.";
    if (days > 0) txt += worst <= days ? " That fits the " + days + " days left." : " That is <b>" + fmt(worst - days) + " days too late</b>: " + late.join("; ") + ".";
    if (!same) txt += " Same " + buysTotal + " buys a day, balanced to finish together: " + REALMS.map(function (r, k) { return sp[k] + " " + r[2]; }).join(", ") + " &rarr; <b>" + fmt(bDays) + " days</b> at " + fmt(bDaw) + " " + D.names.dawnium + " a day. <button type=\"button\" class=\"pickbtn\" id=\"p_usesplit\">Use this split</button>";
    $("out_days").innerHTML = txt;
    var btn = $("p_usesplit"); if (btn) btn.addEventListener("click", function () { REALMS.forEach(function (r, k) { $("buy_" + r[0]).value = sp[k]; }); compute(); });
  }
  /* --- recommenders: greedy by points per swing within the gates, optionally within the tools available --- */
  function plan(limitByTime) {
    var s = season(), c = caps(), tgtChar = Math.max(val("tgt_player"), c.player + charNow()[1]), gate = gateFor(Math.max(0, tgtChar - c.player));
    var goal = val("p_goal"), need = $("p_goalkind").value === "stars" ? Math.max(0, (goal - s.fixed) * s.divisor) : goal;
    var us = units().map(function (u) { u.bought = 0; return u; }), bud = {}, used = { ironvein: 0, gilded: 0, dread: 0, dustfall: 0 }, days = val("p_days");
    REALMS.forEach(function (r) { bud[r[0]] = val("bag_" + r[0]) + days * buysOf(r[0]) * D.tools.pack; });
    us.forEach(function (u) { if (u.curN < c[u.sys]) { var sw = swingsFor(normalCost(u.sys, u.curN, c[u.sys])); for (var r in sw) used[r] += sw[r] * u.mult; } });
    var have = nowPoints(), pn = petNow(), sc = D.playerScore[fam()] || [];
    have += Math.max(0, Math.min(Math.max(0, val("tgt_pet") - c.pet), gate.pet) - pn[1]) * s.rates.pet * pn[2];
    have += (sc[Math.max(0, tgtChar - c.player) - 1] || 0) - (charNow()[1] > 0 ? sc[charNow()[1] - 1] || 0 : 0);
    var guard = 0;
    while ((limitByTime || have < need) && guard++ < 20000) {
      var best = null;
      us.forEach(function (u) {
        var k = u.curS + u.bought + 1; if (k > gate[u.sys] || u.mult <= 0) return;
        var lc = levelCost(u.sys, k); if (!lc) return;
        var sw = swingsFor(lc), t = total(sw) * u.mult; if (t <= 0) return;
        if (limitByTime) { for (var r in sw) if (used[r] + sw[r] * u.mult > bud[r] + 1e-9) return; }
        var ppw = s.rates[u.sys] * u.mult / t;
        if (!best || ppw > best.ppw) best = { u: u, sw: sw, ppw: ppw };
      });
      if (!best) break;
      best.u.bought++; have += s.rates[best.u.sys] * best.u.mult;
      for (var r2 in best.sw) used[r2] += best.sw[r2] * best.u.mult;
    }
    return { units: us, have: have, need: need, used: used, reached: have >= need };
  }
  function recommend(timeMode) {
    var c = caps(), p = plan(timeMode);
    p.units.forEach(function (u) { $(u.tgtId).value = c[u.sys] + u.curS + u.bought; dirty[u.tgtId] = true; });
    compute();
    var parts = p.units.filter(function (u) { return u.bought > 0; }).map(function (u) { return u.name + " to " + (c[u.sys] + u.curS + u.bought); });
    $("out_goal").innerHTML = (timeMode ? "Best in the " + val("p_days") + " days left with your buys and bag: " : (p.reached ? "To reach the goal: " : "The goal is out of reach at that character level (the gates cap it); the most is ")) +
      (parts.join(", ") || "nothing more") + " &rarr; " + fmt(p.have) + " points, " + fmt(stars(p.have)) + " " + D.names.star + ", grade " + grade(p.have) + ", about " + fmt(total(p.used)) + " swings. The targets below are set to this.";
  }
  function init() {
    var s = season(), sel = $("p_tier");
    function fillTiers() { var cur = sel.value; sel.innerHTML = ""; season().tiers.forEach(function (t) { var o = document.createElement("option"); o.value = t[0]; o.textContent = t[1]; sel.appendChild(o); }); sel.value = season().tiers.some(function (t) { return t[0] === cur; }) ? cur : season().top; var sc = season(); $("p_caps").textContent = "Season levels count past these caps at " + sc.topName + ": character " + sc.caps.player + ", gear " + sc.caps.equip + ", skills " + sc.caps.skill + ", relics " + sc.caps.relic + ", Fantomon " + sc.caps.pet + ". Points per season level: character " + sc.rates.player + ", gear " + sc.rates.equip + ", skills " + sc.rates.skill + ", Fantomon " + sc.rates.pet + ", relics " + sc.rates.relic + "; " + D.names.star + " = score / " + sc.divisor + " + " + sc.fixed + "."; }
    fillTiers();
    $("p_season").addEventListener("change", function () { fillTiers(); setDefaultTargets(); compute(); });
    document.querySelectorAll("#primo input, #primo select").forEach(function (el) {
      if (el.id === "p_season") return;
      var isTgt = /^tgt_/.test(el.id);
      el.addEventListener("input", function () { if (isTgt) dirty[el.id] = true; else setDefaultTargets(); compute(); });
      el.addEventListener("change", function () { if (isTgt) dirty[el.id] = true; else setDefaultTargets(); compute(); });
    });
    $("p_reco").addEventListener("click", function () { recommend(false); });
    $("p_recotime").addEventListener("click", function () { recommend(true); });
    setDefaultTargets(); compute();
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

    xp = {"player": {}, "pet": {}}
    h, lx = rows_of("level_exp"); xi = {c: i for i, c in enumerate(h)}
    for r in lx:
        lv = _num(r[0], -1)
        if lv < 0:
            continue
        if xi.get("1") is not None and r[xi["1"]].strip():
            xp["player"][lv] = _num(r[xi["1"]])
        if xi.get("2") is not None and r[xi["2"]].strip():
            xp["pet"][lv] = _num(r[xi["2"]])

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

    data = {"seasons": seasons, "ladders": ladders, "playerScore": player_score, "normal": normal, "yields": yields, "tools": tool_cfg, "pact": pact_cum, "pieces": pieces, "xp": xp,
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
    tier_opts = "".join(f'<option value="{t[0]}"{" selected" if t[0] == s2["top"] else ""}>{esc(t[1])}</option>' for t in s2["tiers"])
    season_opts = "".join(f'<option value="{i}"{" selected" if s["n"] == 2 else ""}>Season {s["n"]} &middot; {esc(s["name"])} ({esc(s["topName"])})</option>' for i, s in enumerate(seasons))

    def lab(text, inp):
        return f"<label>{text} {inp}</label>"

    def num(id_, v, extra=""):
        return f'<input type="number" id="{id_}" value="{v}" min="0"{extra}>'

    gear_tgt = "".join(f'<tr><th>{esc(name)}</th><td>{num(f"tgt_equip_{key}", 150)}</td></tr>' for key, name in pieces)
    gear_now = "".join(f'<label>{esc(name)} now {num(f"now_equip_{key}", 130)}</label>' for key, name in pieces)
    buy_rows = ""
    for t, k, d in (("RoughRefineStone", "ironvein", 4), ("SilverCoin", "gilded", 2), ("SkillSeniorMaterial", "dread", 2), ("SandsOfTime", "dustfall", 4)):
        buy_rows += "<tr><th>" + esc(item_name(tools[t])) + "</th><td>" + num("buy_" + k, d, ' max="%d"' % tool_cfg["max"]) + "</td><td>" + num("bag_" + k, 0) + "</td></tr>"

    body = f"""
<div class="wrap">
<p class="eyebrow">Season planner</p>
<h1>{esc(item_name(61))} planner</h1>
<p class="lede">Copy the numbers from your season's Progression tab, set targets or let the planner pick them, and see the
{esc(item_name(61))}s at season end and the Material Realm tools, days and {esc(item_name(2))} they cost.</p>

<section class="calc" id="primo">
  <h3>1. Season</h3>
  <div class="conv">
    <label>Season <select id="p_season">{season_opts}</select></label>
    <label>Your promotion <select id="p_tier">{tier_opts}</select></label>
    <label>Days left <input type="number" id="p_days" value="30" min="0"></label>
    <label><input type="checkbox" id="p_norefined" checked> ignore {esc(item_name(41301))}</label>
    <div class="out hint" id="p_caps"></div>
  </div>

  <h3>2. Where you are: your Progression tab</h3>
  <div class="conv">
    <label>Season Character Level <input type="number" id="pan_player" value="1" min="0"></label>
    <label>Season Gear Level <input type="number" id="pan_equip" value="0" min="0"></label>
    <label>Season Skill Level <input type="number" id="pan_skill" value="0" min="0"></label>
    <label>Season Fantomon Level <input type="number" id="pan_pet" value="0" min="0"></label>
    <label>Season Relic Level <input type="number" id="pan_relic" value="0" min="0"></label>
    <label>Skill slots <input type="number" id="n_skill" value="8" min="1"></label>
    <label>Relics you level <input type="number" id="n_relic" value="4" min="1" max="20"></label>
    <label>Fantomon you level <input type="number" id="n_pet" value="1" min="1"></label>
    <div class="out" id="now_sum"></div>
  </div>
  <details class="statbox"><summary>My items are uneven, or below the cap</summary>
    <p class="calcnote">The tab's totals are spread evenly over your pieces, slots, relics and Fantomon. Tick this to enter each item's
    level as its own screen shows it instead (a gear piece at 142, a skill at 129); levels below the cap are then priced up to the cap too.</p>
    <div class="conv"><label><input type="checkbox" id="p_uneven"> use these levels</label>
      {gear_now}<label>Skills now {num("now_skill", 130)}</label><label>Relics now {num("now_relic", 13)}</label><label>Fantomon now {num("now_pet", 130)}</label><label>Character now {num("now_player", 131)}</label></div>
  </details>

  <h3>3. Where you want to be</h3>
  <div class="conv"><label>I want <input type="number" id="p_goal" value="200" min="0"></label><label>&nbsp;<select id="p_goalkind"><option value="stars">{esc(item_name(61))}</option><option value="score">points</option></select></label>
    <label>&nbsp;<button type="button" id="p_reco" class="pickbtn">Recommend for this goal</button></label>
    <label>&nbsp;<button type="button" id="p_recotime" class="pickbtn">Best I can do in the days left</button></label>
    <div class="out" id="out_goal">Or set the targets by hand below. Levels are as each item's screen shows them.</div></div>
  <div class="pgrid">
    <div class="pfield"><b>Gear targets</b><div class="tablewrap" style="margin:6px 0 0"><table class="xp small"><tbody>{gear_tgt}</tbody></table></div></div>
    <div class="pfield"><b>Other targets</b>{lab("Skills", num("tgt_skill", 160))}{lab("Relics", num("tgt_relic", 16))}{lab("Fantomon", num("tgt_pet", 160))}{lab("Character", num("tgt_player", 140))}</div>
    <div class="pfield"><b>Tool buys a day &amp; in bag</b><div class="tablewrap" style="margin:6px 0 0"><table class="xp small"><thead><tr><th>Tool</th><th>Buys/day</th><th>In bag</th></tr></thead><tbody>{buy_rows}</tbody></table></div></div>
  </div>

  <h3>4. Result</h3>
  <p class="verdict" id="out_sum"></p>
  <div class="tablewrap"><table class="xp small"><thead><tr><th>Category</th><th class=num>Level</th><th class=num>Season levels gained</th><th class=num>Points</th><th>Materials</th><th class=num>Swings</th></tr></thead><tbody id="out_rows"></tbody></table></div>
  <ul class="calcnote" id="out_notes"></ul>
  <div class="tablewrap"><table class="xp small"><thead><tr><th>Realm</th><th class=num>Tools needed</th><th class=num>Buys &times; pack a day</th><th class=num>Days</th><th class=num>{esc(item_name(2))} a day</th><th class=num>{esc(item_name(2))} in all</th></tr></thead><tbody id="out_tools"></tbody></table></div>
  <p class="verdict" id="out_days"></p>
</section>

<details class="statbox"><summary>How it is scored, and where the numbers come from</summary>
<p class="calcnote">The game's rule card: <i>"For each Season Character Level gained, you receive {{1}} pts. For each Total Season Gear Enhancement
Level gained, {{2}} pts. For each Total Season Skill Level gained, {{3}} pts. For each Total Season Fantomon Level gained, {{4}} pts. For each Total
Season Relic Level gained, {{5}} pts. The conversion rate of {esc(item_name(61))} is your total season progression score divided by {{6}}, rounded down.
In addition to this conversion, you'll also receive a fixed amount."</i> The game also adds a few points for XP part-way to the next character
level, so its score can run slightly above the planner's. Season levels are the levels past the caps; they are sold only at the top tier of the
season's promotion, and each ladder opens further as your character's season level rises. Recommendations buy gear, skill and relic levels in
order of points per swing; Fantomon and character levels are XP, not realm materials, so they are taken from your targets.</p>
<h3>Rates and conversion by season</h3>
<div class="tablewrap"><table class="xp small"><thead><tr><th>Season</th><th>Season levels at</th><th class=num>Character</th><th class=num>Gear</th><th class=num>Skill</th><th class=num>Fantomon</th><th class=num>Relic</th><th class=num>Score per {esc(item_name(61))}</th><th class=num>Fixed</th><th>Progression grades</th></tr></thead><tbody>{rate_rows}</tbody></table></div>
<h3>Gates: season levels each character season level opens</h3>
<div class="tablewrap"><table class="xp small"><thead><tr><th>Season</th><th class=num>Character season level</th><th class=num>Gear</th><th class=num>Skills</th><th class=num>Relics</th><th class=num>Fantomon</th></tr></thead><tbody>{gate_rows}</tbody></table></div>
<h3>Realm yield per swing by promotion</h3>
<div class="tablewrap"><table class="xp small"><thead><tr><th>Promotion</th><th class=num>Factor</th><th class=num>{esc(item_name(41300))}</th><th class=num>{esc(item_name(41301))}</th><th class=num>{esc(item_name(1))}</th><th class=num>{esc(item_name(42200))}</th><th class=num>{esc(item_name(41400))} equiv.</th></tr></thead><tbody>{tier_rows}</tbody></table></div>
<p class="calcnote">Shop: {tool_cfg['pack']} tools per purchase; purchases per day cost {tool_txt} {esc(tool_cfg['currency'])}, {tool_cfg['max']} a day at most.
Sources: <code>astrological_season_config</code>, <code>destiny_score_award</code>, <code>system_level_limit</code>, <code>equip_upgrade_bless</code>,
<code>skill_slot_upgrade_bless</code> (4 active + 4 passive slots), <code>treasure_bless</code> (up to 20 relics: 5 element slots &times; 4),
<code>pet_upgrade_bless</code>, <code>level_bless</code>, <code>equip_upgrade_material</code>, <code>skill_slot_upgrade_material</code>,
<code>treasure_levelup_material</code>, <code>level_exp</code>, <code>item_merge</code>, the mop-up tables (see the Realms page), <code>quick_buy</code>,
<code>astrological_level</code>. Swings are averages over the swing roll and node odds. Season 6 has no season ladders in this client build.</p>
</details>
</div>
<script>var PRIMO = {json.dumps(data)};</script>
<script>{JS}</script>
"""
    return layout(f"{item_name(61)} planner",
                  f"Season Progression score, grade and {item_name(61)}s for any season, with the Material Realm swings, tools and days each target costs, and a recommender for the cheapest mix.",
                  body, "primostars", 0)
