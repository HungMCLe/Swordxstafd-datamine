#!/usr/bin/env python3
"""Purrwikimania static site builder.

Reads the datamined config/localisation in ../../out and writes a static site
into ../dist (which is what Vercel serves).
"""
from __future__ import annotations
import csv, io, json, os, re, shutil, struct, sys, html
from pathlib import Path
import xxhash

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]        # repo root
OUT  = ROOT / "out"
DIST = ROOT / "web" / "dist"
CFG  = OUT / "config_decrypted"

SITE = "Purrwikimania"
TAGLINE = "Sword x Staff, datamined"

# ---------------------------------------------------------------- localisation
_d = (OUT / "localization" / "text_en_US.bytes").read_bytes()
_n = struct.unpack_from("<i", _d, 0)[0]
_start = 4 + _n * 12
_idx = {}
for _i in range(_n):
    _h, _o = struct.unpack_from("<Qi", _d, 4 + _i * 12)
    _idx[_h] = _o

def L(key: str):
    h = xxhash.xxh64(key.encode("utf-8"), seed=0).intdigest()
    if h not in _idx:
        return None
    o = _start + _idx[h]
    ln = struct.unpack_from("<H", _d, o)[0]
    return _d[o + 2:o + 2 + ln].decode("utf-8", "replace")

def csvrows(name):
    p = CFG / name
    return list(csv.reader(io.StringIO(p.read_text(encoding="utf-8-sig", errors="replace"))))

# ---------------------------------------------------------------- layout
NAV = [
    ("Home",            "index.html",              "home"),
    ("Combat mechanics","combat/index.html",       "combat"),
    ("Top-up ladder",   "top-up-ladder.html",      "topup"),
    ("Method",          "method.html",             "method"),
]

def layout(title, desc, body, active, depth=0):
    up = "../" * depth
    nav = "".join(
        f'<a href="{up}{href}"{" aria-current=\"page\"" if key==active else ""}>{html.escape(label)}</a>'
        for label, href, key in NAV)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)} · {SITE}</title>
<meta name="description" content="{html.escape(desc)}">
<meta property="og:title" content="{html.escape(title)} · {SITE}">
<meta property="og:description" content="{html.escape(desc)}">
<meta property="og:type" content="website">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Spectral:ital,wght@0,400;0,600;1,400&family=Barlow:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<link rel="stylesheet" href="{up}assets/style.css">
</head>
<body>
<header class="masthead"><div class="masthead-in">
  <a class="brand" href="{up}index.html"><span class="paw">&#128062;</span>{SITE}<small>{TAGLINE}</small></a>
  <nav class="top">{nav}</nav>
</div></header>
{body}
<footer class="site"><div class="in">
  <p><b>{SITE}</b> — an independent, fan-made reference for <i>Sword x Staff</i> (Boltray Games).
  Every number here is read directly out of the game's own configuration files and decompiled code,
  not from testing or estimation. Item names are the game's official English strings.</p>
  <p>Not affiliated with or endorsed by Boltray Games. Game names, images and data are the property of their owners.
  Figures reflect the client build they were extracted from and can change with any patch — see
  <a href="{up}method.html">Method</a> for exactly what was read and when.</p>
</div></footer>
</body>
</html>
"""

def write(relpath, htmltext):
    p = DIST / relpath
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(htmltext, encoding="utf-8")
    return len(htmltext)

# ---------------------------------------------------------------- data
def load_tiers():
    return json.loads((OUT / "_topup_tiers.json").read_text(encoding="utf-8"))

def base_tables():
    """(rank display, level cap, BaseElementMaster) ladder + per-level dict."""
    disp = ["No Rank"]
    for g in ["Apprentice","Elite","Expert","Champion","Master","Paragon","Saint",
              "Ascendant","Divinity","Eternity","Genesis","Void"]:
        disp += [f"{g} {r}" for r in ("I","II","III")]
    ps = csvrows("player_subrank")
    sr = [(r[0].strip(), int(r[1])) for r in ps[2:] if len(r) >= 2 and r[1].strip().isdigit()]
    rpg = csvrows("role_prop_group"); grp = {}
    for r in rpg[2:]:
        if len(r) >= 3 and r[0].strip() == "1" and r[1].strip() and r[2].strip().isdigit():
            grp[r[1].strip()] = int(r[2])
    name = {nm: (disp[i] if i < len(disp) else "(unreleased)") for i, (nm, _) in enumerate(sr)}
    be = csvrows("level_prop_battle_extra")
    ix = {c.strip(): i for i, c in enumerate(be[0])}
    B, BA, BC = {}, {}, {}
    for r in be[2:]:
        if len(r) > 3 and r[0].strip().isdigit():
            k = (int(r[0]), int(r[1]))
            B[k]  = int(r[ix["BaseElementMaster"]])
            BA[k] = int(r[ix["BaseElementAdd"]])
            BC[k] = int(r[ix["BaseCritRatePercentValue"]])
    ladder = []
    for nm, cap in sr:
        cid = grp.get(nm)
        if cid is None or (cid, cap) not in B: continue
        ladder.append({"rank": name[nm], "internal": nm, "cap": cap, "cid": cid,
                       "bem": B[(cid,cap)], "bea": BA[(cid,cap)], "bcr": BC[(cid,cap)]})
    return ladder, B, BA, BC, sr, grp, name

# ---------------------------------------------------------------- pages
def page_home():
    body = """
