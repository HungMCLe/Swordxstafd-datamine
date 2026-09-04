# Purrwikimania — the site

Static site for the datamined *Sword x Staff* reference. No framework, no build step at deploy
time: `web/dist/` is committed and Vercel serves it directly.

```
web/
  build/          generator (run locally, commits its output)
    build.py      layout, localisation lookup, config readers, home/method/combat pages
    site.py       entry point — remaining pages + main()
  dist/           what Vercel serves. Committed.
    assets/
      style.css
      icons/      113 item icons extracted from the game
    index.html  method.html  top-up-ladder.html  combat/*.html
```

## Rebuilding

Needs the extracted data in `../out/` (not committed — it is ~3 GB and contains game assets):

```bash
pip install xxhash pillow
cd web/build
python site.py
```

That regenerates every page into `web/dist/`. Commit the result; Vercel deploys on push.

## Where the content comes from

| Page | Source |
|---|---|
| Combat pages | `out/decompiled/Console/Common/BattleFormulaHandler.cs` |
| Elemental / crit tables | `out/config_decrypted/level_prop_battle_extra` + `player_subrank` + `role_prop_group` |
| Top-up ladder | `out/config_decrypted/accumulated_pay_award` |
| Every name | `out/localization/text_en_US.bytes`, looked up by `XXHash64(key, seed=0)` |

Names are never hand-translated — see `build.py:L()`. Keys follow the game's own patterns
(`item_{id}_name`, `accumulated_pay_desc_{tier}`).

## Deploying

The repo is wired for Vercel via `vercel.json` at the root (`outputDirectory: web/dist`, no build
command). Import the GitHub repo once at vercel.com and every push to the default branch deploys.
