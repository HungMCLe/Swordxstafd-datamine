/* Pets page: per-skill quality stepper (Rare .. Immortal), pet level, character rank. Same maths as skills.js:
   a value is either fixed per rank, or a per-rank multiplier on the level curve the character rank picks. */
(function () {
  "use strict";
  var G = {};
  try { G = JSON.parse(document.getElementById("petdata").textContent); } catch (e) { return; }
  var QCLASS = { Rare: "q-rare", Epic: "q-epic", Legendary: "q-legendary", Mythic: "q-mythic", Divine: "q-divine", Immortal: "q-immortal" };
  var level = String(G.defaultLevel), subrank = G.defaultSubrank, CURVES = null;

  function fmt(v, isPct) {
    if (isPct) return (Math.round(v * 10) / 10).toFixed(1).replace(/\.0$/, "") + "%";
    if (Math.abs(v) < 10) return String(Math.round(v * 100) / 100);
    return Math.round(v).toLocaleString("en-US");
  }
  function Card(el) {
    var d; try { d = JSON.parse(el.getAttribute("data-skill")); } catch (e) { return null; }
    if (!d || !d.ranks || !d.ranks.length) return null;
    var nameEl = el.querySelector(".qname"), dl = el.querySelector(".sk-stats"), costEl = el.querySelector(".qcost"), i = 0;
    var paired = {};
    Object.keys(d.pair || {}).forEach(function (k) { paired[d.pair[k]] = true; });
    var props = Object.keys(d.labels).filter(function (k) { return !paired[k]; }).sort(function (a, b) { return (d.order[b] || 0) - (d.order[a] || 0); });
    function valueOf(prop, rank) {
      var direct = d.vals[rank];
      if (direct && direct[prop] !== undefined) return direct[prop];
      var mult = d.lmult[rank];
      if (!mult || mult[prop] === undefined || !CURVES) return undefined;
      var lpid = (G.lpidOf[d.lgroup[prop]] || {})[subrank], curve = CURVES[lpid];
      if (!curve) return undefined;
      var row = curve[level], ck = (d.lkey || {})[prop] || prop;
      if (!row || row[ck] === undefined) return undefined;
      return row[ck] * mult[prop];
    }
    function render() {
      var rank = String(d.ranks[i]), q = G.rankQuality[rank] || "";
      nameEl.textContent = q || rank; nameEl.className = "qname " + (QCLASS[q] || "");
      nameEl.title = "Rank " + rank + " of 34, the first rank of " + q;
      var cost = d.stepCost && d.stepCost[rank];
      if (costEl) costEl.textContent = i === 0 ? (d.origRank === Number(rank) ? "starting quality" : "") : (cost ? cost.toLocaleString("en-US") + " shards to reach" : "");
      var h = "";
      props.forEach(function (p) {
        var v = valueOf(p, rank);
        if (v === undefined) return;
        if (p === "CD" && v < 0) return;                 /* a passive's -1 CD is "no cooldown" */
        var txt = fmt(v, d.pct[p]), mate = d.pair[p], onCurve = d.lmult[rank] && d.lmult[rank][p] !== undefined;
        if (mate) { var f = valueOf(mate, rank); if (f !== undefined && f) { txt += " + " + fmt(f, d.pct[mate]); onCurve = true; } }
        if (onCurve) txt += ' <span class="hint">at Lv ' + level + "</span>";     /* the flat part sits on the pet-level curve */
        h += '<div class="row"><dt>' + d.labels[p] + "</dt><dd>" + txt + "</dd></div>";
      });
      dl.innerHTML = h; dl.className = "sk-stats " + (QCLASS[q] || "");
      el.querySelectorAll(".qbtn").forEach(function (b) { var dir = Number(b.getAttribute("data-dir")); b.disabled = (dir < 0 && i === 0) || (dir > 0 && i === d.ranks.length - 1); });
    }
    el.querySelectorAll(".qbtn").forEach(function (b) {
      b.addEventListener("click", function () { var n = i + Number(b.getAttribute("data-dir")); if (n < 0 || n >= d.ranks.length) return; i = n; render(); });
    });
    render();
    return { redraw: render, setQuality: function (q) { var first = G.qualityRanks[q]; if (first == null) return; var n = d.ranks.length - 1; for (var k = 0; k < d.ranks.length; k++) if (d.ranks[k] >= first) { n = k; break; } i = n; render(); } };
  }
  var cards = [];
  document.querySelectorAll(".petskill[data-skill]").forEach(function (el) { var c = Card(el); if (c) cards.push(c); });
  function redrawAll() { cards.forEach(function (c) { c.redraw(); }); }
  document.querySelectorAll(".qall").forEach(function (b) {
    b.addEventListener("click", function () {
      var q = b.getAttribute("data-q");
      document.querySelectorAll(".qall").forEach(function (o) { o.setAttribute("aria-pressed", String(o === b)); });
      cards.forEach(function (c) { c.setQuality(q); });
    });
  });
  var lvlEl = document.getElementById("petlvl");
  if (lvlEl) lvlEl.addEventListener("input", function () { var n = parseInt(lvlEl.value, 10); if (!n || n < 1) return; level = String(n); redrawAll(); });
  var srEl = document.getElementById("petsubrank");
  if (srEl) srEl.addEventListener("change", function () { subrank = srEl.value; redrawAll(); });
  fetch("assets/curves.json?v=" + (G.v || "")).then(function (r) { return r.json(); }).then(function (c) { CURVES = c; redrawAll(); }).catch(function () {});
})();
