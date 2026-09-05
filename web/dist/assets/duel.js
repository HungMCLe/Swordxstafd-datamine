/* Duel simulator: SpeedToTime for the clock, Damage() for every hit,
   and a scene that plays one fight back action by action. */
(function () {
  "use strict";
  var C;
  try { C = JSON.parse(document.getElementById("dueldata").textContent); }
  catch (e) { return; }

  var $ = function (id) { return document.getElementById(id); };
  var TECH = 4, CHARM = 4;   /* the game gives exactly four of each */
  var DATA = null, CURVES = null, LOAD = { a: [null, null, null, null, null, null, null, null],
                                           b: [null, null, null, null, null, null, null, null] };
  var FIELDS = ["hp", "atk", "def", "spd", "mast", "kfm", "aff", "eres", "aegis",
                "cr", "cd", "critres", "boost", "dmgres", "blockrate", "blockeff", "acc"];
  var A_COL = "#b8863b", B_COL = "#3d6ea8";
  var SIDE = ["a", "b"], WHO = ["You", "Opponent"];

  function n(id) { var el = $(id); if (!el) return 0; var v = parseFloat(el.value); return isFinite(v) ? v : 0; }

  /* PropType -> the sheet field it feeds */
  var PROP2FIELD = {
    ElementMaster: "mast", KongFuMaster: "kfm", ElementResistance: "eres",
    Attack: "atk", MaxHp: "hp", Defence: "def", Speed: "spd",
    CritRatePercent: "cr", CritPowerPercent: "cd",
    CritAvoidPercent: "critres", DmgAddPercent: "boost", DmgReducePercent: "dmgres",
    BlockPercent: "blockrate", BlockValuePercent: "blockeff",
    WindDamageAdd: "aff", WaterDamageAdd: "aff", FireDamageAdd: "aff",
    LightDamageAdd: "aff", DarkDamageAdd: "aff",
    WindDamageReduce: "aegis", WaterDamageReduce: "aegis", FireDamageReduce: "aegis",
    LightDamageReduce: "aegis", DarkDamageReduce: "aegis",
    FinalDamageReducePercent: "dmgres"
  };
  /* flat "value" forms divide by their per-rank base before joining the percentage */
  var PROP2RATIO = {
    CritRatePercentValue: ["cr", "BaseCritRatePercentValue"],
    CritAvoidPercentValue: ["critres", "BaseCritAvoidPercentValue"],
    BlockPercentValue: ["blockrate", "BaseBlockPercentValue"]
  };
  /* props this model has no place for — listed on the page rather than dropped */
  var UNMODELLED = {
    DamageByDamage: "reflected damage", FixedDamageByDamage: "reflected damage",
    SkillCureByHp: "healing", SkillFixedCure: "healing",
    StatusDmgReducePer: "status damage reduction", FixedStatusDmgReduce: "status damage reduction",
    StatusDmgAddPer: "status damage", FixedStatusDmgAdd: "status damage",
    SkillFixedShield: "shields", StatusFixedShieldAdd: "shields",
    ShieldByDefence: "shields", ShieldByTargetHp: "shields",
    EffectRate: "status landing rate", EffectDodge: "status resistance",
    CureAddPercent: "healing", BeCureAddPercent: "healing", CureAdd: "healing"
  };

  function charmValue(entry, srank, slevel, rankName) {
    if (entry.v !== undefined) return entry.v;
    if (entry.m === undefined || !CURVES) return 0;
    var lp = (DATA.lpidOf[String(entry.g)] || {})[rankIdOf(rankName)];
    var curve = CURVES[lp];
    if (!curve) return 0;
    var row = curve[String(slevel)];
    return row && row[entry.k] !== undefined ? row[entry.k] * entry.m : 0;
  }

  function sheet(side) {
    var r = C.ranks[parseInt($(side + "_rank").value, 10)] || C.ranks[0];
    var s = { rank: r, srank: Math.round(n(side + "_srank")), slevel: Math.round(n(side + "_slevel")) };
    FIELDS.forEach(function (f) { s[f] = n(side + "_" + f); });
    /* Charms are passive stats: CalcSkillPassiveProps, added to the typed sheet */
    s.charmAdds = {}; s.ignored = {};
    LOAD[side].slice(TECH).forEach(function (ch) {
      if (!ch || !ch.props) return;
      var row = ch.props[String(s.srank)];
      if (!row) return;
      Object.keys(row).forEach(function (prop) {
        var v = charmValue(row[prop], s.srank, s.slevel, r.name);
        if (!v) return;
        var field = PROP2FIELD[prop];
        if (field) {
          s[field] += v;
          s.charmAdds[field] = (s.charmAdds[field] || 0) + v;
          return;
        }
        var ratio = PROP2RATIO[prop];
        if (ratio) {
          var add = v / r[ratio[1]] * 100;   /* into the sheet's percent units */
          s[ratio[0]] += add;
          s.charmAdds[ratio[0]] = (s.charmAdds[ratio[0]] || 0) + add;
          return;
        }
        s.ignored[UNMODELLED[prop] || prop] = true;
      });
    });
    ["cr", "cd", "critres", "boost", "dmgres", "blockrate", "blockeff"].forEach(function (f) { s[f] /= 100; });
    s.hp = Math.max(1, s.hp); s.atk = Math.max(1, s.atk); s.spd = Math.max(1, s.spd);
    return s;
  }

  /* interval = 100000 / sqrt(SPD x rankSpeedScale) */
  function interval(s) {
    var scale = C.speedScale[s.rank.name] || 1;
    return 100000 / Math.sqrt(Math.max(1, s.spd) * scale);
  }

  /* the flat half of a skill's damage rides the character-level growth curve */
  function flatOf(sk, srank, slevel, rankName) {
    var row = sk.r[String(srank)];
    if (!row || row.fx === undefined || !CURVES) return 0;
    var lp = (DATA.lpidOf[String(row.fg)] || {})[rankIdOf(rankName)];
    var curve = CURVES[lp];
    if (!curve) return 0;
    var c = curve[String(slevel)];
    return c && c.SkillFixedAttack1 !== undefined ? c.SkillFixedAttack1 * row.fx : 0;
  }
  var RANKID = null;
  function rankIdOf(displayName) {
    if (!RANKID) {
      RANKID = {};
      var ids = Object.keys(DATA.lpidOf[Object.keys(DATA.lpidOf)[0]] || {});
      C.ranks.forEach(function (r, i) { RANKID[r.name] = ids[i]; });
    }
    return RANKID[displayName];
  }

  /* one action's numbers. With EC data each hit carries its own coefficient
     prop (SkillAttack1..4); without it, fall back to the summed coefficients. */
  function hitParts(att, def, sk) {
    var row = sk.id === 0 ? { SkillAttack1: 100 } : (sk.r[String(att.srank)] || {});
    var ec = sk.ec || null;
    var elemental = sk.ele !== "Physical";
    var mast = elemental ? att.mast : att.kfm;
    var aff = elemental ? att.aff : 0;
    var foeMasterBase = elemental ? def.rank.BaseElementResistance : def.rank.BaseKongFuResistance;
    var myMasterBase = elemental ? att.rank.BaseElementMaster : att.rank.BaseKongFuMaster;
    var eNum = 1 + aff / def.rank.BaseElementReduce + mast / foeMasterBase;
    var eDen = 1 + (elemental ? def.aegis / att.rank.BaseElementAdd : 0) + def.eres / myMasterBase;
    var pct = (1 + att.boost) / Math.max(0.1, 1 + def.dmgres);
    var scale = att.atk / (att.atk + def.def) * (eNum / eDen) * pct;
    var flat = flatOf(sk, att.srank, att.slevel, att.rank.name);
    var hits = [];
    if (ec && ec.skillType === "Cure") {
      return { hits: [], heal: (row.SkillCureByHp || 0) / 100 * att.hp };
    }
    if (ec && ec.hits && ec.hits.length && ec.hits.every(function (h) { return h.kind === "HitFixed"; })) {
      /* one entry per hit, each with the coefficient the engine reads for it */
      ec.hits.forEach(function (h, i) {
        var coef = (row[h.prop] || 0) / 100;
        hits.push((att.atk * coef + (i === 0 ? flat : 0)) * scale);
      });
    } else {
      var coef = ((row.SkillAttack1 || 0) + (row.SkillAttack2 || 0) + (row.SkillAttack3 || 0) + (row.SkillAttack4 || 0)) / 100;
      var cnt = sk.hits || 1, per = (att.atk * coef + flat) * scale / cnt;
      for (var k = 0; k < cnt; k++) hits.push(per);
    }
    return { hits: hits, heal: 0 };
  }

  function critChance(att, def) { return Math.min(1, Math.max(0, 0.05 + att.cr - def.critres)); }
  function critMult(att, def) { return Math.max(C.minCrit, 1 + att.cd - def.critres); }
  function blockChance(att, def) {
    return Math.min(1, Math.max(0, def.blockrate - att.acc / att.rank.BaseBlockAvoidPercentValue));
  }
  function blockDiv(def) { return Math.max(C.minBlock, 1 + def.blockeff); }

  var BASIC = { id: 0, name: "Basic attack", ele: "Physical", hits: 1, r: {} };

  function cdOf(sk, srank) {
    var row = sk.r[String(srank)] || {};
    return Math.max(0, Math.round(row.CD || 0));
  }

  function oneFight(A, B, loadA, loadB, rng, wantLog, maxRounds) {
    function side(S, load, idx) {
      var techs = load.slice(0, TECH);
      return {
        s: S, load: techs, hp: S.hp, t: interval(S), idx: idx, turns: 0,
        /* InitLastRound: a skill with a cooldown starts ON cooldown unless it is
           ResetCDAtStart — the "Zero Initial CD" keyword — in which case it is ready. */
        cd: techs.map(function (sk) { return !sk ? 0 : (sk.ec && sk.ec.resetCdAtStart ? 0 : cdOf(sk, S.srank)); }),
        uses: techs.map(function () { return 0; })
      };
    }
    var sides = [side(A, loadA, 0), side(B, loadB, 1)];
    var log = [], turns = 0, MAXT = 600, capped = false;
    while (sides[0].hp > 0 && sides[1].hp > 0 && turns < MAXT) {
      if (maxRounds > 0 && Math.min(sides[0].turns, sides[1].turns) >= maxRounds) { capped = true; break; }
      var gap = sides[0].t - sides[1].t;
      var i = Math.abs(gap) < 1e-9 ? (rng() < 0.5 ? 0 : 1) : (gap < 0 ? 0 : 1);
      var me = sides[i], foe = sides[1 - i];
      turns++; me.turns++;
      for (var c = 0; c < me.cd.length; c++) if (me.cd[c] > 0) me.cd[c]--;
      var pick = null, slot = -1;
      for (var k = 0; k < me.load.length; k++) {
        var cand = me.load[k];
        if (!cand || me.cd[k] !== 0) continue;
        var lim = cand.ec ? cand.ec.limitedTimes : -1;
        if (lim > 0 && me.uses[k] >= lim) continue;
        pick = cand; slot = k; break;
      }
      if (!pick) pick = BASIC;
      var parts = hitParts(me.s, foe.s, pick);
      var p = critChance(me.s, foe.s), m = critMult(me.s, foe.s);
      var b = blockChance(me.s, foe.s), bd = blockDiv(foe.s);
      var total = 0, rolled = [];
      parts.hits.forEach(function (d) {
        var crit = false, block = false;
        if (rng() < b) { d /= bd; block = true; }          /* block cancels crit */
        else if (rng() < p) { d *= m; crit = true; }
        total += d;
        if (wantLog) rolled.push({ d: d, crit: crit, block: block });
      });
      foe.hp -= total;
      if (parts.heal) me.hp = Math.min(me.s.hp, me.hp + parts.heal);
      if (slot >= 0) { me.cd[slot] = cdOf(pick, me.s.srank); me.uses[slot]++; }
      if (wantLog) {
        log.push({ t: Math.round(me.t), side: i, who: WHO[i], slot: slot, skill: pick.name,
                   skillId: pick.id, ele: pick.ele, hits: rolled, dmg: total, heal: parts.heal || 0,
                   turn: me.turns, cd: me.cd.slice(),
                   hpA: Math.max(0, sides[0].hp), hpB: Math.max(0, sides[1].hp),
                   left: Math.max(0, foe.hp) });
      }
      me.t += interval(me.s);
    }
    return { winner: sides[0].hp <= 0 ? 1 : (sides[1].hp <= 0 ? 0 : -1), capped: capped,
             turns: turns, log: log, hpA: Math.max(0, sides[0].hp), hpB: Math.max(0, sides[1].hp) };
  }

  function mulberry(seed) {
    return function () {
      seed |= 0; seed = seed + 0x6D2B79F5 | 0;
      var t = Math.imul(seed ^ seed >>> 15, 1 | seed);
      t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
      return ((t ^ t >>> 14) >>> 0) / 4294967296;
    };
  }

  function fmt(v) {
    if (v >= 1e6) return (v / 1e6).toFixed(2) + "M";
    if (v >= 1000) return (v / 1000).toFixed(1) + "K";
    return Math.round(v).toString();
  }

  /* ---------- the run ---------- */
  var PLAY = null;   /* { A, B, sample } for the scene */

  function currentSheets() {
    var A = sheet("a"), B;
    if ($("mirror").checked) { B = JSON.parse(JSON.stringify(A)); B.rank = A.rank; }
    else B = sheet("b");
    var loadB = $("mirror").checked ? LOAD.a.slice() : LOAD.b;
    return { A: A, B: B, loadA: LOAD.a, loadB: loadB };
  }

  function run() {
    if (!DATA || !CURVES) return;
    stopPlayback();
    var cs = currentSheets(), A = cs.A, B = cs.B;
    var N = 1000, winA = 0, draws = 0, turnList = [], rng = mulberry(12345);
    var maxR = parseInt(($("maxrounds") || {}).value, 10) || 0;
    for (var i = 0; i < N; i++) {
      var r = oneFight(A, B, cs.loadA, cs.loadB, rng, false, maxR);
      if (r.winner === 0) winA++; else if (r.winner < 0) draws++;
      turnList.push(r.turns);
    }
    var sample = oneFight(A, B, cs.loadA, cs.loadB, mulberry(999), true, maxR);
    PLAY = { A: A, B: B, sample: sample, i: 0, timer: null };
    turnList.sort(function (x, y) { return x - y; });
    var med = turnList[Math.floor(turnList.length / 2)];
    var pa = winA / N, pb = (N - winA - draws) / N;
    $("result").hidden = false;
    $("oddsa").style.width = (pa * 100).toFixed(1) + "%";
    $("oddsb").style.width = (pb * 100).toFixed(1) + "%";
    $("oddsa").textContent = pa >= 0.08 ? "You " + (pa * 100).toFixed(0) + "%" : "";
    $("oddsb").textContent = pb >= 0.08 ? (pb * 100).toFixed(0) + "% Opponent" : "";
    $("oddstext").innerHTML = "<b>You win " + (pa * 100).toFixed(1) + "%</b> of 1,000 duels" +
      (draws ? ", " + (draws / N * 100).toFixed(1) + "% hit the round cap with both alive" : "") +
      ". Median fight length <b>" + med + " actions</b>. Your interval is <b>" +
      Math.round(interval(A)) + "</b> against theirs of <b>" + Math.round(interval(B)) +
      "</b>, so you act " + (interval(B) / interval(A)).toFixed(2) + "x as often.";
    var rows = sample.log.map(function (l) {
      var hits = l.hits.map(function (h) { return h.block ? "B" : (h.crit ? "C" : "·"); }).join("");
      return "<tr><td class=num>" + l.t + "</td><td class=num>" + l.turn + "</td><td>" + l.who +
        "</td><td>" + l.skill + (l.heal ? " <i>(heals " + fmt(l.heal) + ")</i>" : "") +
        '</td><td class="mono">' + hits + "</td><td class=num>" + fmt(l.dmg) + "</td><td class=num>" + fmt(l.left) + "</td></tr>";
    }).join("");
    $("logbody").innerHTML = rows || '<tr><td colspan="7">no actions</td></tr>';
    $("detail").hidden = false;
    drawHp(sample, A, B);
    charmReport(A);
    sceneReset();
    $("play").disabled = false; $("step").disabled = false;
  }

  var LABEL = { hp: "HP", atk: "ATK", def: "DEF", spd: "SPD", mast: "Elemental Mastery",
                kfm: "Physical Mastery", aff: "Affinity", eres: "Elemental RES", aegis: "Aegis",
                cr: "Crit Rate", cd: "Crit DMG", critres: "Crit RES", boost: "DMG Boost",
                dmgres: "DMG RES", blockrate: "Block Rate", blockeff: "Block Efficiency",
                acc: "Accuracy" };
  var PCTF = { cr: 1, cd: 1, critres: 1, boost: 1, dmgres: 1, blockrate: 1, blockeff: 1 };

  function charmReport(A) {
    var added = Object.keys(A.charmAdds).map(function (f) {
      var v = A.charmAdds[f];
      return "<b>+" + (PCTF[f] ? v.toFixed(1) + "%" : fmt(v)) + "</b> " + (LABEL[f] || f);
    });
    var skipped = Object.keys(A.ignored);
    var html = added.length
      ? "Your Charms add " + added.join(", ") + " to the sheet."
      : "Your Charms add nothing this model uses.";
    if (skipped.length) {
      html += " They also give " + skipped.join(", ") +
        " &mdash; none of which this simulation covers, so those Charms are doing less here than in game.";
    }
    $("charmnote").innerHTML = html;
  }

  function drawHp(sample, A, B) {
    var W = 680, H = 240, pl = 62, pr = 16, pb = 34, pt = 16;
    var seriesA = [[0, 1]], seriesB = [[0, 1]];
    sample.log.forEach(function (l, i) {
      seriesA.push([i + 1, Math.max(0, l.hpA / A.hp)]);
      seriesB.push([i + 1, Math.max(0, l.hpB / B.hp)]);
    });
    var x1 = Math.max(1, seriesA.length - 1);
    var px = function (x) { return pl + x / x1 * (W - pl - pr); };
    var py = function (y) { return H - pb - y * (H - pb - pt); };
    var o = "";
    for (var i = 0; i <= 4; i++) {
      var gy = i / 4;
      o += '<line class="grid" x1="' + pl + '" x2="' + (W - pr) + '" y1="' + py(gy).toFixed(1) + '" y2="' + py(gy).toFixed(1) + '"/>';
      o += '<text class="tick" x="' + (pl - 8) + '" y="' + (py(gy) + 4).toFixed(1) + '" text-anchor="end">' + (gy * 100).toFixed(0) + '%</text>';
    }
    o += '<line class="axis" x1="' + pl + '" x2="' + (W - pr) + '" y1="' + (H - pb) + '" y2="' + (H - pb) + '"/>';
    [[seriesA, A_COL], [seriesB, B_COL]].forEach(function (pair) {
      var d = pair[0].map(function (q, i) { return (i ? "L" : "M") + px(q[0]).toFixed(1) + " " + py(q[1]).toFixed(1); }).join(" ");
      o += '<path d="' + d + '" fill="none" stroke="' + pair[1] + '" stroke-width="2.2"/>';
    });
    o += '<text class="axlabel" x="' + pl + '" y="' + (pt - 3) + '">HP remaining</text>';
    o += '<text class="axlabel" x="' + (W - pr) + '" y="' + (H - 4) + '" text-anchor="end">actions</text>';
    $("hpchart").innerHTML = '<figure class="chartbox"><svg viewBox="0 0 ' + W + ' ' + H +
      '" class="chart" role="img" aria-label="HP over the fight">' + o +
      '</svg><div class="legend"><span class="key"><i style="background:' + A_COL + '"></i>You</span>' +
      '<span class="key"><i style="background:' + B_COL + '"></i>Opponent</span></div></figure>';
  }

  /* ---------- the scene ---------- */
  function rankBadge(srank) {
    var lab = C.rankLabels[String(srank)] || "", q = C.rankQuality[String(srank)] || "";
    var m = /\+(\d+)/.exec(lab);
    return { stars: m ? parseInt(m[1], 10) : 0, quality: q, label: lab };
  }

  function paint(side, slot) {
    var el = $(side + "_slot" + slot), sk = LOAD[side][slot];
    var kind = slot >= TECH ? "charm" : "tech";
    if (!sk) {
      el.className = "slot " + kind;
      el.innerHTML = '<span class="slotnum">' + (slot % TECH + 1) + '</span>';
      return;
    }
    var rb = rankBadge(Math.round(n(side + "_srank")));
    el.className = "slot filled " + kind + " ele-" + sk.ele.toLowerCase() + " q-" + rb.quality.toLowerCase();
    el.innerHTML =
      '<img src="../assets/skills/skill_' + sk.id + '.png" alt="" width="52" height="52" loading="lazy">' +
      '<span class="starbadge" title="' + rb.label + '">' + (rb.stars ? "★" + rb.stars : "★") + '</span>' +
      '<span class="cdov" hidden></span>' +
      '<span class="slotcap">' + sk.name + '</span>' +
      '<span class="slotlv">Lv. ' + Math.round(n(side + "_slevel")) + '</span>';
  }

  function paintAll() {
    SIDE.forEach(function (s) { for (var i = 0; i < TECH + CHARM; i++) paint(s, i); });
    portraits();
  }

  function classOf(side) {
    var tally = {};
    LOAD[side].forEach(function (sk) { if (sk) tally[sk.cls] = (tally[sk.cls] || 0) + 1; });
    var best = null;
    Object.keys(tally).forEach(function (c) { if (!best || tally[c] > tally[best]) best = c; });
    return best;
  }

  function portraits() {
    SIDE.forEach(function (side) {
      var cls = classOf(side), el = $(side + "_portrait"), icon = cls ? C.classIcon[cls] : null;
      var first = LOAD[side].filter(function (x) { return x && x.kind === "Technique"; })[0];
      if (icon) {
        el.innerHTML = '<img src="../assets/skills/class_' + icon + '.png" alt="' + cls + '">';
      } else if (first) {
        el.innerHTML = '<img src="../assets/skills/skill_' + first.id + '.png" alt="">';
      } else {
        el.innerHTML = '<span class="medallion-empty">?</span>';
      }
      $(side + "_class").textContent = cls || "";
      var r = C.ranks[parseInt($(side + "_rank").value, 10)];
      $(side + "_rankname").textContent = r ? r.name : "";
    });
  }

  function hpSet(side, cur, max, animate) {
    var f = $(side + "_hpfill"), pct = Math.max(0, Math.min(1, cur / max));
    f.style.transition = animate ? "width .45s ease" : "none";
    f.style.width = (pct * 100).toFixed(1) + "%";
    f.className = "hpfill" + (pct < 0.25 ? " low" : pct < 0.5 ? " mid" : "");
    $(side + "_hptext").textContent = fmt(Math.max(0, cur)) + " / " + fmt(max);
  }

  function cdPaint(side, cd) {
    for (var k = 0; k < TECH; k++) {
      var el = $(side + "_slot" + k), ov = el.querySelector(".cdov");
      if (!ov) continue;
      var v = cd ? cd[k] : 0;
      ov.hidden = !v; ov.textContent = v || "";
      el.classList.toggle("cooling", !!v);
    }
  }

  function orderStrip(from) {
    if (!PLAY) { $("orderstrip").innerHTML = ""; return; }
    var log = PLAY.sample.log, out = "";
    for (var i = from; i < Math.min(log.length, from + 10); i++) {
      var l = log[i];
      out += '<span class="ord ' + SIDE[l.side] + (i === from ? " now" : "") + '" title="' + l.who + " — " + l.skill + '">' +
        (l.skillId ? '<img src="../assets/skills/skill_' + l.skillId + '.png" alt="">' : '<b>' + l.who[0] + '</b>') +
        '</span>';
    }
    if (from >= log.length) out = '<span class="ordend">end of fight</span>';
    $("orderstrip").innerHTML = out;
  }

  function float(side, text, cls) {
    var box = $(side + "_floats"), el = document.createElement("span");
    el.className = "float " + (cls || "");
    el.textContent = text;
    el.style.left = (18 + Math.random() * 64) + "%";
    box.appendChild(el);
    setTimeout(function () { if (el.parentNode) el.parentNode.removeChild(el); }, 1400);
  }

  function sceneReset() {
    if (!PLAY) return;
    hpSet("a", PLAY.A.hp, PLAY.A.hp, false);
    hpSet("b", PLAY.B.hp, PLAY.B.hp, false);
    var first = PLAY.sample.log[0];
    /* opening cooldowns: what the fight starts with, before anyone acts */
    SIDE.forEach(function (s, idx) {
      var load = idx === 0 ? LOAD.a : ($("mirror").checked ? LOAD.a : LOAD.b);
      var S = idx === 0 ? PLAY.A : PLAY.B;
      cdPaint(s, load.slice(0, TECH).map(function (sk) {
        return !sk ? 0 : (sk.ec && sk.ec.resetCdAtStart ? 0 : cdOf(sk, S.srank));
      }));
      $(s + "_callout").textContent = "";
      $(s + "_floats").innerHTML = "";
    });
    document.querySelectorAll(".slot.acting").forEach(function (e) { e.classList.remove("acting"); });
    $("banner").hidden = true;
    PLAY.i = 0;
    orderStrip(0);
    void first;
  }

  function stepOnce() {
    if (!PLAY) return false;
    var log = PLAY.sample.log;
    if (PLAY.i >= log.length) { finish(); return false; }
    var l = log[PLAY.i], me = SIDE[l.side], foe = SIDE[1 - l.side];
    document.querySelectorAll(".slot.acting").forEach(function (e) { e.classList.remove("acting"); });
    if (l.slot >= 0) {
      var el = $(me + "_slot" + l.slot);
      el.classList.add("acting");
    }
    $(me + "_callout").innerHTML = '<span class="ele-' + l.ele.toLowerCase() + '">' + l.skill + '</span>' +
      '<small>turn ' + l.turn + '</small>';
    /* one floating number per hit, staggered */
    l.hits.forEach(function (h, k) {
      setTimeout(function () {
        float(foe, "−" + fmt(h.d) + (h.crit ? " CRIT" : h.block ? " BLOCK" : ""), h.crit ? "crit" : h.block ? "block" : "");
      }, Math.min(k * 45, 500));
    });
    if (l.heal) float(me, "+" + fmt(l.heal), "heal");
    hpSet("a", l.hpA, PLAY.A.hp, true);
    hpSet("b", l.hpB, PLAY.B.hp, true);
    cdPaint(me, l.cd);
    PLAY.i++;
    orderStrip(PLAY.i);
    if (PLAY.i >= log.length) { setTimeout(finish, 500); return false; }
    return true;
  }

  function finish() {
    if (!PLAY) return;
    var s = PLAY.sample, b = $("banner");
    b.hidden = false;
    b.className = "banner " + (s.winner === 0 ? "wina" : s.winner === 1 ? "winb" : "draw");
    b.innerHTML = s.winner === 0 ? "You win" : s.winner === 1 ? "Opponent wins"
      : (s.capped ? "Round cap reached &mdash; both standing" : "No result");
    stopPlayback(true);
  }

  function stopPlayback(keepButtons) {
    if (PLAY && PLAY.timer) { clearTimeout(PLAY.timer); PLAY.timer = null; }
    $("play").innerHTML = "&#9654; Watch one fight";
    if (!keepButtons) { $("play").disabled = !PLAY; $("step").disabled = !PLAY; }
  }

  function playLoop() {
    if (!PLAY) return;
    var ms = parseInt($("speed").value, 10);
    if (ms === 0) {          /* instant: jump to the final state */
      while (PLAY.i < PLAY.sample.log.length) {
        var l = PLAY.sample.log[PLAY.i]; PLAY.i++;
        hpSet("a", l.hpA, PLAY.A.hp, false); hpSet("b", l.hpB, PLAY.B.hp, false);
        cdPaint(SIDE[l.side], l.cd);
      }
      orderStrip(PLAY.i); finish(); return;
    }
    if (!stepOnce()) return;
    PLAY.timer = setTimeout(playLoop, ms);
  }

  function togglePlay() {
    if (!PLAY) return;
    if (PLAY.timer) { stopPlayback(); return; }
    if (PLAY.i >= PLAY.sample.log.length) sceneReset();
    $("play").innerHTML = "&#10074;&#10074; Pause";
    playLoop();
  }

  /* ---------- slot picker ---------- */
  var current = null;
  function openPicker(side, slot) {
    current = { side: side, slot: slot };
    $("pickfind").value = "";
    fillList("");
    $("pickfind").placeholder = "Search " + (slot >= TECH ? "Charms" : "Techniques") + "…";
    $("pickele").hidden = slot >= TECH;
    $("picker").showModal();
    $("pickfind").focus();
  }
  function fillList(q) {
    q = q.toLowerCase();
    var want = current && current.slot >= TECH ? "Charm" : "Technique";
    var wantCls = $("pickclass").value, wantEle = $("pickele").value;
    var matches = DATA.skills.filter(function (s) {
      if (s.kind !== want) return false;
      if (wantCls && s.cls !== wantCls) return false;
      if (wantEle && want === "Technique" && s.ele !== wantEle) return false;
      return !q || s.name.toLowerCase().indexOf(q) >= 0 || s.cls.toLowerCase().indexOf(q) >= 0;
    });
    $("pickcount").textContent = matches.length + " of " +
      DATA.skills.filter(function (s) { return s.kind === want; }).length;
    var out = matches.slice(0, 200).map(function (s) {
      var on = LOAD[current.side].some(function (x, k) { return x && x.id === s.id && k !== current.slot; });
      var cdrow = s.r && s.r["22"] ? s.r["22"].CD : 0;
      return '<button type="button" class="pick' + (on ? " equipped" : "") + '" data-id="' + s.id + '">' +
        '<img src="../assets/skills/skill_' + s.id + '.png" alt="" width="34" height="34" loading="lazy">' +
        '<span class="pn">' + s.name + '</span>' +
        '<span class="pm">' + s.cls + ' &middot; T' + s.tier +
        (s.kind === "Technique"
          ? ' &middot; ' + s.ele + (s.hits > 1 ? ' &middot; ' + s.hits + ' hits' : '') +
            (cdrow ? ' &middot; CD ' + cdrow : ' &middot; no CD') +
            (s.ec && s.ec.resetCdAtStart ? ' &middot; ready at start' : '')
          : ' &middot; Charm') +
        (on ? ' &middot; <b>equipped &mdash; picking moves it here</b>' : '') + '</span></button>';
    }).join("");
    $("picklist").innerHTML = out || '<p class="pickempty">Nothing matches.</p>';
  }

  function buildFilters() {
    var byTier = {}, eles = {};
    DATA.skills.forEach(function (s) {
      (byTier[s.tier] = byTier[s.tier] || {})[s.cls] = true;
      if (s.kind === "Technique") eles[s.ele] = true;
    });
    var html = '<option value="">All classes</option>';
    Object.keys(byTier).sort().forEach(function (t) {
      html += '<optgroup label="Tier ' + t + '">';
      Object.keys(byTier[t]).sort().forEach(function (c) {
        html += '<option value="' + c + '">' + c + '</option>';
      });
      html += '</optgroup>';
    });
    $("pickclass").innerHTML = html;
    var eh = '<option value="">Any element</option>';
    ["Physical", "Wind", "Water", "Fire", "Light", "Dark"].forEach(function (e) {
      if (eles[e]) eh += '<option value="' + e + '">' + e + '</option>';
    });
    $("pickele").innerHTML = eh;
  }

  function invalidate() {
    /* any change to loadout or sheet makes the last run stale */
    stopPlayback();
    PLAY = null;
    $("play").disabled = true; $("step").disabled = true;
    $("banner").hidden = true;
    $("orderstrip").innerHTML = '<span class="ordend">run the duel to see the order of play</span>';
    document.querySelectorAll(".slot.acting").forEach(function (e) { e.classList.remove("acting"); });
    SIDE.forEach(function (s) { cdPaint(s, null); $(s + "_callout").textContent = ""; });
    var A = sheet("a"), B = $("mirror").checked ? A : sheet("b");
    hpSet("a", A.hp, A.hp, false); hpSet("b", B.hp, B.hp, false);
    portraits();
  }

  function boot() {
    buildFilters();
    $("pickclass").addEventListener("change", function () { fillList($("pickfind").value); });
    $("pickele").addEventListener("change", function () { fillList($("pickfind").value); });
    SIDE.forEach(function (side) {
      for (var i = 0; i < TECH + CHARM; i++) {
        (function (s, k) {
          $(s + "_slot" + k).addEventListener("click", function () { openPicker(s, k); });
        })(side, i);
      }
    });
    $("pickfind").addEventListener("input", function () { fillList(this.value); });
    $("pickclose").addEventListener("click", function () { $("picker").close(); });
    $("pickclear").addEventListener("click", function () {
      if (current) { LOAD[current.side][current.slot] = null; paint(current.side, current.slot); invalidate(); }
      $("picker").close();
    });
    $("picklist").addEventListener("click", function (ev) {
      var b = ev.target.closest ? ev.target.closest(".pick") : null;
      if (!b || !current) return;
      var id = parseInt(b.getAttribute("data-id"), 10);
      var picked = DATA.skills.filter(function (s) { return s.id === id; })[0] || null;
      /* the same skill cannot occupy two slots, so move it rather than duplicate */
      if (picked) {
        LOAD[current.side].forEach(function (x, k) {
          if (x && x.id === picked.id && k !== current.slot) {
            LOAD[current.side][k] = null; paint(current.side, k);
          }
        });
      }
      LOAD[current.side][current.slot] = picked;
      paint(current.side, current.slot);
      invalidate();
      $("picker").close();
    });
    $("run").addEventListener("click", run);
    $("play").addEventListener("click", togglePlay);
    $("step").addEventListener("click", function () { stopPlayback(); if (PLAY && PLAY.i >= PLAY.sample.log.length) sceneReset(); stepOnce(); });
    $("reset").addEventListener("click", function () {
      try { localStorage.removeItem("pw_duel"); } catch (e) {}
      location.reload();
    });
    $("mirror").addEventListener("change", function () {
      document.querySelector('.fighter[data-side="b"]').classList.toggle("dimmed", this.checked);
      document.querySelector('.duelstats details:nth-of-type(2)').classList.toggle("dimmed", this.checked);
      invalidate();
    });
    document.querySelector('.fighter[data-side="b"]').classList.add("dimmed");
    document.querySelector('.duelstats details:nth-of-type(2)').classList.add("dimmed");
    /* sheet edits: repaint level/rank badges and mark the run stale */
    document.querySelectorAll(".duelstats input, .duelstats select").forEach(function (el) {
      el.addEventListener("change", function () { paintAll(); invalidate(); });
    });
  }

  Promise.all([
    fetch("../assets/duel.json?v=" + (C.v || "")).then(function (r) { return r.json(); }),
    fetch("../assets/curves.json?v=" + (C.v || "")).then(function (r) { return r.json(); })
  ]).then(function (v) {
    DATA = v[0]; CURVES = v[1];
    boot();
    /* a sensible opening loadout: an Archmage kit, since the default sheet is one */
    var names = ["Divine Wrath", "Aqua Vortex", "Howling Hurricane", "Fire Blast",
                 "Rapid Cast", "Frost Guard", "Incarnation of Light", "Radiant Sear"];
    names.forEach(function (nm, i) {
      var s = DATA.skills.filter(function (x) { return x.name === nm; })[0];
      if (s) { LOAD.a[i] = s; LOAD.b[i] = s; }
    });
    paintAll();
    invalidate();
    $("run").disabled = false;
  }).catch(function () {
    $("run").textContent = "Could not load skill data";
  });
})();
