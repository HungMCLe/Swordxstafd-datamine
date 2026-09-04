/* The whole of BattleFormulaHandler.Damage, evaluated and differentiated. */
(function () {
  "use strict";
  var C;
  try { C = JSON.parse(document.getElementById("calcdata").textContent); }
  catch (e) { return; }

  var GOLD = "#b8863b", BLUE = "#3d6ea8", GREEN = "#4e8a5c", PLUM = "#8a5a86",
      TEAL = "#3f7f7a", RUST = "#a3603f";
  var $ = function (id) { return document.getElementById(id); };
  var IDS = ["atk", "mast", "aff", "kfm", "cr", "cd", "boost", "pve", "acc", "yrank",
             "def", "eres", "aegis", "critres", "dmgres", "pveres", "blockrate", "blockeff",
             "erank", "lvlgap", "coef", "flat", "elem"];

  function n(id) { var v = parseFloat($(id).value); return isFinite(v) ? v : 0; }

  function state() {
    var you = C.ranks[parseInt($("yrank").value, 10)] || C.ranks[0];
    var foe = C.ranks[parseInt($("erank").value, 10)] || C.ranks[0];
    var elemental = $("elem").value === "1";
    return {
      atk: Math.max(1, n("atk")), def: Math.max(0, n("def")),
      mast: elemental ? n("mast") : n("kfm"), aff: elemental ? n("aff") : 0,
      eres: n("eres"), aegis: elemental ? n("aegis") : 0,
      cr: n("cr") / 100, cd: n("cd") / 100, critres: n("critres") / 100,
      boost: n("boost") / 100, pve: n("pve") / 100,
      dmgres: n("dmgres") / 100, pveres: n("pveres") / 100,
      blockrate: n("blockrate") / 100, blockeff: n("blockeff") / 100, acc: n("acc"),
      coef: Math.max(0, n("coef") / 100), flat: Math.max(0, n("flat")),
      gap: n("lvlgap"), elemental: elemental, you: you, foe: foe,
      /* which base divisors apply depends on whether the hit carries an element */
      myMasterBase: elemental ? you.BaseElementMaster : you.BaseKongFuMaster,
      foeMasterBase: elemental ? foe.BaseElementResistance : foe.BaseKongFuResistance,
      myAddBase: you.BaseElementAdd, foeAddBase: foe.BaseElementReduce
    };
  }

  /* ---- the pipeline, term by term ---- */
  function core(s)    { return (s.atk * s.coef + s.flat) * s.atk / (s.atk + s.def); }
  function elemNum(s, mast, aff) { return 1 + aff / s.foeAddBase + mast / s.foeMasterBase; }
  function elemDen(s) { return 1 + s.aegis / s.myAddBase + s.eres / s.myMasterBase; }
  function pctNum(s)  { return 1 + s.boost + s.pve; }
  function pctDen(s)  { return Math.max(0.1, 1 + s.dmgres + s.pveres); }
  function critP(s)   { return Math.min(1, Math.max(0, 0.05 + s.cr - s.critres)); }
  function critM(s)   { return Math.max(C.minCrit, 1 + s.cd - s.critres); }
  function blockB(s)  { return Math.min(1, Math.max(0, s.blockrate - s.acc / s.you.BaseBlockAvoidPercentValue)); }
  function blockDiv(s){ return Math.max(C.minBlock, 1 + s.blockeff); }
  /* block cancels crit: the roll sets IsCrit false, so these are exclusive */
  function expMult(s) {
    var p = critP(s), b = blockB(s), m = critM(s);
    return (1 - b) * ((1 - p) + p * m) + b / blockDiv(s);
  }
  function levelScale(s) {
    var g = Math.abs(Math.round(s.gap));
    var v = C.levelOffset[Math.min(g, C.levelOffset.length - 1)] || 0;
    return s.gap >= 0 ? (1 + v) : 1 / (1 + v);
  }
  function damage(s) {
    return core(s) * (elemNum(s, s.mast, s.aff) / elemDen(s)) *
           (pctNum(s) / pctDen(s)) * expMult(s) * levelScale(s);
  }

  /* ---- d(ln D)/d(stat) ---- */
  function dATK(s)   { return s.coef / (s.atk * s.coef + s.flat) + s.def / (s.atk * (s.atk + s.def)); }
  function dMast(s)  { return (1 / s.foeMasterBase) / elemNum(s, s.mast, s.aff); }
  function dAff(s)   { return (1 / s.foeAddBase) / elemNum(s, s.mast, s.aff); }
  function dAcc(s) {
    /* Accuracy only pays while the enemy can still block */
    if (blockB(s) <= 0) return 0;
    var m = critM(s), p = critP(s), db = -1 / s.you.BaseBlockAvoidPercentValue;
    var dE = db * (-((1 - p) + p * m) + 1 / blockDiv(s));
    return dE / expMult(s);
  }
  function dCritRate(s) {                       /* per +1 percentage point */
    if (critP(s) >= 1) return 0;
    return (1 - blockB(s)) * (critM(s) - 1) * 0.01 / expMult(s);
  }
  function dCritDmg(s) {                        /* per +1 percentage point */
    if (1 + s.cd - s.critres <= C.minCrit) return 0;   /* under the 1.3x floor */
    return (1 - blockB(s)) * critP(s) * 0.01 / expMult(s);
  }
  function dBoost(s) { return 0.01 / pctNum(s); }
  function dPvE(s)   { return 0.01 / pctNum(s); }

  function pct(v, dp) { return (v * 100).toFixed(dp === undefined ? 2 : dp) + "%"; }
  function kfmt(v) {
    if (v >= 1e6) return (v / 1e6).toFixed(2).replace(/\.?0+$/, "") + "M";
    if (v >= 1000) return (v / 1000).toFixed(v >= 10000 ? 0 : 1).replace(/\.0$/, "") + "K";
    return v.toFixed(0);
  }

  function drawBars(el, rows, unit) {
    rows = rows.filter(function (r) { return r.value > 1e-9; })
               .sort(function (a, b) { return b.value - a.value; });
    if (!rows.length) { el.innerHTML = ""; return rows; }
    var mx = rows[0].value, W = 680, LW = 196, BH = 30, GAP = 11;
    var H = rows.length * (BH + GAP) + 8, out = "";
    rows.forEach(function (r, i) {
      var y = i * (BH + GAP) + 4, w = Math.max(1, r.value / mx * (W - LW - 104));
      out += '<text class="barlabel" x="' + (LW - 10) + '" y="' + (y + BH * 0.68) + '" text-anchor="end">' + r.label + '</text>';
      out += '<rect x="' + LW + '" y="' + y + '" width="' + w.toFixed(1) + '" height="' + BH + '" rx="4" fill="' + r.colour + '"/>';
      out += '<text class="barval" x="' + (LW + w + 9).toFixed(1) + '" y="' + (y + BH * 0.68) + '">+' + pct(r.value) + '</text>';
    });
    el.innerHTML = '<figure class="chartbox"><svg viewBox="0 0 ' + W + ' ' + H +
      '" class="chart" role="img" aria-label="Damage gained per ' + unit + '">' + out +
      '</svg><figcaption>damage gained per ' + unit + '</figcaption></figure>';
    return rows;
  }

  function line(el, series, opts) {
    var W = 680, H = 300, pl = 68, pr = 18, pb = 38, pt = 20;
    var xs = [], ys = [];
    series.forEach(function (s) { s.pts.forEach(function (q) { xs.push(q[0]); ys.push(q[1]); }); });
    var x0 = Math.min.apply(null, xs), x1 = Math.max.apply(null, xs);
    var y1 = Math.max.apply(null, ys) * 1.1 || 1;
    var px = function (x) { return pl + (x - x0) / (x1 - x0 || 1) * (W - pl - pr); };
    var py = function (y) { return H - pb - y / y1 * (H - pb - pt); };
    var o = "", i, k;
    for (i = 0; i <= 4; i++) {
      var gy = y1 * i / 4;
      o += '<line class="grid" x1="' + pl + '" x2="' + (W - pr) + '" y1="' + py(gy).toFixed(1) + '" y2="' + py(gy).toFixed(1) + '"/>';
      o += '<text class="tick" x="' + (pl - 8) + '" y="' + (py(gy) + 4).toFixed(1) + '" text-anchor="end">' + opts.yfmt(gy) + '</text>';
    }
    for (k = 0; k <= 5; k++) {
      var gx = x0 + (x1 - x0) * k / 5;
      o += '<text class="tick" x="' + px(gx).toFixed(1) + '" y="' + (H - pb + 18) + '" text-anchor="middle">' + opts.xfmt(gx) + '</text>';
    }
    o += '<line class="axis" x1="' + pl + '" x2="' + (W - pr) + '" y1="' + (H - pb) + '" y2="' + (H - pb) + '"/>';
    series.forEach(function (s) {
      var d = s.pts.map(function (q, m) { return (m ? "L" : "M") + px(q[0]).toFixed(1) + " " + py(q[1]).toFixed(1); }).join(" ");
      o += '<path d="' + d + '" fill="none" stroke="' + s.colour + '" stroke-width="2.2"' + (s.dash ? ' stroke-dasharray="5 4"' : "") + '/>';
    });
    (opts.marks || []).forEach(function (m) {
      if (m.x < x0 || m.x > x1) return;
      o += '<line class="mark" x1="' + px(m.x).toFixed(1) + '" x2="' + px(m.x).toFixed(1) + '" y1="' + pt + '" y2="' + (H - pb) + '"/>';
      o += '<text class="marklabel" x="' + (px(m.x) + 6).toFixed(1) + '" y="' + (pt + 13) + '">' + m.label + '</text>';
    });
    if (opts.ylabel) o += '<text class="axlabel" x="' + pl + '" y="' + (pt - 5) + '">' + opts.ylabel + '</text>';
    if (opts.xlabel) o += '<text class="axlabel" x="' + (W - pr) + '" y="' + (H - 4) + '" text-anchor="end">' + opts.xlabel + '</text>';
    var legend = series.filter(function (s) { return s.name; }).map(function (s) {
      return '<span class="key"><i style="background:' + s.colour + '"></i>' + s.name + '</span>';
    }).join("");
    el.innerHTML = '<figure class="chartbox"><svg viewBox="0 0 ' + W + ' ' + H +
      '" class="chart" role="img" aria-label="' + (opts.ylabel || "chart") + '">' + o +
      '</svg><div class="legend">' + legend + '</div></figure>';
  }

  function crossover(s) {
    var atkVal = dATK(s) * 1000, pts = [], atkLine = [];
    var cross = 1 / dATK(s) - s.foeMasterBase - s.foeMasterBase * s.aff / s.foeAddBase;
    if (!(cross > 0) || !isFinite(cross)) cross = null;
    var top = Math.max(s.mast * 2.2, (cross || 0) * 1.3, 20000), step = top / 140;
    for (var m = 0; m <= top; m += step) {
      pts.push([m, (1 / s.foeMasterBase) / elemNum(s, m, s.aff) * 1000]);
      atkLine.push([m, atkVal]);
    }
    var marks = [{ x: s.mast, label: "you" }];
    if (cross !== null) marks.push({ x: cross, label: "crossover" });
    var word = s.elemental ? "Elemental Mastery" : "Physical Mastery";
    line($("cross"), [
      { name: word, colour: BLUE, pts: pts },
      { name: "ATK at your current " + kfmt(s.atk), colour: GOLD, pts: atkLine, dash: true }
    ], {
      ylabel: "damage per +1,000 points", xlabel: "your " + word,
      yfmt: function (v) { return (v * 100).toFixed(2) + "%"; }, xfmt: kfmt, marks: marks
    });
    $("crosstext").innerHTML = cross === null
      ? word + " stays ahead of ATK across this whole range."
      : "Against a <b>" + s.foe.name + "</b> enemy, " + word + " drops below ATK at about <b>" +
        kfmt(Math.round(cross / 500) * 500) + "</b>. You are at " + kfmt(s.mast) + ", where it is worth " +
        pct(dMast(s) * 1000) + " per thousand — " +
        (s.mast < cross ? "still the better of the two." : "<b>ATK has already overtaken it.</b>");
  }

  function critCross(s) {
    var m = critM(s), rate = [], dmg = [], b = 1 - blockB(s);
    for (var p = 0; p <= 1.0001; p += 0.01) {
      var f = (1 - blockB(s)) * ((1 - p) + p * m) + blockB(s) / blockDiv(s);
      rate.push([p * 100, b * (m - 1) * 0.01 / f * 100]);
      dmg.push([p * 100, b * p * 0.01 / f * 100]);
    }
    var eq = (m - 1) > 0 ? 100 / (m - 1) : 1e9;
    var marks = [{ x: critP(s) * 100, label: "you" }];
    if (eq <= 100) marks.push({ x: eq, label: "they swap" });
    line($("critx"), [
      { name: "+1 point of Crit Rate", colour: PLUM, pts: rate },
      { name: "+1 point of Crit DMG", colour: GOLD, pts: dmg }
    ], {
      ylabel: "expected damage gained", xlabel: "your crit chance",
      yfmt: function (v) { return v.toFixed(2) + "%"; },
      xfmt: function (v) { return v.toFixed(0) + "%"; }, marks: marks
    });
    var p = critP(s);
    var share = p * (m - 1) / ((1 - p) + p * m);
    var lead = p * 100 < eq ? "Crit Rate" : "Crit DMG";
    $("crittext").innerHTML =
      "Crits carry <b>" + pct(share, 0) + "</b> of your damage right now: a " + pct(p, 0) +
      " chance at <b>" + m.toFixed(2) + "x</b>. Per equal percentage point the two are level at a crit " +
      "chance of " + (eq > 100 ? "<b>" + eq.toFixed(0) + "%</b>, which is out of reach"
                              : "<b>" + eq.toFixed(0) + "%</b>") +
      ", so <b>" + lead + "</b> wins the next point — by " +
      (dCritDmg(s) > 0 ? (Math.max(dCritRate(s), dCritDmg(s)) / Math.min(dCritRate(s), dCritDmg(s))).toFixed(2) + "x" : "a wide margin") +
      ". Points are not the unit gear sells them in, though: one substat roll of Crit DMG is usually far " +
      "larger than one of Crit Rate." +
      (1 + s.cd - s.critres <= C.minCrit ? " <b>Your crit multiplier is at the 1.3x floor</b>, so the next points of Crit DMG do nothing at all." : "");
  }

  function redraw() {
    var s = state();
    $("dmgout").textContent = kfmt(damage(s));

    var flatRows = drawBars($("barsflat"), [
      { label: "ATK", value: dATK(s) * 1000, colour: GOLD },
      { label: s.elemental ? "Elemental Mastery" : "Physical Mastery", value: dMast(s) * 1000, colour: BLUE },
      { label: "Affinity", value: dAff(s) * 1000, colour: GREEN },
      { label: "Accuracy", value: dAcc(s) * 1000, colour: TEAL }
    ], "+1,000 points");

    var pctRows = drawBars($("barspct"), [
      { label: "Crit Rate", value: dCritRate(s), colour: PLUM },
      { label: "Crit DMG", value: dCritDmg(s), colour: GOLD },
      { label: "DMG Boost", value: dBoost(s), colour: RUST },
      { label: "PvE Bonus DMG", value: dPvE(s), colour: GREEN }
    ], "+1 percentage point");

    var bits = [];
    if (flatRows.length > 1) {
      bits.push("Of the point stats, <b>" + flatRows[0].label + "</b> leads at " + pct(flatRows[0].value) +
                " per thousand, against " + pct(flatRows[1].value) + " for " + flatRows[1].label + ".");
    }
    if (pctRows.length > 1) {
      bits.push("Of the percentage stats, <b>" + pctRows[0].label + "</b> leads at " + pct(pctRows[0].value) +
                " per point.");
    }
    $("verdict").innerHTML = bits.join(" ");

    critCross(s); crossover(s);
    try { localStorage.setItem("pw_calc2", JSON.stringify(IDS.map(function (i) { return $(i).value; }))); } catch (e) {}
  }

  try {
    var saved = JSON.parse(localStorage.getItem("pw_calc2") || "null");
    if (saved && saved.length === IDS.length) IDS.forEach(function (i, k) { $(i).value = saved[k]; });
  } catch (e) {}
  IDS.forEach(function (i) {
    $(i).addEventListener("input", redraw);
    $(i).addEventListener("change", redraw);
  });
  redraw();
})();
