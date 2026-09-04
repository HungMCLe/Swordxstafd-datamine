#!/usr/bin/env python3
"""Purrwikimania — entry point. Builds every page into web/dist."""
from __future__ import annotations
import html, json, shutil, sys
from pathlib import Path

from build import (layout, write, load_tiers, base_tables, L, csvrows,
                   OUT, DIST, page_home, page_method, page_combat_index, page_damage)
import skills_page
import calc_page
import charts

sys.stdout.reconfigure(encoding="utf-8")


# ------------------------------------------------------------------ elemental
def page_elemental(ladder):
    # BaseElementMaster explodes with rank while BaseElementAdd barely moves, so the
    # useful picture is their ratio: how many points of Mastery equal one of Affinity.
    walls = charts.line_chart(
        [{"name": "points of Mastery equal to one point of Affinity",
          "colour": "#3d6ea8",
          "points": [(i, r["bem"] / r["bea"]) for i, r in enumerate(ladder) if r["bea"]]}],
        ylabel="Mastery needed to match 1 Affinity", xlabel="character rank",
        xticks=[i for i in range(0, len(ladder), 6)],
        xfmt=lambda v: ladder[int(round(v))]["rank"] if 0 <= int(round(v)) < len(ladder) else "",
        yfmt=lambda v: f"{v:.0f}x",
        marks=[{"x": 9, "label": "Champion"}],
        caption="Affinity divides by BaseElementAdd, Mastery by BaseElementMaster. The first grows "
                "from 1,952 to 37,128 across the whole ladder; the second from 141 to 30 million. "
                "They are equal around Elite, and by Champion one point of Affinity is worth "
                "thirteen of Mastery.")
    walls = charts.line_chart(
        [{"name": "Base Elemental Mastery (the divisor)", "colour": "#3d6ea8",
          "points": [(i, r["bem"]) for i, r in enumerate(ladder)]},
         {"name": "Base Elemental Add (Affinity divisor)", "colour": "#4e8a5c",
          "points": [(i, r["bea"]) for i, r in enumerate(ladder)]}],
        ylabel="divisor", xlabel="character rank",
        xticks=[i for i in range(0, len(ladder), 6)],
        xfmt=lambda v: ladder[int(round(v))]["rank"] if 0 <= int(round(v)) < len(ladder) else "",
        yfmt=lambda v: f"{v/1000:.0f}K" if v >= 1000 else f"{v:.0f}",
        caption="Both divisors climb every promotion, so the same raw Mastery is worth steadily "
                "less. Affinity divides by the lower of the two throughout.")
    rows, prev = [], None
    for e in ladder:
        jump = f"&times;{e['bem']/prev:.2f}" if prev else "&mdash;"
        cls = ' class="hi"' if prev and e["bem"] / prev > 4 else ""
        rows.append(f'<tr{cls}><td>{html.escape(e["rank"])}</td><td class="num">{e["cap"]}</td>'
                    f'<td class="num">{e["bem"]:,}</td><td class="num">{jump}</td></tr>')
        prev = e["bem"]
    table = "\n".join(rows)
    body = f"""
<div class="wrap">
<p class="eyebrow">Combat mechanics</p>
<h1>Elemental Mastery &amp; Affinity</h1>
<p class="lede">Your Elemental Mastery number is never used raw. The game divides it by a hidden value
that grows every rank &mdash; which is why the same gear feels strong at the end of a rank and weak at the
start of the next.</p>

<h2>The formula</h2>
<p>Elemental damage is multiplied by a ratio: your offence over their defence.</p>
<pre><code>            1 + (YourXAffinity / TheirBaseElemAdd) + (YourElemMastery / TheirBaseElemMastery)
ElemMult = ---------------------------------------------------------------------------------
            1 + (TheirXRES     / YourBaseElemAdd)  + (TheirElemRES    / YourBaseElemMastery)</code></pre>
<p>where <code>X</code> is the attack's element. Two layers stack: a <b>per-element Affinity</b> and a
<b>general Mastery</b>. Physical hits use Physical Mastery and Physical RES through the identical structure.</p>

<h2>What "Base Elemental Mastery" is</h2>
<p>It is a stat, but you never see it &mdash; the game's own config marks it <code>Catalog = Hide</code>.
It is a per-rank, per-level constant: the expected value for a character at that point in the game.
Your actual Mastery is scored against it.</p>
<div class="note">
<p><b>Because it appears on both sides, equal level plus equal investment is exactly neutral.</b>
Across all 1,710 rows of the table, Base Mastery and Base RES are always identical, so two evenly matched
characters produce a multiplier of exactly <code>&times;1.000</code>. Advantage only appears when one side
beats the expected value harder than the other.</p>
</div>

<h2>Worked at one rank</h2>
<p>At Expert III (level 100) the base value is 10,987:</p>
<div class="tablewrap"><table>
<thead><tr><th>Situation</th><th class="num">Your Mastery</th><th class="num">Their RES</th><th class="num">Multiplier</th></tr></thead>
<tbody>
<tr><td>Both at the expected value</td><td class="num">10,987</td><td class="num">10,987</td><td class="num">&times;1.00</td></tr>
<tr><td>You triple it, they don't</td><td class="num">33,000</td><td class="num">10,987</td><td class="num">&times;2.00</td></tr>
<tr><td>Both triple it</td><td class="num">33,000</td><td class="num">33,000</td><td class="num">&times;1.00</td></tr>
<tr><td>They triple it, you don't</td><td class="num">10,987</td><td class="num">33,000</td><td class="num">&times;0.50</td></tr>
</tbody></table></div>

<h2>Base Elemental Mastery by rank</h2>
{walls}
<p>The value at each rank's level cap. Base Elemental RES is identical at every row.</p>
<div class="tablewrap"><table>
<thead><tr><th>Rank</th><th class="num">Level cap</th><th class="num">Base Elemental Mastery</th><th class="num">vs previous</th></tr></thead>
<tbody>
{table}
</tbody></table><caption>Source: <code>level_prop_battle_extra</code>, joined to <code>player_subrank</code> and <code>role_prop_group</code>.</caption></div>

<h2>The Champion wall</h2>
<p>One transition dwarfs the rest. Promoting out of Expert III multiplies the base value by
<b>&times;4.56 at the same level</b> (10,987 &rarr; 50,061), and by the time you reach Champion I's own cap it
has risen <b>&times;7.53</b> overall. Every other rank-up in the game falls between &times;1.04 and &times;1.7.</p>
<div class="note warn">
<p><b>Be precise about which number you quote.</b> The &times;7.53 figure spans the promotion <i>and</i> ten
levels of growth. The promotion alone, measured at a fixed level 100, is &times;4.56. Both are real; they
answer different questions.</p>
<p>Two promotions actually <i>lower</i> the base value &mdash; Elite III &rarr; Expert I (&times;0.94) and
Paragon III &rarr; Saint I (&times;0.90) &mdash; which makes existing gear relatively stronger.</p>
</div>

<h2>A tunable the developers left in</h2>
<p>The normalisation is written as <code>(rating / ownBase) &times; (ownBase / theirBase)^k</code> with
<code>k</code> hardcoded to <code>1.0</code>. As written that exponent is a no-op, but it is plainly a dial
for how much the level gap matters. If elemental scaling ever shifts without a stat change, this is where.</p>
</div>
"""
    return layout("Elemental Mastery", "How Sword x Staff scores Elemental Mastery against a hidden per-rank value, with the full base table for every rank.", body, "combat", 1)


