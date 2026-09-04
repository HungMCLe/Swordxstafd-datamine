"""'Where your next point goes' — marginal damage per stat, from the real formula."""
from __future__ import annotations
import html, json


def render(layout, base_tables, charts):
    ladder, B, BA, BC, sr, grp, name = base_tables()
    # everything the client needs to evaluate Damage() for a single hit
    ranks = [{"name": r["rank"], "id": r["internal"], "cap": r["cap"],
              "bem": r["bem"], "bea": r["bea"], "bcr": r["bcr"]} for r in ladder]
    # BaseElementResistance / BaseElementReduce come from the same table
    import build as _b
    be = _b.csvrows("level_prop_battle_extra")
    ix = {c.strip(): i for i, c in enumerate(be[0])}
    BR, BRD = {}, {}
    for r in be[2:]:
        if len(r) > 3 and r[0].strip().isdigit():
            BR[(int(r[0]), int(r[1]))] = int(r[ix["BaseElementResistance"]])
            BRD[(int(r[0]), int(r[1]))] = int(r[ix["BaseElementReduce"]])
    for r in ranks:
        cid = grp.get(r["id"])
        r["ber"] = BR.get((cid, r["cap"]), r["bem"])
        r["bered"] = BRD.get((cid, r["cap"]), r["bea"])
    cfg = json.dumps({"ranks": ranks, "minCrit": 1.3, "fixedDmgLimit": 0.9},
                     ensure_ascii=False).replace("</", "<" + chr(92) + "/")

    default_rank = next((i for i, r in enumerate(ranks) if r["name"] == "Expert III"), 8)
    opts = "".join(
        f'<option value="{i}"{" selected" if i == default_rank else ""}>'
        f'{html.escape(r["name"])}</option>' for i, r in enumerate(ranks))

    body = f"""
<div class="wrap">
<p class="eyebrow">Combat mechanics</p>
<h1>Where your next point goes</h1>
<p class="lede">Every stat feeds the same damage formula, but they enter it in different places — some
multiply, some divide, some sit inside a sum that is already large. That decides which one is worth
more <i>to you right now</i>. Put your numbers in and the chart ranks them.</p>

<div class="calc">
  <div class="calcgrid">
    <label>Your ATK<input type="number" id="atk" value="97000" min="1" step="1000"></label>
    <label>Elemental Mastery<input type="number" id="mast" value="11300" min="0" step="500"></label>
    <label>Elemental Affinity<span class="hint">of the element you attack with</span>
      <input type="number" id="aff" value="0" min="0" step="500"></label>
    <label>Crit Rate <span class="hint">%, as the sheet shows it</span>
      <input type="number" id="cr" value="63" min="0" max="100" step="1"></label>
    <label>Crit DMG bonus <span class="hint">% above normal</span>
      <input type="number" id="cd" value="50" min="0" step="5"></label>
    <label>Your rank<select id="yrank">{opts}</select></label>
    <label>Enemy rank<select id="erank">{opts}</select></label>
    <label>Enemy DEF<input type="number" id="def" value="40000" min="0" step="1000"></label>
    <label>Enemy Elem. RES<input type="number" id="eres" value="0" min="0" step="500"></label>
    <label>Skill coefficient <span class="hint">%</span>
      <input type="number" id="coef" value="204" min="1" step="10"></label>
  </div>
  <p class="calcnote">Defaults are a mid-game Expert III sheet. Nothing is stored or sent; the page
  computes in your browser.</p>
</div>

<h2>Damage gained per +1,000 points</h2>
<p>These four are all raw points, so they compare directly — a thousand of one against a thousand of
another. The winner is whichever term you are furthest from saturating.</p>
<div id="bars"></div>
<p id="verdict" class="verdict"></p>

<h2>Where the crossover is</h2>
<p>Elemental Mastery divides by the enemy's Base Elemental Resistance and then sits inside
<code>1 + affinity + mastery</code>. The bigger that sum grows, the less another point moves it. ATK has
no such ceiling — it appears twice, once as the coefficient's base and once in
<code>ATK/(ATK+DEF)</code> — so its value decays only as <code>1/ATK</code>. Somewhere the two curves
cross.</p>
<div id="cross"></div>
<p id="crosstext" class="verdict"></p>

<h2>Crit Rate against Crit DMG</h2>
<p>Expected damage carries a factor of <code>1 + p x (multiplier - 1)</code>. Raising the rate is worth
the whole crit bonus; raising the bonus is worth only the fraction of hits that crit. So rate leads while
your crit chance is low, and they swap once it is high. The crossover is exactly where
<code>p = 1 / (multiplier - 1)</code> in the units each is bought in.</p>
<div id="critx"></div>
<p id="crittext" class="verdict"></p>

<div class="note">
<p><b>What this computes.</b> One hit through <code>BattleFormulaHandler.Damage</code>, differentiated
with respect to each stat:</p>
<pre><code>D  =  (ATK x coef + flat) x ATK/(ATK+DEF)
      x (1 + affinity/foeBaseElemReduce + mastery/foeBaseElemRes)
      / (1 + foeRes/yourBaseElemMastery + ...)
      x (1 + DmgAddPercent ...) / (1 + DmgReducePercent ...)
      x (1 + p x (critMultiplier - 1))            <i>expected over crits</i>
      x levelOffsetScale</code></pre>
<p>The percentage blocks and the level offset multiply everything equally, so they cancel out of a
comparison between stats and are left at 1 here. They change how hard you hit; they do not change
<i>which stat to buy next</i>.</p>
<p><b>Base Elemental Mastery and Base Elemental Resistance</b> are the hidden per-rank divisors from
<code>level_prop_battle_extra</code>; they jump at every promotion, which is why the same Mastery number
is worth less against a higher-ranked enemy. Crit Rate's flat form divides by
<code>BaseCritRatePercentValue</code> the same way.</p>
<p><b>The crit multiplier has a floor</b> of 1.3 (<code>MinCritPowerPercent</code>), so a crit always
lands at least 30% above a normal hit however much Crit Avoid the target carries.</p>
<p><b>What is deliberately left out:</b> block, dodge and blinding are rolls that zero or divide a hit
rather than scale it, and the flat additive block (<code>DmgAdd</code>, <code>CritPower</code>,
<code>BlockValue</code>) is floored at -90% of base damage. Neither changes the ranking above.</p>
</div>
</div>
<script type="application/json" id="calcdata">{cfg}</script>
<script src="../assets/calc.js" defer></script>
"""
    return layout("Where your next point goes",
                  "Rank ATK, Elemental Mastery, Affinity, Crit Rate and Crit DMG by how much damage each "
                  "actually adds for your current sheet, straight from the game's damage formula.",
                  body, "combat", 1)
