"""'Where your next point goes' — the whole damage expression, differentiated."""
from __future__ import annotations
import html, json

BASE_COLS = ["BaseEffectDodge", "BaseEffectRate", "BaseElementMaster", "BaseElementResistance",
             "BaseKongFuMaster", "BaseKongFuResistance", "BaseCritRatePercentValue",
             "BaseCritAvoidPercentValue", "BaseBlockPercentValue", "BaseBlockAvoidPercentValue",
             "BaseElementAdd", "BaseElementReduce"]


def render(layout, base_tables, charts):
    import build as _b
    ladder, _B, _BA, _BC, sr, grp, name = base_tables()
    be = _b.csvrows("level_prop_battle_extra")
    ix = {c.strip(): i for i, c in enumerate(be[0])}
    rows = {}
    for r in be[2:]:
        if len(r) > 3 and r[0].strip().isdigit():
            rows[(int(r[0]), int(r[1]))] = r

    ranks = []
    for L in ladder:
        r = rows.get((grp.get(L["internal"]), L["cap"]))
        if not r:
            continue
        entry = {"name": L["rank"], "cap": L["cap"]}
        for c in BASE_COLS:
            try:
                entry[c] = int(r[ix[c]])
            except Exception:
                entry[c] = 1
        ranks.append(entry)

    off = _b.csvrows("fight_level_offset_damage")
    offs = [int(r[1]) / 10000.0 for r in off[2:] if len(r) >= 2 and r[0].strip().isdigit()]

    cfg = json.dumps({"ranks": ranks, "minCrit": 1.3, "minBlock": 1.5,
                      "levelOffset": offs}, ensure_ascii=False).replace("</", "<\\/")
    dflt = next((i for i, r in enumerate(ranks) if r["name"] == "Champion III"), len(ranks) // 2)
    opts = lambda sel: "".join(
        f'<option value="{i}"{" selected" if i == sel else ""}>{html.escape(r["name"])}</option>'
        for i, r in enumerate(ranks))

    def fld(id_, label, val, hint="", step="1"):
        h = f'<span class="hint">{hint}</span>' if hint else ""
        return (f'<label>{label}{h}<input type="number" id="{id_}" value="{val}" step="{step}"></label>')

    body = f"""
<div class="wrap">
<p class="eyebrow">Combat mechanics</p>
<h1>Where your next point goes</h1>
<p class="lede">This evaluates the whole of <code>BattleFormulaHandler.Damage</code> for a sheet you type
in, then differentiates it with respect to every stat that touches the result. It answers which stat buys
the most damage <i>at your current numbers</i> — not in general, because there is no answer in general.</p>

<div class="calc">
  <h3 class="calchead">Your sheet</h3>
  <div class="calcgrid">
    {fld("atk", "ATK", 494000, "", "1000")}
    {fld("mast", "Elemental Mastery", 86600, "", "1000")}
    {fld("aff", "Affinity", 8040, "of the element you attack with", "500")}
    {fld("kfm", "Physical Mastery", 15600, "used instead when the hit has no element", "500")}
    {fld("cr", "Crit Rate", 45, "%", "1")}
    {fld("cd", "Crit DMG", 94.3, "%", "1")}
    {fld("boost", "DMG Boost", 30.8, "%", "1")}
    {fld("pve", "PvE Bonus DMG", 21, "%", "1")}
    {fld("acc", "Accuracy", 37700, "cuts the enemy's block chance", "1000")}
    <label>Your rank<select id="yrank">{opts(dflt)}</select></label>
  </div>

  <h3 class="calchead">The enemy</h3>
  <div class="calcgrid">
    {fld("def", "DEF", 392000, "", "1000")}
    {fld("eres", "Elemental RES", 9380, "", "500")}
    {fld("aegis", "Aegis", 7080, "of your attacking element", "500")}
    {fld("critres", "Crit RES", 29.1, "%", "1")}
    {fld("dmgres", "DMG RES", 24, "%", "1")}
    {fld("pveres", "PvE DMG RES", 20.1, "%", "1")}
    {fld("blockrate", "Block Rate", 11.4, "%", "1")}
    {fld("blockeff", "Block Efficiency", 100, "%", "5")}
    <label>Enemy rank<select id="erank">{opts(dflt)}</select></label>
    {fld("lvlgap", "Your level minus theirs", 0, "", "1")}
  </div>

  <h3 class="calchead">The hit</h3>
  <div class="calcgrid">
    {fld("coef", "Skill coefficient", 204, "%", "10")}
    {fld("flat", "Skill flat damage", 494887, "", "10000")}
    <label>Element<select id="elem">
      <option value="1" selected>elemental</option>
      <option value="0">physical (no element)</option>
    </select></label>
  </div>
  <p class="calcnote">Defaults are a real Champion-era sheet. Everything is computed in your browser;
  nothing is stored or sent. Your entries stay on this device.</p>
</div>

<div class="bignum"><span id="dmgout">&mdash;</span><em>expected damage per hit, averaged over crit and block</em></div>

<h2>Per +1,000 points</h2>
<p>The stats you buy in raw points. These compare directly with each other.</p>
<div id="barsflat"></div>

<h2>Per +1 percentage point</h2>
<p>The stats printed as percentages. These compare with each other &mdash; but <b>not</b> with the chart
above. A thousand ATK and one point of Crit DMG are not the same purchase, and until the equipment tables
are on this site there is no honest exchange rate between them. Read each chart within itself.</p>
<div id="barspct"></div>
<p id="verdict" class="verdict"></p>

<h2>Crit Rate against Crit DMG</h2>
<p>Crit DMG absolutely makes crits hit harder &mdash; it is the entire size of the bonus. The question is
narrower: given one more percentage point, which one? Expected damage carries
<code>1 + p x (multiplier - 1)</code>, so a point of rate is worth the whole bonus while a point of the
bonus is worth only the fraction of hits that crit. They meet at <code>p = 1 / (multiplier - 1)</code>.
That is a statement about equal percentage points, not about which stat matters.</p>
<div id="critx"></div>
<p id="crittext" class="verdict"></p>

<h2>Where Mastery stops winning</h2>
<p>Elemental Mastery divides by the enemy's Base Elemental Resistance and then sits inside
<code>1 + affinity + mastery</code>, so it saturates. ATK appears twice &mdash; once as the coefficient's
base, once in <code>ATK/(ATK+DEF)</code> &mdash; and decays only as <code>1/ATK</code>. They cross.</p>
<div id="cross"></div>
<p id="crosstext" class="verdict"></p>

<div class="note">
<p><b>The expression being evaluated.</b> In the order <code>Damage()</code> applies it:</p>
<pre><code>base   = (ATK x coef + flatDamage) x ATK/(ATK+DEF)
elem   = (1 + affinity/foeBaseElementReduce + mastery/foeBaseElementResistance)
       / (1 + foeAegis/yourBaseElementAdd + foeElementRES/yourBaseElementMastery)
pct    = (1 + DMGBoost + PvEBonusDMG) / (1 + foeDMGRES + foePvEDMGRES)
p      = 0.05 + CritRate - foeCritRES              <i>crit chance</i>
m      = max(1.3, 1 + CritDMG - foeCritRES)        <i>crit multiplier</i>
b      = foeBlockRate - Accuracy/BaseBlockAvoid    <i>block chance</i>
E[mult]= (1-b)((1-p) + p x m) + b / max(1.5, 1 + foeBlockEfficiency)
D      = base x elem x pct x E[mult] x levelOffset</code></pre>
<p><b>Block cancels crit</b> &mdash; the roll sets <code>IsCrit = false</code> whenever it blocks, so the
two are exclusive and the expectation above is not a product of independent factors.</p>
<p><b>Crit RES is subtracted twice:</b> once from the crit chance and again from the multiplier. A
high-Crit-RES target both crits you less and crits you softer.</p>
<p><b>Two floors the game enforces:</b> a crit lands at no less than <code>1.3x</code>
(<code>MinCritPowerPercent</code>), and a block divides by no less than <code>1.5x</code>
(<code>MinBlockValuePercent</code>).</p>
<p><b>The level offset</b> is <code>fight_level_offset_damage</code>: 4% a level, flat at 16% from four
levels up. Above the target you multiply by it, below you divide &mdash; so the same gap costs more than
it pays.</p>
<p><b>Left out on purpose:</b> the flat additive block (<code>DmgAdd</code>, <code>FixedStatusDmgAdd</code>,
the hidden flat <code>CritPower</code>, <code>BlockValue</code>), which is floored at -90% of base damage;
dodge and blinding, which zero a hit rather than scale it; and the profession-versus-profession scalars,
which multiply everything equally and so cannot change the ranking.</p>
</div>
</div>
<script type="application/json" id="calcdata">{cfg}</script>
<script src="../assets/calc.js" defer></script>
"""
    return layout("Where your next point goes",
                  "Evaluate the full Sword x Staff damage formula for your own stats, and see which "
                  "stat — ATK, Elemental Mastery, Affinity, Crit Rate or Crit DMG — buys the most damage next.",
                  body, "combat", 1)
