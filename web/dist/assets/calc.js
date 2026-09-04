/* Marginal damage per stat, differentiated from BattleFormulaHandler.Damage. */
(function () {
  "use strict";
  var C;
  try { C = JSON.parse(document.getElementById("calcdata").textContent); }
  catch (e) { return; }

  var GOLD = "#b8863b", BLUE = "#3d6ea8", GREEN = "#4e8a5c", PLUM = "#8a5a86";
  var $ = function (id) { return document.getElementById(id); };
  var IDS = ["atk", "mast", "aff", "cr", "cd", "yrank", "erank", "def", "eres", "coef"];

  function num(id) { var v = parseFloat($(id).value); return isFinite(v) ? v : 0; }

  function state() {
    var you = C.ranks[parseInt($("yrank").value, 10)] || C.ranks[0];
    var foe = C.ranks[parseInt($("erank").value, 10)] || C.ranks[0];
    return {
      atk: Math.max(1, num("atk")), mast: num("mast"), aff: num("aff"),
      p: Math.min(1, Math.max(0, num("cr") / 100)),
      cdmg: num("cd") / 100,
      def: Math.max(0, num("def")), eres: num("eres"),
      coef: Math.max(0.01, num("coef") / 100),
      you: you, foe: foe
    };
  }

  /* the terms every stat is measured against */
  function elemNum(s, mast, aff) { return 1 + aff / s.foe.bered + mast / s.foe.ber; }
  function critMult(s) { return Math.max(C.minCrit, 1 + s.cdmg); }
  function critFactor(s, p) { return 1 + p * (critMult(s) - 1); }

  /* d(ln D)/d(stat): the fractional damage change per +1 point */
  function dATK(s) { return 1 / s.atk + s.def / (s.atk * (s.atk + s.def)); }
  function dMast(s) { return (1 / s.foe.ber) / elemNum(s, s.mast, s.aff); }
  function dAff(s) { return (1 / s.foe.bered) / elemNum(s, s.mast, s.aff); }
  function dCritV(s) { return (critMult(s) - 1) / (s.you.bcr * critFactor(s, s.p)); }

  function pct(v) { return (v * 100).toFixed(2).replace(/\.?0+$/, "") + "%"; }
  function kfmt(v) { return v >= 1000 ? (v / 1000).toFixed(0) + "K" : v.toFixed(0); }

  function bars(s) {
    var rows = [
      { label: "ATK", value: dATK(s) * 1000, colour: GOLD },
      { label: "Elemental Mastery", value: dMast(s) * 1000, colour: BLUE },
      { label: "Elemental Affinity", value: dAff(s) * 1000, colour: GREEN },
      { label: "Crit Rate (flat value)", value: dCritV(s) * 1000, colour: PLUM }
    ].sort(function (a, b) { return b.value - a.value; });
    var mx = rows[0].value || 1, W = 680, LW = 182, BH = 30, GAP = 11;
    var H = rows.length * (BH + GAP) + 8, out = "";
    rows.forEach(function (r, i) {
      var y = i * (BH + GAP) + 4, w = Math.max(1, r.value / mx * (W - LW - 108));
      out += '<text class="barlabel" x="' + (LW - 10) + '" y="' + (y + BH * 0.68) + '" text-anchor="end">' + r.label + '</text>';
      out += '<rect x="' + LW + '" y="' + y + '" width="' + w.toFixed(1) + '" height="' + BH + '" rx="4" fill="' + r.colour + '"/>';
      out += '<text class="barval" x="' + (LW + w + 9).toFixed(1) + '" y="' + (y + BH * 0.68) + '">+' + pct(r.value) + ' DMG</text>';
    });
    $("bars").innerHTML = '<figure class="chartbox"><svg viewBox="0 0 ' + W + ' ' + H +
      '" class="chart" role="img" aria-label="Damage gained per 1000 points of each stat">' + out +
      '</svg></figure>';
    var best = rows[0], second = rows[1];
    var ratio = second.value > 0 ? (best.value / second.value).toFixed(2) + "x" : "no contest";
    $("verdict").innerHTML = "<b>" + best.label + "</b> is ahead right now — a thousand points buys " +
      pct(best.value) + " more damage, against " + pct(second.value) + " for " + second.label +
      " (" + ratio + ").";
  }

  function line(el, series, opts) {
    var W = 680, H = 300, pl = 66, pr = 18, pb = 38, pt = 20;
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
      var d = s.pts.map(function (q, n) { return (n ? "L" : "M") + px(q[0]).toFixed(1) + " " + py(q[1]).toFixed(1); }).join(" ");
      o += '<path d="' + d + '" fill="none" stroke="' + s.colour + '" stroke-width="2.2"' + (s.dash ? ' stroke-dasharray="5 4"' : "") + '/>';
    });
    (opts.marks || []).forEach(function (m) {
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
    /* solve (1/ber) / (1 + aff/bered + M/ber) = dATK for M */
    var cross = 1 / dATK(s) - s.foe.ber - s.foe.ber * s.aff / s.foe.bered;
    if (!(cross > 0) || !isFinite(cross)) cross = null;
    var top = Math.max(s.mast * 2.4, (cross || 0) * 1.35, 20000), step = top / 140;
    for (var m = 0; m <= top; m += step) {
      var v = (1 / s.foe.ber) / elemNum(s, m, s.aff) * 1000;
      pts.push([m, v]); atkLine.push([m, atkVal]);
    }
    var marks = [{ x: s.mast, label: "you" }];
    if (cross !== null) marks.push({ x: cross, label: "crossover" });
    line($("cross"), [
      { name: "Elemental Mastery", colour: BLUE, pts: pts },
      { name: "ATK at your current " + kfmt(s.atk), colour: GOLD, pts: atkLine, dash: true }
    ], {
      ylabel: "damage per +1,000 points", xlabel: "your Elemental Mastery",
      yfmt: function (v) { return (v * 100).toFixed(1) + "%"; }, xfmt: kfmt, marks: marks
    });
    $("crosstext").innerHTML = cross === null
      ? "Against a <b>" + s.foe.name + "</b> enemy, Mastery stays ahead of ATK across this whole range."
      : "Against a <b>" + s.foe.name + "</b> enemy, Mastery drops below ATK at about <b>" +
        kfmt(Math.round(cross / 500) * 500) + "</b> Mastery. You are at " + kfmt(s.mast) + ", where it is worth " +
        pct(dMast(s) * 1000) + " per thousand — " + (s.mast < cross ? "still the better buy." : "ATK has overtaken it.");
  }

  function critCross(s) {
    var cm = critMult(s), rate = [], dmg = [];
    for (var p = 0; p <= 1.0001; p += 0.01) {
      var f = 1 + p * (cm - 1);
      rate.push([p * 100, ((cm - 1) / f) * 0.01 * 100]);
      dmg.push([p * 100, (p / f) * 0.01 * 100]);
    }
    var eq = (cm - 1) > 0 ? 100 / (cm - 1) : 1e9;
    var marks = [{ x: s.p * 100, label: "you" }];
    if (eq <= 100) marks.push({ x: eq, label: "swap" });
    line($("critx"), [
      { name: "+1 point of Crit Rate", colour: PLUM, pts: rate },
      { name: "+1 point of Crit DMG", colour: GOLD, pts: dmg }
    ], {
      ylabel: "expected damage gained", xlabel: "your crit chance",
      yfmt: function (v) { return v.toFixed(2) + "%"; },
      xfmt: function (v) { return v.toFixed(0) + "%"; }, marks: marks
    });
    var lead = s.p * 100 < eq ? "Crit Rate" : "Crit DMG";
    var where = eq > 100
      ? "Crit Rate leads at every reachable crit chance, because your crit bonus is small."
      : "The two are equal at a crit chance of <b>" + eq.toFixed(0) + "%</b>.";
    $("crittext").innerHTML = "Your crit multiplier is <b>" + cm.toFixed(2) + "x</b>. " + where +
      " At your " + (s.p * 100).toFixed(0) + "%, <b>" + lead + "</b> is the better point." +
      (cm <= C.minCrit + 1e-9 ? " Note your crit bonus is at the 1.3x floor the game enforces, so the first points of Crit DMG do nothing." : "");
  }

  function redraw() {
    var s = state();
    bars(s); crossover(s); critCross(s);
    try { localStorage.setItem("pw_calc", JSON.stringify(IDS.map(function (i) { return $(i).value; }))); } catch (e) {}
  }

  try {
    var saved = JSON.parse(localStorage.getItem("pw_calc") || "null");
    if (saved && saved.length === IDS.length) IDS.forEach(function (i, k) { $(i).value = saved[k]; });
  } catch (e) {}
  IDS.forEach(function (i) {
    $(i).addEventListener("input", redraw);
    $(i).addEventListener("change", redraw);
  });
  redraw();
})();
