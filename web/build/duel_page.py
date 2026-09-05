"""Duel simulator: two loadouts, the real turn clock, the real damage formula —
presented as a battle scene you can watch play out."""
from __future__ import annotations
import html, json
from pathlib import Path

BASE_COLS = ["BaseElementMaster", "BaseElementResistance", "BaseKongFuMaster",
             "BaseKongFuResistance", "BaseCritRatePercentValue", "BaseCritAvoidPercentValue",
             "BaseBlockPercentValue", "BaseBlockAvoidPercentValue",
             "BaseElementAdd", "BaseElementReduce", "BaseEffectRate", "BaseEffectDodge"]

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
    ("erate", "Effect Hit Rate", 13100, "lands your statuses", "500"),
    ("edodge", "Effect RES", 63600, "resists theirs", "500"),
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

    # rank labels ("Divine +6") and class portraits, for the scene
    sk = json.loads((out / "_skills.json").read_text(encoding="utf-8"))
    avail = {p.stem for p in (dist / "assets" / "skills").glob("class_*.png")}
    class_icon = {}
    for t in sk["tiers"]:
        for c in t["classes"]:
            base = Path((c.get("icon") or "").strip()).name
            class_icon[c["name"]] = base if base and f"class_{base}" in avail else None

    cfg = json.dumps({"ranks": ranks, "minCrit": 1.3, "minBlock": 1.5,
                      "speedScale": spd_scale, "v": _b.asset_v(),
                      "rankLabels": sk["rankLabels"], "rankQuality": sk["rankQuality"],
                      "classIcon": class_icon},
                     ensure_ascii=False).replace("</", "<\\/")
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
            f'data-slot="{n}" data-kind="{kind}" title="{"Technique" if kind == "tech" else "Charm"} slot {n - n0 + 1}">'
            f'<span class="slotnum">{n - n0 + 1}</span></button>'
            for n in range(n0, n0 + count))

    def fighter(side, label):
        return f"""
      <section class="fighter" data-side="{side}">
        <div class="nameplate">
          <span class="fname">{label}</span>
          <span class="fclass" id="{side}_class"></span>
          <span class="frank" id="{side}_rankname"></span>
        </div>
        <div class="hpbar"><div class="hpfill" id="{side}_hpfill"></div>
          <div class="shfill" id="{side}_shfill" hidden></div>
          <span class="hptext" id="{side}_hptext"></span></div>
        <div class="statusrow" id="{side}_status" aria-live="polite"></div>
        <div class="fighter-row">
          <div class="slotcol" aria-label="Techniques">{slots(side, "tech", 0, 4)}</div>
          <div class="medallion" id="{side}_portrait"><span class="medallion-empty">?</span></div>
          <div class="slotcol" aria-label="Charms">{slots(side, "charm", 4, 4)}</div>
        </div>
        <div class="callout" id="{side}_callout" aria-live="polite"></div>
        <div class="floats" id="{side}_floats"></div>
      </section>"""

    def stats(side, label, open_):
        return f"""
    <details class="statbox"{" open" if open_ else ""}><summary>{label} &mdash; stats</summary>
      <div class="calcgrid tight">{sheet(side)}
        <label>Rank<select id="{side}_rank">{ropts}</select></label>
        <label>Skill rank<input type="number" id="{side}_srank" value="22" min="1" max="34"></label>
        <label>Skill level<input type="number" id="{side}_slevel" value="127" min="1" max="500"></label>
      </div>
    </details>"""

    body = f"""
<div class="wrap wide">
<p class="eyebrow">Combat mechanics</p>
<h1>Duel simulator</h1>
<p class="lede">Load four Techniques and four Charms a side, tap a slot to change it, then run a thousand
duels &mdash; or watch one play out action by action on the game's own turn clock, with every hit through
<code>Damage()</code> and every crit and block rolled.</p>

<div class="arena" id="arena">
  <div class="orderstrip" id="orderstrip" aria-label="Upcoming turn order"></div>
  <div class="arena-body">
    {fighter("a", "You")}
    <div class="vs"><span>VS</span></div>
    {fighter("b", "Opponent")}
  </div>
  <div class="banner" id="banner" hidden></div>

  <div class="playbar">
    <button type="button" id="run" class="runbtn" disabled>Run 1,000 duels</button>
    <button type="button" id="play" class="pickbtn" disabled>&#9654; Watch one fight</button>
    <button type="button" id="step" class="pickbtn" disabled>Step</button>
    <select id="speed" aria-label="Playback speed">
      <option value="900">1x</option><option value="450" selected>2x</option>
      <option value="220">4x</option><option value="0">Instant</option>
    </select>
    <label class="mirror"><input type="checkbox" id="mirror" checked> mirror my sheet onto the opponent</label>
    <label class="mirror">Round cap <input type="number" id="maxrounds" value="15" min="0" max="100" class="short">
      <span class="hint">stages use 15, 20 or 30; 0 = none</span></label>
    <button type="button" id="reset" class="pickbtn">Reset to defaults</button>
  </div>

  <div id="result" class="result" hidden>
    <div class="odds"><div class="oddsbar"><span id="oddsa"></span><span id="oddsb"></span></div>
      <p id="oddstext"></p></div>
    <p id="charmnote" class="verdict"></p>
  </div>
</div>

<div class="duelstats">
  {stats("a", "You", True)}
  {stats("b", "Opponent", False)}
</div>

<div id="detail" hidden>
  <div id="hpchart"></div>
  <h3>The fight above, as a table</h3>
  <p class="calcnote">The same seeded run the scene plays. The odds come from a thousand of these with fresh rolls.</p>
  <div class="tablewrap"><table class="log"><thead><tr>
    <th class="num">t</th><th class="num">turn</th><th>actor</th><th>skill</th><th>hits</th>
    <th class="num">damage</th><th class="num">HP left</th></tr></thead><tbody id="logbody"></tbody></table></div>
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
<i>Zero Initial CD</i> skill (<code>ResetCDAtStart</code> in its prefab), which is what that keyword means.
The strip of portraits along the top is the real order of play for the fight being shown.</p>
<p><b>From the EC prefabs, not the description text:</b> each skill's element, its hit list with the coefficient
each hit reads (Lion Combo is <code>SkillAttack1, SkillAttack1, SkillAttack2</code>; Divine Wrath rolls
<code>SkillAttack4</code> through a random-target hit), use limits, and heals. Damage is the whole of
<code>Damage()</code> with crit and block <i>rolled</i> per hit, block cancelling crit exactly as
<code>CalcDamageTypeImpl</code> does. Charms are folded into the sheet through
<code>CalcSkillPassiveProps</code>, and the scene says which of their effects it could not use.</p>
<p><b>Statuses, from the prefabs.</b> Every hit's damage entity lists the statuses it applies
(<code>FightDamageComponent.StatusList</code>: id, base chance, whether Effect Hit Rate and Effect RES modify it),
and each status entity says what it is. The fight now runs them: <b>stat buffs and debuffs</b> from
<code>FightStatusPropComponent</code>, scaled by the caster's rank like everything else; <b>per-hit falloff</b>
(Divine Wrath's sixteen hits stamp a 40% decay on the target, so the cast is worth about 2.5 hits, not 16);
<b>Stun</b> and <b>Frozen</b> (the holder loses its action, and Stun also freezes cooldowns via
<code>FightStatusSkillStopCdComponent</code>); <b>Blind</b> (the holder's next Attack skill deals nothing, then it
clears); <b>shields</b> that absorb before HP; <b>poison</b> and other round-start ticks; and expiry triggers, which
is how Icebound heals when it ends. Durations count the <i>holder's</i> own turns. Landing rolls use
<code>EffectRate()</code>: base chance x (1 + Effect Hit Rate / base) / (1 + Effect RES / base), cubed-ratio penalty
for hard controls against a higher-ranked target, and Damp raising the odds of Frozen.</p>
<p><b>Charms with procs</b> now fire: on-hit skills, each-turn skills, when-hit skills (reflect), and the
turn-with-no-Technique check that Frost Guard uses. Fear, Confusion, Ridicule and Restrict are applied and shown but
change nothing here &mdash; taunts and movement have no meaning in a 1v1 without a grid.</p>
<p><b>Modelled, not extracted:</b> which skill to cast. The prefab lists the AI's tie-break priorities, but the
choice itself runs in an ECS behaviour tree that is not in the config, so each side casts the first ready
Technique in slot order. There is no grid, so range, area and positioning do nothing.</p>
</div>
</div>
<script type="application/json" id="dueldata">{cfg}</script>
<script src="../assets/duel.js?v={_b.asset_v()}" defer></script>
"""
    return layout("Duel simulator",
                  "Load two builds — four Techniques and four Charms each — and watch a 1v1 play out on "
                  "Sword x Staff's own turn clock, cooldowns and damage formula, then see the odds over a thousand fights.",
                  body, "combat", 1)
