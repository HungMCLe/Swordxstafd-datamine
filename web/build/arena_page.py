"""Arena and legion war — matchmaking, scoring, schedules and rewards, from the arena_* and
legion_fight_* tables."""
from __future__ import annotations
import html, re, collections


def _num(s, d=0):
    try:
        return int(str(s).strip())
    except Exception:
        return d


def render(layout):
    import build as _b
    L = _b.L

    def loc(key, fallback=""):
        v = L(key)
        return (v or fallback).strip()

    def rows_of(name):
        r = _b.csvrows(name); h = [c.strip() for c in r[0]]
        return h, [x for x in r[2:] if x and x[0].strip() and not x[0].startswith("#")]

    def item(i):
        return loc(f"item_{i}_name", f"item {i}")

    def awards(s):
        """'{2:180,7:1440}' -> 'Dawnium ×180, Arena Token ×1,440'"""
        parts = []
        for i, n in re.findall(r"(\d+)\s*:\s*(\d+)", s or ""):
            parts.append(f"{html.escape(item(i))} &times;{_num(n):,}")
        return ", ".join(parts) or "&mdash;"

    def rank_band(last, prev, final=False):
        if final or last >= 100000:
            return f"{prev + 1}+"
        return f"{last}" if last == prev + 1 else f"{prev + 1}–{last}"

    # ---------------- arena
    h, rule = rows_of("arena_match_rule"); ri = {c: i for i, c in enumerate(h)}
    rules = {r[0].strip(): r for r in rule}
    h, strat = rows_of("arena_match_strategy")
    h, ratio = rows_of("arena_score_ratio")
    h, daily = rows_of("arena_daily_award")
    h, season = rows_of("arena_season_award")
    h, destiny = rows_of("arena_destiny")
    h, guards = rows_of("arena_guard_template"); gi = {c: i for i, c in enumerate(h)}

    def rule_text(rid, count):
        r = rules.get(rid)
        if not r:
            return f"rule {rid} &times;{count}"
        ahead = r[ri["IsAhead"]].strip().upper() == "TRUE"
        if r[ri["Type"]].strip() == "Range":
            lo, hi = [_num(x) for x in re.findall(r"\d+", r[ri["Range"]])[:2]]
            return f"{count} from {lo}–{hi} places {'above' if ahead else 'below'} you"
        lo, hi = [_num(x) for x in re.findall(r"\d+", r[ri["Percent"]])[:2]]
        return f"{count} from {lo}–{hi}% {'above' if ahead else 'below'} you"

    strat_rows, prev = "", 0
    srows = sorted(strat, key=lambda r: _num(r[0]))
    for i, r in enumerate(srows):
        last = _num(r[0])
        picks = re.findall(r"(\d+)\s*:\s*(\d+)", r[1])
        strat_rows += f"<tr><td>rank {rank_band(last, prev, final=(i == len(srows) - 1))}</td><td>{'; '.join(rule_text(a, b) for a, b in picks)}</td></tr>"
        prev = last
    ratio_rows, prev = "", 0
    for r in sorted(ratio, key=lambda r: _num(r[0])):
        last = _num(r[0]); ratio_rows += f"<tr><td>{rank_band(last, prev)}</td><td class='num'>{_num(r[1])}%</td></tr>"; prev = last
    daily_rows, prev = "", 0
    for r in sorted(daily, key=lambda r: _num(r[0])):
        last = _num(r[0]); daily_rows += f"<tr><td>{rank_band(last, prev)}</td><td>{awards(r[1])}</td></tr>"; prev = last
    season_rows, prev = "", 0
    for r in sorted(season, key=lambda r: _num(r[0])):
        last = _num(r[0]); season_rows += f"<tr><td>{rank_band(last, prev)}</td><td>{awards(r[1])}</td><td>{awards(r[2])}</td></tr>"; prev = last
    seasons_d = sorted({_num(r[0]) for r in destiny})
    bands = sorted({(_num(r[1]), _num(r[2])) for r in destiny})
    dest_head = "".join(f"<th class='num'>S{s}</th>" for s in seasons_d)
    dest_rows = ""
    for lo, hi in bands:
        cells = ""
        for s in seasons_d:
            m = [r for r in destiny if _num(r[0]) == s and _num(r[1]) == lo]
            cells += f"<td class='num'>{_num(m[0][3]):,}–{_num(m[0][4]):,}</td>" if m else "<td>&mdash;</td>"
        dest_rows += f"<tr><td>{lo}–{hi if hi < 100000 else '∞'}</td>{cells}</tr>"
    # guards: which professions, which levels, how many
    prof = collections.Counter(loc(f"Profession.{g[gi['Profession']].strip()}", g[gi["Profession"]].strip()) for g in guards)
    lv = sorted({_num(g[gi["Level"]]) for g in guards})
    sub = sorted({g[gi["SubRank"]].strip() for g in guards}, key=lambda s: [_num(x[gi["Level"]]) for x in guards if x[gi["SubRank"]].strip() == s][0])
    guard_txt = (f"{len(guards)} templates across {', '.join(f'{html.escape(p)} ({n})' for p, n in prof.most_common())}, levels {lv[0]}–{lv[-1]}, "
                 f"promotions {html.escape(loc('SubRank.' + sub[0], sub[0]))} to {html.escape(loc('SubRank.' + sub[-1], sub[-1]))}")

    # ---------------- legion war
    h, period = rows_of("legion_fight_period"); pi = {c: i for i, c in enumerate(h)}
    h, base = rows_of("legion_fight_base_score")
    h, contrib = rows_of("legion_fight_contribution_score")
    h, tiers = rows_of("legion_fight_rank_score"); ti = {c: i for i, c in enumerate(h)}
    h, result = rows_of("legion_fight_result_award")
    h, hold = rows_of("legion_fight_stronghold"); hi_ = {c: i for i, c in enumerate(h)}
    h, donate = rows_of("legion_donate"); di = {c: i for i, c in enumerate(h)}

    groups = collections.defaultdict(list)
    for r in period:
        groups[r[pi["Group"]].strip()].append(r)
    sched = ""
    for g, rs in sorted(groups.items()):
        steps = []
        for r in sorted(rs, key=lambda r: _num(r[0])):
            t = r[pi["StartDate"]].strip("() ")[:5]
            mins = _num(r[pi["Duration"]])
            dur = f"{mins // 60}h" if mins % 60 == 0 else f"{mins} min"
            steps.append(f"<b>{html.escape(r[pi['PhaseStatus']])}</b> {html.escape(r[pi['StartDayOfWeek']])} {t} ({dur})")
        sched += f"<li>Group {html.escape(g)}: {' &rarr; '.join(steps)}</li>"
    base_rows = "".join(f"<tr><td>{_num(r[0])}–{_num(r[1]) if _num(r[1]) > 0 else '∞'}</td><td class='num'>{_num(r[2]):,}</td></tr>" for r in base)
    contrib_rows = "".join(f"<tr><td>{_num(r[0]):,}–{_num(r[1]) if _num(r[1]) > 0 else '∞'}</td><td><b>{html.escape(r[2])}</b></td><td class='num'>{_num(r[3])}</td></tr>" for r in contrib)
    tier_rows = ""
    for r in tiers:
        key = r[ti["SubRank"]].strip()
        nm = loc(f"SubRank.{key}", "") or key
        hi = _num(r[ti["ScoreEnd"]])
        tier_rows += (f"<tr><td><b>{html.escape(nm)}</b>{' <span class=hint>' + html.escape(key) + '</span>' if nm != key else ''}</td>"
                      f"<td class='num'>{_num(r[ti['ScoreStart']]):,}{'–' + format(hi, ',') if hi > 0 else '+'}</td>"
                      f"<td class='num'>{_num(r[ti['EloStepSize']])}</td><td class='num'>&minus;{_num(r[ti['LoseScoreOffset']])}</td>"
                      f"<td class='num'>{_num(r[ti['ResetScore']]):,}</td><td>{awards(r[ti['WinAward']])}</td><td>{awards(r[ti['LoseAward']])}</td></tr>")
    result_rows = "".join(f"<tr><td>{_num(r[0])}{'–' + str(_num(r[1])) if _num(r[1]) > _num(r[0]) else ('+' if _num(r[1]) < 0 else '')}</td><td>{awards(r[2])}</td><td>{awards(r[3])}</td></tr>" for r in result)
    hold_rows = "".join(f"<tr><td>{html.escape(r[0])}</td><td class='num'>{_num(r[hi_['Count']]) if _num(r[hi_['Count']]) > 0 else 'the rest'}</td>"
                        f"<td class='num'>{_num(r[hi_['DestroyScore']])}</td><td class='num'>{_num(r[hi_['AttackFixedContributionScore']])} + {_num(r[hi_['AttackPermillageContributionScore']])}‰ of damage</td>"
                        f"<td class='num'>{_num(r[hi_['DestroyContributionScore']])}</td></tr>" for r in hold)
    donate_rows = "".join(f"<tr><td class='num'>{_num(r[0])}</td><td>{('free' if _num(r[di['CostItemCount']]) == 0 else html.escape(item(r[di['CostItemId']])) + ' &times;' + str(_num(r[di['CostItemCount']])))}</td>"
                          f"<td>{awards(r[di['MemberReward']])}</td><td>{awards(r[di['LegionReward']])}</td></tr>" for r in donate)

    body = f"""
<div class="wrap">
<p class="eyebrow">Reference</p>
<h1>Arena and legion war</h1>
<p class="lede">The rules the two competitive modes actually run on: who the arena offers you, what a win is worth,
what each rank pays daily and per season; and the legion war's weekly clock, its rating tiers, strongholds and
payouts. Everything here is the config table, with item names from the localisation.</p>

<h2>Arena</h2>
<h3>Who you are offered</h3>
<p><code>arena_match_strategy</code> picks opponents by your current rank, drawing from the rules in
<code>arena_match_rule</code>. "Above" is a better rank than yours.</p>
<div class="tablewrap"><table><thead><tr><th>Your rank</th><th>Opponents offered</th></tr></thead><tbody>{strat_rows}</tbody></table></div>

<h3>What a win is worth</h3>
<p><code>arena_score_ratio</code>: the score you take from a win, as a share of the base, by the rank of the opponent
you beat. Beating the top pays 95%; below rank 5,000 it pays nothing.</p>
<div class="tablewrap"><table><thead><tr><th>Opponent's rank</th><th class="num">Score ratio</th></tr></thead><tbody>{ratio_rows}</tbody></table></div>

<h3>Payouts</h3>
<div class="twocol">
<div class="tablewrap"><table><thead><tr><th>Rank</th><th>Daily</th></tr></thead><tbody>{daily_rows}</tbody></table><caption><code>arena_daily_award</code></caption></div>
<div class="tablewrap"><table><thead><tr><th>Rank</th><th>Season, core</th><th>Season, extra</th></tr></thead><tbody>{season_rows}</tbody></table><caption><code>arena_season_award</code></caption></div>
</div>

<h3>Destiny score by season</h3>
<p><code>arena_destiny</code> maps your final rank band to a destiny score range each season.</p>
<div class="tablewrap"><table><thead><tr><th>Final rank</th>{dest_head}</tr></thead><tbody>{dest_rows}</tbody></table></div>

<h3>The guards</h3>
<p>When the ladder has no player to offer, the arena fields a template guard: {guard_txt}. Each carries a fixed
loadout of Techniques and Charms at its level.</p>

<h2 id="legion">Legion war</h2>
<h3>The weekly clock</h3>
<p><code>legion_fight_period</code> runs three groups a week. Sign-up lasts a day, matching an hour and a half, the
battle twelve hours, then a truce until the next sign-up.</p>
<ul class="plain">{sched}</ul>

<h3>Rating tiers</h3>
<p><code>legion_fight_rank_score</code>: the score band of each tier, the Elo step a result moves you by, the
extra loss offset, where a new season resets you, and what a win or a loss pays. The tier keys are the
config's own; the promotion names apply to the first six, the rest have no separate name in the localisation.</p>
<div class="tablewrap"><table><thead><tr><th>Tier</th><th class="num">Score</th><th class="num">Elo step</th><th class="num">Loss offset</th><th class="num">Reset to</th><th>Win</th><th>Loss</th></tr></thead>
<tbody>{tier_rows}</tbody></table></div>

<h3>Score and contribution</h3>
<div class="twocol">
<div class="tablewrap"><table><thead><tr><th>Legion rank</th><th class="num">Base score</th></tr></thead><tbody>{base_rows}</tbody></table><caption><code>legion_fight_base_score</code></caption></div>
<div class="tablewrap"><table><thead><tr><th>Contribution</th><th>Grade</th><th class="num">Activity</th></tr></thead><tbody>{contrib_rows}</tbody></table><caption><code>legion_fight_contribution_score</code></caption></div>
</div>
<div class="tablewrap"><table><thead><tr><th>Stronghold</th><th class="num">Count</th><th class="num">Score on destroy</th><th class="num">Contribution per attack</th><th class="num">Contribution on destroy</th></tr></thead>
<tbody>{hold_rows}</tbody></table><caption><code>legion_fight_stronghold</code></caption></div>

<h3>Placement rewards</h3>
<div class="tablewrap"><table><thead><tr><th>Placement</th><th>Reward</th><th>Resources</th></tr></thead><tbody>{result_rows}</tbody></table></div>

<h3>Donations</h3>
<p><code>legion_donate</code>: five donations a day, the first free, each paying the member and the legion.</p>
<div class="tablewrap"><table><thead><tr><th class="num">#</th><th>Cost</th><th>You get</th><th>Legion gets</th></tr></thead><tbody>{donate_rows}</tbody></table></div>
</div>
"""
    return layout("Arena and legion war", "The matchmaking, scoring, schedule and reward tables behind Sword x Staff's "
                  "arena and legion war.", body, "arena", 0)