# ------------------------------------------------------------------ speed
def page_speed():
    # only the RATIO of two SPDs matters, so plot that — absolute SPD runs into
    # the hundreds of thousands and an absolute axis would be misleading.
    spd = charts.line_chart(
        [{"name": "turns you take per turn of theirs", "colour": "#3d6ea8",
          "points": [(r / 20.0, (r / 20.0) ** 0.5) for r in range(20, 321)]},
         {"name": "what people expect (linear)", "colour": "#9a938a", "dash": True,
          "points": [(r / 20.0, r / 20.0) for r in range(20, 81)]}],
        ylabel="your turns per their turn", xlabel="your SPD divided by theirs",
        ymax=4.2, xticks=[1, 2, 4, 6, 9, 12, 16],
        yfmt=lambda v: f"{v:.1f}x", xfmt=lambda v: f"{v:.0f}x",
        marks=[{"x": 4, "label": "2x turns"}, {"x": 9, "label": "3x turns"}],
        caption="Scale-free on purpose: 200 against 100 and 400,000 against 200,000 are the same "
                "fight. Only the ratio counts, so raw SPD numbers never saturate or cap.")
    spd = charts.line_chart(
        [{"name": "turns taken, against a 100-SPD unit", "colour": "#3d6ea8",
          "points": [(x, (x / 100.0) ** 0.5) for x in range(100, 10001, 100)]},
         {"name": "if SPD were linear", "colour": "#9a938a", "dash": True,
          "points": [(x, x / 100.0) for x in range(100, 1101, 100)]}],
        ylabel="relative turns", xlabel="SPD", ymax=10.5,
        yfmt=lambda v: f"{v:.0f}x", xfmt=lambda v: f"{v/1000:.0f}K" if v >= 1000 else f"{v:.0f}",
        marks=[{"x": 400, "label": "2x"}, {"x": 1600, "label": "4x"}],
        caption="Doubling your turn rate costs four times the SPD; tripling it costs nine times.")
    body = f"""
<div class="wrap">
<p class="eyebrow">Combat mechanics</p>
<h1>SPD and turn order</h1>
<p class="lede">Speed is not initiative. The battle runs on a timeline, and SPD buys how often you act &mdash;
on a square root, so it gets expensive fast.</p>

<h2>The battle is a timeline</h2>
<p>Every unit sits in a queue ordered by the moment it will next act. The engine takes whoever is earliest,
lets them act, then re-inserts them at <code>now + their interval</code>. A faster unit's clock advances in
smaller steps, so it keeps returning to the front.</p>
<pre><code>interval = 100000 / sqrt(SPD x rankSpeedScale)</code></pre>
<p>A smaller interval means acting sooner and more often. SPD is floored at 1.</p>

<h2>The consequence</h2>
<p>Because SPD sits under a square root, relative turn frequency is:</p>
<pre><code>your actions / their actions = sqrt(your SPD / their SPD)</code></pre>
<p><b>To act twice as often you need four times the SPD.</b></p>
{spd}

<div class="tablewrap"><table>
<thead><tr><th class="num">SPD</th><th class="num">Interval</th><th>Turns vs a 100-SPD unit</th></tr></thead>
<tbody>
<tr><td class="num">100</td><td class="num">10,000</td><td>1&times;</td></tr>
<tr><td class="num">400</td><td class="num">5,000</td><td>2&times;</td></tr>
<tr><td class="num">900</td><td class="num">3,333</td><td>3&times;</td></tr>
<tr><td class="num">1,600</td><td class="num">2,500</td><td>4&times;</td></tr>
<tr><td class="num">10,000</td><td class="num">1,000</td><td>10&times;</td></tr>
</tbody></table></div>

<h2>What extra turns cost</h2>
<p>Starting from 65,200 SPD, a realistic late-Expert value:</p>
<div class="tablewrap"><table>
<thead><tr><th>Gain</th><th class="num">SPD needed</th><th class="num">Increase</th></tr></thead>
<tbody>
<tr><td>+10% actions</td><td class="num">78,892</td><td class="num">+21%</td></tr>
<tr><td>+20% actions</td><td class="num">93,888</td><td class="num">+44%</td></tr>
<tr><td>+50% actions</td><td class="num">146,700</td><td class="num">+125%</td></tr>
<tr><td>+100% actions</td><td class="num">260,800</td><td class="num">+300%</td></tr>
</tbody></table></div>

<h2>The rank multiplier</h2>
<p><code>rankSpeedScale</code> sits <i>inside</i> the square root, which makes it a large lever. It is constant
within a rank, so it cancels out in same-rank fights and only matters across ranks.</p>
<div class="tablewrap"><table>
<thead><tr><th>Rank band</th><th class="num">Scale</th><th class="num">Effect on turn rate</th></tr></thead>
<tbody>
<tr><td>No Rank &rarr; Master</td><td class="num">1</td><td class="num">baseline</td></tr>
<tr><td>Paragon</td><td class="num">10</td><td class="num">&times;3.16</td></tr>
<tr><td>Saint and above</td><td class="num">150</td><td class="num">&times;12.25</td></tr>
</tbody></table><caption>Source: <code>fight_rank_offset_damage</code>, <code>SpeedScale</code> column.</caption></div>

<h2>Two things that ignore SPD entirely</h2>
<p>Status effects can move a unit's next action time directly, bypassing the stat: a positive
<code>RoundIntervalPercent</code> advances the turn, a negative one delays it, and <b>zero makes the unit act
immediately</b>. Skill cooldowns are a separate flat system that SPD does not reduce.</p>

<div class="note">
<p><b>On the community formula.</b> A widely shared version writes each unit's share of total actions as
<code>2R &times; sqrt(s) / sum(sqrt(s))</code> across both teams. That is correct &mdash; it is the fight-level
integral of the same rule, and the ratio it produces, <code>sqrt(s/e)</code>, matches the code exactly.
Two caveats: it omits <code>rankSpeedScale</code> (harmless within one rank), and the "2R action pool" is a
modelling convenience rather than something the code computes.</p>
</div>
</div>
"""
    return layout("SPD and turn order", "Sword x Staff runs an active-time battle; SPD buys turn frequency on a square root. The formula, the real costs, and the rank multiplier.", body, "combat", 1)