<div class="wrap">
<p class="eyebrow">Independent datamined reference</p>
<h1>The numbers behind <em>Sword&nbsp;x&nbsp;Staff</em></h1>
<p class="lede">Every figure on this site is read straight out of the game's own configuration
tables and decompiled code — the same files the client reads at runtime. Nothing here is estimated,
inferred from testing, or translated by hand.</p>

<div class="facts">
  <div class="fact"><b>3,249</b><span>Config tables read</span></div>
  <div class="fact"><b>4,349</b><span>Lines of combat code</span></div>
  <div class="fact"><b>353</b><span>Stats catalogued</span></div>
  <div class="fact"><b>75</b><span>Top-up tiers</span></div>
</div>

<h2>Start here</h2>
<div class="cards">
  <a class="card" href="combat/damage.html"><span class="rail"></span>
    <h3>The damage formula</h3>
    <p>Every step of a single hit, in order, with a worked example using real player and monster stats.</p>
    <span class="tag">Combat</span></a>
  <a class="card" href="combat/elemental.html"><span class="rail"></span>
    <h3>Elemental Mastery</h3>
    <p>Why your Mastery number means nothing on its own, and the hidden per-rank value it is measured against.</p>
    <span class="tag">Combat</span></a>
  <a class="card" href="combat/speed.html"><span class="rail"></span>
    <h3>SPD and turn order</h3>
    <p>Speed is not initiative — it buys turn frequency, on a square root. What that actually costs.</p>
    <span class="tag">Combat</span></a>
  <a class="card gold" href="top-up-ladder.html"><span class="rail"></span>
    <h3>Top-up ladder</h3>
    <p>All 75 cumulative spending tiers, $5 to $150,000, with every reward and its real icon.</p>
    <span class="tag">Economy</span></a>
</div>

<h2>Why this exists</h2>
<p>Most guides for this game describe what a stat feels like. This one shows the line of code that uses it.
Several mechanics turn out to work very differently from how they are usually explained — Elemental Mastery
is scored against a hidden per-rank value rather than used raw, SPD scales on a square root so doubling your
turns costs four times the stat, and the flat "+1K" versions of Crit and Effect stats decay hard as you rank up.</p>

<div class="note">
<p><b>Everything is dated and sourced.</b> Game balance changes with patches. Each page states which client
build its numbers came from, and the <a href="method.html">Method</a> page documents exactly how the files
were read, so anything here can be re-checked or challenged.</p>
</div>

<h2>Coming next</h2>
<p>A full skill database — every skill at every level and rarity, for all classes, with the exact coefficients
and how rarity changes the numbers.</p>
</div>
"""
    return layout("Home", "Datamined reference for Sword x Staff: combat formulas, stat tables and the top-up ladder, read from the game's own config files.", body, "home", 0)


def page_method():
    body = """
<div class="wrap narrow">
<p class="eyebrow">Method</p>
<h1>How these numbers were obtained</h1>
<p class="lede">So that anything on this site can be checked, challenged, or reproduced.</p>

<h2>Sources</h2>
<p>Two, and pages say which they used:</p>
<ul>
  <li><b>Client build 1.0.0 (155652)</b> — the shipped Android package. Holds the code and the base config tables.</li>
  <li><b>Client build 88_156110</b> — a live install's downloaded cache. Newer, and the source for assets and
      tables the package does not contain.</li>
</ul>
<p>The package only carries about a quarter of the game's assets; the rest download on first launch.
Anything version-sensitive is taken from the newer build.</p>

<h2>Reading the code</h2>
<p>The game is Unity IL2CPP, but the gameplay logic is not compiled into the binary — it ships as
HybridCLR hot-update assemblies, ordinary .NET DLLs stored as text assets. Decompiling those gives readable
C#. All combat maths on this site comes from one file, <code>BattleFormulaHandler.cs</code> (4,349 lines),
inside <code>Console.dll</code>.</p>

