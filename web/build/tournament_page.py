"""Tournament projection: the real bracket the client received (tools/liveproto/tournament.py) played on the team
engine (tools/liveproto/tournament_sim.js).

Reads, all under the gitignored out/liveproto: tournament.json (divisions, teams, members), tournament_result.json
(the simulated bracket), tournament_fighters.json (which players have captured sheets) and, if present,
tournament_meta.json {"server": "...", "captured": "YYYY-MM-DD"}. The page is skipped when the first two are absent.
"""
from __future__ import annotations
import html, json, os


def render(layout, out):
    lp = os.path.join(out, "liveproto")
    tp, rp, fp, mp = (os.path.join(lp, n) for n in ("tournament.json", "tournament_result.json", "tournament_fighters.json", "tournament_meta.json"))
    if not (os.path.exists(tp) and os.path.exists(rp)):
        return None
    T = json.load(open(tp, encoding="utf-8")); R = json.load(open(rp, encoding="utf-8"))
    have = {str(f["id"]) for f in json.load(open(fp, encoding="utf-8"))} if os.path.exists(fp) else set()
    meta = json.load(open(mp, encoding="utf-8")) if os.path.exists(mp) else {}
    esc = html.escape
    teams = T["teams"]; players = T["players"]
    names = {t["id"]: (t.get("name") or t["id"]) for t in teams.values()}
    complete = {t["id"]: t["complete"] for d in R["divisions"].values() for t in d["teams"]}

    def pname(pid):
        return players.get(str(pid), {}).get("name") or str(pid)

    def tname(tid):
        return esc(str(names.get(str(tid), tid)))

    def team_cell(tid):
        if tid in ("0", 0, None):
            return "<td class=bye>bye</td>"
        t = teams.get(str(tid), {})
        memb = ", ".join(f"<{'b' if str(p) in have else 'span'}>{esc(str(pname(p)))}</{'b' if str(p) in have else 'span'}>" for p in (t.get("players") or []))
        return (f"<td class=\"{'ok' if complete.get(str(tid)) else 'part'}\"><b class=tn>{tname(tid)}</b>"
                f"<span class=hint> #{t.get('combatRatingRank')}</span><br><span class=hint>{memb}</span></td>")

    def how_cell(m):
        if m["how"] == "bye":
            return "<td class=hint>bye</td>"
        if m["how"] == "simulated":
            o = m["odds"]; a = o["a"] * 100
            return f"<td class=num><b>{a:.0f}%</b> &middot; {100 - a:.0f}%<br><span class=hint>{o['turns']:.0f} actions</span></td>"
        return "<td class=hint>by Power rank</td>"

    def rounds_table(rounds, labels=None):
        h = ""
        for i, rnd in enumerate(rounds):
            lab = labels[i] if labels and i < len(labels) else f"Round {i + 1}"
            rows = "".join(f"<tr>{team_cell(m['a'])}{team_cell(m['b'])}{how_cell(m)}<td>{tname(m['winner'])}</td></tr>" for m in rnd)
            h += (f"<div class=\"tablewrap\"><table class=\"xp small tour\"><thead><tr><th colspan=4>{lab}</th></tr>"
                  f"<tr><th>Team</th><th>Team</th><th class=num>Odds</th><th>Advances</th></tr></thead><tbody>{rows}</tbody></table></div>")
        return h

    prelim = ""
    for d in sorted(R["divisions"].values(), key=lambda x: x["id"]):
        tl = " &middot; ".join(f"<span class=\"{'ok' if t['complete'] else 'part'}\"><b class=tn>{esc(str(t['name']))}</b> <span class=hint>#{t['rank']}</span></span>" for t in d["teams"])
        hows = [m["how"] for rnd in d["rounds"] for m in rnd if m["how"] != "bye"]
        how = "simulated" if hows and all(h == "simulated" for h in hows) else ("by Power rank" if hows else "walkover")
        prelim += f"<tr><td class=num>{d['id']}</td><td>{tl}</td><td><b>{esc(str(d['winnerName']))}</b></td><td class=hint>{how}</td></tr>"
    ko = "".join(f"<h3>Group {k['group']} <span class=hint>winner {esc(str(k['winnerName']))}</span></h3>" + rounds_table(k["rounds"]) for k in R["knockouts"])
    f = R["finals"]
    finals = rounds_table([f["semis"], [f["third"]], [f["final"]]], ["Semifinals", "Third place", "Grand final"])
    n_complete = sum(1 for v in complete.values() if v)
    missing = []
    for t in sorted(teams.values(), key=lambda x: x.get("combatRatingRank") or 9999)[:30]:
        miss = [pname(p) for p in (t.get("players") or []) if str(p) not in have]
        if miss and not complete.get(t["id"]):
            missing.append(f"<li><b>{esc(str(t.get('name')))}</b> <span class=hint>#{t.get('combatRatingRank')}</span>: {esc(', '.join(map(str, miss)))}</li>")
    server = meta.get("server") or "the captured server"
    when = meta.get("captured") or "capture day"
    body = f"""
<div class="wrap">
<p class="eyebrow">Combat mechanics</p>
<h1>Tournament projection</h1>
<p class="lede">The Tournament bracket on {esc(server)} exactly as the client received it on {esc(when)}, played on the
<a href="team.html">team simulator</a>: {R['fightsPerMatch']} fights per match, the winner advances.
{len(R['divisions'])} preliminary divisions, {len(teams)} teams. Projected champion: <b>{esc(str(f['championName']))}</b>.</p>
<div class="facts"><div class="fact"><b>{R['matches']['simulated']}</b><span>matches simulated</span></div>
<div class="fact"><b>{R['matches']['powerRank']}</b><span>decided by Power rank</span></div>
<div class="fact"><b>{R['matches']['byes']}</b><span>byes</span></div>
<div class="fact"><b>{n_complete}</b><span>teams with all four sheets</span></div></div>
<p class="calcnote">A match is simulated only when all eight players have captured sheets (a <b>bold</b> member name). Otherwise the
team with the better Power rank advances, and the row says so. The preliminaries are the game's own pairings and byes; the
later rounds pair the winners in bracket order. {esc(R['notes'][0]) if R.get('notes') else ''}
The engine's known gaps are listed on the <a href="team.html">team simulator</a> page; a bracket is a ladder of 50/50 coin
flips at the top, so read the odds, not just the winner.</p>

<h2>Finals</h2>
{finals}
<h2>Knockouts <span class="hint">projected</span></h2>
{ko}
<h2>Preliminaries <span class="hint">as drawn by the game</span></h2>
<div class="tablewrap"><table class="xp small"><thead><tr><th class=num>Division</th><th>Teams (Power rank)</th><th>Projected winner</th><th>How</th></tr></thead><tbody>{prelim}</tbody></table></div>
<h2>Teams that need more captures</h2>
<p class="calcnote">The strongest teams with members who have no captured sheet. Open these players' pages during a capture and rerun the simulation.</p>
<ul class="calcnote">{''.join(missing) or '<li>none in the top 30</li>'}</ul>
</div>
"""
    return layout("Tournament projection",
                  f"This week's Tournament bracket played on the team simulator: {R['matches']['simulated']} matches simulated, projected champion {f['championName']}.",
                  body, "combat", 1)