# ------------------------------------------------------------------ crit
def page_crit(ladder):
    rows, prev = [], None
    for e in ladder:
        worth = 1000 / e["bcr"] * 100
        cls = ' class="hi"' if prev and e["bcr"] / prev > 4 else ""
        rows.append(f'<tr{cls}><td>{html.escape(e["rank"])}</td><td class="num">{e["cap"]}</td>'
                    f'<td class="num">{e["bcr"]:,}</td><td class="num">+{worth:.2f}%</td></tr>')
        prev = e["bcr"]
    table = "\n".join(rows)
    body = f"""
<div class="wrap">
<p class="eyebrow">Combat mechanics</p>
<h1>Crit, Block and the flat "value" stats</h1>
<p class="lede">Several stats come in two forms &mdash; a percentage and a flat "K" value. They are not
interchangeable. The flat version is divided by a hidden per-rank number, and loses most of its worth
as you climb.</p>

<h2>The crit roll</h2>
<pre><code>critChance = 0.05
           + ( CritRate%      + CritRateValue      / BaseCritRateValue )
           - ( theirCritAvoid% + theirCritAvoidValue / theirBaseCritAvoidValue )</code></pre>
<p>Everyone has a hidden <b>5% base crit</b>. Your percentage stat adds directly. Your flat value is divided
by a per-rank base first &mdash; the same normalisation Elemental Mastery uses.</p>
<p>Crit damage is <code>max(MinCritPower, 1 + CritDMG% &minus; theirCritAvoid%)</code>, with the floor set to
1.3 in <code>game_settings</code>. <b>Crit and Block are mutually exclusive</b>: a blocked hit cannot crit.</p>

<h2>What "+1K Crit" is really worth</h2>
<div class="tablewrap"><table>
<thead><tr><th>Rank</th><th class="num">Level cap</th><th class="num">Base Crit Value</th><th class="num">+1,000 gives</th></tr></thead>
<tbody>
{table}
</tbody></table><caption>Source: <code>level_prop_battle_extra</code>, <code>BaseCritRatePercentValue</code>.</caption></div>

<div class="note warn">
<p><b>The same roll is worth +11.20% at Expert III and +1.43% at Champion I.</b> The base value jumps from
8,927 to 69,975 across that one promotion &mdash; so flat crit is the strongest stat in the game right before
that wall, and close to worthless after it. Percentage crit does not decay.</p>
</div>

<h2>Percentage points are not damage</h2>
<p>Crit rate only pays out through crit damage. Expected damage is
<code>1 + critChance &times; (critMult &minus; 1)</code>, so with a 1.59&times; multiplier, +11% crit rate is about
<b>+6% damage</b> &mdash; real, but far less than the headline suggests.</p>
<p>The two stats gate each other. <b>Crit Rate is the better buy while <code>CritDMG% &gt; 5% + CritRate%</code></b>;
past that point Crit DMG takes over. They are balanced when the two numbers are roughly equal, and crit rate
becomes worthless entirely once effective crit chance reaches 100%.</p>

<h2>The same pattern elsewhere</h2>
<p>Every stat below uses an identical <code>value / base</code> normalisation, with the base growing each rank:</p>
<ul>
  <li><b>Effect Hit Rate</b> and <b>Effect RES</b> &mdash; via <code>BaseEffectRate</code> / <code>BaseEffectDodge</code>.</li>
  <li><b>Block</b> &mdash; via <code>BaseBlockPercentValue</code>.</li>
  <li><b>Accuracy</b> &mdash; internally <code>BaseBlockAvoidPercentValue</code>, literally "base accuracy value".
      It is the counter to enemy Block, not a hit-chance stat.</li>
</ul>
<p>At level 83 the Effect base is 6,049, so an Effect Hit Rate of 2.73K is contributing about
<b>45%</b> effect chance.</p>
</div>
"""
    return layout("Crit and flat value stats", "How Sword x Staff resolves crit, and why flat +1K Crit rolls lose most of their value as you rank up.", body, "combat", 1)