<h2>Reading the tables</h2>
<p>Balance data lives in config bundles that are obfuscated with a single-byte XOR (<code>0x40</code>).
Undoing that yields 3,249 plain CSV tables — level curves, monster stats, drop rules, the reward ladders.
Column headers are English; a second header row carries the designers' own Chinese comments, which is often
the clearest statement of what a column means.</p>

<h2>Names</h2>
<p>Item and stat names are <b>not</b> translated here. The game's English localisation is a binary keyed by
a 64-bit hash of each string's key, so names are looked up exactly as the game would:</p>
<pre><code>key   = "item_{id}_name"
hash  = XXHash64(key, seed = 0)
value = lookup(hash)</code></pre>
<p>This matters. Hand-translating the Chinese config names produces wrong results — what reads literally as
"Star Wish" is <b>Stellatie</b> in game, and the currency that looks like "Goddess Card" is an
<b>Auroral Badge</b>.</p>

<h2>What this site will not do</h2>
<p>No account data, no server interaction, no modification of the game, and no tooling for cheating.
This is a read-only reference built from files a normal install already has.</p>

<div class="note warn">
<p><b>Corrections welcome.</b> If a number here disagrees with what you see in game, the number here is
probably from a different build — or simply wrong. Both are worth reporting.</p>
</div>
</div>
"""
    return layout("Method", "How the Sword x Staff data on this site was extracted: sources, builds, decompilation and exact name lookups.", body, "method", 0)


def page_combat_index():
    body = """
<div class="wrap">
<p class="eyebrow">Combat mechanics</p>
<h1>How a hit is actually calculated</h1>
<p class="lede">All of this is read from <code>BattleFormulaHandler.cs</code>, the single 4,349-line file
inside <code>Console.dll</code> that resolves every point of damage, healing and status in the game.</p>

<div class="cards">
  <a class="card" href="damage.html"><span class="rail"></span>
    <h3>The damage formula</h3>
    <p>The full pipeline in execution order, from skill coefficient to final number, with a worked example.</p>
    <span class="tag">Start here</span></a>
  <a class="card" href="elemental.html"><span class="rail"></span>
    <h3>Elemental Mastery &amp; Affinity</h3>
    <p>The two stacked elemental layers, and the hidden per-rank value they are scored against.</p>
    <span class="tag">Includes full tables</span></a>
  <a class="card" href="speed.html"><span class="rail"></span>
    <h3>SPD and turn order</h3>
    <p>The battle runs on a timeline, not fixed turns. Turn frequency scales with the square root of SPD.</p>
    <span class="tag">Mechanic</span></a>
  <a class="card" href="crit.html"><span class="rail"></span>
    <h3>Crit, Block and flat "value" stats</h3>
    <p>Why a "+1K Crit" roll is worth 15% at one rank and 1% a few ranks later.</p>
    <span class="tag">Mechanic</span></a>
  <a class="card" href="scaling.html"><span class="rail"></span>
    <h3>Level and rank scaling</h3>
    <p>Three separate systems punish punching up. What each is worth, from the real tables.</p>
    <span class="tag">Mechanic</span></a>
</div>

<h2>The short version</h2>
<ul>
  <li><b>Damage is a chain of multipliers</b>, not a sum. The order matters, and a few steps are capped.</li>
  <li><b>Armour uses <code>ATK / (ATK + DEF)</code></b> — so defence has diminishing returns, and ATK enters the
      formula twice.</li>
  <li><b>Several stats are never used raw.</b> Elemental Mastery, Crit value, Effect value and Block value are all
      divided by a hidden per-rank number before use, which is why they quietly lose value as you rank up.</li>
  <li><b>SPD buys turns on a square root.</b> Twice the turns costs four times the stat.</li>
  <li><b>The battle is server-authoritative.</b> The client mirrors the simulation; it does not run it.</li>
</ul>
</div>
"""
    return layout("Combat mechanics", "How Sword x Staff resolves damage: the full formula, elemental layers, speed, crit and level scaling.", body, "combat", 1)


def page_damage():
    body = """
<div class="wrap">
<p class="eyebrow">Combat mechanics</p>
<h1>The damage formula</h1>
<p class="lede">Every step the game runs for one hit, in the order it runs them. Source:
<code>BattleFormulaHandler.Damage()</code>.</p>

<h2>Before anything is calculated</h2>
<p>Three checks return zero immediately, in this order: <b>Blind</b>, <b>Dodge</b>, <b>Immunity</b>.
A blinded attacker misses before the target's dodge is even rolled.</p>

