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
<p><b>The board is the game's.</b> Team Challenge 4v4 (stage 9998) fights on battlefield 910: a 21 by 20 grid,
Y up, distance counted in cells (<code>Pos2d.Distance</code> is Manhattan). Each side deploys inside a 5-wide,
4-deep box around its entry cell (<code>stage.TeamChangePosRange = {5, 4}</code>: columns 9&ndash;13, rows
7&ndash;10 for Team 1 and rows 11&ndash;14 for Team 2), one fighter per cell, and the two boxes touch. The page
shows the boxes with two cells of margin; fighters may wander further during the fight.</p>
<p><b>Reach and area come from each skill's prefab.</b> A skill lists the cells, relative to the caster, where its
aim point may be placed (<code>FightSkillComponentInfo.Range</code>, near to far), and every hit lists the cells
it covers around that aim point, or around the caster when the hit acts on its source
(<code>HitScopCfg</code>, <code>HitCfg.ActOnSouce</code>). Areas are authored facing up and turned to face the
aim, as <code>CalcLocalToWorldDir</code> does. Heart of Challenge, for instance, has no reach of its own but
covers every cell within three of the Paladin; Howling Hurricane reaches five cells away and covers a
two-cell diamond there.</p>
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
for its last. A basic attack on an adjacent enemy happens when nothing is ready, and a fighter with nothing in
reach walks toward the nearest enemy. A fallen player keeps its cell (<code>DestroyOnDie = false</code>), so
bodies block paths.</p>
<p><b>Before round 1: the PlayStart phase.</b> The fight has a <code>PlayStart</code> status before
<code>Play</code>, during which the AI is driven on a fixed interval (<code>Battle.DrivePlayStartAIInterval</code>),
and the skill table marks what fires then (<code>skill.TryAtStartType</code>: Heart of Challenge, Valor Surge,
Gale Dance, Void Blessing are "Casts once before battle starts"; the self-cast Charm effects such as Rapid Cast are
<code>AutoSelfAtStart</code>). The order among fighters is server-side; what real fights show, and what this page
does, is that every fighter fires its next start skill on each tick, the faster fighter first within the tick, so
both sides' opening buffs land before the faster tank's taunt. A taunt such as Heart of Challenge lands
<i>Ridicule</i> on every enemy within three cells, and for as long as that lasts each of them must aim at the
taunter, walking to it if needed. Every other skill with a cooldown opens the fight on it unless it is a Zero
Initial CD skill.</p>
<p><b>Not modelled.</b> Fantomon ride along off the clock and are untargetable in the real fight; their
triggered skills are not run here. The end-of-fight rule at the 100-round cap is server-side and unknown, so
a capped fight is scored by remaining HP. The AI's scoring loop is server-side: the criteria and each
skill's ordering are the client's, their default ordering and the global weights in
<code>BattleAISetting</code> (preferred distance to teammates, bunching penalty) are not modelled.</p>
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
    cfg = json.dumps({"ranks": ranks, "minCrit": 1.3, "minBlock": 1.5, "pvp": pvpgov, "speedScale": spd_scale,
                      "v": _b.asset_v(), "grid": grid, "fightersUrl": fighters_url}, ensure_ascii=False).replace("</", "<\\/")

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
equipped, each at its own rank and level.</p>

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