# ------------------------------------------------------------------ scaling
def page_scaling():
    off = csvrows("fight_level_offset_damage")
    pts = [(int(r[0]), int(r[1]) / 10000.0 * 100) for r in off[2:]
           if len(r) >= 2 and r[0].strip().isdigit()][:26]
    lvl = charts.line_chart(
        [{"name": "damage swing from a level gap", "colour": "#b8863b", "points": pts}],
        ylabel="damage change", xlabel="levels above (or below) the target",
        yfmt=lambda v: f"{v:.0f}%", xfmt=lambda v: f"{v:.0f}",
        marks=[{"x": 4, "label": "caps here"}],
        caption="It rises 4% a level then stops dead at four levels. Above your target you multiply "
                "by this; below it you divide by it, so the same gap hurts more than it helps.")
    body = f"""
<div class="wrap">
<p class="eyebrow">Combat mechanics</p>
<h1>Level and rank scaling</h1>
<p class="lede">Three separate systems decide what happens when you fight something above or below your
own level. They stack, and they are not equally important.</p>

<h2>1. Level offset</h2>
{lvl}
<p>Outside PvP, the game looks up the level gap in <code>fight_level_offset_damage</code> and applies a
multiplier: damage is multiplied when you are higher level, divided when you are lower.</p>
<div class="note">
<p><b>This is a weak lever.</b> The scale caps at <b>+16%</b> from a gap of 4 levels through 20, and any gap
beyond 20 falls back to <code>MaxLevelOffsetDamageScale</code>, which is only <b>+10%</b>. Raw level
difference matters far less than most players assume.</p>
</div>

<h2>2. Rank offset</h2>
<p>The same idea by rank, from <code>fight_rank_offset_damage</code>. This one is <b>dominant</b>. The
per-rank damage scale (divided by 10,000) climbs steeply:</p>
<div class="tablewrap"><table>
<thead><tr><th>Rank</th><th class="num">DamageScale</th></tr></thead>
<tbody>
<tr><td>No Rank</td><td class="num">0</td></tr>
<tr><td>Apprentice / Elite / Expert</td><td class="num">0.7</td></tr>
<tr><td>Champion</td><td class="num">15</td></tr>
<tr><td>Master</td><td class="num">95</td></tr>
<tr><td>Paragon</td><td class="num">300</td></tr>
<tr><td>Saint</td><td class="num">700</td></tr>
<tr><td>Ascendant I / II / III</td><td class="num">1,000 / 1,500 / 2,000</td></tr>
<tr><td>Divinity I / II / III</td><td class="num">2,500 / 3,000 / 3,500</td></tr>
</tbody></table><caption>The gap between two ranks, not the absolute value, sets the multiplier.</caption></div>

<h2>3. Combat-rating suppression</h2>
<p>A power-score comparison applied on top. It has one notable exemption: the check
<code>IsCombatRatingSuppressionEfective</code> returns <b>false</b> when a player already out-ranks the
monster &mdash; so once you are a full rank above the content, suppression stops applying and you simply
steamroll it.</p>

<h2>The one that actually hurts</h2>
<p>None of the three is the real wall. The <a href="elemental.html">elemental base value</a> is: because your
Mastery is divided by the <i>defender's</i> base and their RES by <i>yours</i>, fighting up is penalised twice
over, and the effect is far larger than a &plusmn;16% level offset.</p>
<p>Unlocking matters too &mdash; rank suppression only begins to apply from <code>SuppressUnlockRank</code>,
which is set to <b>Champion I</b>.</p>
</div>
"""
    return layout("Level and rank scaling", "The three systems in Sword x Staff that scale damage by level and rank, with the real table values for each.", body, "combat", 1)