<h2>The pipeline</h2>
<p>Everything below is applied in sequence to a single running number.</p>
<ol>
  <li><b>Base damage</b> = the skill's base stat &times; its coefficient. For an attack skill that is
      your ATK &times; the skill ratio.</li>
  <li><b>Flat skill damage</b> is added.</li>
  <li><b>Armour mitigation</b>: &times; <code>ATK / (ATK + DEF)</code>.</li>
  <li><b>Skill damage reduction</b> from the target, applied as a divisor.</li>
  <li><b>Elemental layer</b> — see <a href="elemental.html">Elemental Mastery</a>.</li>
  <li><b>Damage bonus vs resistance</b>: &times; <code>(1 + DMG Boost + PvE/PvP bonus) / (1 + their DMG RES + their reduction scales)</code>.</li>
  <li><b>Crit</b>, if it landed, and <b>Block</b>, if it landed. They are mutually exclusive.</li>
  <li><b>Level offset</b> and <b>rank offset</b> — see <a href="scaling.html">Level and rank scaling</a>.</li>
  <li><b>Situational</b>: food buffs, distance bonuses, execute scaling, bonus versus large monsters.</li>
</ol>

<div class="note">
<p><b>ATK is in the formula twice.</b> Once as the base value in step 1, and again in the mitigation term
in step 3. That is why its value per point behaves differently from every other offensive stat — its
effectiveness ranges from linear to quadratic depending on the target's DEF.</p>
</div>

<h2>Worked example</h2>
<p>A single cast of <i>Water Bullet</i> (skill entity 10500, coefficient 0.8899, flat 8,899) from a
level-83 player against a same-level standard monster. All inputs are real table values.</p>

<div class="tablewrap"><table>
<thead><tr><th>Side</th><th>Stat</th><th class="num">Value</th></tr></thead>
<tbody>
<tr><td>Attacker</td><td>ATK</td><td class="num">97,000</td></tr>
<tr><td>Attacker</td><td>Elemental Mastery</td><td class="num">11,300</td></tr>
<tr><td>Attacker</td><td>Water Affinity</td><td class="num">4,820</td></tr>
<tr><td>Attacker</td><td>DMG Boost / PvE Bonus</td><td class="num">16.3% / 19%</td></tr>
<tr><td>Monster</td><td>DEF</td><td class="num">31,543</td></tr>
<tr><td>Monster</td><td>HP</td><td class="num">101,532</td></tr>
<tr><td>Monster</td><td>Water RES / Elemental RES</td><td class="num">957 / 0</td></tr>
</tbody></table><caption>Monster row: <code>level_prop_monster</code> class 501, level 83.</caption></div>

<pre><code>1. base  = 97,000 x 0.8899                        =  86,320
2. + flat skill damage 8,899                      =  95,219
3. x armour  97,000/(97,000+31,543) = 0.75461     =  71,854   you keep 75.5%
4. / target skill damage reduction (1 + 0.10)     =  65,321
5. x elemental multiplier 2.80755                 = 183,393   &lt;- largest single step
6. x (1+0.163+0.19) / (1+0.0405+0.05)             = 227,538
7. level offset x1.0, rank offset x1.0            = 227,538
                                                    -------
   NON-CRIT HIT                                     227,538
   CRIT  x max(1.3, 1+0.63-0.0385) = x1.5915        362,127</code></pre>

<p>Against a monster with 101,532 HP that is <b>2.24&times; its health</b> — a one-shot. At an 18.3% crit
rate the average hit is about <b>252,168</b>.</p>

<h2>What the example shows</h2>
<p><b>Step 5 does the heavy lifting.</b> The elemental multiplier alone nearly triples the hit. Of its
numerator, roughly 70% comes from Affinity and Mastery — without them the hit would be about a third
of the size. This particular monster has <b>zero</b> Elemental RES, which is why the multiplier is so
generous; a boss with real resistance changes the picture substantially.</p>
<p><b>Step 3 is the biggest loss.</b> Armour removes 24.5% flat.</p>
<p><b>Steps 7 do nothing here</b> because attacker and target are the same level and rank. They only
matter when punching up or down.</p>

<div class="note warn">
<p><b>Set to zero in this example:</b> profession damage scales (they depend on both classes),
combat-rating suppression, distance bonuses and execute scaling. Each is a real multiplier in the
chain — this example simply has none of them active.</p>
</div>
</div>
"""
    return layout("The damage formula", "Every step Sword x Staff runs to resolve one hit, in order, with a worked example from real config values.", body, "combat", 1)
