"""Material Realms and relic levels.

Material Realms are the client's "mop-up" system (mop_up_dungeon / mop_up_material): each realm holds one object at
a time (an ore node, a gnoll, an abandoned chest) with a durability; every swing spends one tool
(mop_up_dungeon.CostDict) and deals BattleFormulaHandler.GetMopUpDamage = attack x U(1-DamageFloat, 1+DamageFloat)
x (1 + crit power on a crit), rounded. Each point of durability pays the object's AttackRewardIds and the break pays
BreakRewardIds; both are reward_rule rows whose count is CountList x level_number[SubRankCountId][(int)SubRank],
truncated (RewardRuleInfoParser.GetRewardDropInfosByRuleList), so a promotion is one step up level_number column 6.
A realm's "level" is the number of its unlock stages the player has cleared
(MopUpDungeonInfoParser.GetUnlockDungeonHighestLevel); the client uses it for unlocking only.

Sand grades merge 5 -> 1 (item_merge: 5 Chrono Sand = 1 Rare, 5 Rare = 1 Epic; the Legendary and Mythic recipes are
commented out), and the client pays a higher grade from lower ones automatically (ItemMergeInfoParser.CalcMergeCost).

Relics are the game's Treasures. Normal levels cost treasure_levelup_material up to the promotion's cap
(system_level_limit.TreasureLevel, Formula.GetMaxTreasureBaseLevel); above the cap a level is a season level and
costs treasure_bless[player's Rank family][level - cap] (TreasureHelper.GetTreasureLevelUpCostMaterials). Season
levels open only at the top sub-rank of the season's promotion (FormulaHandler.GetMaxTreasureBlessLevel) and each is
gated by a character level (system_level_limit rows) and by the other relic slots (system_level_gap_limit).
"""
from __future__ import annotations
import html, re, collections, math, json


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


