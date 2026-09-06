/* SPD breakpoints: the timeline rule, interval = 100000 / sqrt(SPD x rankSpeedScale) */
(function () {
  "use strict";
  var C = window.SPD_CFG || { ranks: [] };
  function $(id) { return document.getElementById(id); }
  function fmt(v) {
    v = Math.round(v);
    if (Math.abs(v) >= 1e6) return (v / 1e6).toFixed(2) + "M";
    if (Math.abs(v) >= 1e4) return (v / 1e3).toFixed(1) + "K";
    return String(v);
  }
  function pct(v) { return (v >= 0 ? "+" : "") + (v * 100).toFixed(1) + "%"; }
  function interval(spd, scale) { return 100000 / Math.sqrt(Math.max(1, spd) * scale); }

  function compute() {
    var mine = ($("my_spd").value || "").split(/[,\s;]+/).map(Number).filter(function (x) { return x > 0; });
    var mr = C.ranks[parseInt($("my_rank").value, 10)] || { scale: 1, name: "" };
    var tr = C.ranks[parseInt($("their_rank").value, 10)] || { scale: 1, name: "" };
    var theirs = Math.max(1, Number($("their_spd").value) || 1);
    var N = parseInt($("turns").value, 10) || 10;
    var intB = interval(theirs, tr.scale);
    /* the SPD you need for exactly m of your turns inside N of theirs */
    function needFor(m) { return theirs * (tr.scale / mr.scale) * Math.pow(m / N, 2); }
    var rows = "", firstLine = "";
    mine.forEach(function (spd, i) {
      var intA = interval(spd, mr.scale);
      var turns = Math.floor(N * intB / intA + 1e-9);
      var rate = Math.sqrt(spd * mr.scale / (theirs * tr.scale));
      var first = Math.abs(intA - intB) < 1e-9 ? "coin flip" : (intA < intB ? "you" : "them");
      var next1 = needFor(turns + 1), next2 = needFor(turns + 2), below = needFor(turns);
      rows += "<tr><td class=\"num\"><b>" + fmt(spd) + "</b></td><td>" + first + "</td>" +
        "<td class=\"num\">" + turns + " in their " + N + "</td>" +
        "<td class=\"num\">" + rate.toFixed(2) + "x</td>" +
        "<td class=\"num\">" + fmt(next1) + " <span class=\"hint\">(" + pct(next1 / spd - 1) + ")</span></td>" +
        "<td class=\"num\">" + fmt(next2) + " <span class=\"hint\">(" + pct(next2 / spd - 1) + ")</span></td>" +
        "<td class=\"num\">" + (turns > 0 ? fmt(below) + " <span class=\"hint\">(" + pct(below / spd - 1) + ")</span>" : "&mdash;") + "</td></tr>";
      if (i === 0) {
        var gap = next1 / spd - 1;
        firstLine = "At <b>" + fmt(spd) + "</b> SPD you take <b>" + turns + "</b> turns while a " + fmt(theirs) + " SPD " +
          tr.name + " takes " + N + ", and " + (first === "you" ? "you act first" : first === "them" ? "they act first" : "the first action is a coin flip") +
          ". Your next extra turn needs <b>" + fmt(next1) + "</b> SPD, which is <b>" + pct(gap) + "</b> on what you have" +
          (mr.scale !== tr.scale ? " &mdash; the promotion gap (" + mr.name + " against " + tr.name + ") is already in that number" : "") + ".";
      }
    });
    $("spd_rows").innerHTML = rows || "<tr><td colspan=\"7\">Enter at least one SPD.</td></tr>";
    $("spd_verdict").innerHTML = firstLine;
    /* the general answer: how much higher your SPD must be than theirs for +1, +2 turns over N */
    var lead1 = Math.pow((N + 1) / N, 2) * (tr.scale / mr.scale) - 1;
    var lead2 = Math.pow((N + 2) / N, 2) * (tr.scale / mr.scale) - 1;
    $("spd_note").innerHTML = "In general, over " + N + " of their turns you need <b>" + pct(lead1) +
      "</b> more SPD than the opponent for one extra turn and <b>" + pct(lead2) + "</b> for two" +
      (mr.scale !== tr.scale ? ", with the promotion scales (" + mr.scale + " against " + tr.scale + ") folded in" : "") +
      ". Ties on the timeline are a coin flip, so a lead of a few hundred SPD is not a lead.";
  }
  ["my_spd", "my_rank", "their_spd", "their_rank", "turns"].forEach(function (id) {
    var el = $(id); if (!el) return;
    el.addEventListener("input", compute); el.addEventListener("change", compute);
  });
  compute();
})();
