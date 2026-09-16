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
  var PIECES = D.pieces;

  function season() { return D.seasons[$("p_season").value]; }
  function fam() { return season().family; }
  function tier() { return $("p_tier").value; }
  function caps() { return season().caps; }                 /* the caps at the season's top tier: past them a level is a season level */
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
  function split(sys, shown) {                  /* a shown level -> [normal part, season part] */
    var cap = caps()[sys]; return [Math.min(shown, cap), Math.max(0, shown - cap)];
  }
  function fillTiers() {
    var s = season(), sel = $("p_tier"), cur = sel.value; sel.innerHTML = "";
    s.tiers.forEach(function (t) { var o = document.createElement("option"); o.value = t[0]; o.textContent = t[1] + " (x" + t[2] + ")"; sel.appendChild(o); });
    sel.value = s.tiers.some(function (t) { return t[0] === cur; }) ? cur : s.top;
    $("p_caps").innerHTML = "Season " + s.n + " (" + s.name + "): levels past the caps are <b>season levels</b> and only they score. Caps at " + s.topName + ": character " + s.caps.player + ", gear " + s.caps.equip + ", skills " + s.caps.skill + ", relics " + s.caps.relic + ", Fantomon " + s.caps.pet + ". Points per season level: character " + s.rates.player + ", gear " + s.rates.equip + ", skills " + s.rates.skill + ", Fantomon " + s.rates.pet + ", relics " + s.rates.relic + ". " + D.names.star + " = score / " + s.divisor + " (rounded down) + " + s.fixed + ".";
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
  function budget() {                          /* tools available per realm in the days left: bag + days x buys x pack */
    var days = val("p_days"), b = {};
    REALMS.forEach(function (r) { b[r[0]] = val("bag_" + r[0]) + days * buysOf(r[0]) * D.tools.pack; });
    return b;
  }
  /* the units the planner walks: 5 gear pieces, skills x slots, relics x count; levels are the SHOWN level */
  function unitsList() {
    var list = PIECES.map(function (p) { return { sys: "equip", name: p[1], mult: 1, cur: val("cur_equip_" + p[0]), tgtId: "tgt_equip_" + p[0] }; });
    list.push({ sys: "skill", name: "Skills", mult: val("n_skill"), cur: val("cur_skill"), tgtId: "tgt_skill" });
    list.push({ sys: "relic", name: "Relics", mult: val("n_relic"), cur: val("cur_relic"), tgtId: "tgt_relic" });
    return list;
  }
  function charSeason(shown) { return Math.max(0, shown - caps().player); }
  function compute() {
    var s = season(), tgtChar = Math.max(val("tgt_player"), val("cur_player")), gate = gateFor(charSeason(tgtChar)), notes = [], pts = 0, cost = {}, rows = "";
    unitsList().forEach(function (u) {
      var tgt = Math.max(val(u.tgtId), u.cur), lad = ladder(u.sys), cap = caps()[u.sys];
      var cs = split(u.sys, u.cur), ts = split(u.sys, tgt), maxS = Math.min(gate[u.sys], lad.length);
      if (ts[1] > maxS) { notes.push(u.name + ": level " + tgt + " needs season level " + ts[1] + "; at character level " + tgtChar + " the gate allows " + gate[u.sys] + " (ladder " + lad.length + "), so it is cut to " + (cap + maxS)); ts[1] = maxS; tgt = cap + maxS; }
      var c = {};
      if (ts[0] > cs[0]) addCost(c, normalCost(u.sys, cs[0], ts[0]), u.mult);
      for (var k = cs[1] + 1; k <= ts[1]; k++) { var lc = levelCost(u.sys, k); if (lc) addCost(c, lc, u.mult); }
      var p = (ts[1] - cs[1]) * s.rates[u.sys] * u.mult; pts += p; addCost(cost, c);
      var sw = swingsFor(c), mats = Object.keys(c).filter(function (k) { return c[k] > 0; }).map(function (k) { return fmt(c[k]) + " " + MAT[k]; }).join(", ");
      rows += "<tr><th>" + u.name + "</th><td class=num>" + u.cur + " &rarr; " + tgt + (u.mult > 1 ? " &times; " + u.mult : "") + "</td><td class=num>" + (ts[1] - cs[1]) + "</td><td class=num>" + fmt(p) + "</td><td>" + (mats || "&mdash;") + "</td><td class=num>" + (total(sw) ? fmt(total(sw)) : "&mdash;") + "</td></tr>";
    });
    /* Fantomon and character: XP, not swings */
    var pcur = val("cur_pet"), ptgt = Math.max(val("tgt_pet"), pcur), pn = val("n_pet"), pl = ladder("pet"), pcs = split("pet", pcur), pts_ = split("pet", ptgt), pmax = Math.min(gate.pet, pl.length);
    if (pts_[1] > pmax) { notes.push("Fantomon: level " + ptgt + " cut to " + (caps().pet + pmax) + " by the gate or the ladder"); pts_[1] = pmax; ptgt = caps().pet + pmax; }
    var pxp = ((D.xp.pet[pts_[0]] || 0) - (D.xp.pet[pcs[0]] || 0) + (pl[pts_[1] - 1] || 0) - (pcs[1] > 0 ? pl[pcs[1] - 1] : 0)) * pn, pp = (pts_[1] - pcs[1]) * s.rates.pet * pn; pts += pp;
    rows += "<tr><th>Fantomon</th><td class=num>" + pcur + " &rarr; " + ptgt + (pn > 1 ? " &times; " + pn : "") + "</td><td class=num>" + (pts_[1] - pcs[1]) + "</td><td class=num>" + fmt(pp) + "</td><td>" + (pxp > 0 ? fmt(pxp) + " Fantomon XP" : "&mdash;") + "</td><td class=num>&mdash;</td></tr>";
    var ccur = val("cur_player"), ccs = split("player", ccur), cts = split("player", tgtChar), sc = D.playerScore[fam()] || [], cl = ladder("player");
    var cp = (sc[cts[1] - 1] || 0) - (ccs[1] > 0 ? sc[ccs[1] - 1] : 0), cxp = (D.xp.player[cts[0]] || 0) - (D.xp.player[ccs[0]] || 0) + (cl[cts[1] - 1] || 0) - (ccs[1] > 0 ? cl[ccs[1] - 1] : 0); pts += cp;
    rows += "<tr><th>Character</th><td class=num>" + ccur + " &rarr; " + tgtChar + "</td><td class=num>" + (cts[1] - ccs[1]) + "</td><td class=num>" + fmt(cp) + "</td><td>" + (cxp > 0 ? fmt(cxp) + " Character XP" : "&mdash;") + "</td><td class=num>&mdash;</td></tr>";
    var stars = Math.floor(pts / s.divisor) + s.fixed;
    $("out_rows").innerHTML = rows;
    $("out_sum").innerHTML = "<b>" + fmt(pts) + " points</b> &rarr; Progression grade <b>" + grade(pts) + "</b> &rarr; <b>" + fmt(stars) + " " + D.names.star + "</b> (" + fmt(pts) + " / " + s.divisor + " + " + s.fixed + "), enough for Astral Pact level " + pactLevels(stars) + " of " + D.pact.length + " from zero.";
    toolsTable(swingsFor(cost));
    $("out_notes").innerHTML = notes.length ? "<li>" + notes.join("</li><li>") + "</li>" : "";
    bestNext(gate);
  }
  function toolsTable(sw) {
    var days = val("p_days"), trs = "", worst = 0, worstName = "", dawDay = 0, totalDaw = 0, buysTotal = 0, late = [], needBuys = {};
    REALMS.forEach(function (r) {
      var n = Math.max(0, sw[r[0]] - val("bag_" + r[0])), b = buysOf(r[0]), tools = b * D.tools.pack, daw = dawniumFor(b); buysTotal += b;
      if (n <= 0) { if (sw[r[0]] > 0) trs += "<tr><th>" + r[1] + "</th><td class=num>" + fmt(Math.ceil(sw[r[0]])) + " " + r[2] + "</td><td colspan=4>covered by the tools in your bag</td></tr>"; return; }
      var d = tools ? Math.ceil(n / tools) : Infinity; if (d > worst) { worst = d; worstName = r[1]; }
      dawDay += daw; totalDaw += (isFinite(d) ? d : 0) * daw;
      var nb = days > 0 ? Math.ceil(n / (days * D.tools.pack)) : Infinity; needBuys[r[0]] = nb;
      if (days > 0 && (!isFinite(d) || d > days)) late.push(r[1] + " needs " + (nb <= D.tools.max ? nb + " buys a day (" + fmt(dawniumFor(nb)) + " " + D.names.dawnium + ")" : "more than the shop sells (" + D.tools.max + " buys a day)"));
      trs += "<tr><th>" + r[1] + "</th><td class=num>" + fmt(Math.ceil(sw[r[0]])) + " " + r[2] + "</td><td class=num>" + b + " &times; " + D.tools.pack + " = " + tools + "</td><td class=num>" + (isFinite(d) ? fmt(d) + " days" : "never (0 bought)") + (days > 0 && isFinite(d) && d > days ? " <span class=warn>late</span>" : "") + "</td><td class=num>" + fmt(daw) + "</td><td class=num>" + (isFinite(d) ? fmt(d * daw) : "&mdash;") + "</td></tr>";
    });
    $("out_tools").innerHTML = trs || "<tr><td colspan=6>No realm materials needed.</td></tr>";
    if (!worst) { $("out_days").innerHTML = trs ? "Everything is covered by the tools in your bag." : ""; return; }
    var need = REALMS.map(function (r) { return Math.max(0, (sw[r[0]] || 0) - val("bag_" + r[0])); }), tot = need.reduce(function (a, b) { return a + b; }, 0);
    var sp = need.map(function (n) { return n > 0 ? Math.max(1, Math.round(buysTotal * n / tot)) : 0; });
    var over = sp.reduce(function (a, b) { return a + b; }, 0) - buysTotal;
    while (over > 0) { var i = sp.indexOf(Math.max.apply(null, sp)); if (sp[i] > 1) { sp[i]--; over--; } else break; }
    while (over < 0) { var j = -1, best = -1; need.forEach(function (n, k) { if (n > 0) { var gain = n / (sp[k] * D.tools.pack) - n / ((sp[k] + 1) * D.tools.pack); if (gain > best) { best = gain; j = k; } } }); if (j < 0) break; sp[j]++; over++; }
    var bDays = 0, bDaw = 0; need.forEach(function (n, k) { if (n > 0) { var d = Math.ceil(n / (sp[k] * D.tools.pack)); if (d > bDays) bDays = d; bDaw += dawniumFor(sp[k]); } });
    var same = REALMS.every(function (r, k) { return sp[k] === buysOf(r[0]); });
    var txt = "With your split you finish in <b>" + fmt(worst) + " days</b> (" + worstName + " is the slowest) at " + fmt(dawDay) + " " + D.names.dawnium + " a day, about " + fmt(totalDaw) + " in all.";
    if (days > 0) txt += worst <= days ? " That fits the <b>" + days + " days</b> left." : " That is <b>" + fmt(worst - days) + " days too late</b> for the " + days + " days left: " + late.join("; ") + ".";
    if (!same) txt += " Same " + buysTotal + " purchases a day, balanced to finish together: " + REALMS.map(function (r, k) { return sp[k] + " " + r[2]; }).join(", ") + " &rarr; <b>" + fmt(bDays) + " days</b> at " + fmt(bDaw) + " " + D.names.dawnium + " a day. <button type=\"button\" class=\"pickbtn\" id=\"p_usesplit\">Use this split</button>";
    $("out_days").innerHTML = txt;
    var btn = $("p_usesplit"); if (btn) btn.addEventListener("click", function () { REALMS.forEach(function (r, k) { $("buy_" + r[0]).value = sp[k]; }); compute(); });
  }
  function bestNext(gate) {
    var s = season(), list = [];
    unitsList().forEach(function (u) {
      var lad = ladder(u.sys), cs = split(u.sys, u.cur), cap = caps()[u.sys];
      for (var k = cs[1] + 1; k <= Math.min(cs[1] + 40, lad.length); k++) {
        var c = levelCost(u.sys, k); if (!c) break;
        var sw = total(swingsFor(c));
        list.push({ name: u.name, lvl: cap + k, pts: s.rates[u.sys], sw: sw, ppw: s.rates[u.sys] / sw, open: k <= gate[u.sys] });
      }
    });
    list.sort(function (a, b) { return b.ppw - a.ppw; });
    var h = "";
    list.slice(0, 12).forEach(function (x) {
      h += "<tr" + (x.open ? "" : " class=dim") + "><th>" + x.name + " to " + x.lvl + "</th><td class=num>" + x.pts + "</td><td class=num>" + fmt(x.sw, 1) + "</td><td class=num>" + x.ppw.toFixed(2) + "</td><td>" + (x.open ? "open" : "needs a higher character level") + "</td></tr>";
    });
    $("out_best").innerHTML = h;
  }
  /* greedy: buy the season level with the most points per swing, within the gates and (optionally) the tools available */
  function plan(limitByTime) {
    var s = season(), tgtChar = Math.max(val("tgt_player"), val("cur_player")), gate = gateFor(charSeason(tgtChar));
    var goal = val("p_goal"), need = $("p_goalkind").value === "stars" ? Math.max(0, (goal - s.fixed) * s.divisor) : goal;
    var units = unitsList().map(function (u) { var sp = split(u.sys, u.cur); u.curS = sp[1]; u.curN = sp[0]; u.bought = 0; u.pre = {}; return u; });
    var bud = budget(), used = { ironvein: 0, gilded: 0, dread: 0, dustfall: 0 };
    /* the normal ladder to the cap is a precondition, paid first */
    units.forEach(function (u) { if (u.curN < caps()[u.sys]) { u.pre = normalCost(u.sys, u.curN, caps()[u.sys]); var sw = swingsFor(u.pre); for (var r in sw) used[r] += sw[r] * u.mult; } });
    var have = 0;
    units.forEach(function (u) { have += u.curS * s.rates[u.sys] * u.mult; });
    var pcs = split("pet", val("cur_pet")), pts_ = split("pet", Math.max(val("tgt_pet"), val("cur_pet"))), sc = D.playerScore[fam()] || [], cS = charSeason(val("cur_player"));
    have += Math.max(0, Math.min(pts_[1], gate.pet) - pcs[1]) * s.rates.pet * val("n_pet") + (sc[charSeason(tgtChar) - 1] || 0) - (cS > 0 ? (sc[cS - 1] || 0) : 0);
    units.forEach(function (u) { have -= u.curS * s.rates[u.sys] * u.mult; });   /* count only levels gained, like the table */
    var cost = {}, guard = 0;
    while ((limitByTime || have < need) && guard++ < 20000) {
      var best = null;
      units.forEach(function (u) {
        var k = u.curS + u.bought + 1; if (k > gate[u.sys] || u.mult <= 0) return;
        var c = levelCost(u.sys, k); if (!c) return;
        var sw = swingsFor(c), t = total(sw) * u.mult; if (t <= 0) return;
        if (limitByTime) { var fits = true; for (var r in sw) if (used[r] + sw[r] * u.mult > bud[r] + 1e-9) fits = false; if (!fits) return; }
        var ppw = s.rates[u.sys] * u.mult / t;
        if (!best || ppw > best.ppw) best = { u: u, c: c, sw: sw, ppw: ppw };
      });
      if (!best) break;
      best.u.bought++; have += s.rates[best.u.sys] * best.u.mult; addCost(cost, best.c, best.u.mult);
      for (var r2 in best.sw) used[r2] += best.sw[r2] * best.u.mult;
    }
    return { units: units, have: have, need: need, cost: cost, reached: have >= need, used: used, bud: bud };
  }
  function describe(p, timeMode) {
    var s = season(), parts = p.units.filter(function (u) { return u.bought > 0; }).map(function (u) { return u.name + " to " + (caps()[u.sys] + u.curS + u.bought) + (u.mult > 1 ? " (x" + u.mult + ")" : ""); });
    var stars = Math.floor(p.have / s.divisor) + s.fixed, tot = total(p.used);
    var head = timeMode ? "Best in the " + val("p_days") + " days left with your purchases and bag: " : (p.reached ? "Reachable: " : "Not reachable at that character level (the gates cap it): ");
    return head + (parts.join(", ") || "nothing to buy") + " &rarr; " + fmt(p.have) + " points (" + fmt(stars) + " " + D.names.star + ", grade " + grade(p.have) + ") for about " + fmt(tot) + " swings: " +
      REALMS.filter(function (r) { return p.used[r[0]] > 0; }).map(function (r) { return fmt(Math.ceil(p.used[r[0]])) + " in " + r[1]; }).join(", ") + ". The targets above have been set to this.";
  }
  function recommend(timeMode) {
    var p = plan(timeMode);
    p.units.forEach(function (u) { $(u.tgtId).value = caps()[u.sys] + u.curS + u.bought; });
    compute();
    $("out_goal").innerHTML = describe(p, timeMode);
    $("out_sum").scrollIntoView({ behavior: "smooth", block: "center" });
  }
  function panel() {
    var s = season(), keys = ["player", "equip", "skill", "pet", "relic"], names = { player: "Season Character Level", equip: "Season Gear Level", skill: "Season Skill Level", pet: "Season Fantomon Level", relic: "Season Relic Level" };
    var rows = "", tot = 0, sc = D.playerScore[fam()] || [];
    keys.forEach(function (k) {
      var v = val("pan_" + k), p = k === "player" ? (sc[v - 1] || v * s.rates.player) : v * s.rates[k]; tot += p;
      rows += "<tr><th>" + names[k] + "</th><td class=num>" + v + "</td><td class=num>" + s.rates[k] + "</td><td class=num>" + fmt(p) + "</td></tr>";
    });
    var stars = Math.floor(tot / s.divisor) + s.fixed;
    $("pan_rows").innerHTML = rows;
    $("pan_sum").innerHTML = "<b>" + fmt(tot) + " points</b> &rarr; grade <b>" + grade(tot) + "</b> &rarr; <b>" + fmt(stars) + " " + D.names.star + "</b> (" + fmt(tot) + " / " + s.divisor + " + " + s.fixed + "). The game adds a few points for XP part-way to the next character level, so its score can run slightly above this.";
  }
  function seedFromPanel() {
    var c = caps(), g = val("pan_equip"), n = PIECES.length;
    PIECES.forEach(function (p, i) { $("cur_equip_" + p[0]).value = c.equip + Math.floor(g / n) + (i < g % n ? 1 : 0); });
    var ns = Math.max(1, val("n_skill")), nr = Math.max(1, val("n_relic")), np = Math.max(1, val("n_pet"));
    $("cur_skill").value = c.skill + Math.round(val("pan_skill") / ns);
    $("cur_relic").value = c.relic + Math.round(val("pan_relic") / nr);
    $("cur_pet").value = c.pet + Math.round(val("pan_pet") / np);
    $("cur_player").value = c.player + val("pan_player");
    compute();
    $("out_sum").scrollIntoView({ behavior: "smooth", block: "center" });
  }
  function init() {
    fillTiers();
    ["pan_player", "pan_equip", "pan_skill", "pan_pet", "pan_relic"].forEach(function (id) { $(id).addEventListener("input", panel); });
    $("p_seed").addEventListener("click", seedFromPanel);
    panel();
    $("p_season").addEventListener("change", function () { fillTiers(); panel(); compute(); });
    document.querySelectorAll("#primo input, #primo select").forEach(function (el) {
      if (el.id === "p_season") return;
      el.addEventListener("input", compute); el.addEventListener("change", compute);
    });
    $("p_reco").addEventListener("click", function () { recommend(false); });
    $("p_recotime").addEventListener("click", function () { recommend(true); });
    compute();
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
    tier_opts = "".join(f'<option value="{t[0]}"{" selected" if t[0] == s2["top"] else ""}>{esc(t[1])} (&times;{t[2]})</option>' for t in s2["tiers"])
    season_opts = "".join(f'<option value="{i}"{" selected" if s["n"] == 2 else ""}>Season {s["n"]} &middot; {esc(s["name"])} ({esc(s["topName"])})</option>' for i, s in enumerate(seasons))

    def lab(text, inp):
        return f"<label>{text} {inp}</label>"

    def num(id_, v, ph=""):
        return f'<input type="number" id="{id_}" value="{v}" min="0"{f" placeholder=\"{ph}\"" if ph else ""}>'

    gear_rows = "".join(f'<tr><th>{esc(name)}</th><td>{num(f"cur_equip_{key}", 130)}</td><td>{num(f"tgt_equip_{key}", 150)}</td></tr>' for key, name in pieces)

    body = f"""
<div class="wrap">
<p class="eyebrow">Season planner</p>
<h1>{esc(item_name(61))} planner</h1>
<p class="lede">Set the season, where you stand and where you want to be; the planner returns the Progression score,
the grade, the {esc(item_name(61))}s at season end, and the Material Realm swings, tools, days and {esc(item_name(2))} it takes &mdash;
gear piece by piece, skills, relics, Fantomon and character levels all counted with the game's own rates. Give it a goal and
press <b>Recommend</b> to have it pick the cheapest levels for you, or ask for the most it can reach in the days you have left.</p>

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
    <label>Days left in the season <input type="number" id="p_days" value="30" min="0"></label>
    <label><input type="checkbox" id="p_norefined" checked> ignore {esc(item_name(41301))} costs (untick if you have to mine it)</label>
    <div class="out" id="p_caps"></div>
  </div>

  <h3>Your Progression panel</h3>
  <p class="calcnote">Copy the five numbers from the season's Progression tab: they are totals of season levels per category
  (gear over all five pieces, skills over all eight slots, relics over every relic you level, Fantomon over every Fantomon).</p>
  <div class="conv">
    <label>Season Character Level <input type="number" id="pan_player" value="0" min="0"></label>
    <label>Season Gear Level <input type="number" id="pan_equip" value="0" min="0"></label>
    <label>Season Skill Level <input type="number" id="pan_skill" value="0" min="0"></label>
    <label>Season Fantomon Level <input type="number" id="pan_pet" value="0" min="0"></label>
    <label>Season Relic Level <input type="number" id="pan_relic" value="0" min="0"></label>
    <label>&nbsp;<button type="button" id="p_seed" class="pickbtn">Use these as my current levels</button></label>
    <div class="out"><div class="tablewrap" style="margin:0 0 8px"><table class="xp small"><thead><tr><th>Category</th><th class=num>Season levels</th><th class=num>Points each</th><th class=num>Points</th></tr></thead><tbody id="pan_rows"></tbody></table></div><div id="pan_sum"></div></div>
  </div>

  <h3>Where you are and where you want to be</h3>
  <p class="calcnote">Enter the levels as the game shows them on each item (a gear piece at 142, a skill at 129). The planner
  knows the caps, so it works out which part is a season level by itself; targets below the cap cost materials but score nothing.
  The counts say over how many pieces, slots, relics and Fantomon the season levels are spread.</p>
  <div class="pgrid">
    <div class="pfield"><b>Character</b> <span class=hint>cap <span id="cap_player"></span></span>
      {lab("Level now", num("cur_player", 131))}{lab("Target level", num("tgt_player", 140))}</div>
    <div class="pfield"><b>Skills</b> <span class=hint>cap <span id="cap_skill"></span>, all slots alike</span>
      {lab("Level now", num("cur_skill", 130))}{lab("Target level", num("tgt_skill", 160))}{lab("Slots", num("n_skill", 8))}</div>
    <div class="pfield"><b>Relics</b> <span class=hint>cap <span id="cap_relic"></span>, all levelled relics alike</span>
      {lab("Level now", num("cur_relic", 13))}{lab("Target level", num("tgt_relic", 16))}{lab("Relics levelled (up to 20: 5 elements &times; 4 slots)", num("n_relic", 4))}</div>
    <div class="pfield"><b>Fantomon</b> <span class=hint>cap <span id="cap_pet"></span></span>
      {lab("Level now", num("cur_pet", 130))}{lab("Target level", num("tgt_pet", 160))}{lab("Fantomon levelled", num("n_pet", 1))}</div>
  </div>
  <div class="pfield" style="margin:0 0 14px"><b>Gear</b> <span class=hint>cap <span id="cap_equip"></span>, each piece on its own</span>
    <div class="tablewrap" style="margin:6px 0 0"><table class="xp small"><thead><tr><th>Piece</th><th>Level now</th><th>Target level</th></tr></thead><tbody>{gear_rows}</tbody></table></div></div>

  <h3>Your daily tool purchases</h3>
  <div class="conv">
    <label>{esc(item_name(tools["RoughRefineStone"]))} buys/day <input type="number" id="buy_ironvein" value="4" min="0" max="{tool_cfg['max']}"></label>
    <label>{esc(item_name(tools["SilverCoin"]))} buys/day <input type="number" id="buy_gilded" value="2" min="0" max="{tool_cfg['max']}"></label>
    <label>{esc(item_name(tools["SkillSeniorMaterial"]))} buys/day <input type="number" id="buy_dread" value="2" min="0" max="{tool_cfg['max']}"></label>
    <label>{esc(item_name(tools["SandsOfTime"]))} buys/day <input type="number" id="buy_dustfall" value="4" min="0" max="{tool_cfg['max']}"></label>
    <label>{esc(item_name(tools["RoughRefineStone"]))} in bag <input type="number" id="bag_ironvein" value="0" min="0"></label>
    <label>{esc(item_name(tools["SilverCoin"]))} in bag <input type="number" id="bag_gilded" value="0" min="0"></label>
    <label>{esc(item_name(tools["SkillSeniorMaterial"]))} in bag <input type="number" id="bag_dread" value="0" min="0"></label>
    <label>{esc(item_name(tools["SandsOfTime"]))} in bag <input type="number" id="bag_dustfall" value="0" min="0"></label>
  </div>

  <h3>Recommend</h3>
  <div class="conv"><label>I want <input type="number" id="p_goal" value="200" min="0"></label><label>&nbsp;<select id="p_goalkind"><option value="stars">{esc(item_name(61))}</option><option value="score">points</option></select></label>
  <label>&nbsp;<button type="button" id="p_reco" class="pickbtn">Recommend for this goal</button></label>
  <label>&nbsp;<button type="button" id="p_recotime" class="pickbtn">Best I can do in the days left</button></label>
  <div class="out" id="out_goal"></div></div>
  <p class="calcnote">Both buttons start from your current levels and buy gear, skill and relic levels in order of points per swing,
  within the gates of your target character level, then write the targets into the fields above. The second one also stays inside
  the tools you can have: what is in your bag plus days left &times; buys &times; {tool_cfg['pack']} per realm. Fantomon and character levels
  come from your own fields, since they are XP, not realm materials.</p>

  <p class="verdict" id="out_sum"></p>
  <div class="tablewrap"><table class="xp small"><thead><tr><th>Category</th><th class=num>Level</th><th class=num>Season levels gained</th><th class=num>Points</th><th>Materials</th><th class=num>Swings</th></tr></thead><tbody id="out_rows"></tbody></table></div>
  <ul class="calcnote" id="out_notes"></ul>
  <h3>Tools and days</h3>
  <div class="tablewrap"><table class="xp small"><thead><tr><th>Realm</th><th class=num>Tools needed</th><th class=num>Buys &times; pack a day</th><th class=num>Days</th><th class=num>{esc(item_name(2))} a day</th><th class=num>{esc(item_name(2))} in all</th></tr></thead><tbody id="out_tools"></tbody></table></div>
  <p class="verdict" id="out_days"></p>
  <p class="calcnote">Shop: {tool_cfg['pack']} tools per purchase; purchases per day cost {tool_txt} {esc(tool_cfg['currency'])}, {tool_cfg['max']} purchases a day at most
  (<code>quick_buy</code>). Swings are averages over the swing roll and the node odds; Refined Ore comes flat from the Refined Ore Mine and is the slow part of gear.</p>
  <h3>Best next levels</h3>
  <p>Points per swing of the next levels open to you, best first. Greyed rows wait for a higher character level.</p>
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