TAB_JS = r"""
(function () {
  var bar = document.getElementById("rtabs"), panes = document.querySelectorAll(".tabpane");
  function show(id, push) {
    var found = false;
    panes.forEach(function (p) { p.hidden = p.id !== "tab-" + id; if (!p.hidden) found = true; });
    if (!found) { show("sand"); return; }
    bar.querySelectorAll("button").forEach(function (b) { b.setAttribute("aria-selected", b.dataset.tab === id ? "true" : "false"); });
    if (push && history.replaceState) history.replaceState(null, "", "#" + id);
  }
  bar.addEventListener("click", function (e) { var b = e.target.closest("button"); if (b) show(b.dataset.tab, true); });
  window.addEventListener("hashchange", function () { show(location.hash.slice(1) || "sand"); });
  show(location.hash.slice(1) || "sand");

  var D = REALM_DATA, $ = function (id) { return document.getElementById(id); };
  function fmt(v, d) { return Number(v).toLocaleString("en-US", { maximumFractionDigits: d == null ? 0 : d }); }
  function bind(k) {
    var amt = $("cv_amt_" + k), gr = $("cv_grade_" + k), pr = $("cv_prom_" + k), out = $("cv_out_" + k);
    if (!amt) return;
    function go() {
      var a = Number(amt.value) || 0, rate = Number(gr.value), plain = a * rate, t = D.sand[pr.value];
      var nodes = t.sand > 0 ? plain / t.sand : 0, swings = nodes * t.swings;
      out.innerHTML = fmt(plain) + " " + D.names.plain + " &nbsp;=&nbsp; " + fmt(plain / 5, 1) + " " + D.names.rare + " &nbsp;=&nbsp; " + fmt(plain / 25, 2) + " " + D.names.epic +
        "<br><span class=hint>at " + t.name + ": about " + fmt(swings) + " swings (one " + D.names.tool + " each) over " + fmt(nodes, 1) + " objects, counting every node type and chest at its odds</span>";
    }
    [amt, gr, pr].forEach(function (el) { el.addEventListener("input", go); el.addEventListener("change", go); });
    go();
  }
  bind("a"); bind("b");
})();
"""


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
    h, ps = rows_of("player_subrank")
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
        """[(item, count)] the way RewardRuleInfoParser scales and truncates it for this promotion"""
        out = collections.OrderedDict()
        for rid in rule_ids:
            for rule in rules.get(rid, []):
                f = 1.0
                if rule["levelId"]:
                    f *= numbers.get((rule["levelId"], 0), 1.0)
                if rule["subId"]:
                    f *= numbers.get((rule["subId"], ordinal.get(sub, 0)), 1.0)
                out[rule["item"]] = out.get(rule["item"], 0) + int(rule["count"] * f)
        return list(out.items())

    # ---- sand grades (item_merge): item -> plain Chrono Sand per unit
    h, im = rows_of("item_merge")
    merge = {_num(r[0]): (_num(r[3]), _num(r[4]), _num(r[2]) or 1) for r in im if r[3].strip()}

    def plain_rate(iid, base):
        """units of `base` per one `iid`, following the active merge recipes"""
        rate = 1.0
        while iid != base and iid in merge:
            mat, cnt, made = merge[iid]
            rate *= cnt / made
            iid = mat
        return rate if iid == base else None

    SAND, RARE, EPIC = 41400, 41401, 41402
    rate = {i: plain_rate(i, SAND) for i in (SAND, RARE, EPIC, 41403, 41404)}

    def as_sand(pairs):
        tot = sum(c * rate[i] for i, c in pairs if rate.get(i))
        return int(round(tot))

    # ---- the realms
    h, md = rows_of("mop_up_dungeon"); mi = {c: i for i, c in enumerate(h)}
    h, mm = rows_of("mop_up_material"); oi = {c: i for i, c in enumerate(h)}
    objects = {}
    for r in mm:
        objects[_num(r[0])] = {"attack": _list(r[oi["AttackRewardIds"]]), "brk": _list(r[oi["BreakRewardIds"]]),
                               "dur": _num(r[oi["Durability"]]), "count": r[oi["CanCount"]].strip().upper() == "TRUE",
                               "cost": r[oi["NeedCost"]].strip().upper() == "TRUE"}
    realms = collections.OrderedDict()
    for r in md:
        t = r[mi["Type"]].strip()
        gen = _num(r[mi["GenerateMaterialRuleId"]])
        pool = [(x["item"], x["weight"] / x["total"]) for x in rules.get(gen, []) if x["total"]]
        realms[t] = {"type": t, "name": loc(f"NormalMaterial.{t}", t), "stages": _list(r[mi["UnlockStages"]]),
                     "cost": _items(r[mi["CostDict"]]), "pool": pool, "newbie": _list(r[mi["NewbieRewardMaterials"]]),
                     "props": {k: r[mi[k + "Prop"]].strip() for k in ("Attack", "CritRate", "CritPower")}}

    gs = open(_b.CFG / "game_settings", encoding="utf-8-sig", errors="replace").read()
    m = re.search(r'"MopUp"\s*:\s*\{(.*?)\}', gs, re.S)
    mop = {k: float(v) for k, v in re.findall(r'"(\w+)"\s*:\s*([\d.]+)', m.group(1) if m else "")}
    dmg_float = mop.get("DamageFloat", 0.1)
    daily_free = int(mop.get("DailyFreeCount", 0) * mop.get("TimesForOneFreeCount", 1))
    once_max = int(mop.get("MopUpOnceMaxCount", 0))

    h, lp = rows_of("level_prop"); li = {c: i for i, c in enumerate(h)}
    swing = {}
    for rm in realms.values():
        vals = {k: sorted({_num(r[li[c]]) for r in lp if c in li and li[c] < len(r)}) for k, c in rm["props"].items()}
        swing[rm["type"]] = {"atk": vals["Attack"], "crit": [v / 10000 for v in vals["CritRate"]], "power": [v / 10000 for v in vals["CritPower"]]}

    def expected_damage(t):
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

    ed = {t: expected_damage(t) for t in realms}
    same_swing = len({(tuple(s["atk"]), tuple(s["crit"]), tuple(s["power"])) for s in swing.values()}) == 1
    t0 = next(iter(realms)); s0 = swing[t0]; ed0 = ed[t0]

    def obj_pay(o, sub):
        per = payout(o["attack"], sub); brk = payout(o["brk"], sub)
        tot = collections.OrderedDict()
        for i, c in per:
            tot[i] = tot.get(i, 0) + c * o["dur"]
        for i, c in brk:
            tot[i] = tot.get(i, 0) + c
        return per, brk, list(tot.items())

    def swings_for(o, t):
        return math.ceil(o["dur"] / ed[t]) if (ed[t] and o["dur"] > 0) else 0

    # ---- material panes: one per realm, keyed by the material the user names
    panes = collections.OrderedDict([("sand", "SandsOfTime"), ("essence", "SkillSeniorMaterial"), ("ore", "RoughRefineStone"), ("rolla", "SilverCoin")])
    labels = {"sand": item_name(SAND), "essence": item_name(42200), "ore": item_name(41300), "rolla": item_name(1)}

    def pane_html(key, t):
        rm = realms[t]
        tool = ", ".join(esc(item_name(i)) for i, c in rm["cost"])
        objs = [(iid, w, objects[iid]) for iid, w in rm["pool"] if iid in objects]
        paid = [(iid, w, o) for iid, w, o in objs if o["cost"]]
        chests = [(iid, w, o) for iid, w, o in objs if not o["cost"]]
        # group paid objects by identical payout + durability so the table stays narrow
        groups = collections.OrderedDict()
        for iid, w, o in paid:
            sig = (o["dur"], tuple(payout(o["attack"], tiers[0])), tuple(payout(o["brk"], tiers[0])))
            g = groups.setdefault(sig, {"names": [], "w": 0, "o": o, "dur": o["dur"]})
            g["names"].append(item_name(iid)); g["w"] += w
        intro = (f"<p>{esc(rm['name'])}, one {tool} per swing. What the realm puts in front of you: " +
                 "; ".join(f"{esc(' / '.join(g['names']))} ({g['w'] * 100:.0f}%, {g['dur']} durability, about {swings_for(g['o'], t)} swings)" for g in groups.values()) +
                 ("; " + "; ".join(f"{esc(item_name(iid))} ({w * 100:.0f}%, opens free)" for iid, w, o in chests) if chests else "") + ".</p>")
        head = "<tr><th>Promotion</th><th class=num>Factor</th>"
        for g in groups.values():
            head += f"<th class=num>{esc(' / '.join(g['names']))}<br><span class=hint>per swing &middot; per object</span></th>"
        for iid, w, o in chests:
            head += f"<th class=num>{esc(item_name(iid))}</th>"
        head += "</tr>"
        body = ""; prevf = None
        for sub in tiers:
            f = factor(sub)
            row = f"<tr><th>{esc(disp[sub])}</th><td class=num>{f:g}&times;" + (f" <span class=hint>+{(f / prevf - 1) * 100:.0f}%</span>" if prevf else "") + "</td>"
            prevf = f
            for g in groups.values():
                per, brk, tot = obj_pay(g["o"], sub)
                per_swing = [(i, int(round(c * ed[t]))) for i, c in per] if ed[t] else per
                row += f"<td class=num>{lst(per_swing)}<br><span class=hint>{lst(tot)}</span></td>"
            for iid, w, o in chests:
                row += f"<td class=num>{lst(obj_pay(o, sub)[2])}</td>"
            body += row + "</tr>"
        table = f'<div class="tablewrap"><table class="xp small"><thead>{head}</thead><tbody>{body}</tbody></table></div>'
        return intro, table

    # expected plain sand and swings per object drawn, per promotion (for the converter)
    sand_rm = realms[panes["sand"]]
    sand_tiers = []
    for sub in tiers:
        es = 0.0; esw = 0.0
        for iid, w in sand_rm["pool"]:
            o = objects.get(iid)
            if not o:
                continue
            es += w * as_sand(obj_pay(o, sub)[2])
            esw += w * (o["dur"] / ed[panes["sand"]] if (ed[panes["sand"]] and o["dur"] > 0) else 0)
        sand_tiers.append({"name": disp[sub], "sand": round(es, 2), "swings": round(esw, 3)})
    default_prom = next((i for i, s in enumerate(tiers) if s == "Gold1"), 0)

    def converter(k):
        opts = "".join(f'<option value="{i}"{" selected" if i == default_prom else ""}>{esc(disp[s])}</option>' for i, s in enumerate(tiers))
        grades = "".join(f'<option value="{rate[i]:g}"{" selected" if i == EPIC else ""}>{esc(item_name(i))}</option>' for i in (SAND, RARE, EPIC))
        return (f'<div class="conv"><label>Amount <input type="number" id="cv_amt_{k}" value="900" min="0"></label>'
                f'<label>Grade <select id="cv_grade_{k}">{grades}</select></label>'
                f'<label>Your promotion <select id="cv_prom_{k}">{opts}</select></label>'
                f'<div class="out" id="cv_out_{k}"></div></div>')

    realm_data = {"sand": sand_tiers, "names": {"plain": item_name(SAND), "rare": item_name(RARE), "epic": item_name(EPIC),
                                                 "tool": item_name(sand_rm["cost"][0][0]) if sand_rm["cost"] else "tools"}}

    # ---- unlock stages
    h, st = rows_of("stage"); si = {c: i for i, c in enumerate(h)}
    stage = {_num(r[0]): r for r in st}
    where = {}
    for r in _b.csvrows("stage_map_location")[2:]:
        if r and r[0].strip().isdigit():
            mm_ = re.search(r"'(\d+)':\[(\d+)\]", r[1] if len(r) > 1 else "")
            if mm_:
                where[int(r[0])] = (int(mm_.group(1)), int(mm_.group(2)))
    maxlv = max(len(rm["stages"]) for rm in realms.values())
    unlock_head = "<tr><th class=num>Level</th>" + "".join(f"<th>{esc(rm['name'])}</th>" for rm in realms.values()) + "</tr>"
    unlock_body = ""
    missing_rules = set()
    for k in range(maxlv):
        cells = ""
        for rm in realms.values():
            if k >= len(rm["stages"]):
                cells += "<td>&mdash;</td>"; continue
            sid = rm["stages"][k]; r = stage.get(sid)
            if not r:
                cells += f"<td>stage {sid}</td>"; continue
            sub = r[si["SubRank"]].strip(); lvl = r[si["Level"]].strip()
            awards = _list(r[si["Awards"]])
            missing_rules |= {a for a in awards if a not in rules}
            loc_ = where.get(sid)
            place = f" &middot; {esc(loc(f'region_{loc_[0]}_{loc_[1]}'))}" if loc_ else ""
            cells += f"<td>{esc(disp.get(sub, sub))} Lv. {esc(lvl)}{place}<br><span class=hint>{lst(payout(awards, sub))}</span></td>"
        unlock_body += f"<tr><th class=num>{k + 1}</th>{cells}</tr>"

    # ---- relics
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

    def cost_cell(its):
        mats = [x for x in its if x[0] != 1]
        sand = as_sand(mats)
        show_sand = sand and any(rate.get(i) and i != SAND for i, c in mats)
        return f"<td>{lst(mats)}" + (f"<br><span class=hint>= {n(sand)} {esc(item_name(SAND))}</span>" if show_sand else "") + f"</td><td class=num>{n(dict(its).get(1, 0))}</td>"

    h, lm = rows_of("treasure_levelup_material")
    normal = [(_num(r[0]), _items(r[1])) for r in lm]
    normal_rows = ""
    for lv, its in normal:
        nd = needs(lv)
        normal_rows += (f"<tr><td class=num>{lv - 1} &rarr; {lv}</td>{cost_cell(its)}"
                        f"<td>{esc(nd) if nd else '<span class=hint>no promotion in this build</span>'}</td></tr>")

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
    current_fam = family("Gold1")      # the September 2026 roster is Champion I/II: Season 2

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
            season_blocks += (f"<details><summary>{title}</summary><p class=calcnote>No season relic ladder in this client build: "
                              + ("no <code>treasure_bless</code> rows for this promotion" if not rows else "no relic caps for this promotion in <code>system_level_limit</code>")
                              + ".</p></details>")
            continue
        g = gap.get(sn, [])
        trs = ""
        for lv, its in rows:
            ua = unlock_at(top, lv)
            over = lv > bcap
            trs += (f"<tr{' class=dim' if over else ''}><td class=num>{cap + lv - 1} &rarr; {cap + lv}</td><td class=num>{lv}</td>{cost_cell(its)}"
                    f"<td class=num>{('Lv. ' + str(ua)) if ua else ('above the cap of ' + str(bcap) if over else '&mdash;')}</td></tr>")
        gap_txt = (f" From relic level {g[0][0] + 1} on, all five relic slots must stand at level {g[0][0]} or higher, and each further "
                   f"level needs all five at the level below it.") if g else ""
        season_blocks += (f"<details{' open' if fam == current_fam else ''}><summary>{title}</summary>"
                          f"<p>Normal levels run to <b>{cap}</b> at {esc(disp[top])}. Season levels: {len(rows)} in the ladder, "
                          f"<b>{bcap}</b> buyable in this build (relic level {cap + bcap}), each opening at the character level shown "
                          f"(<i>\"{esc(unlock_str)}\"</i>).{gap_txt}</p>"
                          f"<div class=\"tablewrap\"><table class=\"xp small\"><thead><tr><th class=num>Relic level</th><th class=num>Season level</th>"
                          f"<th>Cost</th><th class=num>Rolla</th><th class=num>Character level</th></tr></thead><tbody>{trs}</tbody></table></div></details>")
        if cap < 11 and rows:
            k = 11 - cap
            its = dict(rows).get(k)
            if its:
                example.append((sn, f"season level {k}, sold at {esc(disp[top])} only: {lst([x for x in its if x[0] != 1])} ({n(as_sand(its))} {esc(item_name(SAND))}) and {n(dict(its).get(1, 0))} Rolla"))
        elif cap >= 11:
            its = dict(normal).get(11)
            if its:
                example.append((sn, f"normal level 11, open from {esc(needs(11))}: {lst([x for x in its if x[0] != 1])} ({n(as_sand(its))} {esc(item_name(SAND))}) and {n(dict(its).get(1, 0))} Rolla"))
    grouped = []
    for sn, ans in example:
        if grouped and grouped[-1][1] == ans:
            grouped[-1][0].append(sn)
        else:
            grouped.append(([sn], ans))
    example_txt = "; ".join(("in Season " + str(sns[0]) if len(sns) == 1 else f"from Season {sns[0]} to {sns[-1]}") + " it is " + ans for sns, ans in grouped)

    # stars
    h, um = rows_of("treasure_upgrade_material"); ui = {c: i for i, c in enumerate(h)}
    star_rows = collections.OrderedDict()
    for r in um:
        star_rows.setdefault(r[ui["Quality"]].strip(), []).append((_num(r[ui["Star"]]), _num(r[ui["PieceCount"]]), _num(r[ui["SpecialPieceCount"]]), _items(r[ui["Materials"]])))
    star_head = "<tr><th>Star</th>" + "".join(f"<th class=num>{esc(loc(f'Quality.{q}', q))}</th>" for q in star_rows) + "</tr>"
    star_body = ""
    for s in sorted({s for rows in star_rows.values() for s, *_ in rows}):
        cells = ""
        for q, rows in star_rows.items():
            row = next((x for x in rows if x[0] == s), None)
            if not row:
                cells += "<td class=num>&mdash;</td>"; continue
            _s, pc, spc, mats = row
            cells += (f"<td class=num>{n(pc)} shards" + (f" <span class=hint>({n(spc)} for a special relic)</span>" if spc != pc else "")
                      + (f"<br><span class=hint>+ {lst(mats)}</span>" if mats else "") + "</td>")
        star_body += f"<tr><th>{'&#9733;' * s if s else '0 stars'}</th>{cells}</tr>"

    # ---- assemble
    tips = [loc(f"rule_tip_NormalMaterialUpInfo_{i}") for i in (1, 2, 3)]
    quick_map = loc("Mainland_14")
    merge_txt = " &rarr; ".join(f"{n(merge[i][1])} {esc(item_name(merge[i][0]))} = 1 {esc(item_name(i))}" for i in (RARE, EPIC) if i in merge)
    tab_buttons = "".join(f'<button type="button" data-tab="{k}">{esc(labels[k])}</button>' for k in panes) + \
                  '<button type="button" data-tab="relics">Relics</button><button type="button" data-tab="unlock">Unlock fights</button>'
    pane_html_all = ""
    for k, t in panes.items():
        intro, table = pane_html(k, t)
        extra = ""
        if k == "sand":
            extra = (f"<p><b>Sand grades.</b> {merge_txt}, so 1 {esc(item_name(EPIC))} is {n(rate[EPIC])} {esc(item_name(SAND))}; the game merges "
                     f"upward for you when a cost asks for a grade you lack (<code>item_merge</code>, <code>CalcMergeCost</code>). The next two "
                     f"grades have no active recipe in this build.</p>{converter('a')}")
        pane_html_all += f'<section class="tabpane" id="tab-{k}" hidden>{intro}{extra}{table}</section>'

    facts = (f'<div class="facts"><div class="fact"><b>1 tool</b><span>per swing, no free swings</span></div>'
             f'<div class="fact"><b>&asymp; {ed0:.0f}</b><span>durability per swing: {s0["atk"][0]:g} &times; {1 - dmg_float:g}&ndash;{1 + dmg_float:g}, '
             f'{s0["crit"][0] * 100:g}% crit &times;{1 + s0["power"][0]:g}</span></div>'
             f'<div class="fact"><b>&times;{factor("Gold1"):g} &rarr; &times;{factor("Gold2"):g}</b><span>{esc(disp["Gold1"])} to {esc(disp["Gold2"])}: +{(factor("Gold2") / factor("Gold1") - 1) * 100:.0f}% on every reward</span></div>'
             f'<div class="fact"><b>{n(rate[EPIC])} : {n(rate[RARE])} : 1</b><span>{esc(item_name(SAND))} per {esc(item_name(EPIC))} and {esc(item_name(RARE))}</span></div></div>')

    body = f"""
<div class="wrap">
<p class="eyebrow">Progression</p>
<h1>Material Realms and relics</h1>
<p class="lede">One tool per swing, a reward per point of durability, and every reward multiplied by your promotion's
factor. Pick a material below for its table by promotion; the Relics tab prices every level in the sand you actually mine.
For what those swings are worth in season points, use the <a href="primostars.html">Primostar planner</a>.</p>
{facts}
<p class="calcnote">The rule card in the game: <i>"{esc(tips[0])}"</i> <i>"{esc(tips[1])}"</i> Reward counts are
<code>reward_rule</code> base &times; <code>level_number</code> column 6 at your sub-rank, rounded down; the realm
"level" only tracks which unlock fights you have cleared and scales nothing. Quick mode swings until the object breaks
({once_max} per request) once {esc(quick_map)} is open. Per-swing figures are averages over the swing roll.</p>

<div class="tabbar" id="rtabs" role="tablist">{tab_buttons}</div>
{pane_html_all}

<section class="tabpane" id="tab-relics" hidden>
<p>A relic has normal levels up to a cap set by your promotion (+1 per tier: {esc(disp['Silver3'])} {base_cap.get('Silver3', '?')},
{esc(disp['Gold3'])} {base_cap.get('Gold3', '?')}, {esc(disp['Saint3'])} {base_cap.get('Saint3', '?')}). Past the cap the level is a
<b>season level</b> (<i>"{esc(loc('ui_blessing_player_level_tip_1'))}"</i>): sold only at the top tier of the season's promotion,
priced from that promotion's ladder, and gone when the season ends. So the same number costs different things in different
seasons &mdash; <b>level 10 &rarr; 11</b>: {example_txt}.</p>
{converter('b')}
<h3>Normal levels <span class=hint>(every season)</span></h3>
<div class="tablewrap"><table class="xp small"><thead><tr><th class=num>Level</th><th>Cost</th><th class=num>Rolla</th><th>Needs</th></tr></thead>
<tbody>{normal_rows}</tbody></table></div>
<h3>Season levels</h3>
{season_blocks}
<details><summary>Stars</summary>
<p>Bought with the relic's own shards, by quality; the last star also takes universal shards of the same grade.</p>
<div class="tablewrap"><table class="xp small"><thead>{star_head}</thead><tbody>{star_body}</tbody></table></div></details>
</section>

<section class="tabpane" id="tab-unlock" hidden>
<p>Each realm level opens when you clear its fight on the world map (<i>"{esc(loc('TravelNotesPanel.NormalMaterialUnlockStage').replace('{1}', 'the fight').replace('{0}', 'its region'))}"</i>).
The small line is the fight's first-clear reward, scaled by the fight's own tier.</p>
<div class="tablewrap"><table class="xp small"><thead>{unlock_head}</thead><tbody>{unlock_body}</tbody></table></div>
{'<p class="calcnote">Reward rule ' + ', '.join(str(x) for x in sorted(missing_rules)) + ' is named by the stage table but does not exist in the client&rsquo;s reward table, so it is left out.</p>' if missing_rules else ''}
</section>

<details class="statbox"><summary>Where this comes from</summary>
<p class="calcnote">Realms: <code>mop_up_dungeon</code> (tools, unlock fights, object pools), <code>mop_up_material</code>
(durability, per-point and break reward rules), <code>reward_rule</code> scaled by <code>level_number</code> as
<code>RewardRuleInfoParser.GetRewardDropInfosByRuleList</code> does it, <code>level_prop</code> for the swing stats,
<code>BattleFormulaHandler.GetMopUpDamage</code> for the roll, <code>game_settings.MopUp</code>, <code>rule_tip</code>,
<code>stage</code> and <code>stage_map_location</code>; sand grades from <code>item_merge</code>. Relics:
<code>treasure_levelup_material</code>, <code>treasure_bless</code>, <code>treasure_upgrade_material</code>,
<code>system_level_limit</code>, <code>system_level_gap_limit</code>, read the way <code>TreasureHelper</code> reads
them; seasons from <code>astrological_season_config</code>. Names are the game's English strings. One assumption: the
server pays the per-point reward per point of durability removed; the client never computes it, so a swing that
overkills an object may pay for the whole roll or only for the durability left.</p></details>
</div>
<script>var REALM_DATA = {json.dumps(realm_data)};</script>
<script>{TAB_JS}</script>
"""
    return layout("Material Realms and relics",
                  "What each Material Realm pays per swing at every promotion, a sand-grade converter, the fights that unlock each realm level, and every relic level's cost on the normal and season ladders.",
                  body, "realms", 0)
