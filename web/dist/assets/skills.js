/* Skills page: class-tree picker + per-skill quality stepper. */
(function () {
  "use strict";

  var QCLASS = {
    Rare: "q-rare", Epic: "q-epic", Legendary: "q-legendary",
    Mythic: "q-mythic", Divine: "q-divine", Immortal: "q-immortal"
  };

  function fmt(val, isPct, isDirect) {
    if (isDirect) return val.toFixed(1).replace(/\.0$/, "") + "%";
    if (isPct) return (val / 100).toFixed(1).replace(/\.0$/, "") + "%";
    return Math.round(val).toLocaleString("en-US");
  }

  /* ---------- quality stepper ---------- */
  function Card(el) {
    var raw = el.getAttribute("data-skill");
    if (!raw) return null;
    var d;
    try { d = JSON.parse(raw); } catch (e) { return null; }
    if (!d.order || !d.order.length) return null;

    var nameEl = el.querySelector(".qname");
    var dl = el.querySelector(".sk-stats");
    var i = 0;

    function render() {
      var q = d.order[i], entry = d.q[q];
      if (nameEl) {
        nameEl.textContent = q;
        nameEl.className = "qname " + (QCLASS[q] || "");
        nameEl.title = "Rank " + entry.rank;
      }
      if (dl) {
        var out = "";
        Object.keys(entry.vals).forEach(function (k) {
          out += '<div class="row"><dt>' + (d.labels[k] || k) + "</dt>" +
                 "<dd>" + fmt(entry.vals[k], d.pct[k], d.direct && d.direct[k]) + "</dd></div>";
        });
        dl.innerHTML = out;
      }
      el.querySelectorAll(".qbtn").forEach(function (b) {
        var dir = parseInt(b.getAttribute("data-dir"), 10);
        b.disabled = (dir < 0 && i === 0) || (dir > 0 && i === d.order.length - 1);
      });
    }

    el.querySelectorAll(".qbtn").forEach(function (b) {
      b.addEventListener("click", function () {
        var n = i + parseInt(b.getAttribute("data-dir"), 10);
        if (n < 0 || n >= d.order.length) return;
        i = n; render();
      });
    });

    render();
    return { setQuality: function (q) { var n = d.order.indexOf(q); if (n >= 0) { i = n; render(); } } };
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
