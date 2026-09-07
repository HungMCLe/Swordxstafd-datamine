"""XP requirements — the normal ladder (level_exp column 1, cumulative from level 0) up to
each promotion cap, and each season's bless ladder (level_bless, cumulative per promotion
family) that continues past the cap.

Player.Level = BaseLevel + bless level (PlayerBlessLevelUtils.UpdateShowLevel).
A level above the promotion's base cap is a "season level" (PlayerRankUtils.IsSeasonLevel).
The bless ladder opens at the top sub-rank of the season's promotion, at its base cap, and
runs to system_level_limit.PlayerBlessLevel for that promotion.
"""
from __future__ import annotations
import html, collections, re


def _num(s, d=0):
    try:
        return int(str(s).strip())
    except Exception:
        return d


def render(layout, base_tables):
    import build as _b
    L = _b.L
    ladder, *_ = base_tables()

    def loc(key, fallback=""):
        v = L(key)
        return (v or fallback).strip()

    def rows_of(name):
        r = _b.csvrows(name); h = [c.strip() for c in r[0]]
        return h, [x for x in r[2:] if x and x[0].strip() and not x[0].startswith("#")]

    # ---- the normal ladder: cumulative XP from level 0, column 1; pets are column 2
    h, lx = rows_of("level_exp"); xi = {c: i for i, c in enumerate(h)}
    cum, pet_cum = {}, {}
    for r in lx:
        lv = _num(r[0], -1)
        if lv < 0:
            continue
        if r[xi["1"]].strip():
            cum[lv] = _num(r[xi["1"]])
        if r[xi["2"]].strip():
            pet_cum[lv] = _num(r[xi["2"]])
    max_normal = max(cum)

    # ---- promotions: internal -> display name and base cap
    disp = {Ld["internal"]: Ld["rank"] for Ld in ladder}
    h, ps = rows_of("player_subrank")
    caps = [(r[0].strip(), _num(r[1])) for r in ps]          # in ladder order
    cap_of = dict(caps)

    def family(internal):
        base = internal.split("_")[0]
        return base if base.startswith(("Godtouched", "Demigod")) else base.rstrip("123")

    # ---- seasons: family -> (n, name); bless cap per family from system_level_limit
    seasons = {}
    for r in _b.csvrows("astrological_season_config")[2:]:
        if r and r[0].strip().isdigit():
            seasons[r[1].strip()] = (int(r[0]), loc(f"astrological_season_{r[0]}_name", f"Season {r[0]}"))
    h, sl = rows_of("system_level_limit"); si = {c: i for i, c in enumerate(h)}
    bless_cap = collections.defaultdict(int)
    for r in sl:
        bless_cap[family(r[0].strip())] = max(bless_cap[family(r[0].strip())], _num(r[si["PlayerBlessLevel"]]))
    h, lb = rows_of("level_bless"); bi = {c: i for i, c in enumerate(h)}
    bless = collections.defaultdict(dict)
    score = collections.defaultdict(dict)
    for r in lb:
        fam = r[0].strip(); k = _num(r[bi["BlessLevel"]])
        bless[fam][k] = _num(r[bi["Exp"]]); score[fam][k] = _num(r[bi["SeasonScore"]])

    def n(v):
        return f"{v:,}"

    # ---- one block per season; the promotions before the first season share one block
    def fam_label(internal):
        return re.sub(r" (I|II|III)$", "", disp.get(internal, internal))

    families = []
    for internal, cap in caps:
        fam = family(internal)
        if fam not in [f for f, _ in families]:
            families.append((fam, internal))
    # group: every family before the first season is one "Before the seasons" block
    blocks, pre = [], []
    for fam, first in families:
        if fam in seasons:
            if pre:
                blocks.append(("pre", pre)); pre = []
            blocks.append((fam, [fam]))
        else:
            pre.append(fam)
    if pre:
        blocks.append(("tail", pre))

    sections, summary = [], []
    prev_cap = 0
    for key, fams in blocks:
        fam_caps = [(i, c) for i, c in caps if family(i) in fams]
        top_internal, top_cap = fam_caps[-1]
        if top_cap > max_normal and not any(f in bless for f in fams):
            break
        start = prev_cap + 1
        fam = fams[-1]
        season = seasons.get(fam)
        fam_name = fam_label(top_internal)
        if key == "pre":
            title = f"Before the seasons — levels {start}–{top_cap}"
        elif season:
            sname = season[1]
            title = (f"Season {season[0]} · {html.escape(sname)} — {html.escape(fam_name)}, cap {top_cap}" if sname != f"Season {season[0]}"
                     else f"Season {season[0]} — {html.escape(fam_name)}, cap {top_cap}")
        else:
            title = f"{html.escape(fam_name)}, cap {top_cap}"
        normal_rows, fam_total = "", 0
        for internal, c in fam_caps:
            rows_html, sub_total = "", 0
            for lv in range(prev_cap + 1, c + 1):
                if lv not in cum:
                    continue
                step = cum[lv] - cum.get(lv - 1, 0)
                sub_total += step
                rows_html += f"<tr><td class='num'>{lv}</td><td class='num'>{n(step)}</td><td class='num'>{n(cum[lv])}</td></tr>"
            if rows_html:
                normal_rows += (f"<tr class='sub'><th colspan='3'>{html.escape(disp.get(internal, internal))} &middot; levels {prev_cap + 1}–{c}"
                                f" &middot; {n(sub_total)} XP for the band</th></tr>" + rows_html)
            fam_total += sub_total
            prev_cap = c
        bless_rows, bless_total, bcap = "", 0, bless_cap.get(fam, 0)
        table = bless.get(fam, {})
        shown = [k for k in sorted(table) if k <= bcap] if bcap else []
        for k in shown:
            step = table[k] - table.get(k - 1, 0)
            bless_total += step
            bless_rows += (f"<tr><td class='num'>{top_cap + k} <span class='hint'>Season Level {k}</span></td><td class='num'>{n(step)}</td>"
                           f"<td class='num'>{n(table[k])}</td><td class='num'>{n(score[fam].get(k, 0))}</td></tr>")
        extra = len(table) - len(shown) if table else 0
        block = f'<h2 id="s-{fam.lower()}">{title}</h2>'
        block += (f"<details><summary>Normal levels {start}–{top_cap} &mdash; "
                  f"<b>{n(fam_total)}</b> XP across them, <b>{n(cum.get(top_cap, 0))}</b> from level 0</summary>"
                  f"<div class='tablewrap'><table class='xp'><thead><tr><th class='num'>Level</th><th class='num'>XP for this level</th><th class='num'>XP from level 0</th></tr></thead>"
                  f"<tbody>{normal_rows}</tbody></table></div></details>")
        if shown:
            block += (f"<details open><summary>Season Levels {top_cap + 1}–{top_cap + bcap} &mdash; the season ladder of {html.escape(fam_name)}, "
                      f"<b>{n(bless_total)}</b> Season XP to max it</summary>"
                      f"<p class='hint'>Opens once you are {html.escape(disp.get(top_internal, top_internal))} at level {top_cap}. Season XP is its own pool; "
                      f"the level shown is {top_cap} plus the Season Level, and it expires with the season. Each Season Level also adds season score."
                      + (f" The table continues to Season Level {max(table)}, past this promotion's limit of {bcap}." if extra > 0 else "") + "</p>"
                      f"<div class='tablewrap'><table class='xp'><thead><tr><th class='num'>Shown level</th><th class='num'>Season XP for this level</th><th class='num'>Season XP total</th><th class='num'>Season score</th></tr></thead>"
                      f"<tbody>{bless_rows}</tbody></table></div></details>")
        elif season:
            block += f"<p class='hint'>No Season Level ladder is configured for {html.escape(fam_name)} yet.</p>"
        sections.append(block)
        summary.append((title, top_cap, cum.get(top_cap, 0), fam_total, bcap, bless_total))

    sum_rows = "".join(
        f"<tr><td>{t}</td><td class='num'>{c}</td><td class='num'>{n(ft)}</td><td class='num'>{n(cc)}</td>"
        f"<td class='num'>{('+' + str(bc)) if bc else '&mdash;'}</td><td class='num'>{n(bt) if bt else '&mdash;'}</td></tr>"
        for t, c, cc, ft, bc, bt in summary)

    # ---- pets, briefly
    pet_rows = "".join(f"<tr><td class='num'>{lv}</td><td class='num'>{n(pet_cum[lv] - pet_cum.get(lv - 1, 0))}</td><td class='num'>{n(pet_cum[lv])}</td></tr>"
                       for lv in (10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120, 130, 140, 150, 160, 180, 200, 220, 250) if lv in pet_cum)

    body = f"""
<div class="wrap">
<p class="eyebrow">Reference</p>
<h1>XP requirements</h1>
<p class="lede">Every level's cost on both ladders. Normal levels run on the player XP column up to each promotion's
cap; past the cap, <b>Season Levels</b> take over with their own XP pool, and the level you see is the cap plus your
Season Level. Promote in the next season and the numbers you already passed become ordinary levels again.</p>

<h2>How the game counts it</h2>
<p>The game's own tooltip puts it as <i>"Level {{0}} + Season Level {{1}}"</i> and <i>"Levels beyond your Rank's cap are
calculated as Season Levels."</i> When a season ends, <i>"Season Levels will expire and convert to {{CONVERT}}"</i>,
which <i>"can be used to upgrade your Astral Pact."</i> In the code that is <code>Player.Level = BaseLevel + season
level</code>, with <code>IsSeasonLevel</code> true whenever <code>level &gt; base cap</code>. The Season Level ladder
opens only when you hold the top sub-rank of the season's promotion and stand at its cap, and runs to that
promotion's limit in <code>system_level_limit</code>. Normal XP is <code>level_exp</code> column 1, stored as the
total from level 0; Season Level XP is <code>level_bless</code> (the config's internal name for the season system is
"bless"), stored as the total per promotion family. The per-level numbers below are the differences.</p>

<div class="tablewrap"><table><thead><tr><th>Season</th><th class="num">Cap</th><th class="num">XP across the promotion</th>
<th class="num">XP from level 0</th><th class="num">Season Levels</th><th class="num">Season XP to max</th></tr></thead>
<tbody>{sum_rows}</tbody></table></div>

{"".join(sections)}

<h2 id="pets">Pet levels</h2>
<p>Column 2 of the same table, the pet XP ladder, at every tenth level.</p>
<div class="tablewrap"><table class="xp"><thead><tr><th class="num">Level</th><th class="num">XP for this level</th><th class="num">XP from level 0</th></tr></thead>
<tbody>{pet_rows}</tbody></table></div>
</div>
"""
    body = body.replace("{CONVERT}", html.escape(loc("item_61_name", "the season item")))
    return layout("XP requirements", "Every Sword x Staff level's XP cost: the normal ladder to each promotion cap and each "
                  "season's Season Level ladder past it.", body, "xp", 0)
