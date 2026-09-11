"""Team battle simulator (4v4): the duel engine on the game's grid, with fighters dragged in from the live
top-100 leaderboard (tools/liveproto roster export)."""
from __future__ import annotations
import html, json
from pathlib import Path

import team_data

# ---------------------------------------------------------------------------- the board
# From the stage prefab of TeamChallenge4V4 (stage 9998 -> battlefield EC 910): a 21 x 20 grid, Y up, with the
# two factions' entry cells and the 5 x 4 deployment box each side gets (stage.TeamChangePosRange = {5, 4}:
# offsets X -2..+2, Y -2..+1 around the entry cell). Terrain other than plain ground cannot be entered.
def grid_from_prefab():
    import ec_data
    ground = ec_data.comp(910, "GridGroundComponent") or {}
    fight = ec_data.comp(910, "FightComponent") or {}
    size = ground.get("Size") or [21, 20]
    blocked = [list(c["Pos"]) for c in ground.get("PosInfos", []) if c.get("GroundType") not in (None, "None", "Shallow")]
    entries = {f["Faction"]: f["EntryPosList"][0] for f in fight.get("FactionInfoList", [])}
    e0, e1 = entries.get(0, [10, 8]), entries.get(127, [10, 12])
    def box(e):
        return {"x0": e[0] - 2, "x1": e[0] + 2, "y0": e[1] - 2, "y1": e[1] + 1}
    z0, z1 = box(e0), box(e1)
    return {
        "w": size[0], "h": size[1], "blocked": blocked, "entries": [e0, e1],
        "zones": [z0, z1],
        # a plain opening formation: two in the front row, two behind
        "start": [[[e0[0], z0["y1"]], [e0[0] - 1, z0["y1"]], [e0[0] + 1, z0["y1"]], [e0[0], z0["y1"] - 1]],
                  [[e1[0], z1["y0"]], [e1[0] - 1, z1["y0"]], [e1[0] + 1, z1["y0"]], [e1[0], z1["y0"] + 1]]],
        "view": {"x0": z0["x0"] - 2, "x1": z0["x1"] + 2, "y0": z0["y0"] - 2, "y1": z1["y1"] + 2},
        "defaultMove": 4, "maxAttack": 7,
    }