# ------------------------------------------------------------------ top-up
def page_topup(tiers, iconmap):
    def chip(it, big=False):
        nm = L(f"item_{it['id']}_name") or it["cn"]
        src = iconmap.get(it["id"])
        img = (f'<img src="../assets/icons/{it["id"]}.png" alt="" loading="lazy" width="34" height="34">'
               if src else '<span class="noimg" aria-hidden="true"></span>')
        img = img.replace("../assets", "assets")
        cls = "chip big" if big else "chip"
        return (f'<div class="{cls}" title="{html.escape(nm)} — {html.escape(it["cn"])} (id {it["id"]})">'
                f'{img}<span class="cn">{html.escape(nm)}</span><span class="qty">&times;{it["n"]}</span></div>')

    rows, lastg = [], None
    for t in tiers:
        if t["group"] != lastg:
            rows.append('<div class="gdiv"><span>Group %s</span><i></i><span class="gnote">'
                        'unlocks once the previous group is maxed</span></div>' % html.escape(t["group"]))
            lastg = t["group"]
        kind = "big" if t["big"] else "stat"
        label = "Cosmetic milestone" if t["big"] else "Permanent bonus"
        desc = L(f"accumulated_pay_desc_{t['tier']}") or t["desc"] or ""
        core = "".join(chip(i, True) for i in t["core"]) or '<span class="muted">&mdash;</span>'
        sub = "".join(chip(i) for i in t["sub"])
        rows.append(f'''<article class="tier {kind}"><div class="rail"></div>
<div class="no"><span class="n">{t['tier']}</span><span class="k">{label}</span></div>
<div class="cost"><span class="usd">${t['usd']/100:,.0f}</span></div>
<div class="tbody"><h3>{html.escape(desc)}</h3><div class="chips">{core}</div>
<div class="side"><span class="slab">plus</span><div class="chips">{sub}</div></div></div></article>''')
    body = f"""
<div class="wrap">
<p class="eyebrow">Economy</p>
<h1>The cumulative top-up ladder</h1>
<p class="lede">The game tracks total spending across your account and pays out at each threshold.
There are 75 of them, from $5 to $150,000. This is all of them, read from
<code>accumulated_pay_award</code> with the game's own item icons and English names.</p>

<div class="facts">
  <div class="fact"><b>75</b><span>Reward tiers</span></div>
  <div class="fact"><b>$5</b><span>First tier</span></div>
  <div class="fact"><b>$150,000</b><span>Final tier</span></div>
  <div class="fact"><b>15</b><span>Visibility groups</span></div>
</div>

<div class="legend">
  <span class="key g"><i></i> <span><b>Cosmetic milestone</b> &mdash; the <code>IsBigLevel</code> flag; gives a costume piece</span></span>
  <span class="key s"><i></i> <span><b>Permanent bonus</b> &mdash; a permanent stat or damage buff</span></span>
</div>

<main class="ladder">
{chr(10).join(rows)}
</main>

<h2>How to read it</h2>
<p>Rewards alternate by design. Every <b>gold</b> tier is a costume piece from one of five sets, released in
order &mdash; Listen to the World, Arcade Hero, Supreme Might, Starfarer, Aether Nexus &mdash; each rolling out
across main weapon, hair, outfit, off-hand and back over about five tiers. Every other tier is a permanent
stat or damage buff. Past tier 49 the pattern locks: a permanent +7% stat alternating with a costume piece,
and the side rewards settle into a fixed rotation.</p>
<p>Thresholds are stored per region (CNY, USD, JPY, KRW). The dollar figures here are the game's own USD
values, not a conversion &mdash; USD is stored in cents, so tier 18's <code>USD:80000</code> is $800.</p>
</div>
"""
    return layout("Top-up ladder", "All 75 cumulative top-up reward tiers in Sword x Staff, $5 to $150,000, with every reward and its real icon.", body, "topup", 0)


