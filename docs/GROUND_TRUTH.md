# Ground truth: real fights as the server plays them

## Why this exists

The simulators re-implement the battle rules from the client. Most rules are readable there (the damage
pipeline, cooldowns, areas, statuses, Charm components), but the decisions that shape a 4v4 are **not in the
client at all**: which skill a fighter casts, where it aims and walks, what happens when nothing is castable,
the exact opening order, the end-of-fight rule at the cap. `docs/ENGINE_AUDIT.md` marks those A (assumed) or
O (observed). No amount of reading the client closes that gap. The only thing that does is a recording of a
real fight, decision by decision, with the numbers the server actually rolled.

## The client is a playback device

Confirmed in the decompiled client (`out/decompiled`):

- `FightAIComponent`, `FightAIPlayStartComponent`, `FightAIFollowMasterComponent` are empty marker classes.
  There is no skill selector, no target scoring, no path choice anywhere in the client.
- A fight arrives as data: `GAME_START` (`FightProcessStartMsg`: stage, your faction), `GAME_ENTITY_LIST`
  (`FightEntityListMsg`: every entity with its components, which for a fighter means the server-computed
  `PropComponent.FinalProps`, `FightRoleFightComponent` HP and faction, `GridTransformComponent` cell,
  `FightSkillAgentComponent` slots with skill id, rank and level, `FightPassiveSkillAgentComponent` Charms,
  `FightRolePetComponent`), `GAME_START_COMPLETE` (player id to entity id), then `GAME_ROUND`
  (`FightEntityRoundMsg`) messages. Each round message is a list of `FightProcessStepMsg` steps, each a
  timestamp plus a nested message the client replays through its own network handlers
  (`GamePlayManager.PlayRound`).
- The steps carry everything the engine needs to check itself: a skill entity per cast (`FightSkillComponent`:
  caster, slot, aim cell, target), a damage entity per hit (`FightDamageComponent.DamageResult`: value, shield
  taken, absolute value, `IsCrit`, `IsBlock`, `IsDodge`, `IsBlinding`, element, hit class), a status entity per
  applied status (action type, target, stacks, duration, source), and modifications for the turn queue
  (`FightRoundAddDataModification` / `FightRoundUpdateDataModification` with `RoundRuntimeData.PreTime` and
  `NextTime`), whose turn it is (`FightRoundActingDataModification`), positions (`FightRolePlayerPosModification`),
  cooldowns, shields, stacks, HP and the game status (`PlayStart`, `Play`, `BattleEnd`).
- `PLAYER_GAME_RESULT` (`FightProcessResultMsg`) ends it with the winner, the winning faction, the round
  count and `GameBattleEndType` (`PlayerDie`, `RoundLimit`, `FastVictory`, ...): the cap rule, read straight
  from the server.
- The same stream is what an in-game replay plays: `FightProcessRecordSaveData` is the start messages plus the
  round messages, downloaded by game id. Watching a replay does not put the stream on the game connection
  (it is fetched over HTTP), so a **live** fight is what to capture.

All of it travels over the same unencrypted MessagePack-over-KCP connection that `tools/liveproto` already
captures and decodes. Nothing is sent by the client during a fight except "start", "change speed" and
"fast forward"; capturing is passive and changes nothing.

## How to record a fight

1. Start the capture as for the roster (`tools/liveproto/README.md`): an elevated PowerShell running
   `capture.ps1` while the game runs in BlueStacks.
2. In the game, play or watch a fight to its end: a Team Challenge match, an arena fight, or spectating one.
   Do not fast-forward; the fast-forward path drops the intermediate steps.
3. Stop the capture (`stop.txt`), then:

       python tools\liveproto\parse.py out\liveproto\capN\game.pcapng out\liveproto\capN\streams.json
       python tools\liveproto\gproto.py decode out\liveproto\capN\streams.json out\liveproto\capN\decoded.json
       python tools\liveproto\fights.py extract out\liveproto\capN\decoded.json -o out\fights
       python tools\liveproto\fights.py show out\fights\<gameId>.json

`extract` writes one JSON per fight under `out\fights\` (never committed) and an index. `show` prints it as a
log: the units with their server props and skills, then every step with its time.

## What gets checked against the engine

With one recorded fight, `fights.py fighters` exports its players in the team page's `fighters.json` shape
(sheet from `FinalProps`, skills with the ranks the server used, cells). The engine is then run on exactly that
setup and the two sequences are compared step by step:

| Question | Server record | Engine | Settles |
|---|---|---|---|
| Turn order and clock | `RoundRuntimeData.NextTime` per unit, `FightRoundActingDataModification` | activation order, `t` | C1–C4: the interval formula, tie order, queue seeding |
| Opening phase | game status `PlayStart` steps, casts in order | pre-battle ticks | P2, P4, P5: interleaved or per-fighter, Charms before Techniques |
| What was cast, at what, from where | skill entity: slot, aim, target; position modifications before it | plan (cell, aim) | T12, T13, M7, M8: the AI chain and the idle rule |
| Damage per hit | `DamageValue` with the crit/block/dodge flags | the same hit, same flags forced | D0–D19: the formula, exactly, with the server's own props |
| Statuses, shields, stacks, ticks | status entities, shield and stack modifications | applied statuses | S1–S10 |
| Pets and summons | pet entities, `FightRolePetEnergyModification`, summon units | (not yet modelled) | what they do and when |
| End of fight | `GameBattleEndType`, round count | winner, capped | C5, C6 |

Randomness (crit, block, random picks) cannot be matched roll for roll, so the damage check forces the recorded
flags into the engine's hit and compares the value; every other row is deterministic and must match exactly.
Each mismatch becomes an engine fix or a documented server rule; each match moves a row from A/O to V.

## Status

No fight has been captured yet. The decoder and the extractor are in place (`fights.py` round-trips hand-built
steps), the comparison tool is written once the first recording shows the real shape of the stream.