NOTES = """
<p><b>Where the numbers come from.</b> Every fighter's sheet is the <code>BattleProps</code> block the server sends
for that player, the same block the Character Stats screen displays; one was checked against the screen stat by
stat. That block already includes Charm passives (<code>SkillPropChunck</code> adds
<code>CalcSkillPassiveProps</code> into a player's props), so Charms here only fire their procs. Each Technique and
Charm keeps the rank and level it is equipped at. The leaderboard is the top 100 by combat rating as the server
listed it, with every player whose sheet has been captured.</p>
<p><b>Trying another setup.</b> Tap any Technique or Charm on a team card to swap it for another from the
fighter's class line (or from any class), to clear the slot, or to set the rank and level it is equipped at.
The sheet stays the captured one: Charm passives are already folded into a player's <code>BattleProps</code>,
so a swapped Charm changes what it fires during the fight but not the standing stats. A changed loadout is
marked <i>edited</i> on the card and can be put back with &#8635;; edits live in this browser only.</p>
<p><b>The board is the game's.</b> Team Challenge 4v4 (stage 9998) fights on battlefield 910: a 21 by 20 grid,
Y up, distance counted in cells (<code>Pos2d.Distance</code> is Manhattan). Each side deploys inside a 5-wide,
4-deep box around its entry cell (<code>stage.TeamChangePosRange = {5, 4}</code>: columns 9&ndash;13, rows
7&ndash;10 for Team 1 and rows 11&ndash;14 for Team 2), one fighter per cell, and the two boxes touch. The page
shows the boxes with two cells of margin; fighters may wander further during the fight.</p>
<p><b>Reach and area come from each skill's prefab.</b> A skill lists the cells, relative to the caster, where its
aim point may be placed (<code>FightSkillComponentInfo.Range</code>, near to far), and every hit lists the cells
it covers around that aim point, or around the caster when the hit acts on its source
(<code>HitScopCfg</code>, <code>HitCfg.ActOnSouce</code>; a summoning hit's area is its <code>SummonScope</code>).
Areas are authored facing up and turned to face the aim as <code>CalcLocalToWorldDir</code> does: the facing is
<code>Pos2d.LookDirection</code> (exact diagonals resolve sideways), and the area flips on X when the aim is to the
caster's left (<code>CalcFlipX</code>). What the aim may sit on is the skill's <code>SkillTargetType</code>: an
<i>Entity</i> skill needs a unit on the aim, a <i>PosCanStand</i> skill a free cell. Heart of Challenge, for
instance, has no reach of its own but covers every cell within three of the Paladin; Meteoric Flames reaches five
cells away and covers the 3&times;3 square there.</p>
<p><b>A turn is move, then cast; the choice follows the client's own AI lists.</b> Whoever comes due next on
the SPD clock acts (equal times keep queue order) and casts every ready Technique in slot order, each onto its
own cooldown counted in that fighter's turns. For each cast the fighter weighs every cell it can walk to
(up to <code>MoveDist</code>, four ways, through free cells) together with every aim the skill allows from
there, and ranks them by the skill's <code>AiPriorityTypes</code> list, criterion by criterion: most targets
hit, then the shorter walk, then the lowest-HP target, then the nearer aim, then an aim that sits on a unit.
Skills with no list of their own use the chain the designers wrote out on the skills that carry one; the
server's true default is not in the client. The last cast of a turn uses <code>LastAIPriorityTypes</code>,
which swaps "shorter walk" for "safer cell" (farther from every enemy), unless the skill is flagged
<code>DontKeepDistance</code>. Moves and casts interleave: moving is itself a skill with no cost, no cooldown
and no use limit (the player prefab's hop, back-step and fixed-speed moves), a cast waits for a move in
progress and then fires (<code>ActiveSkillWaitActionTypes</code>, <code>IsReleaseSkillAfterMove</code>), and
nothing in the client counts hops per turn; only <code>MoveDist</code> caps each hop. So every cast here may be
preceded by a fresh hop from where the fighter now stands, and a caster will step in for one skill and back off
for its last. There is no basic attack in the client: a fighter with nothing ready passes its turn. A fighter with
nothing in reach walks toward the nearest enemy, or its taunter &mdash; that walk is this page's assumption, since
the server's idle rule is not in the client. A fallen player keeps its cell (<code>DestroyOnDie = false</code>), so
bodies block paths. Skills move fighters too: the caster's own dash or leap (<code>SourceMoveList</code>, Doom
Blade) and the victim's pull or knockback (the damage's <code>MoveCfg</code>, Hunter's Judgment, Lunarwater
Threads) land on the nearest free cell in the client's ring order when the exact cell is taken; a Frozen,
Immobilized or Super Armor unit is not moved.</p>
<p><b>Damage, hit by hit.</b> Every hit runs the client's <code>Damage()</code>: attack times the skill's
coefficient over the target's per-rank PvP scaler, plus the flat term, times ATK/(ATK+DEF), times the elemental
ratio, times the percent block, over the class scaler, times the skill's <code>PvpPropScale</code>. The elemental
ratio is the client's split: the attacker's Affinity is divided by the <i>target's</i> base Elemental DMG RES and
its Mastery by the target's base Elemental RES, while the target's Elemental RES is divided by the
<i>attacker's</i> bases. A further stage multiplies by (1 + the attacker's Status DMG Bonus + the target's Status
DMG Taken) over (1 + the target's Status DMG RES), which is how Curse Resonance and its kin pay out.
Every hit rolls in the client's order (<code>CalcDamageTypeImpl</code>): the attacker's Blind chance, then the
target's Dodge, then block, then crit &mdash; a blinded or dodged hit deals nothing and applies no status, and a
blocked hit cannot crit. The chances add the flat value forms over their per-rank bases (Crit Rate + Crit Rate
Value / base, Block Rate + Block Value / base, and the attacker's Accuracy against both), a crit multiplies by at
least 1.3, a block divides by at least 1.5. Blind is a chance, not a certainty: the status grants its holder a 50%
Blind chance for one Technique, so half its hits still land. Heals
run <code>Cure()</code>: max HP, attack or the target's max HP times the skill's cure coefficient plus the fixed
cure, times (1 + Healing Boost + Healing Received + their value forms over their bases), times the final cure scale.
The PvP governor (<code>PVPSkillPropsScaleOnBattleProcessor</code>, shown under the odds) scales only the damage
of skills whose prop group is <code>AffectedBySkillRank</code>; heals and shields are never governed. A hit
typed <code>HitDamageType.None</code> deals nothing itself but still applies its statuses, forced moves and child
skills: Wind's Delight's damage is its child skill, seven waves each hitting the plus around a random enemy, and
Hunter's Judgment's grab is what drags the target. A child skill (<code>ChildSkillCfg</code>) is cast on every unit
its parent hit covered, with its own numbers. Per-target falloff (<code>FightStatusDamageFalloffComponent</code>)
multiplies each repeat hit on the same target by (1&nbsp;&minus;&nbsp;p): Wind's Delight decays 35% per repeat,
Divine Wrath 40%. Random-target hits (<code>FightHitRandomTargetComponent</code>) draw one cell per pick, with
replacement, from the group's pool; empty cells count unless <code>AllowEmptyScope</code> is off, and
<code>MiniHitTargetCount</code> picks must land on a unit.</p>
<p><b>Charms fire on the events their components name.</b> A when-hit Charm's component
(<code>FightStatusDamageSkillComponent</code>) carries its own conditions and they are honoured: Rebound strikes
back only on a hit the wearer <i>blocks</i> (<code>Block = true</code>), Counter Blade on any damage taken, a Charm
with <code>ConditionCount</code> every Nth event, one with <code>EachRoundMaxCount</code> at most that often per
round. On-hit Charms (<code>FightStatusHitSkillComponent</code>, Radiant Sear, Blade of Judgment) fire per
damaging hit under the same flags. The strike a Charm fires is a skill of its own, and when that skill's
<code>CanTriggerChild</code> is off (Radiant Sear's, Rebound's, a Burn tick) it cannot set off further hooks;
this page also stops any hook chain at depth four as a guard of its own. Also run from the prefabs: Linked
Misfortune, Shadow Erosion, Curse Resonance and Pursuit of Victory, Resurrection, Reflective Armor, Repelling Wind,
Gale Shield, Ripple Impact, Blade of Lament, Soul Splash, Defensive Assault, Eye for an Eye, and the HP-unit
Charms whose stacks come off again as HP climbs back.</p>
<p><b>Summoned creatures.</b> Waterling Summon, Frenzy Totem and Stonechief Summon are summoning hits
(<code>FightHitSummon</code> with a <code>SummonId</code>): the creature appears on the cell the hit names relative
to the caster, or the nearest free one, and acts at once (<code>SummonImmediateRound</code>). Its stats are the
client's <code>CalcSummonMonsterInheritProp</code>: a fixed part from <code>summon_monster_fix_prop</code> on the
skill's level curve at the skill's rank (the Waterling's 76% max-HP factor, for instance), plus a share of the
caster's own props from <code>summon_monster_add_prop</code> times <code>summon_rank_additive_factor</code> at the
skill's rank (the Waterling inherits 19% of the caster's max HP, 25% attack, 50% defence, 80% speed and all of
the secondary stats; the Totem 16% / 0 / 50% / 105%; the Stonechief 18% / 70% / 80% / 70%). "Summons cannot
receive any stat boosts", so the caster's unbuffed sheet is the source. The creature takes its own turns on the
SPD clock, blocks its cell, is removed when killed (<code>DestroyOnDie</code>) and fades after five of its own
turns (its lifespan status ends the entity), never decides the result and never counts toward the round cap. Its
skills and passives are <code>monster_group</code>'s, run by the same rules as a fighter's: the Waterling's
Dewdrop and Misty Vapor heal 6.5% and 4.8% of its max HP (PvP-scaled to a third) and dispel one debuff; the
Totem's Inspiration moves a random ally's next turn 20% closer (<code>FightStatusRoundIntervalComponent</code>)
and its Fighting Spirit is an aura that gives every ally within four cells an attack buff
(<code>FightStatusMoveRangeComponent</code>). <i>Stealth</i> follows the game's own words: a stealthed unit is
never the main target of an attack or a heal while a visible one can be, but it still sits under areas. A
summon's opening cooldowns follow the fighters' rule (this page's assumption) and its skill choice the same AI
lists, which for these skills carry no list of their own.</p>
<p><b>Chained hits.</b> Lightning Chain is one strike plus eight links (<code>FightHitChainedComponent</code>,
its <code>NextHitList</code>): each link picks a random enemy within the skill's own reach of the last victim,
never one already struck and never straight back, and stops when nobody is in reach.</p>
<p><b>Fantomon.</b> Battlefield 910 does spawn each fighter's engaged Fantomon (its root carries
<code>FightRolePetSpawnerComponent</code>). The follower form rides its master's cell, is untargetable
(<code>SafeAttacker</code>), takes no turn (<code>FollowMaster</code>) and fires its support skill when the master
starts an Attack Technique (<code>FightAIFollowMasterComponent</code>), scaled by the pet's own attack; but the
follower's props are set by the server and nowhere in the client (<code>pet_battle</code> is dead config), so
pets are not run here until a recorded fight shows their numbers.</p>
<p><b>Burning cells.</b> Meteoric Flames is a summoning hit: it deals its Fire damage to the 3&times;3 and every
cell of it rolls 60% to spawn grid item 3320 with a Fire status whose <code>MoveNear</code> hook fires the Burn
skill at an enemy standing there when the cell appears (<code>TryAtStart</code>), at one arriving on it
(<code>TryAtEnterRange</code>) and at one starting its round on it (<code>TryAtStandRound</code>), for three of the
caster's rounds, or until the caster falls. The board marks such cells. A walk here is resolved at its
destination, so cells crossed mid-path do not fire; the client's step-by-step path is server-side.</p>
<p><b>Before round 1: the PlayStart phase.</b> The fight has a <code>PlayStart</code> status before
<code>Play</code>, during which the AI is driven on a fixed interval (<code>Battle.DrivePlayStartAIInterval</code>),
and the skill table marks what fires then (<code>skill.TryAtStartType</code>: Heart of Challenge, Valor Surge,
Gale Dance, Void Blessing are "Casts once before battle starts"; the self-cast Charm effects such as Rapid Cast are
<code>AutoSelfAtStart</code>). The game's own note on this phase reads: "When multiple units on both sides are set
to cast skills before battle starts, they cast them from highest to lowest initial SPD. SPD changes during this
phase do not affect the order. If a character has multiple skills to cast before battle starts, Charms are cast
before Techniques. Skills of the same type are cast in loadout order, from top to bottom. Battle starts after all
such skills from both sides have been cast." This page orders by initial SPD and never re-sorts, as that says. It
also interleaves: every fighter fires its next start skill on each tick, the faster fighter first within the tick,
so both sides' opening buffs land before the faster tank's taunt &mdash; which is what real fights showed, though
the note read strictly would let the fastest fighter cast all of its own start skills first. The three self-cast
Charms in this data (Rapid Cast, Iron Fortress, Gale Shield) act through their round-start hooks instead. A taunt such as Heart of Challenge lands
<i>Ridicule</i> on every enemy within three cells. The game states what that does: "Taunted enemies target the
caster only, and approach the caster when using damaging Techniques. Summoning Techniques remain available, but
ally-targeting Techniques (grant buffs, healing, shields, etc.) are disabled while taunted." So a taunted fighter
here aims only at its taunter, cannot cast a buff, heal or shield on itself or an ally until the taunt ends or the
taunter falls, and never uses the keep-distance ordering for a damaging Technique &mdash; it closes on the taunter
to break ties. Its skill's own priorities still come first, so it will step sideways to catch more targets; where
"approach" sits among those priorities is server-side, and this page puts it last. Every other skill with a
cooldown opens the fight on it unless it is a Zero
Initial CD skill. Control comes from the client's <code>state_mutex</code> table: Stun, Frozen and Phoenix Stasis
discard both move and skill, Restrict and Immobilize discard the move only.</p>
<p><b>Not modelled.</b> Fantomon (above). Decoy Clone and Blast Spirit (a voodoo doll and a smart grid item,
equipped by nobody in the top 100). The end-of-fight rule at the
100-round cap is server-side and unknown, so a capped fight is scored by remaining HP. The AI's scoring loop is
server-side: the criteria and each skill's ordering are the client's, their default ordering and the global
weights in <code>BattleAISetting</code> (preferred distance to teammates, bunching penalty) are not modelled.
The full rule-by-rule audit of this engine against the client is in
<a href="https://github.com/HungMCLe/Swordxstafd-datamine/blob/claude/swordxstaff-datamining-2p1ywk/docs/ENGINE_AUDIT.md">docs/ENGINE_AUDIT.md</a>.</p>
"""


