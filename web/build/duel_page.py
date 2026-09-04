"""Duel simulator: two loadouts, the real turn clock, the real damage formula."""
from __future__ import annotations
import html, json, shutil
from pathlib import Path

BASE_COLS = ["BaseElementMaster", "BaseElementResistance", "BaseKongFuMaster",
             "BaseKongFuResistance", "BaseCritRatePercentValue", "BaseCritAvoidPercentValue",
             "BaseBlockPercentValue", "BaseBlockAvoidPercentValue",
             "BaseElementAdd", "BaseElementReduce"]

# a compact sheet: only what actually moves the result
FIELDS = [
    ("hp", "HP", 2640000, "", "10000"),
    ("atk", "ATK", 494000, "", "1000"),
    ("def", "DEF", 392000, "", "1000"),
    ("spd", "SPD", 426000, "", "1000"),
    ("mast", "Elemental Mastery", 86600, "", "1000"),
    ("kfm", "Physical Mastery", 15600, "", "1000"),
    ("aff", "Affinity", 8040, "attacking element", "500"),
    ("eres", "Elemental RES", 9380, "", "500"),
    ("aegis", "Aegis", 7080, "", "500"),
    ("cr", "Crit Rate", 45, "%", "1"),
    ("cd", "Crit DMG", 94.3, "%", "1"),
    ("critres", "Crit RES", 29.1, "%", "1"),
    ("boost", "DMG Boost", 30.8, "%", "1"),
    ("dmgres", "DMG RES", 24, "%", "1"),
    ("blockrate", "Block Rate", 11.4, "%", "1"),
    ("blockeff", "Block Efficiency", 100, "%", "5"),
    ("acc", "Accuracy", 37700, "", "1000"),
]