# ------------------------------------------------------------------ main
def main():
    tiers = load_tiers()
    ladder, B, BA, BC, sr, grp, name = base_tables()

    # copy icons
    icondir = DIST / "assets" / "icons"
    icondir.mkdir(parents=True, exist_ok=True)
    iconmap = {}
    for p in (OUT / "item_icons").glob("*.png"):
        shutil.copy2(p, icondir / p.name)
        iconmap[p.stem] = True

    n = 0
    n += write("index.html", page_home())
    n += write("method.html", page_method())
    n += write("top-up-ladder.html", page_topup(tiers, iconmap))
    n += write("combat/index.html", page_combat_index())
    n += write("combat/damage.html", page_damage())
    n += write("combat/elemental.html", page_elemental(ladder))
    n += write("combat/speed.html", page_speed())
    n += write("combat/crit.html", page_crit(ladder))
    n += write("combat/scaling.html", page_scaling())

    # skills
    skdir = DIST / "assets" / "skills"
    skdir.mkdir(parents=True, exist_ok=True)
    iconset = set()
    src = OUT / "skill_icons"
    if src.exists():
        for p_ in src.glob("*.png"):
            shutil.copy2(p_, skdir / p_.name)
            iconset.add(p_.name)
    sdata = json.loads((OUT / "_skills.json").read_text(encoding="utf-8"))
    n += write("combat/next-point.html",
               calc_page.render(layout, base_tables, charts))
    n += write("combat/skills.html", skills_page.render(layout, sdata, iconset))
    print(f"  skills page: {sum(len(c['skills']) for t in sdata['tiers'] for c in t['classes'])} skills, {len(iconset)} icons")
    print(f"built 11 pages, {n/1024:.0f} KB html, {len(iconmap)} icons -> {DIST}")


if __name__ == "__main__":
    main()
