"""SPD breakpoints — how much more speed buys the next action, from the timeline rule."""
from __future__ import annotations
import html, json

# fight_rank_offset_damage keys its SpeedScale by the rank family; the ladder's
# internal names carry a tier suffix (Gold3, Godtouched1_2, Demigod2_1)
def _family(internal: str) -> str:
    base = internal.split("_")[0]
    if base.startswith(("Godtouched", "Demigod")):
        return base
    return base.rstrip("123")


def render(layout, base_tables, charts):
    import build as _b
    ladder, _B, _BA, _BC, sr, grp, name = base_tables()
    fro = _b.csvrows("fight_rank_offset_damage")
    scale = {}
    for r in fro[2:]:
        if len(r) >= 3 and r[0].strip():
            try:
                scale[r[0].strip()] = int(r[2])
            except Exception:
                pass
    ranks = []
    for L in ladder:
        if L["rank"].startswith("("):
            continue
        ranks.append({"name": L["rank"], "scale": scale.get(_family(L["internal"]), 1)})
    dflt = next((i for i, r in enumerate(ranks) if r["name"] == "Champion III"), len(ranks) // 2)
    opts = lambda sel: "".join(
        f'<option value="{i}"{" selected" if i == sel else ""}>{html.escape(r["name"])}</option>'
        for i, r in enumerate(ranks))
    cfg = json.dumps({"ranks": ranks}, ensure_ascii=False).replace("</", "<\\/")

    ratio_chart = charts.line_chart(
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

    # the breakpoint table: +k turns inside N of the opponent's turns needs the
    # SPD ratio ((N+k)/N)^2 at equal promotion
    def cell(N, k):
        return f"{((N + k) / N) ** 2 * 100 - 100:.1f}%"
    bp_rows = "".join(
        f'<tr><td>{N} turns</td>' + "".join(f'<td class="num">+{cell(N, k)}</td>' for k in (1, 2, 3, 4)) + "</tr>"
        for N in (10, 15, 20, 30))

    # the rank multiplier, by band, in the game's own rank names
    bands, last = [], None
    for r in ranks:
        if last and last["scale"] == r["scale"]:
            last["to"] = r["name"]
        else:
            last = {"from": r["name"], "to": r["name"], "scale": r["scale"]}
            bands.append(last)
    band_rows = "".join(
        f'<tr><td>{html.escape(b["from"])}' + (f' &rarr; {html.escape(b["to"])}' if b["to"] != b["from"] else "") +
        f'</td><td class="num">{b["scale"]}</td><td class="num">' +
        ("baseline" if b["scale"] == 1 else f'&times;{b["scale"] ** 0.5:.2f} turn rate') + "</td></tr>"
        for b in bands)

    body = f"""
<div class="wrap">
<p class="eyebrow">Combat mechanics</p>
<h1>SPD breakpoints</h1>
<p class="lede">The battle is a timeline, and SPD only sets how often you come up on it. Enter your speed and
the opponent's and this works out who acts first, how many turns you get, and exactly how much more SPD buys
the next one.</p>

<section class="calc" id="spdcalc">
  <div class="calc-grid">
    <div class="calc-side">
      <h3>You</h3>
      <label>SPD <span class="hint">one or several, comma-separated &mdash; now, after the next upgrade, a target</span>
        <input type="text" id="my_spd" value="426000, 450000, 500000" inputmode="numeric"></label>
      <label>Promotion <select id="my_rank">{opts(dflt)}</select></label>
    </div>
    <div class="calc-side">
      <h3>Opponent</h3>
      <label>SPD <input type="number" id="their_spd" value="381000" min="1" step="1000"></label>
      <label>Promotion <select id="their_rank">{opts(dflt)}</select></label>
      <label>Fight length <select id="turns">
        <option value="10" selected>10 of their turns &mdash; a typical fight</option>
        <option value="15">15 &mdash; most stages' round cap</option>
        <option value="20">20</option><option value="30">30</option></select></label>
    </div>
  </div>
  <p class="verdict" id="spd_verdict"></p>
  <div class="tablewrap"><table id="spd_table">
    <thead><tr><th class="num">Your SPD</th><th>First to act</th><th class="num">Your turns</th>
      <th class="num">Turn rate</th><th class="num">Next extra turn at</th><th class="num">Two more at</th>
      <th class="num">You lose a turn below</th></tr></thead>
    <tbody id="spd_rows"></tbody>
  </table></div>
  <p class="note" id="spd_note"></p>
</section>

<h2>The rule</h2>
<p>Every unit sits in a queue ordered by the moment it will next act. The engine takes whoever is earliest, lets
them act, then puts them back at <code>now + interval</code>. <code>FightRoundComponent</code> computes that
interval as</p>
<pre><code>interval = 100000 / sqrt(SPD x rankSpeedScale)</code></pre>
<p>so the number of turns you take while the opponent takes one is <code>sqrt(your SPD / their SPD)</code>
at the same promotion. Whoever's first interval is shorter acts first; an exact tie is a coin flip.</p>
{ratio_chart}

<h2>What the next turn costs</h2>
<p>Inside a fight of <i>N</i> of the opponent's turns you get <code>floor(N &times; sqrt(your SPD / their SPD))</code>
turns. So one extra turn needs the ratio <code>((N+1)/N)&sup2;</code>, and the extra SPD you need over the
opponent's depends on how long the fight runs &mdash; the shorter the fight, the more each extra turn costs:</p>
<div class="tablewrap"><table>
<thead><tr><th>Fight length</th><th class="num">+1 turn</th><th class="num">+2</th><th class="num">+3</th><th class="num">+4</th></tr></thead>
<tbody>{bp_rows}</tbody>
</table><caption>SPD needed above the opponent's, at the same promotion. A ten-turn fight makes the first extra turn
a 21% speed lead; a thirty-turn one only 6.8%.</caption></div>

<h2>Promotion is inside the square root</h2>
<p><code>rankSpeedScale</code> comes from <code>fight_rank_offset_damage</code> by rank family. It is constant
within a band, so it cancels in same-band fights and only matters across bands &mdash; where it is large.</p>
<div class="tablewrap"><table>
<thead><tr><th>Promotion band</th><th class="num">Scale</th><th class="num">Effect</th></tr></thead>
<tbody>{band_rows}</tbody>
</table></div>

<h2>Two things that ignore SPD entirely</h2>
<p>Status effects can move a unit's next action time directly, bypassing the stat: a positive
<code>RoundIntervalPercent</code> advances the turn, a negative one delays it, and zero makes the unit act
immediately. Cooldowns count the caster's own turns and SPD does not reduce them &mdash; it only brings the turns
round faster.</p>
</div>
<script>var SPD_CFG = {cfg};</script>
<script src="../assets/speed.js?v={_b.asset_v()}"></script>
"""
    return layout("SPD breakpoints", "How much more SPD buys the next action in Sword x Staff, from the "
                  "timeline rule, with your promotion and the opponent's.", body, "combat", 1)