def render(layout, base_tables, dist: Path, out: Path):
    import build as _b
    import duel_page
    ladder, _B, _BA, _BC, sr, grp, name = base_tables()
    be = _b.csvrows("level_prop_battle_extra")
    ix = {c.strip(): i for i, c in enumerate(be[0])}
    rows = {}
    for r in be[2:]:
        if len(r) > 3 and r[0].strip().isdigit():
            rows[(int(r[0]), int(r[1]))] = r
    ranks = []
    rank_enum = ["None", "Norank", "Blackiron", "Bronze", "Silver", "Gold", "Saint", "Legend", "Angel",
                 "Godtouched1", "Godtouched2", "Godtouched3", "Demigod1", "Demigod2", "Demigod3"]
    for L in ladder:
        r = rows.get((grp.get(L["internal"]), L["cap"]))
        if not r:
            continue
        e = {"name": L["rank"], "cap": L["cap"], "internal": L["internal"]}
        for c in duel_page.BASE_COLS:
            try:
                e[c] = int(r[ix[c]])
            except Exception:
                e[c] = 1
        base = L["internal"].rstrip("123").rstrip("_")
        e["rankEnum"] = rank_enum.index(base) if base in rank_enum else 0
        ranks.append(e)
    fro = _b.csvrows("fight_rank_offset_damage")
    spd_scale = {}
    for r in fro[2:]:
        if len(r) >= 3 and r[0].strip():
            try:
                spd_scale[r[0].strip()] = int(r[2])
            except Exception:
                pass
    asr = {int(r[0]): int(r[1]) for r in _b.csvrows("avg_skill_rank")[2:] if len(r) >= 2 and r[0].strip().isdigit()}
    lnrows = _b.csvrows("level_number")
    ci = [c.strip() for c in lnrows[0]].index("456")
    decay = {int(r[0]): float(r[ci]) for r in lnrows[2:] if r and r[0].strip().isdigit() and len(r) > ci and r[ci].strip()}
    balance = {}
    for r in _b.csvrows("balance_value")[2:]:
        if len(r) >= 3 and r[0].strip().isdigit():
            balance.setdefault(r[1].strip(), {})[int(r[0])] = int(r[2])
    pvpgov = {"minSurvival": 0.10, "defaultBalance": 1.0, "avgSkillRank": asr, "decay": decay, "balance": balance}

    # the live leaderboard, if a roster export exists; served as a separate file that is never committed
    duel = json.loads((out / "_duel.json").read_text(encoding="utf-8"))
    by_id = {s["id"]: s for s in duel["skills"]}
    fighters = team_data.build(out, ranks, by_id)
    fighters_url = None
    if fighters:
        (dist / "assets" / "fighters.json").write_text(json.dumps(fighters, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        fighters_url = "../assets/fighters.json"

    grid = grid_from_prefab()
    sk_data, _class_icon, class_tree = duel_page.class_data(out, dist)
    cfg = json.dumps({"ranks": ranks, "minCrit": 1.3, "minBlock": 1.5, "pvp": pvpgov, "speedScale": spd_scale,
                      "v": _b.asset_v(), "grid": grid, "fightersUrl": fighters_url,
                      # the class line and the skill-rank labels, for the loadout picker on each team card
                      "classTree": class_tree, "rankLabels": sk_data["rankLabels"], "rankQuality": sk_data["rankQuality"],
                      # PropType -> sheet field, so a summoned creature's inherited sheet can be built from its caster's
                      "propFields": dict(list(team_data.PCT.items()) + list(team_data.FLAT.items()))},
                     ensure_ascii=False).replace("</", "<\\/")

    def team(side, label):
        return f"""
      <section class="teamcol" data-side="{side}">
        <h3 class="teamname s{side}">{label} <span class="hint">drop fighters here</span></h3>
        <div class="tcards" id="team{side}"></div>
      </section>"""

    body = f"""
<div class="wrap wide">
<p class="eyebrow">Combat mechanics</p>
<h1>Team battle simulator</h1>
<p class="lede">Four against four on the game's grid. Drag players off the live top-100 leaderboard into either
team, place them on their half of the board, then run a thousand fights or watch one play out on the turn clock.
Every fighter carries the sheet the server reports for that player and the Techniques and Charms they have
equipped, each at its own rank and level. Tap any skill on a team card to swap it, clear it, or change its rank
and level, and try a setup the player does not run today.</p>

<div class="arena team" id="arena">
  <section class="stage">
    <div class="boardlabels"><span class="s1">Team 2 &mdash; top box</span><span class="hint">Y up, as the game counts; the boxes touch in the middle</span></div>
    <div class="board big" id="board" aria-label="Battle grid"></div>
    <div class="boardlabels"><span class="s0">Team 1 &mdash; bottom box</span><span class="hint">drag a fighter (or tap it, then a cell) inside its box</span></div>
    <div class="timeline" id="timeline" hidden>
      <div class="tltrack" id="tltrack" aria-hidden="true"></div>
      <input type="range" id="tlrange" min="0" max="0" value="0" step="1" aria-label="Fight timeline">
      <p class="tlcaption" id="tlcaption"></p>
    </div>
    <div class="banner" id="banner" hidden></div>
    <div class="playbar">
      <button type="button" id="run" class="runbtn" disabled>Run 1,000 fights</button>
      <button type="button" id="play" class="pickbtn" disabled>&#9654; Watch</button>
      <button type="button" id="back" class="pickbtn" title="One action back">&#9664;</button>
      <button type="button" id="step" class="pickbtn" disabled title="One action forward">&#9654;&#9654;</button>
      <select id="speed" aria-label="Playback speed">
        <option value="1000">1x &mdash; the game's own timing</option><option value="500" selected>2x</option>
        <option value="250">4x</option><option value="0">Instant</option>
      </select>
      <label class="mirror">Round cap <input type="number" id="maxrounds" value="100" min="0" max="400" class="short">
        <span class="hint">actions in total; the 4v4 stage uses 100</span></label>
      <label class="mirror">Server age <input type="number" id="serverdays" value="150" min="0" max="400" class="short">
        <span class="hint">days; sets the skill rank the PvP governor expects</span></label>
      <button type="button" id="swap" class="pickbtn">Swap sides</button>
      <button type="button" id="reset" class="pickbtn">Clear</button>
    </div>
    <div id="result" class="result" hidden>
      <div class="odds"><div class="oddsbar"><span id="oddsa"></span><span id="oddsb"></span></div>
        <p id="oddstext"></p><p id="govnote" class="hint"></p></div>
    </div>
  </section>
  <div class="teamlayout2">
    <div class="teams">
      {team(0, "Team 1")}
      {team(1, "Team 2")}
    </div>
    <div class="teamlog">
      <h3>Combat log <span class="hint">click a line to jump there</span></h3>
      <ol id="combatlog" class="combatlog" aria-live="polite"></ol>
    </div>
  </div>
  <section class="lbwrap">
    <div class="lbhead"><h3>Top 100 by combat rating</h3>
      <input type="search" id="lbfind" placeholder="Find a player&hellip;" autocomplete="off">
      <button type="button" id="fill" class="pickbtn">Fill 1&ndash;4 vs 5&ndash;8</button></div>
    <p class="hint">Drag a row onto a team (or tap a row, then a team slot).</p>
    <div class="lb" id="lb"></div>
  </section>
</div>

<dialog id="skpick" class="picker">
  <div class="sktitle" id="sktitle"></div>
  <div class="pickhead">
    <input type="search" id="skfind" placeholder="Search&hellip;" autocomplete="off">
    <button type="button" id="skclear" class="pickbtn">Clear slot</button>
    <button type="button" id="skclose" class="pickbtn">Close</button>
  </div>
  <div class="pickrl">
    <label>Rank <select id="skrank" aria-label="Skill rank"></select></label>
    <label>Level <input type="number" id="sklevel" min="1" max="500" value="1" aria-label="Skill level"></label>
    <span class="hint">the rank and level this slot is equipped at; a change applies to the slot at once</span>
  </div>
  <div class="pickfilters">
    <select id="skclass" aria-label="Filter by class"></select>
    <select id="skele" aria-label="Filter by element"><option value="">Any element</option><option>Physical</option>
      <option>Wind</option><option>Water</option><option>Fire</option><option>Light</option><option>Dark</option></select>
    <span id="skcount" class="pickcount"></span>
  </div>
  <div id="sklist" class="picklist"></div>
</dialog>

<div id="detail" hidden>
  <h3>The fight above, as a table</h3>
  <p class="calcnote">The same seeded run the scene plays. The odds come from a thousand of these with fresh rolls.</p>
  <div class="tablewrap"><table class="log"><thead><tr>
    <th class="num">t</th><th class="num">turn</th><th>actor</th><th>skill</th><th>targets</th><th>hits</th>
    <th class="num">damage</th></tr></thead><tbody id="logbody"></tbody></table></div>
</div>

<details class="statbox"><summary>Load fighters from a roster export</summary>
  <p class="calcnote">Paste the JSON that <code>tools/liveproto/roster.py fighters</code> writes (or the
  <code>fighters.json</code> the site build produces from it). Fighters are kept in this browser only.</p>
  <textarea id="importtext" rows="4" class="importbox" placeholder='[{{"id": 1, "name": "…", "cls": "…", "sheet": {{…}}, "techs": […], "charms": […]}}]'></textarea>
  <p><button type="button" id="importbtn" class="pickbtn">Load</button> <span id="importmsg" class="hint"></span></p>
</details>

<div class="note">
{NOTES}
</div>
</div>
<script type="application/json" id="teamdata">{cfg}</script>
<script src="../assets/team.js?v={_b.asset_v()}" defer></script>
"""
    return layout("Team battle simulator",
                  "Four against four on Sword x Staff's battle grid: drag players off the live top-100 leaderboard, "
                  "place them, and run the real turn clock and damage formula.",
                  body, "combat", 1)
