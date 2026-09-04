/* Skill quality stepper.
   Each .skill[data-skill] carries its own per-quality numbers; the < > buttons
   walk the quality ladder and re-render the stat list. */
(function () {
  "use strict";

  var QCLASS = {
    Rare: "q-rare", Epic: "q-epic", Legendary: "q-legendary",
    Mythic: "q-mythic", Divine: "q-divine", Immortal: "q-immortal"
  };

  function fmt(key, val, isPct) {
    if (isPct) return (val / 100).toFixed(1).replace(/\.0$/, "") + "%";
    return Math.round(val).toLocaleString("en-US");
  }

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
      var q = d.order[i];
      var entry = d.q[q];
      if (nameEl) {
        nameEl.textContent = q;
        nameEl.className = "qname " + (QCLASS[q] || "");
        nameEl.title = "Rank " + entry.rank;
      }
      if (dl) {
        var out = "";
        Object.keys(entry.vals).forEach(function (k) {
          out += '<div class="row"><dt>' + (d.labels[k] || k) + "</dt>" +
                 '<dd>' + fmt(k, entry.vals[k], d.pct[k]) + "</dd></div>";
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
        var dir = parseInt(b.getAttribute("data-dir"), 10);
        var n = i + dir;
        if (n < 0 || n >= d.order.length) return;
        i = n;
        render();
      });
    });

    render();
    return {
      setQuality: function (q) {
        var n = d.order.indexOf(q);
        if (n >= 0) { i = n; render(); }
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
})();
