# Formula hunting — where to look and what to search for

Once `./datamine.sh` has run, this is your field guide for finding specific
calculations in the dump. Everything below is a `grep` you can run against
`out/il2cpp/dump.cs`, `out/configs/`, and `out/unity_assets/`.

## Start from the report

`out/REPORT_formulas.md` is already the ranked index. Skim the top 20 files
first — they're sorted by how much combat/stat math they contain.

## High-value method names (in `dump.cs`)

```bash
grep -nE 'Calc|Compute|Formula|Damage|Attack|Defense|Mitigat|Critical|Crit|Hit|Dodge|Evasion|Penetrat|Resist|Heal|LevelUp|Exp' out/il2cpp/dump.cs
```

Names you'll typically find in a game like this:

- **Damage:** `CalcDamage`, `DealDamage`, `TakeDamage`, `OnHit`,
  `GetDamage`, `DamageHelper.*`
- **Final stats:** `GetFinalAtk`, `GetFinalDef`, `CalcAttribute`,
  `AttributeManager.*`, `RefreshAttr`
- **Crit/hit:** `CalcCritRate`, `IsCrit`, `CalcHitRate`, `CalcDodge`
- **Mitigation:** `Mitigation`, `DefReduce`, `ArmorFactor`
- **Progression:** `GetExpForLevel`, `LevelUp`, `CalcGrowth`, `ExpCurve`
- **Economy:** `CalcReward`, `DropRate`, `GachaRate`, `CalcPrice`

## Stat & attribute vocabulary

The battle/attribute enums reveal the full stat list. Search for the enum:

```bash
grep -nEi 'enum .*(Attr|Stat|Property|Prop)' out/il2cpp/dump.cs
```

Then look for the fields it drives:
`atk/attack, def/defense, hp/maxHp, mp, critRate, critDamage, hitRate,
dodgeRate, speed, penetration, resist, block, lifesteal, damageBonus,
damageReduce, elementDamage`.

## The coefficients (in `out/configs/` and `out/unity_assets/`)

The methods use fields whose *values* are in the data dump:

```bash
# find the balance tables
ls -S out/configs/**/*.json out/unity_assets/*.json 2>/dev/null | head
grep -rilE 'atk|growth|coeff|ratio|crit|skill|level|exp|drop' out/configs out/unity_assets | head -40
```

Look for tables keyed by level or by hero/skill id:

- **Hero base stats + growth per level** → `hero*`, `char*`, `unit*` tables.
- **Skill coefficients** (`ratio`, `multiplier`, `coeff`) → `skill*` tables.
- **Level/EXP curve** → a flat array indexed by level.
- **Defense→mitigation constant** (the `k` in `def/(def+k)`) → a global
  balance/const table.

## Reading actual arithmetic (method bodies)

`dump.cs` gives names, not bodies. For the real arithmetic:

1. Open `out/extracted/**/libil2cpp.so` in **Ghidra** (free).
2. Run the Il2CppDumper Ghidra script from the tool zip
   (`_tools/il2cppdumper/` → `ghidra_with_struct.py` + `script.json`) to
   apply the recovered names.
3. Navigate to the method (e.g. `CalcDamage`) and read the decompiled C —
   that's where you see `atk * ratio - def * factor`, crit multipliers, and
   clamps.

For **Unity Mono** games (if you find `Managed/*.dll` instead), skip Ghidra:
open the DLL in **ILSpy**/**dnSpy** and read C# directly — bodies included.

## A checklist for "all the formulas"

- [ ] Damage formula (physical + magic, if split)
- [ ] Defense/armor → mitigation curve and its constant
- [ ] Crit rate + crit damage multiplier
- [ ] Hit vs dodge/evasion resolution
- [ ] Penetration / resistance interaction
- [ ] Elemental / type advantage multipliers
- [ ] Healing / shield formulas
- [ ] Stat aggregation: base + per-level growth + equipment + buffs
- [ ] Level → EXP required curve
- [ ] Skill coefficient tables
- [ ] Drop / gacha probability tables
- [ ] Idle/offline reward accrual (this game is idle-RPG)

Tick each off as you confirm it in the dump.
