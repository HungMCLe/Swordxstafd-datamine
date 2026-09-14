"""Material Realms and relic levels.

Material Realms are the client's "mop-up" system (mop_up_dungeon / mop_up_material): each realm holds one object at
a time (an ore node, a gnoll, an abandoned chest) with a durability; every swing spends one tool
(mop_up_dungeon.CostDict) and deals BattleFormulaHandler.GetMopUpDamage = attack x U(1-DamageFloat, 1+DamageFloat)
x (1 + crit power on a crit), rounded. Each point of durability pays the object's AttackRewardIds and the break pays
BreakRewardIds; both are reward_rule rows whose count is CountList x level_number[SubRankCountId][(int)SubRank],
truncated (RewardRuleInfoParser.GetRewardDropInfosByRuleList), so a promotion is one step up level_number column 6.
A realm's "level" is the number of its unlock stages the player has cleared
(MopUpDungeonInfoParser.GetUnlockDungeonHighestLevel); the client uses it for unlocking only.

Relics are the game's Treasures. Normal levels cost treasure_levelup_material up to the promotion's cap
(system_level_limit.TreasureLevel, Formula.GetMaxTreasureBaseLevel); above the cap a level is a season level and
costs treasure_bless[player's Rank family][level - cap] (TreasureHelper.GetTreasureLevelUpCostMaterials). Season
levels open only at the top sub-rank of the season's promotion (FormulaHandler.GetMaxTreasureBlessLevel) and each is
gated by a character level (system_level_limit rows) and by the other relic slots (system_level_gap_limit).
"""
from __future__ import annotations
import html, re, collections, math


def _num(s, d=0):
    try:
        return int(str(s).strip())
    except Exception:
        try:
            return float(str(s).strip())
        except Exception:
            return d


def _items(s):
    """{41402:900,1:40500,} -> [(41402, 900), (1, 40500)]"""
    return [(int(a), int(b)) for a, b in re.findall(r"(\d+)\s*:\s*(\d+)", s or "")]


def _list(s):
    return [int(x) for x in re.findall(r"-?\d+", s or "")]


