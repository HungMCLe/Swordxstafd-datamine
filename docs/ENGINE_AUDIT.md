# Combat engine audit — what is the client's, what is observed, what is assumed

The team (4v4) and duel (1v1) simulators on Purrwikimania run a re-implementation of *Sword x Staff*'s battle
rules. The goal is an engine with **nothing invented**: every rule is either read from the client
(`out/decompiled`, the EC prefabs in `out/ec_decoded`, the config tables), observed in real fights, or clearly
labelled as an assumption on the page. This table is the inventory. It was rebuilt on 2026-09-09 after a full pass
over the engine; the fixes made during that pass are listed at the end.

Status codes: **V** verified in client code or data · **O** observed in real fights (rule is server-side) ·
**A** assumption, labelled on the page · **M** the client has it, the engine does not (labelled on the page).

## Clock and turns

| # | Rule | Status | Evidence |
|---|---|---|---|
| C1 | interval = 100000 / sqrt(max(1, SPD) × rank SpeedScale) | V | `BattleFormulaHandler.SpeedToTime`, `fight_rank_offset_damage.SpeedScale` |
| C2 | first NextTime = interval; earliest acts; equal times keep queue order | V | `FightRoundDriverComponent.AddRuntimeDataToList` (insert before the first strictly greater) |
| C3 | after acting, NextTime += interval at the current SPD | V/A | plumbing in the client (PreTime/NextTime/ResetTime); the `+=` itself is server-side |
| C4 | initial queue order = Team 1 slots then Team 2 slots | A | spawn order is not in the client |
| C5 | round cap = 100 player activations | V | `stage.MaxRound = 100`, `Battle.Round.GloablRoundCountTypes` |
| C6 | result at the cap: higher remaining HP share wins | A | `FightResult*` are stubs; rule unknown; labelled |

## Cooldowns and availability

| # | Rule | Status | Evidence |
|---|---|---|---|
| K1 | ready iff Round − LastRound > CD, counted in the owner's own rounds | V | `FightSkillAgentComponent`; user-verified sequence |
| K2 | opens the fight on CD+1 unless `ResetCDAtStart`; Rapid Cast's cut applies to the opening count | V/O | `ResetAllSkillCD`; user-verified |
| K3 | Stun freezes cooldowns | V | `FightStatusSkillStopCdComponent` |
| K4 | `LimitedTimes` respected | V | `FightSkillComponentInfo.LimitedTimes` |
| K5 | every ready Technique is cast, in slot order, in one activation; no per-activation cap | V/O | no cap anywhere in the client; 1v1 observation |
| K6 | no basic attack: with nothing ready the turn passes | V | no basic-attack skill exists in the client (removed from the engine in this audit) |
| K7 | no "skip a buff that is already up" rule | V | no such rule in the client (removed in this audit) |
| K8 | Replay (repeat-cast chance) | — | dead config: `Replay.Rate = 0` on every skill |

## The PlayStart phase

| # | Rule | Status | Evidence |
|---|---|---|---|
| P1 | skills flagged `TryAtStartType` fire before round 1 | V | `GameStatus.PlayStart`, `skill.TryAtStartType` (AutoAIAtStart / AutoSelfAtStart) |
| P2 | each tick every fighter fires its next start skill in slot order, the faster one first within the tick | O | observed in real fights by the user (both sides' Valor Surge before the faster tank's taunt). **Open question:** the in-game tooltip reads "they cast them from highest to lowest initial SPD ... If a character has multiple skills to cast before battle starts, Charms are cast before Techniques. Skills of the same type are cast in loadout order", which read strictly would let the fastest fighter cast all of its own start skills first. The observed interleaving is kept; the tooltip is quoted on the page |
| P4 | order is by *initial* SPD and never re-sorted during the phase | V | the same tooltip: "SPD changes during this phase do not affect the order" |
| P5 | Charms cast before Techniques within a fighter | M | the same tooltip. The three self-cast Charms in this data (Rapid Cast, Iron Fortress, Gale Shield) carry round-start hooks, which the engine runs on the holder's first round instead |
| P3 | a start cast may walk first like any AI cast | A | no evidence either way |

## Movement

