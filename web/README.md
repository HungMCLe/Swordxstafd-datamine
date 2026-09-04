# Purrwikimania — the site

Static site for the datamined *Sword x Staff* reference. No framework, no build step at deploy
time: `web/dist/` is committed and Vercel serves it directly.

```
web/
  build/          generator (run locally, commits its output)
    build.py      layout, localisation lookup, config readers, home/method/combat pages
    charts.py     inline-SVG line and bar charts (no library)
    calc_page.py  'Where your next point goes' — marginal damage per stat
    duel_page.py  duel simulator page
    site.py       entry point — remaining pages + main()
    skills_data.py    builds out/_skills.json (tier -> class -> skill, per-quality stats)
    skills_page.py    renders the skills page
    extract_skill_icons.py
  dist/           what Vercel serves. Committed.
    assets/
      style.css
      icons/      113 item icons extracted from the game
      skills/     328 skill icons
      skills.js   client-side rank stepper + skill-level / character-rank controls
      calc.js     stat calculator: differentiates the damage formula, draws its own charts
      duel.js     duel simulator: turn clock, cooldowns, Monte Carlo
      duel.json   162 Techniques with element, hit count and per-rank coefficients
      curves.json growth curves, fetched (too big to inline)
    index.html  method.html  top-up-ladder.html  combat/*.html
```

## Rebuilding

Needs the extracted data in `../out/` (not committed — it is ~3 GB and contains game assets):

```bash
pip install xxhash pillow
cd web/build
python skills_data.py   # regenerates out/_skills.json
python site.py
```

That regenerates every page into `web/dist/`. Commit the result; Vercel deploys on push.

## Where the content comes from

| Page | Source |
|---|---|
| Combat pages | `out/decompiled/Console/Common/BattleFormulaHandler.cs` |
| Elemental / crit tables | `out/config_decrypted/level_prop_battle_extra` + `player_subrank` + `role_prop_group` |
| Top-up ladder | `out/config_decrypted/accumulated_pay_award` |
| Skills | `profession_base` + `skill` + `skill_rank` (34 ranks -> quality +N) + `entity_prop_skill` / `entity_prop_status` / `PassivePropFactors` (factors) + `entity_prop_group_level` -> the growth curves listed in **`level_prop_files`** |
| Every name | `out/localization/text_en_US.bytes`, looked up by `XXHash64(key, seed=0)` |

`level_prop_files` is the game's own manifest of which `level_prop_*` CSVs are baked into
`Assets/Config/Binary/level_prop.bytes`. Only those are merged — reading the others produces
wrong numbers.

Names are never hand-translated — see `build.py:L()`. Keys follow the game's own patterns
(`item_{id}_name`, `accumulated_pay_desc_{tier}`).

## Deploying

The repo is wired for Vercel via `vercel.json` at the root (`outputDirectory: web/dist`, no build
command). Import the GitHub repo once at vercel.com and every push to the default branch deploys.
