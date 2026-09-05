"""Duel simulator: two loadouts, the real turn clock, the real damage formula —
presented as a battle scene you can watch play out."""
from __future__ import annotations
import html, json
from pathlib import Path

BASE_COLS = ["BaseElementMaster", "BaseElementResistance", "BaseKongFuMaster",
             "BaseKongFuResistance", "BaseCritRatePercentValue", "BaseCritAvoidPercentValue",
             "BaseBlockPercentValue", "BaseBlockAvoidPercentValue",
             "BaseElementAdd", "BaseElementReduce", "BaseEffectRate", "BaseEffectDodge",
             "PlayerSkillDmgReduceScale", "ProSkillDmgReduceScale"]

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
    ("pvpadd", "PvP Bonus DMG", 9.6, "%", "0.5"),
    ("pvpres", "PvP DMG RES", 9.6, "%", "0.5"),
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
    class_icon, class_tree = {}, []
    for t in sk["tiers"]:
        for c in t["classes"]:
            base = Path((c.get("icon") or "").strip()).name
            class_icon[c["name"]] = base if base and f"class_{base}" in avail else None
            pre = (c.get("prePro") or "").strip()
            class_tree.append({"name": c["name"], "tier": t["tier"],
                               "pre": pre if pre and pre != "None" else None,
                               "icon": class_icon[c["name"]]})
    # prePro holds the internal id; map it to the display name the tree uses
    id2name = {}
    for t in sk["tiers"]:
        for c in t["classes"]:
            id2name[c["id"]] = c["name"]
    for c in class_tree:
        c["pre"] = id2name.get(c["pre"], c["pre"]) if c["pre"] else None

    # the PvP governor (PVPSkillPropsScaleOnBattleProcessor): its three inputs
    asr = {int(r[0]): int(r[1]) for r in _b.csvrows("avg_skill_rank")[2:]
           if len(r) >= 2 and r[0].strip().isdigit()}
    lnrows = _b.csvrows("level_number")
    ci = [c.strip() for c in lnrows[0]].index("456")
    decay = {int(r[0]): float(r[ci]) for r in lnrows[2:]
             if r and r[0].strip().isdigit() and len(r) > ci and r[ci].strip()}
    balance = {}
    for r in _b.csvrows("balance_value")[2:]:
        if len(r) >= 3 and r[0].strip().isdigit():
            balance.setdefault(r[1].strip(), {})[int(r[0])] = int(r[2])
    # Rank enum index for each subrank, as SubRank.ToRank() yields it (None=0, Norank=1, ...)
    rank_enum = ["None", "Norank", "Blackiron", "Bronze", "Silver", "Gold", "Saint", "Legend", "Angel",
                 "Godtouched1", "Godtouched2", "Godtouched3", "Demigod1", "Demigod2", "Demigod3"]
    for L2, e2 in zip(ladder, ranks):
        base = L2["internal"].rstrip("123").rstrip("_")
        e2["rankEnum"] = rank_enum.index(base) if base in rank_enum else 0
    pvpgov = {"minSurvival": 0.10, "defaultBalance": 1.0, "avgSkillRank": asr,
              "decay": decay, "balance": balance}

    cfg = json.dumps({"ranks": ranks, "minCrit": 1.3, "minBlock": 1.5, "pvp": pvpgov,
                      "speedScale": spd_scale, "v": _b.asset_v(),
                      "rankLabels": sk["rankLabels"], "rankQuality": sk["rankQuality"],
                      "classIcon": class_icon, "classTree": class_tree},
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

    tiers = {}
    for c in class_tree:
        tiers.setdefault(c["tier"], []).append(c["name"])
    clsopts = "".join(
        f'<optgroup label="Tier {t}">' +
        "".join(f'<option value="{html.escape(nm)}"{" selected" if nm == "Archmage" else ""}>{html.escape(nm)}</option>'
                for nm in names) + "</optgroup>"
        for t, names in sorted(tiers.items()))

    def fighter(side, label):
        return f"""
      <section class="fighter" data-side="{side}">
        <div class="nameplate">
          <span class="fname">{label}</span>
          <select class="fclass" id="{side}_cls" aria-label="{label}: class">{clsopts}</select>
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
<p class="lede">Pick a class a side, load four Techniques and four Charms from its line &mdash; its own tier and every
tier below it &mdash; tap a slot to change one, then run a thousand
duels &mdash; or watch one play out action by action on the game's own turn clock, with every hit through
<code>Damage()</code> and every crit and block rolled.</p>

<div class="arena" id="arena">
  <div class="orderstrip" id="orderstrip" aria-label="Upcoming turn order"></div>
  <div class="arena-body">
    {fighter("a", "You")}
    <div class="vs"><span>VS</span></div>
    {fighter("b", "Opponent")}
  </div>
  <div class="ribbon" id="ribbon" hidden></div>
  <div class="banner" id="banner" hidden></div>

  <div class="playbar">
    <button type="button" id="run" class="runbtn" disabled>Run 1,000 duels</button>
    <button type="button" id="play" class="pickbtn" disabled>&#9654; Watch one fight</button>
    <button type="button" id="step" class="pickbtn" disabled>Step</button>
    <select id="speed" aria-label="Playback speed">
      <option value="1000">1x &mdash; the game's own timing</option><option value="500" selected>2x</option>
      <option value="250">4x</option><option value="0">Instant</option>
    </select>
    <label class="mirror"><input type="checkbox" id="mirror" checked> mirror my sheet onto the opponent</label>
    <label class="mirror">Round cap <input type="number" id="maxrounds" value="15" min="0" max="100" class="short">
      <span class="hint">stages use 15, 20 or 30; 0 = none</span></label>
    <label class="mirror">Server age <input type="number" id="serverdays" value="150" min="0" max="400" class="short">
      <span class="hint">days; sets the skill-rank the PvP governor expects</span></label>
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
  <div class="logwrap">
    <h3>Combat log</h3>
    <p class="calcnote">Fills in as the fight plays. Each line is one action: who, what, every hit with its
    roll, what it did to the target, and anything the statuses or Charms did on the side.</p>
    <ol id="combatlog" class="combatlog" aria-live="polite"></ol>
  </div>
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
<p><b>It is a PvP fight, and Damage() knows.</b> Damage from a player is divided by the target's
<code>PlayerSkillDmgReduceScale</code> and again by <code>ProSkillDmgReduceScale</code>, both per-rank bases
from <code>level_prop_battle_extra</code> &mdash; at Champion III that is &divide;1.14 and &divide;1.31. The sheet's
PvP Bonus DMG and PvP DMG RES join the percentage block, and the few skills with a <code>PvpPropScale</code>
under 100% are scaled by it.</p>
<p><b>Then the governor.</b> <code>PVPSkillPropsScaleOnBattleProcessor</code> multiplies every skill's damage by
one more factor, the product of three: a <b>survival floor</b> &mdash; each fighter's burst-to-HP ratio,
<code>ATK&sup2;/(ATK+DEF)/HP</code> carried through crit, block, element and the percentage block, and if the
lowest one exceeds <code>MinSurvivalRatio</code> (0.10, a full-coefficient hit is worth at most a tenth of a
health bar) all damage is scaled down to meet it; a <b>skill-rank decay</b> &mdash; the fighters' average skill
rank against what <code>avg_skill_rank</code> expects for a server of this age, through
<code>level_number[456]</code>, never above 1; and a <b>balance value</b> from <code>balance_value</code>, which
only has rows from Saint upward and so is 1.0 below that. This is why real fights run to ten rounds.</p>
<p><b>Timing is the prefab's.</b> Every hit carries the moment it lands (<code>HitCfg.Delay</code>): Eclipse
Slash's six cuts fall at 0.3, 0.4, 0.78, 0.9, 1.04 and 1.48 seconds; Divine Wrath's sixteen from 0.85 to 2.24.
At 1x the scene plays them at that pace.</p>
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
<p><b>A turn casts every Technique that is ready.</b> Each goes in slot order and then onto its own cooldown,
counted in that caster's turns &mdash; so a skill with no cooldown fires every turn, a CD&nbsp;1 skill every other,
and a turn with three ready skills is three casts. A basic attack happens only when nothing is ready, which is
also when Charms like Frost Guard that key off a Technique-less turn fire. Blind is spent by the first attack of
the turn. The prefab lists the AI's tie-break priorities for <i>targets</i>, but there is no grid here, so
range, area and positioning do nothing.</p>
</div>
</div>
<script type="application/json" id="dueldata">{cfg}</script>
<script src="../assets/duel.js?v={_b.asset_v()}" defer></script>
"""
    return layout("Duel simulator",
                  "Load two builds — four Techniques and four Charms each — and watch a 1v1 play out on "
                  "Sword x Staff's own turn clock, cooldowns and damage formula, then see the odds over a thousand fights.",
                  body, "combat", 1)