| # | Rule | Status | Evidence |
|---|---|---|---|
| M1 | Manhattan distance, 4-way steps, uniform cost | V | `Pos2d`, `AStarUtils` |
| M2 | Tree/Block cells impassable; players walk None/Shallow | V | `GridMoverComponentInfo.WalkableGroundType` |
| M3 | living and dead players block cells | V | `GamePosData.BeBlocked`, `DestroyOnDie = false` |
| M4 | one hop ≤ `MoveDist` (4) | V | `CalcMoveDist` |
| M5 | no per-turn hop budget; a hop may precede every cast | V | move skills 15300/15310/15320 have no cost, CD or limit; `ActiveSkillWaitActionTypes` |
| M6 | reachable set = BFS within MoveDist through free cells | V | `GridMoverComponent.CalcAllMovablePos`, `CanStand` |
| M7 | destination chosen jointly with the aim by the skill's AI list | V/A | `AiPriorityTypes`, `IsReleaseSkillAfterMove`; the scoring loop is server-side |
| M8 | with nothing castable from anywhere in reach: walk toward the nearest enemy or the taunter | A | server-side; labelled on the page |
| M9 | caster displacement (`SourceMoveList`: Doom Blade's leap) | V | `FightSKillMoveCfg`: anchor = (RelativeToSource ? caster : aim) + rotated Offset; Distance −1 = nearest standable in `MyMath.LoopOut` ring order |
| M10 | victim pull / knockback (damage `MoveCfg`, incl. via child skills) | V | same config; Frozen/Immobilize/SuperArmor are not moved |
| M11 | a walk is resolved at its destination (cells crossed mid-path fire nothing) | A | the client walks a path step by step; labelled |

## Targeting, facing and areas

| # | Rule | Status | Evidence |
|---|---|---|---|
| T1 | aim offsets = `FightSkillComponentInfo.Range` | V | prefab |
| T2 | area = `HitScopCfg` cells around the aim, or the caster when `ActOnSouce`; a summoning hit's area = `SummonScope` | V | prefab, `FightHitSummonComponentInfo.Init` (BaseScopes) |
| T3 | facing = `Pos2d.LookDirection` (exact diagonals resolve horizontally; (0,0) → Up) | V | client |
| T4 | flip on X when the aim is left of the caster; unchanged when dx = 0 | V | `CalcFlipX` |
| T5 | rotation = flip x, then rotate (`CalcLocalToWorldDir`) | V | client |
| T6 | `HitTargetType` Me/Enemy/Friend/FriendNotMe/All/None | V | `GameUtils` |
| T7 | `SkillTargetType`: Entity needs a unit on the aim, PosCanStand a free cell (the caster leaps) | V | client |
| T8 | random-target hits: one pick per HitCfg, with replacement, from the pool; empties allowed unless `AllowEmptyScope` off; `MiniHitTargetCount`; NotSame* flags | V | `FightHitRandomTargetComponentInfo` |
| T9 | chained hits: one strike plus N links (`NextHitList` depth), each link a random unit within the skill's own reach of the last victim, no repeats (`Repeat` off), never straight back (`Back` off) | V/A | `FightHitChainedComponentInfo`; the hop reach being the skill's `Range` is the reading that matches the card text ("within 4 grids of the target"); the random draw is server-side (fixed in the fourth pass) |
| T10 | grid items from summoning hits (Meteoric Flames' Burn cells) | V | `SummonGridItemId` 3320 + status 11542 with `FightStatusMoveNearComponent` (TryAtStart / TryAtEnterRange / TryAtStandRound), 3 creator rounds, `RemoveAtRoundTargetDie` |
| T11 | creature summons: the creature spawns on the hit's `SummonScope` cell (nearest free if taken), acts at once (`SummonImmediateRound`), takes its own turns (`RoundDataDrive`), blocks its cell (`GroundType Wall`), is removed on death (`DestroyOnDie`) and fades after 5 of its own turns (lifespan status with `RemoveApplyEntity`); it never decides the result (`NotCheckFightResult`) or counts toward the cap | V | prefabs 3181/3184/3190, `monster`, `monster_group` (fixed in the fourth pass) |
| T11b | summon stats: fixed part = `CalcSkillProps(summon_monster_fix_prop, skill rank, skill level, caster sub-rank)`; inherited part = caster prop × `summon_monster_add_prop` share × `summon_rank_additive_factor[rank group][rank]`; "Summons cannot receive any stat boosts" | V | `BattleFormulaHandler.CalcSummonMonsterInheritProp`, `CalcSkillProps`; the in-game tooltip |
| T11c | summon skills and passives from `monster_group`, at the summoning skill's rank and level (`SummonSkillInfo`); opening cooldowns follow the fighters' rule | V/A | the opening-cooldown rule for a mid-fight entity is not in the client |
| T11d | Stealth: never the main target of an attack or heal while a visible unit of the pool can be; still under areas | V | `FightStatusActionInvisibleComponent` + the in-game tooltip |
| T11e | `FightStatusRoundIntervalComponent`: the holder's next turn moves by `RoundIntervalPercent` of its interval (earlier when `FastForward`) | V/A | the component; the exact arithmetic on the action bar is server-side |
| T11f | `DisperseStatus` on a damage entity strips `Count` statuses of the listed types that allow it (`CanDispersed`) | V | `FightDamageComponentInfo.DisperseStatus` |
| T11g | auras (`FightStatusMoveRangeComponent`, `TargetCloseTriggerStatus`): units of the target kind inside the range carry the status, checked on spawns and moves | V/A | the component; whether the buff drops on leaving is not in the client |
| T11h | Decoy Clone (voodoo doll) and Blast Spirit (smart grid item) | M | equipped by nobody in the top 100 |
| T12 | AI chain: the skill's own list, else the chain written on the 14 skills that carry one; the last cast uses `LastAIPriorityTypes` unless `DontKeepDistance` | V/A | criteria names V; the server's default chain is unknown |
| T13 | criterion semantics (LowerTargetHp = HP ratio, SaferPos = distance to the nearest enemy, ...) | A | names only |
| T14 | taunt, in the game's own words: "Taunted enemies target the caster only, and approach the caster when using damaging Techniques. Summoning Techniques remain available, but ally-targeting Techniques (grant buffs, healing, shields, etc.) are disabled while taunted." | V | in-game keyword tooltip. Implemented in the second pass: aim only at the taunter; ally-targeting Techniques unavailable (summoning ones stay); a damaging Technique never uses the keep-distance ordering and closes on the taunter to break ties. Where "approach" ranks among the skill's own priorities is server-side, so it sits last (A) |
| T15 | `BattleAISetting` weights (teammate distance, bunching penalty, same-buff weights) | M | unused by the client |
| T16 | `HitTargetActionType` | — | a no-op in the client |
| T17 | a hit's targets are the units under its cells at the moment it lands, after every earlier hit of the same cast has moved units (pulls, knockbacks, leaps) | V | the hits of one skill are separate entities landing at their own delays; fixed 2026-09-12 — Hunter's Judgment pulled its targets in front of the caster and then struck the cells they had left |

## Damage and rolls

| # | Rule | Status | Evidence |
|---|---|---|---|
| D0 | a non-elemental hit (`ElementType.None`, which this site labels Physical) takes the **mean of the five** Affinities on the attacker and the mean of the five elemental resistances on the target, over the same bases as an elemental hit; only Mastery switches to the KongFu pair | V | `Damage()` switch. The engine was using zero for both terms, which is wrong for 38% of the equipped Techniques, Eclipse Slash and Sunset Sword among them. The two missing terms largely cancel, so the error per matchup ran from about -7% to +25% rather than the halving a first look suggested |
| D1 | `Damage()` pipeline: (ATK × coef / psdr + flat) × ATK/(ATK+DEF) × elemental ratio × percent block / prosdr × PvpPropScale; 90% floor on flat adds | V | `BattleFormulaHandler.Damage` |
| D2 | roll order per hit: the attacker's `BlindingPercent`, then the target's `DodgePercent`, then block, then crit; a blinded or dodged hit deals 0 and applies no status; a blocked hit never crits | V | `CalcDamageTypeImpl`, `Damage()` early returns (fixed in the second pass: Blind was a guaranteed miss for a whole cast, Dodge was never rolled) |
| D3 | crit chance = 0.05 + (CritRatePercent + CritRatePercentValue/Base) − (CritAvoidPercent + CritAvoidPercentValue/Base); mult = max(1.3, 1 + CritPowerPercent − crit avoid) | V | same |
| D4 | block chance = (BlockPercent + BlockPercentValue/Base) − (BlockAvoidPercent + BlockAvoidPercentValue/Base); divisor = max(1.5, 1 + BlockValuePercent − attacker's block avoid) | V | same |
| D5 | `HitDamageType.None` hits deal nothing (statuses, moves and child skills still apply) | V | `CalcDamageType` computes only Prop/CustomDamage/SkillCost; `GameRoundUI` (fixed in this audit) |
| D6 | child skills (`ChildSkillCfg`) cast on every unit the parent hit covered, with their own rows, PvP scale and governor gate | V | `FightDamageComponentInfo.ChildSkillCfg` |
| D7 | per-target falloff: damage × (1 − p)^n, n = earlier hits of the root skill on that target (`NumOfStart`, `MaxFalloffCount`) | V | `FightStatusDamageFalloffComponentInfo` tooltip (fixed in this audit: was per cast) |
| D8 | shields absorb before HP; `DamageIgnoreShield` hits | V | |
| D9 | death save (HpLimit) + heal on the card | V | |
| D10 | PvP governor: survival floor × skill-rank decay × balance; skill-rank input = per faction max of member average rank, then mean | V | `PVPSkillPropsScaleOnBattleProcessor`, `SkillRankPropScaleCalculator` |
| D11 | governor scales only prop groups with `AffectedBySkillRank`; never heals or shields | V | `ScaleDamage` gate (fixed in this audit) |
| D12 | `PvpPropScale` on skill props except CD | V | `ScaleSrcPropsByPvp` |
| D13 | `Cure()`: (MaxHp × SkillCureByHp \| Attack × SkillCureByAttack \| target MaxHp × SkillCureByTargetHp) + SkillFixedCure, × (1 + CureAddPercent + BeCureAddPercent + CureAdd/Base + BeCureAdd/Base) × (1 + FinalCureScale) | V | `BattleFormulaHandler.Cure`, `CalcCureAdd` |
| D14 | landing rolls: `EffectRate()` with the cubed-ratio penalty for AbnormalDebuff | V | client |
| D15 | Blind is a *chance*: the status grants its holder `BlindingPercent` 50% for one Technique (`DurationSkillCount` 1), rolled per hit | V | status 24234 props; `CalcDamageTypeImpl` |
| D16 | Dodge: the target's `DodgePercent`, rolled per hit. Only status 24209 (Void Bubble) grants it in this data, and it did nothing before the second pass | V | status 24209 props |
| D17 | `StatusDmgAddPer` (src) and `StatusDmgVulnerablePer` (tgt) multiply, `StatusDmgReducePer` (tgt) divides, as their own stage after the percent block — not folded into DmgAddPercent/DmgReducePercent | V | `Damage()`; 17/5/10 statuses carry them |
| D18 | flat `CritPower` added and flat `BlockValue` subtracted inside the additive term when the hit crits or is blocked, before the skill coefficient and under the same 90% floor | V | `Damage()` num3. Nothing in this data carries either (98 sheets, 138 statuses at every rank, 322 skills, 68 trigger skills all scanned), so the path is exercised by an injected test rather than by live data: a crit gains exactly `CritPower` times the per-point value of any flat add, a block loses exactly `BlockValue` times it, and a `BlockValue` larger than the hit leaves 10% of the base |
| D19 | defence ignore, percent and flat (`StatusIgnoreDefence`, `FixedStatusIgnoreDefence`), applied to the target's Defence before the attack-over-attack-plus-defence term | V | `Damage()`; nothing in the data carries either, so it is covered by an injected test |
| D19b | `FinalDamageScale` and `FinalCharacterDamageScale`, the latter because a PvP target is always a character | V | same; injected test |
| D19c | the missing-HP bonus: `floor(missing fraction / SkillTargetReduceHpPer)` steps of `SkillDmgUnitAddPer`, capped at `SkillDmgMaxAddPer`, then `SkillDmgAddPerByTargetHp` times the target's max HP, both after the crit and block steps | V | same; injected test drives a wounded target and matches the ratio exactly |
| D19d | profession damage scales (`ZhanshiDmgAddScale` and kin) | M | the switch in `Damage()` has a case only for the six base professions; every captured fighter is an advanced class (Dunjiashi, Modaoshi, Kuangzhanshi, Mishushi), so the term is structurally zero for them whatever the props say |
| D19e | cooking finals (17 properties), distance bonuses, monster and large-target bonuses | M | food buffs appear on no captured sheet; the unit of `info.Distance` is not verifiable from the client; the monster terms need a monster target |
| D20 | level offset and rank offset damage | — | `Damage()` applies both only when `!IsPvp`; this is PvP |
| D21 | combat-rating suppression | M | `IsCombatRatingSuppressionEfective` returns true in PvP, but the value comes from the battle setup and the config table (`fight_combat_rating_suppression`) is keyed by target level against a recommended power, i.e. the PvE band mechanic; the PvP balancer we do model is the governor |

## Statuses and Charms

| # | Rule | Status | Evidence |
|---|---|---|---|
| S1 | durations count the holder's own turns; tick at end of own turn; expiry triggers | V | |
| S2 | round-start ticks (poison) | V | |
| S3 | control per `state_mutex`: Stun/Frozen/PhoenixStasis discard move+skill; Restrict/Immobilize discard the move | V | config |
| S4 | statuses that last N casts (`DurationSkillCount`) | V | `FightStatusHitDmgAddPerComponent` |
| S5 | Charm passive stats are already in BattleProps, so only procs run | V | `SkillPropChunck`; stats screen equals BattleProps |
| S6 | when-hit / on-hit conditions: Block, Crit, Damage, Cure flags, `ConditionCount`, `EachRoundMaxCount`, element and skill filters, `SkillTargetType` Enemy | V | `FightStatusDamageBaseComponentInfo`, `FightStatusHitBaseComponentInfo` (fixed in this audit: Rebound fired on every hit) |
| S7 | a triggered skill with `CanTriggerChild = false` sets off no further hooks | V | `FightSkillComponentInfo.CanTriggerChild` (Radiant Sear's, Rebound's strikes, Burn ticks) |
| S8 | hook chains stop at depth 4 | A | engine guard against runaway chains; labelled |
| S9 | modelled Charm components: HitSkill, DamageSkill, RoundStart, RoundEnd, RoundCheck, SkillStart, SkillEnd (every Nth cast), HpDecreaseUnit/HpIncreaseUnit, HpBelow, HpLimit (death save), StatusStackCount, StatusApplyTargetHandle, DoDamageHandle, HitDmgAddPer, RoleDie (revive), DamageCustom (reflect), MoveNear (proximity and grid items), ActionEnd, HitCustomCure (lifesteal), KillSkill, ActionExist | V | `out/ec_decoded` components; `web/build/ec_data.py` |
| S10 | grid-item statuses count on the creator's rounds and vanish with the creator | V | `RoundTarget Creator`, `StatusAutoRemove.RemoveAtRoundTargetDie` |
| S12 | fourth-tier Charms from the 12 September capture: Tactical Adaptation (`TargetCountAffectStatusOwnerSetting`: met while enemies within the range ≤ TargetCount; met/not-met status lists swap), Soul Breaker (`FightStatusHitApplyDamageComponent`: AddPercentPropType × floor(target's missing HP / HpDecreaseUnit), capped at MaxHpScale), Holy Aegis (`FightStatusPropByStatusComponent`: the wearer's shields with an IncludeProptypes prop grow by StatusShieldAddPercent), Explosive Spirit (`FightStatusSkillStartComponent` with element and action-type settings), Iron Will (`FightStatusDamageProcessComponent`: ReducePercentPropType when the attacker carries a SourceActionTypes action), Aberrancy (`FightStatusDamageReducePerComponent`: StatusDmgReducePer scaled by the attacker's statuses of the listed types, at most MaxStatusCount), Summoner's Frenzy and Soul Spark (`FightStatusHitSummonComponent` Create: a status on each new summon; `FightStatusReduceStatusLifeComponent` cuts the lifespan, floor 1), Soul Impact (`FightStatusHitSummonComponent` Remove: a skill at the fallen summon's cell), Soul Pact Resonance (`FightStatusRoleSummonCountComponent`: a status while a summon is on the field) | V/A | the components' Info tooltips; the re-check moments for the range and count hooks (turn start, move, spawn, death) are the engine's reading of "removed when leaving the range" |
| S11 | Fantomon (pets): battlefield 910 spawns the engaged pet (`FightRolePetSpawnerComponent` on its root); the follower rides the master's cell (`GridTransformFollowerComponent`), is untargetable (`SafeAttacker`, no grid body), takes no turn (`FollowMaster`), fires its support skill when the master starts an Attack Technique (`FightAIFollowMasterComponent`, `MasterSkillTypes`, per-pet `CountConditionCfg`) with damage on the pet's own Attack | M | the follower form's props are server-side (`pet_battle` is dead config; `summon_monster_*` rows exist only for the materialized form); waits for a recorded fight |

## Third pass, 2026-09-09: non-elemental damage

A physical hit was losing both of its elemental terms. `Damage()` treats `ElementType.None` like any other
element except that the Affinity and Aegis figures are the mean of the five, and Mastery uses the KongFu pair.
The engine set both to zero. Fixed in both engines; elemental hits are byte-identical afterwards, and the
injected tests still pass. See D0.

## Second pass, 2026-09-09 (user-reported)

Prompted by three questions: a taunted fighter walking away from its taunter, a single Meteoric Flames doing far
more damage than expected, and whether the damage pipeline is really the client's.

- **Taunt was half-implemented.** Aiming was forced at the taunter, but the fighter still used the keep-distance
  ordering on its last cast of the turn and so retreated (Purr, taunted by Wei, walked from 2 cells away to 6),
  and it could still cast buffs, heals and shields on itself and allies. Both now follow the in-game taunt text.
  Over 300 logged fights no taunted fighter now ends a move more than one cell farther from its taunter, and the
  only ally-targeting casts under a listed Ridicule happen after the taunter has fallen.
- **Dodge was never rolled** and **Blind was a guaranteed miss** for a whole cast. Both are per-hit rolls in
  `CalcDamageTypeImpl`, on the target's `DodgePercent` and the attacker's `BlindingPercent` respectively.
- **The three status-damage props** now form their own multiplicative stage instead of being folded into the
  DmgAddPercent / DmgReducePercent block.
- **Flat Crit Power and flat Block Value** now join the additive term on a crit and a block, as `Damage()` does.
- **Defence ignore, the two final scales and the missing-HP bonus** are in as well, so every term `Damage()`
  applies to a player-versus-player hit is now modelled except the five noted at D19d and D19e.
- None of those properties appears anywhere in the captured data (98 sheets, 138 statuses at every rank, 322
  skills, 68 trigger skills were scanned), so they are covered by injected tests rather than by a live fight:
  eight checks, each comparing against the figure `Damage()` gives, including the 90% floor and a wounded target
  earning exactly one step of the missing-HP bonus. Odds over 1,000 fights are unchanged.
- Properties now carried from a captured sheet through the exporter and the engine, so a later capture that does
  contain them works rather than silently dropping them.
- **The damage pipeline was re-derived term by term against `Damage()`** and matches, including the elemental
  divisor split, the two per-rank PvP scalers and where each sits, the additive term's 90% floor, and the crit and
  block multipliers with their avoid terms. The large hits are real: at Champion I a Meteoric Flames from an
  Archmage onto a low-DEF Arcanist computes to about 250K from the coefficient plus about 148K from the skill's
  flat term, so roughly 398K, and a crit at 1.57x makes about 625K before the PvP governor. What the client would
  add beyond this is listed as D18&ndash;D21, and every one of those props is zero in the captured data.

## Fixes made in the first 2026-09-09 pass

- Removed inventions: the basic attack, the redundant-buff skip, one walk per turn, the "keep distance" chain, self-centred aims facing the nearest enemy, a speed-sorted pre-battle list.
- Added client rules that were missing: crit/block value terms and the attacker's block avoid in the divisor; the full `Cure()`; the governor gate per prop group (heals and shields never scaled); `HitTargetType` None/All; `SkillTargetType` checks; facing and flip rules; `SourceMoveList` leaps and damage `MoveCfg` pulls; random-target picks grouped per HitCfg; child skills on every covered unit; fourteen Charm component types.
- Found and fixed in the final pass: hits typed `None` were dealing damage (Wind's Delight counted twice, 2.8M in one cast); falloff was counted per cast instead of per target and never reached child hits; when-hit Charms ignored their Block/Crit/Damage flags (Rebound struck back on every hit, killing its attacker in one cast); Meteoric Flames covered one cell instead of its 3×3 and spawned no Burn cells; round-start events were dropped from the log when the unit then cast.
- The `_duel.json` dataset is rebuilt by `web/build/skills_data.py`; `site.py` only renders pages from it.

## Fourth pass, 2026-09-10: summons, chains, the fight stream

Creature summons are now run from the client's own tables and formulas (T11–T11g); Lightning Chain hops (T9);
skills that target no unit (summons) can now be planned at all, which they could not be before. The pet mechanics
are read (S11) but their numbers are not in the client. The decisive finding of this pass is that the client is a
playback device (below): every rule still marked A or O is now within reach of a recorded fight.

## Ground truth

Every row marked A or O above is a server decision the client does not contain. The client turns out to be a
pure playback device: the fight server streams each cast, each hit's damage with its crit/block/dodge flags,
each status, the turn queue's times, positions and cooldowns, and the result names the winner and the end rule.
`tools/liveproto/fights.py` records such a stream from a passive capture; `docs/GROUND_TRUTH.md` explains the
capture and the step-by-step comparison that will turn those rows into V or into documented server rules.