def render(layout, base_tables, dist: Path, out: Path):
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
        e = {"name": L["rank"], "cap": L["cap"]}
        for c in BASE_COLS:
            try:
                e[c] = int(r[ix[c]])
            except Exception:
                e[c] = 1
        ranks.append(e)

    # rank speed scale — the multiplier under the square root in SpeedToTime
    fro = _b.csvrows("fight_rank_offset_damage")
    spd_scale = {}
    for r in fro[2:]:
        if len(r) >= 3 and r[0].strip():
            try:
                spd_scale[r[0].strip()] = int(r[2])
            except Exception:
                pass

    # the duel dataset the simulator runs on
    duel = json.loads((out / "_duel.json").read_text(encoding="utf-8"))
    (dist / "assets" / "duel.json").write_text(
        json.dumps(duel, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    cfg = json.dumps({"ranks": ranks, "minCrit": 1.3, "minBlock": 1.5,
                      "speedScale": spd_scale, "v": _b.asset_v()}, ensure_ascii=False).replace("</", "<\\/")
    dflt = next((i for i, r in enumerate(ranks) if r["name"] == "Champion III"), len(ranks) // 2)
    ropts = "".join(f'<option value="{i}"{" selected" if i == dflt else ""}>'
                    f'{html.escape(r["name"])}</option>' for i, r in enumerate(ranks))

    def sheet(side):
        return "".join(
            f'<label>{lab}{f"<span class=hint>{hint}</span>" if hint else ""}'
            f'<input type="number" id="{side}_{i}" value="{v}" step="{st}"></label>'
            for i, lab, v, hint, st in FIELDS)

    def slots(side, kind, n0, count):
        return "".join(
            f'<button type="button" class="slot {kind}" id="{side}_slot{n}" data-side="{side}" '
            f'data-slot="{n}" data-kind="{kind}"><span class="slotnum">{n - n0 + 1}</span></button>'
            for n in range(n0, n0 + count))

    body = f"""
<div class="wrap wide">
<p class="eyebrow">Combat mechanics</p>
<h1>Duel simulator</h1>
<p class="lede">Give both sides a sheet and a real loadout &mdash; four Techniques and four Charms, as the game allows &mdash; and this runs the fight: the turn clock from
<code>SpeedToTime</code>, cooldowns from each skill's own CD, and every hit through
<code>Damage()</code> with crit and block rolled rather than averaged. A thousand fights, then the odds.</p>

<div class="duel">
  <section class="duelside" data-side="a">
    <h2 class="sidehead"><span class="dot a"></span>You</h2>
    <p class="slotlabel">4 Techniques</p>
    <div class="slotgrid">{slots("a", "tech", 0, 4)}</div>
    <p class="slotlabel">4 Charms</p>
    <div class="slotgrid">{slots("a", "charm", 4, 4)}</div>
    <details class="statbox" open><summary>Stats</summary>
      <div class="calcgrid tight">{sheet("a")}
        <label>Rank<select id="a_rank">{ropts}</select></label>
        <label>Skill rank<input type="number" id="a_srank" value="22" min="1" max="34"></label>
        <label>Skill level<input type="number" id="a_slevel" value="127" min="1" max="500"></label>
      </div>
    </details>
  </section>

  <section class="duelside" data-side="b">
    <h2 class="sidehead"><span class="dot b"></span>Opponent</h2>
    <p class="slotlabel">4 Techniques</p>
    <div class="slotgrid">{slots("b", "tech", 0, 4)}</div>
    <p class="slotlabel">4 Charms</p>
    <div class="slotgrid">{slots("b", "charm", 4, 4)}</div>
    <details class="statbox"><summary>Stats</summary>
      <div class="calcgrid tight">{sheet("b")}
        <label>Rank<select id="b_rank">{ropts}</select></label>
        <label>Skill rank<input type="number" id="b_srank" value="22" min="1" max="34"></label>
        <label>Skill level<input type="number" id="b_slevel" value="127" min="1" max="500"></label>
      </div>
    </details>
  </section>
</div>

<div class="runbar">
  <button type="button" id="run" class="runbtn">Run 1,000 duels</button>
  <button type="button" id="reset" class="pickbtn">Reset to defaults</button>
  <label class="mirror"><input type="checkbox" id="mirror" checked> mirror my sheet onto the opponent</label>
  <label class="mirror">Round cap <input type="number" id="maxrounds" value="15" min="0" max="100" style="width:4.5em"> <span class="hint">stages use 15, 20 or 30; 0 = none</span></label>
</div>

<div id="result" class="result" hidden>
  <div class="odds"><div class="oddsbar"><span id="oddsa"></span><span id="oddsb"></span></div>
    <p id="oddstext"></p></div>
  <p id="charmnote" class="verdict"></p>
  <div id="hpchart"></div>
  <h3>One fight, blow by blow</h3>
  <p class="calcnote">A single run with a fixed seed so you can watch the turn order, cooldowns and crit/block rolls play out. The odds above come from a thousand of these.</p>
  <div class="tablewrap"><table class="log"><thead><tr>
    <th class="num">t</th><th>actor</th><th>skill</th><th class="num">damage</th>
    <th class="num">HP left</th></tr></thead><tbody id="logbody"></tbody></table></div>
</div>

<dialog id="picker" class="picker">
  <div class="pickhead">
    <input type="search" id="pickfind" placeholder="Search&hellip;" autocomplete="off">
    <button type="button" id="pickclear" class="pickbtn">Clear slot</button>
    <button type="button" id="pickclose" class="pickbtn">Close</button>
  </div>
  <div class="pickfilters">
    <select id="pickclass" aria-label="Filter by class"><option value="">All classes</option></select>
    <select id="pickele" aria-label="Filter by element"><option value="">Any element</option></select>
    <span id="pickcount" class="pickcount"></span>
  </div>
  <div id="picklist" class="picklist"></div>
</dialog>

<div class="note">
<p><b>What is exact.</b> The turn clock is <code>SpeedToTime</code>: each unit carries its own round counter
that advances every <code>100000 / sqrt(SPD x rankSpeedScale)</code>, and whoever comes due next acts &mdash; so a
unit with four times the SPD really does act twice as often. <b>Cooldowns count that unit's own turns</b>, not a
shared round: <code>FightSkillAgentComponent</code> stamps <code>LastRound</code> from the caster's own
<code>FightRoundComponent</code>. A skill with a cooldown <b>starts on cooldown</b> unless it is a
<i>Zero Initial CD</i> skill (<code>ResetCDAtStart</code> in its prefab), which is what that keyword means.</p>
<p><b>From the EC prefabs, not the description text:</b> each skill's element, its hit list with the coefficient
each hit reads (Lion Combo is <code>SkillAttack1, SkillAttack1, SkillAttack2</code>; Divine Wrath rolls
<code>SkillAttack4</code> through a random-target hit), use limits, and heals. Damage is the whole of
<code>Damage()</code> with crit and block <i>rolled</i> per hit, block cancelling crit exactly as
<code>CalcDamageTypeImpl</code> does.</p>
<p><b>Decoded but not yet simulated:</b> status effects. The prefabs carry every status's duration in rounds, its
Buff/Debuff type, the chance each hit applies it (Starlight Burst: 30% Blind), and what fires when it ends
(Icebound heals on expiry). Those are the next thing to wire in; until then Charms that grant reflect, shields
or status damage are reported on the page rather than counted.</p>
<p><b>Still modelled, not extracted:</b> which skill the AI casts (slot order here; the real selector is not in
the shared assembly &mdash; the prefabs only carry per-skill <i>target</i> priorities), and the grid, so
range and area do nothing and multi-target skills hit once. The round cap is the stage's
<code>MaxRound</code> and ends the fight as a draw when the slower unit has had that many turns.</p>
<p><b>So read it as</b> a comparison of two damage-and-tempo builds under identical assumptions, which is
what it is good for &mdash; not a prediction of a real match.</p>
</div>
</div>
<script type="application/json" id="dueldata">{cfg}</script>
<script src="../assets/duel.js?v={_b.asset_v()}" defer></script>
"""
    return layout("Duel simulator",
                  "Load two builds with eight Techniques each and simulate a thousand 1v1 fights using "
                  "Sword x Staff's own turn clock, cooldowns and damage formula.",
                  body, "combat", 1)
