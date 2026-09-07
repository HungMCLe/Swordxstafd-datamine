"""Cookbook — every dish by the kingdom (and so the season) that brings it, with its
ingredients, yield, effect, where the effect applies, the permanent bonus and its decay.

Sources: cooking (materials, yield, unlock), status_effect (battles, scopes, entry),
status_effect_scope (where it applies, named by entry_{id}_name), level_prop_cooking (the
permanent bonus), cooking_prop_effect_full (its decay by meals eaten), item (names, quality,
flavour text), and the itemicon_food_map{N} bundles, which say which kingdom a dish belongs to.
"""
from __future__ import annotations
import html, re, os, json, shutil, collections


def _num(s, d=0):
    try:
        return int(str(s).strip())
    except Exception:
        return d


def render(layout, base_tables, dist, out):
    import build as _b
    L = _b.L
    ladder, *_ = base_tables()

    def loc(key, fallback=""):
        v = L(key)
        return (v or fallback).strip()

    def rows_of(name):
        r = _b.csvrows(name); h = [c.strip() for c in r[0]]
        return h, [x for x in r[2:] if x and x[0].strip() and not x[0].startswith("#")]

    # ---- seasons per kingdom, as on the other pages
    fam_cap, fam_name = {}, {}
    for Ld in ladder:
        fam = Ld["internal"].split("_")[0]
        fam = fam if fam.startswith(("Godtouched", "Demigod")) else fam.rstrip("123")
        fam_cap[fam] = max(fam_cap.get(fam, 0), Ld["cap"]); fam_name.setdefault(fam, Ld["rank"].rsplit(" ", 1)[0])
    season_of_cap = {}
    for r in _b.csvrows("astrological_season_config")[2:]:
        if r and r[0].strip().isdigit():
            fam = r[1].strip()
            season_of_cap[fam_cap.get(fam, 0)] = (int(r[0]), loc(f"astrological_season_{r[0]}_name", f"Season {r[0]}"))
    MAP_CAP = {13: 100, 14: 130, 17: 160, 19: 190, 21: 220}
    MAP_ORDER = [11, 12, 13, 14, 17, 19, 21]

    def map_title(m):
        nm = loc(f"ui_map_{m}", f"Map {m}")
        s = season_of_cap.get(MAP_CAP.get(m, -1))
        return f"Season {s[0]} · {html.escape(s[1])} — {html.escape(nm)}" if s else f"Before the seasons — {html.escape(nm)}"

    # ---- tables
    h, ck = rows_of("cooking"); ci = {c: i for i, c in enumerate(h)}
    h, se = rows_of("status_effect"); si = {c: i for i, c in enumerate(h)}
    effects = {r[0].strip(): r for r in se}
    h, sc = rows_of("status_effect_scope"); sci = {c: i for i, c in enumerate(h)}
    scope_name = {r[0].strip(): loc(f"entry_{r[sci['EntryId']].strip()}_name", r[sci["Name"]]) for r in sc}
    h, lc = rows_of("level_prop_cooking"); lci = {c: i for i, c in enumerate(h)}
    perm = {}
    for r in lc:
        perm[r[0].strip()] = {h[i]: _num(r[i]) for i in range(2, len(h)) if _num(r[i])}
    h, dec = rows_of("cooking_prop_effect_full")
    decay = collections.defaultdict(list)
    for r in dec:
        decay[r[0].strip()].append((_num(r[1]), _num(r[2])))
    it = _b.csvrows("item"); ih = [c.strip() for c in it[0]]; ii = {c: i for i, c in enumerate(ih)}
    items = {r[0].strip(): r for r in it[2:] if r and r[0].strip().isdigit()}
    QW = {q: loc(f"Quality.{q}", q) for q in ("White", "Blue", "Purple", "Orange", "Gold", "Red", "Rainbow")}

    # ---- art
    def copy_dir(sub, dest):
        src = os.path.join(out, sub); d = os.path.join(dist, "assets", dest); os.makedirs(d, exist_ok=True); have = set()
        if os.path.isdir(src):
            for f in os.listdir(src):
                if f.endswith(".png"):
                    shutil.copy2(os.path.join(src, f), os.path.join(d, f)); have.add(f[:-4])
        return have
    have_food = copy_dir("food_icons", "food")
    have_mat = copy_dir("material_icons", "materials")
    try:
        kingdom_of = json.load(open(os.path.join(out, "food_icons", "_map.json"), encoding="utf-8"))
    except Exception:
        kingdom_of = {}

    def item_name(i):
        return loc(f"item_{i}_name", i)

    def mat_icon(i):
        """Higher grades share their base item's icon: follow the item's own icon path."""
        row = items.get(i)
        base = row[ii["Icon"]].strip().rsplit("/", 1)[-1] if row else f"item_{i}"
        return base if base in have_mat else (f"item_{i}" if f"item_{i}" in have_mat else None)

    def prop_label(k):
        base = k.replace("CookFinal", "").replace("Scale", "Percent")
        return loc(f"PropType.{base}", "") or loc(f"PropType.{k}", k)

    # ---- one dish
    def dish(r):
        cid = r[0].strip()
        name = item_name(cid)
        irow = items.get(cid)
        quality = QW.get(irow[ii["Quality"]].strip(), "") if irow else ""
        flavour = loc(f"item_{cid}_desc", "")
        mats = [(i, _num(n)) for i, n in re.findall(r"(\d+)\s*:\s*(\d+)", r[ci["Materials"]])]
        count = _num(r[ci["Count"]], 1)
        cond, param = r[ci["ConditionType"]].strip(), r[ci["ConditionParams"]]
        if cond == "MapUnlock":
            mid = re.search(r"\d+", param)
            unlock = f"unlocks with {html.escape(loc('ui_map_' + mid.group(0), 'map ' + mid.group(0)))}" if mid else "unlocks with a map"
        elif cond == "UsedItem":
            rid = re.search(r"ClassId\W+(\d+)", param)
            unlock = f"learned from <b>{html.escape(item_name(rid.group(1)))}</b>" if rid else "learned from a recipe"
        else:
            unlock = "known from the start"
        # the effect
        typ = r[ci["Type"]].strip()
        eff = r[ci["EffectInfoDict"]]
        if typ == "Recovery":
            pct = re.search(r"CurePercent:([\d.]+)", eff); val = re.search(r"CureValue:(\d+)", eff)
            effect = f"Restores {float(pct.group(1)) * 100:g}% + {_num(val.group(1)):,} HP" if pct and val else html.escape(loc(f"item_{cid}_func_desc", ""))
            where = ""
        else:
            s = effects.get(cid)
            entry = s[si["EntryId"]].strip() if s else ""
            scopes = [scope_name.get(x, x) for x in re.findall(r"\d+", s[si["Scopes"]])] if s else []
            text = loc(f"entry_{entry}_desc", "") if entry else ""
            if not text:
                text = loc(f"item_{cid}_func_desc", "")
            effect = html.escape(text.replace("{0}", " and ".join(scopes) if scopes else "battle"))
            where = ""
        pm = perm.get(cid, {})
        permanent = ", ".join(f"+{v / 100:g}% {html.escape(prop_label(k))}" for k, v in pm.items())
        steps = decay.get(cid, [])
        icon = f'<img src="assets/food/item_{cid}.png" alt="" loading="lazy">' if f"item_{cid}" in have_food else '<span class="noimg"></span>'
        ing = "".join(
            f'<li>{"<img src=assets/materials/" + mat_icon(i) + ".png alt=\"\" loading=lazy>" if mat_icon(i) else ""}'
            f'{html.escape(item_name(i))} <b>&times;{n}</b></li>' for i, n in mats)
        rows = f"<dt>Makes</dt><dd>{count}</dd><dt>How</dt><dd>{unlock}</dd><dt>Effect</dt><dd>{effect}</dd>"
        if permanent:
            rows += f"<dt>Permanent</dt><dd>{permanent} per meal, fading with meals eaten</dd>"
        return (f'<article class="dish" id="dish-{cid}">{icon}<div><h3>{html.escape(name)}'
                f'{" <span class=q-" + irow[ii["Quality"]].strip().lower() + ">" + html.escape(quality) + "</span>" if quality else ""}</h3>'
                f'{"<p class=flavour>" + html.escape(flavour) + "</p>" if flavour else ""}'
                f'<ul class="ing">{ing}</ul><dl>{rows}</dl></div></article>')

    # ---- group by kingdom (from the icon bundle), Recovery first, then by scope and name
    groups = collections.defaultdict(list)
    for r in ck:
        cid = r[0].strip()
        k = kingdom_of.get(f"item_{cid}")
        if not k:
            m = re.search(r"\d+", r[ci["ConditionParams"]]) if r[ci["ConditionType"]].strip() == "MapUnlock" else None
            k = m.group(0) if m else "special"
        groups[str(k)].append(r)

    def sort_key(r):
        s = effects.get(r[0].strip())
        sc_ = re.findall(r"\d+", s[si["Scopes"]])[0] if s and re.findall(r"\d+", s[si["Scopes"]]) else "0"
        return (r[ci["Type"]].strip() != "Recovery", _num(sc_), item_name(r[0].strip()))

    sections = []
    for m in MAP_ORDER:
        rs = groups.pop(str(m), [])
        if not rs:
            continue
        rs.sort(key=sort_key)
        sections.append(f'<h2 id="map-{m}">{map_title(m)} <span class="hint">{len(rs)} dishes</span></h2><div class="dishgrid">{"".join(dish(r) for r in rs)}</div>')
    rest = [r for rs in groups.values() for r in rs]
    if rest:
        rest.sort(key=sort_key)
        sections.append(f'<h2 id="special">Event dishes <span class="hint">{len(rest)}, from the special bundle</span></h2><div class="dishgrid">{"".join(dish(r) for r in rest)}</div>')

    # ---- decay: every dish with a permanent bonus shares one curve
    curves = collections.Counter(tuple(v) for v in decay.values())
    common = curves.most_common(1)[0][0] if curves else ()
    decay_rows = ""
    for i, (start, eff) in enumerate(common):
        end = common[i + 1][0] - 1 if i + 1 < len(common) else None
        decay_rows += f"<tr><td class='num'>{start}{'–' + str(end) if end else '+'}</td><td class='num'>{eff / 100:g}%</td></tr>"

    # ---- ingredient index
    uses = collections.defaultdict(list)
    for r in ck:
        for i, n in re.findall(r"(\d+)\s*:\s*(\d+)", r[ci["Materials"]]):
            uses[i].append(r[0].strip())
    ing_rows = "".join(
        f"<tr><td>{'<img class=mini src=assets/materials/' + mat_icon(i) + '.png alt=\"\" loading=lazy> ' if mat_icon(i) else ''}{html.escape(item_name(i))}</td>"
        f"<td>{', '.join('<a href=#dish-' + d + '>' + html.escape(item_name(d)) + '</a>' for d in ds)}</td></tr>"
        for i, ds in sorted(uses.items(), key=lambda x: (-len(x[1]), item_name(x[0]))))

    scopes_txt = ", ".join(html.escape(scope_name[k]) for k in sorted(scope_name, key=int))

    body = f"""
<div class="wrap">
<p class="eyebrow">Reference</p>
<h1>Cookbook</h1>
<p class="lede">Every dish in the Alchemy Pot, by the kingdom that brings it and so by season, with its ingredients,
how many it makes, how you learn it, what it does and where that applies. Names, flavour text, effects and
places are the game's own text.</p>
<p>Recovery dishes unlock as their kingdom opens. Buff dishes are learned from a recipe scroll and work only in the
modes their scope names: {scopes_txt}. Sixty of them also leave a <b>permanent</b> stat bonus each time you eat one,
which fades with the number of meals of that dish you have eaten:</p>
<div class="tablewrap"><table><thead><tr><th class="num">Meals of the dish</th><th class="num">Bonus efficiency</th></tr></thead>
<tbody>{decay_rows}</tbody></table><caption><code>cooking_prop_effect_full</code>; the same curve for every dish that has a permanent bonus.</caption></div>

{"".join(sections)}

<h2 id="ingredients">Ingredients</h2>
<p>What each ingredient goes into, most-used first.</p>
<div class="tablewrap"><table><thead><tr><th>Ingredient</th><th>Dishes</th></tr></thead><tbody>{ing_rows}</tbody></table></div>
</div>
"""
    return layout("Cookbook", "Every Sword x Staff dish by kingdom and season, with ingredients, yield, effect, scope, "
                  "permanent bonus and its decay.", body, "cookbook", 0)