def render(layout, base_tables):
    import build as _b
    L = _b.L
    ladder, *_ = base_tables()
    esc = html.escape

    def loc(key, fallback=""):
        v = L(key)
        return (v or fallback).strip()

    def rows_of(name):
        r = _b.csvrows(name); h = [c.strip() for c in r[0]]
        return h, [x for x in r[2:] if x and x[0].strip() and not x[0].startswith("#")]

    def item_name(i):
        return loc(f"item_{i}_name", f"item {i}")

    def n(v):
        return f"{int(v):,}"

    def lst(pairs):
        return ", ".join(f"{n(c)} {esc(item_name(i))}" for i, c in pairs)

    # ---- promotions in ladder order: internal -> display (the game's own SubRank strings), enum ordinal
    h, ps = rows_of("player_subrank"); pi = {c: i for i, c in enumerate(h)}
    order = [r[0].strip() for r in ps]
    ordinal = {name: i + 1 for i, name in enumerate(order)}          # SubRank enum: None 0, Norank 1, Blackiron1 2 ...
    disp = {}
    for name in order:
        site = next((Ld["rank"] for Ld in ladder if Ld["internal"] == name), None)
        disp[name] = loc(f"SubRank.{name}") or site or name

    def family(internal):
        base = internal.split("_")[0]
        return base if base.startswith(("Godtouched", "Demigod", "Truegod", "Lordgod")) else base.rstrip("123")

    # ---- level_number: (column id, key) -> number
    h, ln = rows_of("level_number")
    numbers = {}
    for r in ln:
        try:
            key = int(r[0])
        except Exception:
            continue
        for ci, c in enumerate(h[1:], 1):
            v = r[ci].strip() if ci < len(r) else ""
            if v:
                try:
                    numbers[(int(c), key)] = float(v)
                except Exception:
                    pass

    def factor(sub, col=6):
        return numbers.get((col, ordinal.get(sub, 0)))

    tiers = [s for s in order if factor(s) is not None]

    # ---- reward rules
    h, rr = rows_of("reward_rule"); ri = {c: i for i, c in enumerate(h)}
    rules = collections.defaultdict(list)
    for r in rr:
        rid = _num(r[ri["Id"]], -1)
        ids, weights = _list(r[ri["IdList"]]), _list(r[ri["WeightList"]])
        counts = [float(x) for x in re.findall(r"[\d.]+", r[ri["CountList"]])]
        lvl_ids, sub_ids = _list(r[ri["LevelCountId"]]), _list(r[ri["SubRankCountId"]])
        for j, iid in enumerate(ids):
            rules[rid].append({"item": iid, "count": counts[j] if j < len(counts) else 0,
                               "weight": weights[j] if j < len(weights) else 0, "total": sum(weights),
                               "levelId": lvl_ids[j] if j < len(lvl_ids) else 0,
                               "subId": sub_ids[j] if j < len(sub_ids) else 0})

    def payout(rule_ids, sub):
        """[(item, count, scaled?)] the way RewardRuleInfoParser scales and truncates it for this promotion"""
        out = []
        for rid in rule_ids:
            for rule in rules.get(rid, []):
                f = 1.0
                if rule["levelId"]:
                    f *= numbers.get((rule["levelId"], 0), 1.0)
                if rule["subId"]:
                    f *= numbers.get((rule["subId"], ordinal.get(sub, 0)), 1.0)
                out.append((rule["item"], int(rule["count"] * f), bool(rule["subId"] == 6)))
        return out

    def merged(pairs):
        c = collections.OrderedDict()
        for i, v, *_ in pairs:
            c[i] = c.get(i, 0) + v
        return list(c.items())

    # ---- the realms
    h, md = rows_of("mop_up_dungeon"); mi = {c: i for i, c in enumerate(h)}
    h, mm = rows_of("mop_up_material"); oi = {c: i for i, c in enumerate(h)}
    objects = {}
    for r in mm:
        objects[_num(r[0])] = {"attack": _list(r[oi["AttackRewardIds"]]), "brk": _list(r[oi["BreakRewardIds"]]),
                               "dur": _num(r[oi["Durability"]]), "count": r[oi["CanCount"]].strip().upper() == "TRUE",
                               "cost": r[oi["NeedCost"]].strip().upper() == "TRUE"}
    realms = []
    for r in md:
        t = r[mi["Type"]].strip()
        gen = _num(r[mi["GenerateMaterialRuleId"]])
        pool = [(x["item"], x["weight"], x["total"]) for x in rules.get(gen, [])]
        realms.append({"type": t, "name": loc(f"NormalMaterial.{t}", t), "stages": _list(r[mi["UnlockStages"]]),
                       "cost": _items(r[mi["CostDict"]]), "pool": pool, "newbie": _list(r[mi["NewbieRewardMaterials"]]),
                       "top": loc(f"MopUpPanel.TopType_{t}"),
                       "props": {k: r[mi[k + "Prop"]].strip() for k in ("Attack", "CritRate", "CritPower")}})

    # game settings for the swing
    gs = open(_b.CFG / "game_settings", encoding="utf-8-sig", errors="replace").read()
    m = re.search(r'"MopUp"\s*:\s*\{(.*?)\}', gs, re.S)
    mop = {}
    for k, v in re.findall(r'"(\w+)"\s*:\s*([\d.]+)', m.group(1) if m else ""):
        mop[k] = float(v)
    dmg_float = mop.get("DamageFloat", 0.1)
    daily_free = int(mop.get("DailyFreeCount", 0) * mop.get("TimesForOneFreeCount", 1))
    once_max = int(mop.get("MopUpOnceMaxCount", 0))

    h, lp = rows_of("level_prop"); li = {c: i for i, c in enumerate(h)}
    swing = {}
    for rm in realms:
        t = rm["type"]
        vals = {k: sorted({_num(r[li[c]]) for r in lp if c in li and li[c] < len(r)}) for k, c in rm["props"].items()}
        swing[t] = {"atk": vals["Attack"], "crit": [v / 10000 for v in vals["CritRate"]], "power": [v / 10000 for v in vals["CritPower"]]}

    def expected_damage(t):
        """E[round(atk * U(1-d, 1+d) * (1 + power on a crit))] for the realm's stats, computed exactly on the uniform"""
        s = swing[t]
        if len(s["atk"]) != 1:
            return None
        atk, crit, power = s["atk"][0], s["crit"][0], s["power"][0]

        def mean_round(scale):
            lo, hi = atk * scale * (1 - dmg_float), atk * scale * (1 + dmg_float)
            tot = 0.0
            for k in range(int(math.floor(lo)), int(math.ceil(hi)) + 1):
                a, b = max(lo, k - 0.5), min(hi, k + 0.5)
                if b > a:
                    tot += k * (b - a) / (hi - lo)
            return tot
        return (1 - crit) * mean_round(1) + crit * mean_round(1 + power)

    # ---- objects table at factor 1 (No Rank) and the promotion table
    base_sub = tiers[0]
    obj_rows = []
    common = {}
    for rm in realms:
        best = None
        for iid, w, tot in rm["pool"]:
            o = objects.get(iid)
            if not o:
                continue
            per = merged(payout(o["attack"], base_sub)); brk = merged(payout(o["brk"], base_sub))
            total = merged([(i, c * o["dur"]) for i, c in per] + brk)
            ed = expected_damage(rm["type"])
            swings = math.ceil(o["dur"] / ed) if (ed and o["dur"] > 0) else 0
            obj_rows.append((rm, iid, w / tot if tot else 0, o, per, brk, total, swings))
            if o["cost"] and (best is None or w > best[1]):
                best = (iid, w)
        common[rm["type"]] = best[0] if best else None

    obj_html = ""
    for rm, iid, chance, o, per, brk, total, swings in obj_rows:
        tool = ", ".join(f"{n(c)} {esc(item_name(i))}" for i, c in rm["cost"]) if o["cost"] else "free"
        obj_html += (f"<tr><th>{esc(rm['name'])}</th><td>{esc(item_name(iid))}</td><td class=num>{chance * 100:.0f}%</td>"
                     f"<td class=num>{n(o['dur']) if o['dur'] > 0 else '&mdash;'}</td><td class=num>{swings if swings else '&mdash;'}</td><td>{tool}</td>"
                     f"<td>{lst(per) or '&mdash;'}</td><td>{lst(brk) or '&mdash;'}</td><td>{lst(total)}</td>"
                     f"<td>{'yes' if o['count'] else 'no'}</td></tr>")

    def rise(a, b):
        return f" <span class=hint>+{(b / a - 1) * 100:.0f}%</span>" if a and b > a else (" <span class=hint>same</span>" if a == b else "")

    prom_head = "<tr><th>Promotion</th><th class=num>Factor</th>" + "".join(
        f"<th class=num>{esc(rm['name'])}<br><span class=hint>{esc(item_name(common[rm['type']]))}, per node</span></th>" for rm in realms) + "</tr>"
    prom_body, prev = "", {}
    for sub in tiers:
        f = factor(sub)
        cells = f"<td class=num>{f:g}&times;{rise(prev.get('f'), f)}</td>"
        prev["f"] = f
        for rm in realms:
            o = objects[common[rm["type"]]]
            per = merged(payout(o["attack"], sub)); brk = merged(payout(o["brk"], sub))
            total = merged([(i, c * o["dur"]) for i, c in per] + brk)
            main = total[0]
            cells += (f"<td class=num>{n(main[1])}{rise(prev.get(rm['type']), main[1])}"
                      f"<br><span class=hint>{n(dict(per).get(main[0], 0))} per point, {n(dict(brk).get(main[0], 0))} on break</span></td>")
            prev[rm["type"]] = main[1]
        prom_body += f"<tr><th>{esc(disp[sub])}</th>{cells}</tr>"

    # ---- unlock stages
    h, st = rows_of("stage"); si = {c: i for i, c in enumerate(h)}
    stage = {_num(r[0]): r for r in st}
    where = {}
    for r in _b.csvrows("stage_map_location")[2:]:
        if r and r[0].strip().isdigit():
            mm_ = re.search(r"'(\d+)':\[(\d+)\]", r[1] if len(r) > 1 else "")
            if mm_:
                where[int(r[0])] = (int(mm_.group(1)), int(mm_.group(2)))
    maxlv = max(len(rm["stages"]) for rm in realms)
    unlock_head = "<tr><th class=num>Realm level</th>" + "".join(f"<th>{esc(rm['name'])}</th>" for rm in realms) + "</tr>"
    unlock_body = ""
    missing_rules = set()
    for k in range(maxlv):
        cells = ""
        for rm in realms:
            if k >= len(rm["stages"]):
                cells += "<td>&mdash;</td>"; continue
            sid = rm["stages"][k]; r = stage.get(sid)
            if not r:
                cells += f"<td>stage {sid}</td>"; continue
            sub = r[si["SubRank"]].strip(); lvl = r[si["Level"]].strip()
            awards = _list(r[si["Awards"]])
            missing_rules |= {a for a in awards if a not in rules}
            reward = lst(merged(payout(awards, sub)))
            loc_ = where.get(sid)
            place = f"<br><span class=hint>{esc(loc(f'region_{loc_[0]}_{loc_[1]}'))}, {esc(loc(f'Mainland_{loc_[0]}'))}</span>" if loc_ else ""
            cells += f"<td>{esc(disp.get(sub, sub))} &middot; Lv. {esc(lvl)}{place}<br><span class=hint>first clear: {reward}</span></td>"
        unlock_body += f"<tr><th class=num>{k + 1}</th>{cells}</tr>"

    tips = [loc(f"rule_tip_NormalMaterialUpInfo_{i}") for i in (1, 2, 3)]
    quick_map = loc("Mainland_14")
    newbie = "; ".join(f"{esc(rm['name'])}: " + ", ".join(esc(item_name(i)) for i in rm["newbie"]) for rm in realms if rm["newbie"])
    swing_txt = []
    for rm in realms:
        s = swing[rm["type"]]; ed = expected_damage(rm["type"])
        swing_txt.append(f"{esc(rm['name'])} {s['atk'][0]:g} damage, {s['crit'][0] * 100:g}% crit for &times;{1 + s['power'][0]:g}"
                         + (f" (about {ed:.1f} per swing)" if ed else ""))
    same_swing = len({(tuple(s["atk"]), tuple(s["crit"]), tuple(s["power"])) for s in swing.values()}) == 1
    s0 = swing[realms[0]["type"]]; ed0 = expected_damage(realms[0]["type"])
    if same_swing:
        swing_txt = [f"{s0['atk'][0]:g} damage, {s0['crit'][0] * 100:g}% crit for &times;{1 + s0['power'][0]:g}, about {ed0:.1f} durability per swing on average, identical in all four realms"]

    # ---- relics: caps and unlock levels from system_level_limit
    h, sl = rows_of("system_level_limit"); sli = {c: i for i, c in enumerate(h)}
    base_cap, bless_rows = {}, collections.defaultdict(list)
    for r in sl:
        s = r[0].strip()
        if not r[sli["TreasureLevel"]].strip():
            continue
        base_cap.setdefault(s, _num(r[sli["TreasureLevel"]]))
        bless_rows[s].append((_num(r[sli["PlayerLevel"]]), _num(r[sli["PlayerBlessLevel"]]), _num(r[sli["TreasureBlessLevel"]])))

    def bless_cap(s):
        return max((tb for _pl, _pb, tb in bless_rows.get(s, [])), default=0)

    def unlock_at(s, k):
        for pl, pb, tb in bless_rows.get(s, []):
            if tb >= k:
                return pl + pb
        return None

    def needs(level):
        for s in order:
            if base_cap.get(s, 0) >= level:
                return disp[s]
        return None

    h, lm = rows_of("treasure_levelup_material")
    normal, cum = [], collections.Counter()
    for r in lm:
        lv = _num(r[0]); its = _items(r[1])
        for iid, c in its:
            cum[iid] += c
        normal.append((lv, its, dict(cum)))
    normal_rows = ""
    for lv, its, cm in normal:
        nd = needs(lv)
        normal_rows += (f"<tr><td class=num>{lv - 1} &rarr; {lv}</td><td>{lst([x for x in its if x[0] != 1])}</td><td class=num>{n(dict(its).get(1, 0))}</td>"
                        f"<td>{esc(nd) if nd else '<span class=hint>no promotion in this build reaches it</span>'}</td>"
                        f"<td>{lst([x for x in sorted(cm.items()) if x[0] != 1])}</td><td class=num>{n(cm.get(1, 0))}</td></tr>")

    # seasons and their families
    seasons = []
    for r in _b.csvrows("astrological_season_config")[2:]:
        if r and r[0].strip().isdigit():
            seasons.append((int(r[0]), r[1].strip(), loc(f"astrological_season_{r[0]}_name", f"Season {r[0]}")))
    h, tb = rows_of("treasure_bless"); ti = {c: i for i, c in enumerate(h)}
    by_fam = collections.OrderedDict()
    for r in tb:
        by_fam.setdefault(r[ti["Rank"]].strip(), []).append((_num(r[ti["BlessLevel"]]), _items(r[ti["LevelCostItems"]])))
    gap = collections.defaultdict(list)
    for r in rows_of("system_level_gap_limit")[1]:
        if r[0].strip() == "Treasure" and r[4].strip().upper() == "TRUE":
            gap[_num(r[1])].append((_num(r[2]), _num(r[3])))
    fam_subs = collections.defaultdict(list)
    for s in order:
        fam_subs[family(s)].append(s)

    unlock_str = loc("treasure_limit_player_level").replace("{0}", "N")
    season_blocks = ""
    example = []
    for sn, fam, sname in seasons:
        subs = fam_subs.get(fam, [])
        top = subs[-1] if subs else None
        cap = base_cap.get(top, 0) if top else 0
        bcap = bless_cap(top) if top else 0
        rows = by_fam.get(fam, [])
        title = (f"Season {sn}" if sname == f"Season {sn}" else f"Season {sn} &middot; {esc(sname)}") + f" <span class=hint>({esc(disp[subs[0]]) if subs else esc(fam)}{' to ' + esc(disp[top]) if len(subs) > 1 else ''})</span>"
        if not rows or not top or cap == 0:
            season_blocks += (f"<h3>{title}</h3><p class=calcnote>No season relic ladder in this client build: "
                              + ("no <code>treasure_bless</code> rows for this promotion" if not rows else "no relic caps for this promotion in <code>system_level_limit</code>")
                              + f"; <code>player_subrank.TreasurePropBless</code> points these tiers at the Season 5 stat table.</p>")
            continue
        g = gap.get(sn, [])
        cumc = collections.Counter(); trs = ""
        for lv, its in rows:
            for iid, c in its:
                cumc[iid] += c
            ua = unlock_at(top, lv)
            over = lv > bcap
            trs += (f"<tr{' class=dim' if over else ''}><td class=num>{cap + lv - 1} &rarr; {cap + lv}</td><td class=num>{lv}</td>"
                    f"<td>{lst([x for x in its if x[0] != 1])}</td><td class=num>{n(dict(its).get(1, 0))}</td>"
                    f"<td class=num>{('Lv. ' + str(ua)) if ua else ('above the cap of ' + str(bcap) if over else '&mdash;')}</td>"
                    f"<td>{lst([x for x in sorted(cumc.items()) if x[0] != 1])}</td><td class=num>{n(cumc.get(1, 0))}</td></tr>")
        gap_txt = (f" From relic level {g[0][0] + 1} on, every one of the five relic slots must already stand at level {g[0][0]} or "
                   f"higher, and each further level needs all five at the level below it (<code>system_level_gap_limit</code>, season {sn}).") if g else ""
        season_blocks += (f"<h3>{title}</h3><p>Normal levels run to <b>{cap}</b> at {esc(disp[top])}; the season ladder holds "
                          f"{len(rows)} levels and this build caps it at <b>{bcap}</b> (relic level {cap + bcap}), each opening at the character "
                          f"level shown, as <i>\"{esc(unlock_str)}\"</i>.{gap_txt}</p>"
                          f"<div class=\"tablewrap\"><table class=\"xp\"><thead><tr><th class=num>Relic level</th><th class=num>Season level</th>"
                          f"<th>Materials</th><th class=num>Rolla</th><th class=num>Character level</th><th>Cumulative on this ladder</th><th class=num>Rolla total</th></tr></thead>"
                          f"<tbody>{trs}</tbody></table></div>")
        # the 10 -> 11 example: (season, answer)
        if cap < 11 and rows:
            k = 11 - cap
            its = dict(rows).get(k)
            if its:
                example.append((sn, f"season level {k}, sold at {esc(disp[top])} only: {lst([x for x in its if x[0] != 1])} and {n(dict(its).get(1, 0))} Rolla"))
        elif cap >= 11:
            its = next((its for lv, its, _c in normal if lv == 11), None)
            if its:
                example.append((sn, f"normal level 11, open from {esc(needs(11))}: {lst([x for x in its if x[0] != 1])} and {n(dict(its).get(1, 0))} Rolla"))
    grouped = []
    for sn, ans in example:
        if grouped and grouped[-1][1] == ans:
            grouped[-1][0].append(sn)
        else:
            grouped.append(([sn], ans))
    example_txt = "; ".join(("in Season " + str(sns[0]) if len(sns) == 1 else f"from Season {sns[0]} to {sns[-1]}") + " it is " + ans for sns, ans in grouped)

    # ---- stars
    h, um = rows_of("treasure_upgrade_material"); ui = {c: i for i, c in enumerate(h)}
    star_rows = collections.OrderedDict()
    for r in um:
        star_rows.setdefault(r[ui["Quality"]].strip(), []).append((_num(r[ui["Star"]]), _num(r[ui["PieceCount"]]), _num(r[ui["SpecialPieceCount"]]), _items(r[ui["Materials"]])))
    star_head = "<tr><th>Star</th>" + "".join(f"<th class=num>{esc(loc(f'Quality.{q}', q))}</th>" for q in star_rows) + "</tr>"
    stars = sorted({s for rows in star_rows.values() for s, *_ in rows})
    star_body = ""
    for s in stars:
        cells = ""
        for q, rows in star_rows.items():
            row = next((x for x in rows if x[0] == s), None)
            if not row:
                cells += "<td class=num>&mdash;</td>"; continue
            _s, pc, spc, mats = row
            cells += (f"<td class=num>{n(pc)} shards" + (f" <span class=hint>({n(spc)} for a special relic)</span>" if spc != pc else "")
                      + (f"<br><span class=hint>+ {lst(mats)}</span>" if mats else "") + "</td>")
        star_body += f"<tr><th>{'&#9733;' * s if s else '0 stars'}</th>{cells}</tr>"

    unlock_sentence = loc("TravelNotesPanel.NormalMaterialUnlockStage").replace("{1}", "the fight").replace("{0}", "its region")
    missing_txt = ""
    if missing_rules:
        missing_txt = ('<p class="calcnote">Reward rule ' + ", ".join(str(x) for x in sorted(missing_rules)) +
                       " is named by the stage table but does not exist in the client&rsquo;s reward table, so it is left out.</p>")

    body = f"""
<p class="eyebrow">Progression</p>
<h1>Material Realms and relics</h1>
<p class="lede">What a swing in each Material Realm pays at every promotion, which fight unlocks each realm level, and
what every relic level costs &mdash; the normal ladder and each season's ladder, which differ at the same level.</p>

<h2>Material Realms</h2>
<p>The game's own rule card: <i>"{esc(tips[0])}"</i> <i>"{esc(tips[1])}"</i> <i>"{esc(tips[2].replace('{DailyResetTime} {TimeZone}', 'the reset time'))}"</i>
Each realm keeps one object in front of you at a time. A swing spends one tool and takes a bite of the object's
durability; every point of durability you remove pays the object's per-point reward, and breaking it pays the break
reward on top. The next object is drawn from the realm's pool. Quick mode swings until the object breaks
({once_max} swings at most per request) and unlocks once {esc(quick_map)} is open; the realm itself unlocks when you clear
its first unlock fight, and the entry shows from {esc(disp.get('Blackiron1', 'Apprentice I'))}.
{'There are no free daily swings in this build.' if daily_free == 0 else f'{daily_free} swings a day are free.'}</p>

<h3>The swing</h3>
<p>Damage per swing is the realm's attack times a roll between {1 - dmg_float:g} and {1 + dmg_float:g}, times
{1 + s0['power'][0]:g} on a crit, rounded to the nearest point (<code>GetMopUpDamage</code>). The stats come from
<code>level_prop</code> and are the same at every character level: {'; '.join(swing_txt)}.
So a 90-durability node takes about {math.ceil(90 / ed0) if ed0 else '?'} swings, and the number that grows with
your promotion is not the damage but what each point of durability pays.</p>

<h3>What each object pays</h3>
<p>At the No Rank factor of 1. Every count except Refined Ore and Dawnium is multiplied by the promotion factor
below and rounded down at each step (their reward rows use the constant column, so they stay flat).
The first objects a fresh realm shows are fixed: {newbie}. Abandoned chests cost no tool, break at once and do not
count for the weekly ranking.</p>
<div class="tablewrap"><table class="xp"><thead><tr><th>Realm</th><th>Object</th><th class=num>Chance</th><th class=num>Durability</th>
<th class=num>Swings</th><th>Tool per swing</th><th>Per point of durability</th><th>On break</th><th>Per object</th><th>Counted</th></tr></thead>
<tbody>{obj_html}</tbody></table></div>

<h3>Yield by promotion</h3>
<p>The count of every scaled reward is the base count times <code>level_number</code> column 6 at your promotion's
position in the <code>SubRank</code> list, rounded down (<code>RewardRuleInfoParser</code>). The client sends the
swing and the server rolls the reward; the sub-rank it reads is your own, which is how the yield rises the day you
promote. The cells give the common node of each realm, broken in full; the percentage is the rise over the tier
before. Other objects scale the same way: multiply their base counts above by the factor.</p>
<div class="tablewrap"><table class="xp"><thead>{prom_head}</thead><tbody>{prom_body}</tbody></table></div>
<p class="calcnote">The factor column ends at {esc(disp[tiers[-1]])}; later promotions have no entry in this build.
The realm "level" you see in the entry is only how many of its unlock fights you have cleared; nothing in the client
scales a reward by it.</p>

<h3>Unlocking each realm level</h3>
<p>Each level opens when you clear the corresponding fight on the world map (<i>"{esc(unlock_sentence)}"</i>).
The fights are ordinary stages with a first-clear reward (<code>stage.Awards</code>), scaled by
the stage's own tier rather than yours (<code>AwardUsePlayerLevelAndSubRank</code> is off).</p>
<div class="tablewrap"><table class="xp"><thead>{unlock_head}</thead><tbody>{unlock_body}</tbody></table></div>
{missing_txt}

<h2>Relic levels</h2>
<p>Relics have one ladder of normal levels, capped by your promotion (<code>system_level_limit</code>: the cap
rises by one per tier), and above the cap the level you see is a <b>season level</b>, as the game puts it:
<i>"{esc(loc('ui_blessing_player_level_tip_1'))}"</i> A season level is only for sale at the top tier of the season's
promotion, its cost comes from the season's ladder (<code>treasure_bless</code>, keyed by your promotion family), and
when the season ends <i>"Season Levels will expire and convert"</i> to the Astral Pact currency. So the same number
costs different things in different seasons. <b>Level 10 &rarr; 11</b>, for instance: {example_txt}.</p>

<h3>Normal levels</h3>
<p>The same in every season. The promotion column is the first tier whose cap admits the level.</p>
<div class="tablewrap"><table class="xp"><thead><tr><th class=num>Level</th><th>Materials</th><th class=num>Rolla</th><th>Needs</th>
<th>Cumulative from level 1</th><th class=num>Rolla total</th></tr></thead><tbody>{normal_rows}</tbody></table></div>

<h3>Season levels</h3>
{season_blocks}

<h3>Stars</h3>
<p>Stars are bought with the relic's own shards (<code>treasure_upgrade_material</code>, by quality); the last star
also takes universal shards of the same grade.</p>
<div class="tablewrap"><table class="xp"><thead>{star_head}</thead><tbody>{star_body}</tbody></table></div>

<div class="note">
<p><b>Where this comes from.</b> Realms: <code>mop_up_dungeon</code> (tools, unlock fights, object pools),
<code>mop_up_material</code> (durability, per-point and break reward rules), <code>reward_rule</code> scaled by
<code>level_number</code> as <code>RewardRuleInfoParser.GetRewardDropInfosByRuleList</code> does it,
<code>level_prop</code> for the swing stats, <code>BattleFormulaHandler.GetMopUpDamage</code> for the roll,
<code>game_settings.MopUp</code>, <code>rule_tip</code> for the card text, <code>stage</code> and
<code>stage_map_location</code> for the unlock fights. Relics: <code>treasure_levelup_material</code>,
<code>treasure_bless</code>, <code>treasure_upgrade_material</code>, <code>system_level_limit</code> and
<code>system_level_gap_limit</code>, read the way <code>TreasureHelper.GetTreasureLevelUpCostMaterials</code> and
<code>CheckLevelLimits</code> read them; seasons from <code>astrological_season_config</code>. Names are the game's
English strings. One assumption: the server pays the per-point reward per point of durability removed; the client
never computes it, so a swing that overkills an object may pay for the whole roll or only for the durability left.</p>
</div>
"""
    return layout("Material Realms and relics",
                  "What each Material Realm pays per swing at every promotion, the fights that unlock each realm level, and every relic level's cost on the normal and season ladders.",
                  body, "realms", 0)
