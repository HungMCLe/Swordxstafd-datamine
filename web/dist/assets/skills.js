/* Skills page: class-tree picker, per-skill rank stepper, character level. */
(function () {
  "use strict";

  var G = {};
  try { G = JSON.parse(document.getElementById("skilldata").textContent); }
  catch (e) { return; }

  var QCLASS = {
    Rare: "q-rare", Epic: "q-epic", Legendary: "q-legendary",
    Mythic: "q-mythic", Divine: "q-divine", Immortal: "q-immortal"
  };

  var level = String(G.defaultLevel);
  var subrank = G.defaultSubrank;
  var CURVES = null;            /* filled by the fetch below */

  function fmt(v, isPct) {
    if (isPct) return (Math.round(v * 10) / 10).toFixed(1).replace(/\.0$/, "") + "%";
    if (Math.abs(v) < 10) return String(Math.round(v * 100) / 100);
    return Math.round(v).toLocaleString("en-US");
  }

  /* ---------- one card ---------- */
  function Card(el) {
    var raw = el.getAttribute("data-skill");
    if (!raw) return null;
    var d;
    try { d = JSON.parse(raw); } catch (e) { return null; }
    if (!d.ranks || !d.ranks.length) return null;

    var nameEl = el.querySelector(".qname");
    var dl = el.querySelector(".sk-stats");
    var i = 0;

    /* rows in the game's own order; a paired flat prop is not a row of its own */
    var paired = {};
    Object.keys(d.pair || {}).forEach(function (k) { paired[d.pair[k]] = true; });
    var props = Object.keys(d.labels)
      .filter(function (k) { return !paired[k]; })
      .sort(function (a, b) { return (d.order[b] || 0) - (d.order[a] || 0); });

    function valueOf(prop, rank) {
      var direct = d.vals[rank];
      if (direct && direct[prop] !== undefined) return direct[prop];
      var mult = d.lmult[rank];
      if (!mult || mult[prop] === undefined) return undefined;
      if (!CURVES) return undefined;
      var lpid = (G.lpidOf[d.lgroup[prop]] || {})[subrank];
      var curve = CURVES[lpid];
      if (!curve) return undefined;
      var row = curve[level];
      var ck = (d.lkey || {})[prop] || prop;   /* curves key on the bare prop name */
      if (!row || row[ck] === undefined) return undefined;
      return row[ck] * mult[prop];
    }

    function render() {
      var rank = String(d.ranks[i]);
      var q = G.rankQuality[rank] || "";
      if (nameEl) {
        nameEl.textContent = G.rankLabels[rank] || rank;
        nameEl.className = "qname " + (QCLASS[q] || "");
        nameEl.title = "Rank " + rank + " of 34";
      }
      if (dl) {
        dl.className = "sk-stats " + (QCLASS[q] || "");
        var out = "";
        props.forEach(function (p) {
          var v = valueOf(p, rank);
          if (v === undefined) return;
          var text = fmt(v, d.pct[p]);
          var mate = (d.pair || {})[p];          /* "204.4%" + "494K" on one row */
          if (mate) {
            var f = valueOf(mate, rank);
            if (f !== undefined) text += " + " + fmt(f, d.pct[mate]);
          }
          out += '<div class="row"><dt>' + d.labels[p] + "</dt><dd>" + text + "</dd></div>";
        });
        dl.innerHTML = out;
      }
      el.querySelectorAll(".qbtn").forEach(function (b) {
        var dir = parseInt(b.getAttribute("data-dir"), 10);
        b.disabled = (dir < 0 && i === 0) || (dir > 0 && i === d.ranks.length - 1);
      });
    }

    el.querySelectorAll(".qbtn").forEach(function (b) {
      b.addEventListener("click", function () {
        var n = i + parseInt(b.getAttribute("data-dir"), 10);
        if (n < 0 || n >= d.ranks.length) return;
        i = n; render();
      });
    });

    render();
    return {
      redraw: render,
      setQuality: function (quality) {
        var first = G.qualityRanks[quality];
        if (first === undefined || first === null) return;
        for (var n = 0; n < d.ranks.length; n++) {
          if (d.ranks[n] >= first) { i = n; break; }
        }
        render();
      }
    };
  }

  var cards = [];
  document.querySelectorAll(".skill[data-skill]").forEach(function (el) {
    var c = Card(el);
    if (c) cards.push(c);
  });

  document.querySelectorAll(".qall").forEach(function (b) {
    b.addEventListener("click", function () {
      var q = b.getAttribute("data-q");
      document.querySelectorAll(".qall").forEach(function (o) {
        o.setAttribute("aria-pressed", String(o === b));
      });
      cards.forEach(function (c) { c.setQuality(q); });
    });
  });

  function redrawAll() { cards.forEach(function (c) { c.redraw(); }); }

  var lvlEl = document.getElementById("lvl");
  if (lvlEl) {
    lvlEl.addEventListener("input", function () {
      var n = parseInt(lvlEl.value, 10);
      if (!n || n < 1) return;
      level = String(n); redrawAll();
    });
  }
  var srEl = document.getElementById("subrank");
  if (srEl) {
    srEl.addEventListener("change", function () { subrank = srEl.value; redrawAll(); });
  }

  /* the growth curves are big and shared, so they live in their own file */
  fetch("../assets/curves.json?v=" + (G.v || ""))
    .then(function (r) { return r.json(); })
    .then(function (j) { CURVES = j; redrawAll(); })
    .catch(function () { /* coefficients still render without them */ });

  /* ---------- keyword tooltips: hover on a pointer, tap on a touchscreen ---- */
  document.addEventListener("click", function (ev) {
    var kw = ev.target.closest ? ev.target.closest(".sk-desc .kw") : null;
    document.querySelectorAll(".kw.open").forEach(function (o) {
      if (o !== kw) o.classList.remove("open");
    });
    if (kw) { kw.classList.toggle("open"); ev.preventDefault(); }
  });
  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape") {
      document.querySelectorAll(".kw.open").forEach(function (o) { o.classList.remove("open"); });
    }
  });

  /* ---------- class tree ---------- */
  var nodes = Array.prototype.slice.call(document.querySelectorAll(".cnode"));

  function select(id, push) {
    var panel = document.getElementById("cls-" + id);
    if (!panel) return;
    document.querySelectorAll(".panel").forEach(function (p) { p.hidden = true; });
    panel.hidden = false;
    nodes.forEach(function (n) {
      n.setAttribute("aria-current", String(n.getAttribute("data-cls") === id));
    });
    if (push && history.replaceState) history.replaceState(null, "", "#" + id);
  }

  nodes.forEach(function (n) {
    n.addEventListener("click", function () { select(n.getAttribute("data-cls"), true); });
  });

  var initial = (location.hash || "").replace(/^#/, "");
  if (!initial || !document.getElementById("cls-" + initial)) {
    initial = nodes.length ? nodes[0].getAttribute("data-cls") : "";
  }
  if (initial) select(initial, false);
})();
