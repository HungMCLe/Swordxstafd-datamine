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
  var SYS = ["equip", "skill", "relic", "pet", "player"];
  var LABEL = { equip: "Gear", skill: "Skills", relic: "Relics", pet: "Fantomon", player: "Character" };
  var MAT = { ore: D.names.ore, refined: D.names.refined, rolla: D.names.rolla, essence: D.names.essence, sand: D.names.sand + " (plain-sand equivalent)", petxp: "Fantomon XP", xp: "Character XP" };
  var REALM = { ore: "ironvein", refined: "ironvein", rolla: "gilded", essence: "dread", sand: "dustfall" };

  function season() { return D.seasons[$("p_season").value]; }
  function fam() { return season().family; }
  function ladder(sys) { return (D.ladders[fam()] || {})[sys] || []; }
  function gateFor(sl) {
    var g = season().gates, out = { skill: 0, equip: 0, relic: 0, pet: 0 };
    for (var i = 0; i < g.length; i++) if (sl >= g[i][0]) out = g[i][1];
    return out;
  }
  function yields() { var t = $("p_tier").value; return D.yields[fam()][t] || D.yields[fam()][season().top]; }
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
  function addCost(a, b) { for (var k in b) a[k] = (a[k] || 0) + b[k]; return a; }
  function ignoreRefined() { return $("p_norefined").checked; }
  function levelCost(sys, k) {          /* cost of season level k (1-based) of one unit */
    var c = ladder(sys)[k - 1]; if (!c) return null;
    var out = {}; for (var key in c) out[key] = c[key];
    if (ignoreRefined()) delete out.refined;
    return out;
  }
  function normalCost(sys, from, to) {  /* normal-ladder cost from level `from` to `to` (one unit) */
    var lad = D.normal[sys] || {}, out = {};
    for (var l = from + 1; l <= to; l++) { var c = lad[l]; if (c) addCost(out, c); }
    if (ignoreRefined()) delete out.refined;
    return out;
  }
  function fillTiers() {
    var s = season(), sel = $("p_tier"), cur = sel.value; sel.innerHTML = "";
    s.tiers.forEach(function (t) { var o = document.createElement("option"); o.value = t[0]; o.textContent = t[1] + " (x" + t[2] + ")"; sel.appendChild(o); });
    sel.value = s.tiers.some(function (t) { return t[0] === cur; }) ? cur : s.top;
    $("p_caps").textContent = "Season " + s.n + " (" + s.name + "): season levels open at " + s.topName + ". Caps: character " + s.caps.player + ", gear " + s.caps.equip + ", skills " + s.caps.skill + ", relics " + s.caps.relic + ", Fantomon " + s.caps.pet + ". Points per season level: character " + s.rates.player + ", gear " + s.rates.equip + ", skills " + s.rates.skill + ", Fantomon " + s.rates.pet + ", relics " + s.rates.relic + ". Primostars = score / " + s.divisor + " (rounded down) + " + s.fixed + ".";
    SYS.forEach(function (sys) { $("cap_" + sys).textContent = s.caps[sys]; });
  }
  function units(sys) { return sys === "player" ? 1 : Number($("n_" + sys).value) || 0; }
  function grade(score) {
    var g = season().grades, out = g[0][1];
    for (var i = 0; i < g.length; i++) if (score >= g[i][0]) out = g[i][1];
    return out;
  }
  function pactLevels(stars) { var n = 0; while (n < D.pact.length && D.pact[n] <= stars) n++; return n; }

  function compute() {
    var s = season(), sl = Number($("cur_player").value) || 0, tl = Number($("tgt_player").value) || 0, gate = gateFor(tl);
    var rows = "", pts = 0, cost = {}, notes = [];
    SYS.forEach(function (sys) {
      var cur = Number($("cur_" + sys).value) || 0, tgt = Number($("tgt_" + sys).value) || 0, u = units(sys);
      var lad = ladder(sys), max = sys === "player" ? lad.length : Math.min(gate[sys], lad.length);
      if (tgt > max) { notes.push(LABEL[sys] + ": target " + tgt + " cut to " + max + " (the gate at character season level " + tl + " is " + gate[sys] + ", the ladder ends at " + lad.length + ")"); tgt = max; }
      if (tgt < cur) tgt = cur;
      var p = 0, c = {}, xp = 0;
      if (sys === "pet" || sys === "player") {
        var cum = lad; xp = (cum[tgt - 1] || 0) - (tgt > 0 ? (cum[cur - 1] || 0) : 0); if (cur === 0 && tgt > 0) xp = cum[tgt - 1];
        if (sys === "player") { var sc = D.playerScore[fam()] || []; p = (sc[tgt - 1] || 0) - (cur > 0 ? (sc[cur - 1] || 0) : 0); c = { xp: xp }; }
        else { p = (tgt - cur) * s.rates.pet * u; c = { petxp: xp * u }; }
      } else {
        for (var k = cur + 1; k <= tgt; k++) { var lc = levelCost(sys, k); if (lc) { for (var key in lc) c[key] = (c[key] || 0) + lc[key] * u; } }
        p = (tgt - cur) * s.rates[sys] * u;
      }
      /* normal ladder to the cap first */
      var nc = {}, lvEl = $("lvl_" + sys), nlv = lvEl ? Number(lvEl.value) : NaN;
      if (lvEl && lvEl.value !== "" && !isNaN(nlv) && nlv < s.caps[sys]) { nc = normalCost(sys, nlv, s.caps[sys]); for (var kk in nc) c[kk] = (c[kk] || 0) + nc[kk] * u; }
      pts += p; addCost(cost, c);
      var sw = swingsFor(c), mats = Object.keys(c).filter(function (k) { return c[k] > 0; }).map(function (k) { return fmt(c[k]) + " " + MAT[k]; }).join(", ");
      rows += "<tr><th>" + LABEL[sys] + "</th><td class=num>" + cur + " &rarr; " + tgt + (sys === "player" ? "" : " &times; " + u) + "</td><td class=num>" + fmt(p) + "</td><td>" + (mats || "&mdash;") + "</td><td class=num>" + (total(sw) ? fmt(total(sw)) : "&mdash;") + "</td></tr>";
    });
    var stars = Math.floor(pts / s.divisor) + s.fixed;
    $("out_rows").innerHTML = rows;
    var sw = swingsFor(cost);
    $("out_sum").innerHTML = "<b>" + fmt(pts) + " points</b> &rarr; Progression grade <b>" + grade(pts) + "</b> &rarr; <b>" + fmt(stars) + " " + D.names.star + "</b> (" + fmt(pts) + " / " + s.divisor + " + " + s.fixed + "), enough for Astral Pact level " + pactLevels(stars) + " of " + D.pact.length + " from zero.";
    var perDay = Number($("p_buys").value) || 0, tools = perDay * D.tools.pack, daw = dawniumFor(perDay);
    var realms = [["ironvein", "Ironvein Pit", D.names.toolOre], ["gilded", "Gilded Depths", D.names.toolRolla], ["dread", "Dread Hollow", D.names.toolEssence], ["dustfall", "Dustfall Dune", D.names.toolSand]];
    var trs = "";
    realms.forEach(function (r) {
      var n = sw[r[0]]; if (!n) return;
      trs += "<tr><th>" + r[1] + "</th><td class=num>" + fmt(Math.ceil(n)) + " " + r[2] + "</td><td class=num>" + (tools ? fmt(Math.ceil(n / tools)) + " days" : "&mdash;") + "</td><td class=num>" + (tools ? fmt(Math.ceil(n / tools) * daw) : "&mdash;") + "</td></tr>";
    });
    $("out_tools").innerHTML = trs || "<tr><td colspan=4>No realm materials needed.</td></tr>";
    $("out_notes").innerHTML = notes.length ? "<li>" + notes.join("</li><li>") + "</li>" : "";
    bestNext(gate);
  }
  function dawniumFor(buys) {
    var left = buys, d = 0;
    for (var i = 0; i < D.tools.tiers.length && left > 0; i++) { var n = Math.min(left, D.tools.tiers[i][1]); d += n * D.tools.tiers[i][0]; left -= n; }
    return d;
  }
  function fillBuys() {
    var sel = $("p_buys"), acc = 0; sel.innerHTML = "";
    for (var b = 1; b <= D.tools.max; b++) { var o = document.createElement("option"); o.value = b; o.textContent = b + " buy" + (b > 1 ? "s" : "") + " = " + (b * D.tools.pack) + " tools, " + fmt(dawniumFor(b)) + " " + D.names.dawnium + "/day"; sel.appendChild(o); }
    sel.value = "2";
  }
  function bestNext(gate) {
    var s = season(), list = [];
    ["equip", "skill", "relic"].forEach(function (sys) {
      var cur = Number($("cur_" + sys).value) || 0, lad = ladder(sys);
      for (var k = cur + 1; k <= Math.min(cur + 60, lad.length); k++) {
        var c = levelCost(sys, k); if (!c) break;
        var sw = total(swingsFor(c)), open = k <= gate[sys];
        list.push({ sys: sys, k: k, pts: s.rates[sys], sw: sw, ppw: s.rates[sys] / sw, open: open });
      }
    });
    list.sort(function (a, b) { return b.ppw - a.ppw; });
    var h = "";
    list.slice(0, 12).forEach(function (x) {
      h += "<tr" + (x.open ? "" : " class=dim") + "><th>" + LABEL[x.sys] + " +" + x.k + "</th><td class=num>" + x.pts + "</td><td class=num>" + fmt(x.sw, 1) + "</td><td class=num>" + x.ppw.toFixed(2) + "</td><td>" + (x.open ? "open" : "needs a higher character season level") + "</td></tr>";
    });
    $("out_best").innerHTML = h;
    /* greedy: reach a target */
    var goal = Number($("p_goal").value) || 0, goalStars = $("p_goalkind").value === "stars";
    var need = goalStars ? Math.max(0, (goal - s.fixed) * s.divisor) : goal;
    var have = 0, bought = { equip: 0, skill: 0, relic: 0 }, cost = {}, steps = [], cur = {};
    ["equip", "skill", "relic"].forEach(function (sys) { cur[sys] = Number($("cur_" + sys).value) || 0; });
    /* points already held from the current levels (season levels only) plus pets and character targets are not part of the greedy budget */
    var base = 0; SYS.forEach(function (sys) { var cv = Number($("cur_" + sys).value) || 0; if (sys === "player") { var sc = D.playerScore[fam()] || []; base += sc[cv - 1] || 0; } else base += cv * s.rates[sys] * units(sys); });
    have = base;
    var guard = 0;
    while (have < need && guard++ < 5000) {
      var best = null;
      ["equip", "skill", "relic"].forEach(function (sys) {
        var k = cur[sys] + bought[sys] + 1; if (k > gate[sys]) return;
        var c = levelCost(sys, k); if (!c) return;
        var sw = total(swingsFor(c)) * units(sys), ppw = s.rates[sys] * units(sys) / sw;
        if (!best || ppw > best.ppw) best = { sys: sys, k: k, c: c, sw: sw, ppw: ppw };
      });
      if (!best) break;
      bought[best.sys]++; have += s.rates[best.sys] * units(best.sys);
      for (var key in best.c) cost[key] = (cost[key] || 0) + best.c[key] * units(best.sys);
    }
    var sw2 = swingsFor(cost), t2 = total(sw2);
    var txt = need <= 0 ? "Enter a goal above." : (have >= need ? "Reachable: " : "Not reachable at this character season level (gates): ") +
      "gear +" + bought.equip + " on " + units("equip") + " pieces, skills +" + bought.skill + " on " + units("skill") + " slots, relics +" + bought.relic + " on " + units("relic") + " relics &rarr; " + fmt(have) + " points (" + fmt(Math.floor(have / s.divisor) + s.fixed) + " " + D.names.star + ") for about " + fmt(t2) + " swings: " +
      ["ironvein", "gilded", "dread", "dustfall"].filter(function (r) { return sw2[r] > 0; }).map(function (r) { return fmt(Math.ceil(sw2[r])) + " in " + { ironvein: "Ironvein Pit", gilded: "Gilded Depths", dread: "Dread Hollow", dustfall: "Dustfall Dune" }[r]; }).join(", ") + ".";
    $("out_goal").innerHTML = txt;
  }
  function init() {
    fillTiers(); fillBuys();
    var s = season();
    ["p_season"].forEach(function (id) { $(id).addEventListener("change", function () { fillTiers(); compute(); }); });
    document.querySelectorAll("#primo input, #primo select").forEach(function (el) { if (el.id !== "p_season") { el.addEventListener("input", compute); el.addEventListener("change", compute); } });
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
    tools = {}
    for r in md:
        tools[r[mi["Type"]].strip()] = list(_items(r[mi["CostDict"]]).keys())[0]
    ED = 11.0                                    # expected durability per swing (10 attack, +-10%, 20% crit x1.5)
    SAND = {41400: 1, 41401: 5, 41402: 25}
    KEY = {"RoughRefineStone": ("ore", "refined"), "SilverCoin": ("rolla", "dawnium"), "SkillSeniorMaterial": ("essence", None), "SandsOfTime": ("sand", None)}

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

    # ---- seasons
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
        bc["player"] = max(bc["player"], _num(r[li["PlayerLevel"]])); bc["skill"] = max(bc["skill"], _num(r[li["SkillLevel"]]))
        bc["equip"] = max(bc["equip"], _num(r[li["EquipLevel"]])); bc["pet"] = max(bc["pet"], _num(r[li["PetLevel"]])); bc["relic"] = max(bc["relic"], _num(r[li["TreasureLevel"]]))
        g = (_num(r[li["PlayerBlessLevel"]]), {"skill": _num(r[li["SkillBlessLevel"]]), "equip": _num(r[li["EquipBlessLevel"]]), "relic": _num(r[li["TreasureBlessLevel"]]), "pet": _num(r[li["PetBlessLevel"]])})
        if not gates[s] or gates[s][-1][1] != g[1]:
            gates[s].append(g)

    seasons = []
    yields = {}
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
            "gates": [[g[0], g[1]] for g in gates.get(top, [])], "tiers": tiers,
        })

    # ---- ladders per family
    ladders = collections.defaultdict(lambda: {"skill": [], "equip": [], "relic": [], "pet": [], "player": []})
    player_score = collections.defaultdict(list)
    h, sb = rows_of("skill_slot_upgrade_bless")
    for r in sb:
        ladders[r[0].strip()]["skill"].append({"essence": _items(r[2]).get(42200, 0)})
    h, eb = rows_of("equip_upgrade_bless")
    for r in eb:
        c = _items(r[3]); ladders[r[0].strip()]["equip"].append({"ore": c.get(41300, 0), "refined": c.get(41301, 0), "rolla": c.get(1, 0)})
    h, tb = rows_of("treasure_bless")
    for r in tb:
        c = _items(r[2]); ladders[r[0].strip()]["relic"].append({"sand": sum(v * SAND.get(i, 0) for i, v in c.items()), "rolla": c.get(1, 0)})
    h, pb = rows_of("pet_upgrade_bless")
    for r in pb:
        ladders[r[0].strip()]["pet"].append(_num(r[2]))
    h, lb = rows_of("level_bless")
    for r in lb:
        ladders[r[0].strip()]["player"].append(_num(r[2])); player_score[r[0].strip()].append(_num(r[3]))
    # normal ladders (0 points; to reach the cap)
    normal = {"equip": {}, "skill": {}, "relic": {}}
    h, em = rows_of("equip_upgrade_material")
    for r in em:
        c = _items(r[2]); normal["equip"][_num(r[0])] = {"ore": c.get(41300, 0), "refined": c.get(41301, 0), "rolla": c.get(1, 0)}
    h, sm = rows_of("skill_slot_upgrade_material")
    for r in sm:
        normal["skill"][_num(r[0])] = {"essence": _items(r[1]).get(42200, 0)}
    h, tm = rows_of("treasure_levelup_material")
    for r in tm:
        c = _items(r[1]); normal["relic"][_num(r[0])] = {"sand": sum(v * SAND.get(i, 0) for i, v in c.items()), "rolla": c.get(1, 0)}

    # ---- tools and the pact
    h, qb = rows_of("quick_buy"); qi = {c: i for i, c in enumerate(h)}
    q = next(r for r in qb if r[0].strip() == "100")
    prices = _list(q[qi["PriceList"]]); counts = _list(q[qi["PriceBuyCount"]])
    tool_cfg = {"pack": _num(q[qi["BaseCount"]]), "tiers": list(zip(prices, counts)), "max": sum(counts), "currency": item_name(_num(q[qi["CurrencyId"]]))}
    pact_cum, acc = [], 0
    for r in rows_of("astrological_level")[1]:
        acc += _num(r[1]); pact_cum.append(acc)

    data = {"seasons": seasons, "ladders": ladders, "playerScore": player_score, "normal": normal, "yields": yields, "tools": tool_cfg, "pact": pact_cum,
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
            (f"<tr>" if i else "") + f"<td class=num>{g[0]}</td><td class=num>{g[1]['equip']}</td><td class=num>{g[1]['skill']}</td><td class=num>{g[1]['relic']}</td><td class=num>{g[1]['pet']}</td></tr>"
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

    def field(sys, label, cur, tgt, count=None, count_label=None, lvl=True):
        h_ = f'<div class="pfield"><b>{label}</b> <span class=hint>cap <span id="cap_{sys}"></span></span>'
        if lvl:
            h_ += f'<label>Current normal level <input type="number" id="lvl_{sys}" placeholder="at cap" min="0"></label>'
        h_ += f'<label>Season levels now <input type="number" id="cur_{sys}" value="{cur}" min="0"></label><label>Target season level <input type="number" id="tgt_{sys}" value="{tgt}" min="0"></label>'
        if count is not None:
            h_ += f'<label>{count_label} <input type="number" id="n_{sys}" value="{count}" min="0"></label>'
        return h_ + "</div>"

    body = f"""
<div class="wrap">
<p class="eyebrow">Season planner</p>
<h1>{esc(item_name(61))} planner</h1>
<p class="lede">Set the season, where you stand and where you want to be; the planner returns the Progression score,
the grade, the {esc(item_name(61))}s at season end, and the Material Realm swings, tools, days and {esc(item_name(2))} it takes &mdash;
gear, skills, relics, Fantomon and character levels all counted with the game's own rates.</p>

<p class="calcnote">The rule card: <i>"For each Season Character Level gained, you receive {{1}} pts. For each Total Season Gear
Enhancement Level gained, {{2}} pts. For each Total Season Skill Level gained, {{3}} pts. For each Total Season Fantomon Level
gained, {{4}} pts. For each Total Season Relic Level gained, {{5}} pts. The conversion rate of {esc(item_name(61))} is your total season
progression score divided by {{6}}, rounded down. In addition to this conversion, you'll also receive a fixed amount."</i>
Season levels are the levels past your promotion's cap; they are sold only at the top tier of the season's promotion and
each ladder opens further as your own season level rises (the gate table below).</p>

<section class="calc" id="primo">
  <div class="conv">
    <label>Season <select id="p_season">{season_opts}</select></label>
    <label>Your promotion (sets the realm yield) <select id="p_tier">{tier_opts}</select></label>
    <label>Tools bought per realm per day <select id="p_buys"></select></label>
    <label><input type="checkbox" id="p_norefined"> ignore {esc(item_name(41301))} costs</label>
    <div class="out" id="p_caps"></div>
  </div>
  <div class="pgrid">
    {field("player", "Character", 0, 10, lvl=False)}
    {field("equip", "Gear", 0, 20, 5, "Pieces")}
    {field("skill", "Skills", 0, 30, 8, "Slots")}
    {field("relic", "Relics", 0, 3, 4, "Relics")}
    {field("pet", "Fantomon", 0, 30, 1, "Fantomon levelled", lvl=False)}
  </div>
  <p class="verdict" id="out_sum"></p>
  <div class="tablewrap"><table class="xp small"><thead><tr><th>Category</th><th class=num>Season levels</th><th class=num>Points</th><th>Materials</th><th class=num>Swings</th></tr></thead><tbody id="out_rows"></tbody></table></div>
  <ul class="calcnote" id="out_notes"></ul>
  <h3>Tools and days</h3>
  <div class="tablewrap"><table class="xp small"><thead><tr><th>Realm</th><th class=num>Tools (swings)</th><th class=num>Days at your purchase rate</th><th class=num>{esc(item_name(2))} for those days</th></tr></thead><tbody id="out_tools"></tbody></table></div>
  <p class="calcnote">Shop: {tool_cfg['pack']} tools per purchase; purchases per day cost {tool_txt} {esc(tool_cfg['currency'])}, {tool_cfg['max']} purchases a day at most
  (<code>quick_buy</code>). Swings are averages over the swing roll and the node odds; Refined Ore comes flat from the Refined Ore Mine and is the slow part of gear.</p>
  <h3>Best next levels</h3>
  <p>Points per swing of the next levels open to you, best first. Greyed rows wait for a higher character season level.</p>
  <div class="tablewrap"><table class="xp small"><thead><tr><th>Level</th><th class=num>Points</th><th class=num>Swings</th><th class=num>Points per swing</th><th>Gate</th></tr></thead><tbody id="out_best"></tbody></table></div>
  <h3>Reach a goal</h3>
  <div class="conv"><label>Goal <input type="number" id="p_goal" value="1000" min="0"></label><label>in <select id="p_goalkind"><option value="stars">{esc(item_name(61))}</option><option value="score">points</option></select></label>
  <div class="out" id="out_goal"></div></div>
  <p class="calcnote">The goal buys gear, skill and relic levels in order of points per swing from your current season levels, within the gates of the target character season level; Fantomon and character points are taken from the fields above.</p>
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
caps and gates: <code>system_level_limit</code>; ladders: <code>equip_upgrade_bless</code> (5 pieces), <code>skill_slot_upgrade_bless</code>
(4 active + 4 passive slots, <code>game_settings.SkillTypes</code>), <code>treasure_bless</code> (<code>TreasureMaxSlotCount</code> 4),
<code>pet_upgrade_bless</code> and <code>level_bless</code> (cumulative XP); normal ladders <code>equip_upgrade_material</code>,
<code>skill_slot_upgrade_material</code>, <code>treasure_levelup_material</code>; sand grades <code>item_merge</code>; yields from the
mop-up tables as on the Realms page; shop <code>quick_buy</code>; Astral Pact <code>astrological_level</code>. Fantomon and character
XP are shown as XP, since they do not come from the realms. Season 6 has no season ladders in this client build.</p></details>
</div>
<script>var PRIMO = {json.dumps(data)};</script>
<script>{JS}</script>
"""
    return layout(f"{item_name(61)} planner",
                  f"Season Progression score, grade and {item_name(61)}s for any season, with the Material Realm swings, tools and days each target costs.",
                  body, "primostars", 0)
