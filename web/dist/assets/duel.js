/* Duel simulator: SpeedToTime for the clock, Damage() for every hit. */
(function () {
  "use strict";
  var C;
  try { C = JSON.parse(document.getElementById("dueldata").textContent); }
  catch (e) { return; }

  var $ = function (id) { return document.getElementById(id); };
  var DATA = null, CURVES = null, LOAD = { a: [null, null, null, null, null, null, null, null],
                                           b: [null, null, null, null, null, null, null, null] };
  var FIELDS = ["hp", "atk", "def", "spd", "mast", "kfm", "aff", "eres", "aegis",
                "cr", "cd", "critres", "boost", "dmgres", "blockrate", "blockeff", "acc"];
  var A_COL = "#b8863b", B_COL = "#3d6ea8";

  function n(id) { var el = $(id); if (!el) return 0; var v = parseFloat(el.value); return isFinite(v) ? v : 0; }

  function sheet(side) {
    var r = C.ranks[parseInt($(side + "_rank").value, 10)] || C.ranks[0];
    var s = { rank: r, srank: Math.round(n(side + "_srank")), slevel: Math.round(n(side + "_slevel")) };
    FIELDS.forEach(function (f) { s[f] = n(side + "_" + f); });
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

  /* one attack's expected components; crit/block are rolled by the caller */
  function hitParts(att, def, sk) {
    var row = sk.r[String(att.srank)] || {};
    var coef = ((row.SkillAttack1 || 0) + (row.SkillAttack2 || 0) + (row.SkillAttack3 || 0)) / 100;
    var flat = flatOf(sk, att.srank, att.slevel, att.rank.name);
    var elemental = sk.ele !== "Physical";
    var mast = elemental ? att.mast : att.kfm;
    var aff = elemental ? att.aff : 0;
    var foeMasterBase = elemental ? def.rank.BaseElementResistance : def.rank.BaseKongFuResistance;
    var myMasterBase = elemental ? att.rank.BaseElementMaster : att.rank.BaseKongFuMaster;
    var base = (att.atk * coef + flat) * att.atk / (att.atk + def.def);
    var eNum = 1 + aff / def.rank.BaseElementReduce + mast / foeMasterBase;
    var eDen = 1 + (elemental ? def.aegis / att.rank.BaseElementAdd : 0) + def.eres / myMasterBase;
    var pct = (1 + att.boost) / Math.max(0.1, 1 + def.dmgres);
    return { flatHit: base * (eNum / eDen) * pct, hits: sk.hits || 1 };
  }

  function critChance(att, def) { return Math.min(1, Math.max(0, 0.05 + att.cr - def.critres)); }
  function critMult(att, def) { return Math.max(C.minCrit, 1 + att.cd - def.critres); }
  function blockChance(att, def) {
    return Math.min(1, Math.max(0, def.blockrate - att.acc / att.rank.BaseBlockAvoidPercentValue));
  }
  function blockDiv(def) { return Math.max(C.minBlock, 1 + def.blockeff); }

  var BASIC = { id: 0, name: "Basic attack", ele: "Physical", hits: 1,
                r: { "22": { SkillAttack1: 100, CD: 0 } } };

  function oneFight(A, B, loadA, loadB, rng, wantLog) {
    var sides = [
      { s: A, load: loadA, hp: A.hp, cd: loadA.map(function () { return 0; }), t: interval(A), name: "You" },
      { s: B, load: loadB, hp: B.hp, cd: loadB.map(function () { return 0; }), t: interval(B), name: "Opponent" }
    ];
    var log = [], turns = 0, MAXT = 400;
    while (sides[0].hp > 0 && sides[1].hp > 0 && turns < MAXT) {
      /* identical intervals tie on every action; the engine's own tie-break is not
         in the config, so break it fairly rather than always favouring one side */
      var gap = sides[0].t - sides[1].t;
      var i = Math.abs(gap) < 1e-9 ? (rng() < 0.5 ? 0 : 1) : (gap < 0 ? 0 : 1);
      var me = sides[i], foe = sides[1 - i];
      turns++;
      for (var c = 0; c < me.cd.length; c++) if (me.cd[c] > 0) me.cd[c]--;
      var pick = null, slot = -1;
      for (var k = 0; k < me.load.length; k++) {
        if (me.load[k] && me.cd[k] === 0) { pick = me.load[k]; slot = k; break; }
      }
      if (!pick) pick = BASIC;
      var parts = hitParts(me.s, foe.s, pick);
      var p = critChance(me.s, foe.s), m = critMult(me.s, foe.s);
      var b = blockChance(me.s, foe.s), bd = blockDiv(foe.s);
      var total = 0;
      for (var h = 0; h < parts.hits; h++) {
        var d = parts.flatHit / parts.hits;
        if (rng() < b) d /= bd;                 /* block cancels crit */
        else if (rng() < p) d *= m;
        total += d;
      }
      foe.hp -= total;
      if (slot >= 0) {
        var row = pick.r[String(me.s.srank)] || {};
        me.cd[slot] = Math.max(0, Math.round(row.CD || 0));
      }
      if (wantLog && log.length < 40) {
        log.push({ t: Math.round(me.t), who: me.name, skill: pick.name,
                   dmg: total, left: Math.max(0, foe.hp) });
      }
      me.t += interval(me.s);
    }
    return { winner: sides[0].hp <= 0 ? 1 : (sides[1].hp <= 0 ? 0 : -1), turns: turns, log: log,
             hpA: Math.max(0, sides[0].hp), hpB: Math.max(0, sides[1].hp) };
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

  function run() {
    if (!DATA || !CURVES) return;
    var A = sheet("a"), B = $("mirror").checked ? sheet("a") : sheet("b");
    if ($("mirror").checked) { B = JSON.parse(JSON.stringify(A)); B.rank = A.rank; }
    var loadA = LOAD.a, loadB = $("mirror").checked ? LOAD.a.slice() : LOAD.b;
    var N = 1000, winA = 0, draws = 0, turnList = [], rng = mulberry(12345);
    for (var i = 0; i < N; i++) {
      var r = oneFight(A, B, loadA, loadB, rng, false);
      if (r.winner === 0) winA++; else if (r.winner < 0) draws++;
      turnList.push(r.turns);
    }
    var sample = oneFight(A, B, loadA, loadB, mulberry(999), true);
    turnList.sort(function (x, y) { return x - y; });
    var med = turnList[Math.floor(turnList.length / 2)];
    var pa = winA / N, pb = (N - winA - draws) / N;
    $("result").hidden = false;
    $("oddsa").style.width = (pa * 100).toFixed(1) + "%";
    $("oddsb").style.width = (pb * 100).toFixed(1) + "%";
    $("oddsa").textContent = pa >= 0.08 ? "You " + (pa * 100).toFixed(0) + "%" : "";
    $("oddsb").textContent = pb >= 0.08 ? (pb * 100).toFixed(0) + "% Opponent" : "";
    $("oddstext").innerHTML = "<b>You win " + (pa * 100).toFixed(1) + "%</b> of 1,000 duels" +
      (draws ? ", " + (draws / N * 100).toFixed(1) + "% went the distance without a kill" : "") +
      ". Median fight length <b>" + med + " turns</b>. Your interval is <b>" +
      Math.round(interval(A)) + "</b> against theirs of <b>" + Math.round(interval(B)) +
      "</b>, so you act " + (interval(B) / interval(A)).toFixed(2) + "x as often.";
    var rows = sample.log.map(function (l) {
      return "<tr><td class=num>" + l.t + "</td><td>" + l.who + "</td><td>" + l.skill +
        "</td><td class=num>" + fmt(l.dmg) + "</td><td class=num>" + fmt(l.left) + "</td></tr>";
    }).join("");
    $("logbody").innerHTML = rows || '<tr><td colspan="5">no actions</td></tr>';
    drawHp(sample, A, B);
  }

  function drawHp(sample, A, B) {
    var W = 680, H = 240, pl = 62, pr = 16, pb = 34, pt = 16;
    var hp = { You: A.hp, Opponent: B.hp }, seriesA = [[0, 1]], seriesB = [[0, 1]];
    sample.log.forEach(function (l, i) {
      if (l.who === "You") { hp.Opponent = l.left; } else { hp.You = l.left; }
      seriesA.push([i + 1, Math.max(0, hp.You / A.hp)]);
      seriesB.push([i + 1, Math.max(0, hp.Opponent / B.hp)]);
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

  /* ---------- slot picker ---------- */
  var current = null;
  function paint(side, slot) {
    var el = $(side + "_slot" + slot), sk = LOAD[side][slot];
    if (!sk) { el.className = "slot"; el.innerHTML = '<span class="slotnum">' + (slot + 1) + '</span>'; return; }
    el.className = "slot filled ele-" + sk.ele.toLowerCase();
    el.innerHTML = '<img src="../assets/skills/skill_' + sk.id + '.png" alt="" width="44" height="44" loading="lazy">' +
      '<span class="slotname">' + sk.name + '</span>';
  }
  function openPicker(side, slot) {
    current = { side: side, slot: slot };
    $("pickfind").value = "";
    fillList("");
    $("picker").showModal();
    $("pickfind").focus();
  }
  function fillList(q) {
    q = q.toLowerCase();
    var out = DATA.skills.filter(function (s) {
      return !q || s.name.toLowerCase().indexOf(q) >= 0 || s.cls.toLowerCase().indexOf(q) >= 0;
    }).slice(0, 200).map(function (s) {
      return '<button type="button" class="pick" data-id="' + s.id + '">' +
        '<img src="../assets/skills/skill_' + s.id + '.png" alt="" width="34" height="34" loading="lazy">' +
        '<span class="pn">' + s.name + '</span>' +
        '<span class="pm">' + s.cls + ' &middot; T' + s.tier + ' &middot; ' + s.ele +
        (s.hits > 1 ? " &middot; " + s.hits + " hits" : "") + '</span></button>';
    }).join("");
    $("picklist").innerHTML = out || '<p class="pickempty">Nothing matches.</p>';
  }

  function boot() {
    ["a", "b"].forEach(function (side) {
      for (var i = 0; i < 8; i++) {
        (function (s, k) {
          $(s + "_slot" + k).addEventListener("click", function () { openPicker(s, k); });
        })(side, i);
      }
    });
    $("pickfind").addEventListener("input", function () { fillList(this.value); });
    $("pickclose").addEventListener("click", function () { $("picker").close(); });
    $("pickclear").addEventListener("click", function () {
      if (current) { LOAD[current.side][current.slot] = null; paint(current.side, current.slot); }
      $("picker").close();
    });
    $("picklist").addEventListener("click", function (ev) {
      var b = ev.target.closest ? ev.target.closest(".pick") : null;
      if (!b || !current) return;
      var id = parseInt(b.getAttribute("data-id"), 10);
      LOAD[current.side][current.slot] = DATA.skills.filter(function (s) { return s.id === id; })[0] || null;
      paint(current.side, current.slot);
      $("picker").close();
    });
    $("run").addEventListener("click", run);
    $("mirror").addEventListener("change", function () {
      document.querySelector('.side[data-side="b"]').classList.toggle("dimmed", this.checked);
    });
    document.querySelector('.side[data-side="b"]').classList.add("dimmed");
  }

  Promise.all([
    fetch("../assets/duel.json").then(function (r) { return r.json(); }),
    fetch("../assets/curves.json").then(function (r) { return r.json(); })
  ]).then(function (v) {
    DATA = v[0]; CURVES = v[1];
    boot();
    /* a sensible opening loadout: the first few Techniques of a mid tier */
    var seed = DATA.skills.filter(function (s) { return s.tier === 3; }).slice(0, 4);
    seed.forEach(function (s, i) { LOAD.a[i] = s; LOAD.b[i] = s; paint("a", i); paint("b", i); });
    $("run").disabled = false;
  }).catch(function () {
    $("run").textContent = "Could not load skill data";
  });
})();
