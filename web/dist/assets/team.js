/* Team battle simulator (4v4): the duel engine's clock, Damage(), statuses and Charm procs,
   generalised to eight fighters on a grid, each with the sheet and skills the server reports. */
(function () {
  "use strict";
  var C;
  try { C = JSON.parse(document.getElementById("teamdata").textContent); }
  catch (e) { return; }
  var $ = function (id) { return document.getElementById(id); };
  var DATA = null, CURVES = null, SKILL = {};
  var SIDE_COL = ["#b8863b", "#3d6ea8"], SIDE_NAME = ["Team 1", "Team 2"];
  var ELES = ["Wind", "Water", "Fire", "Light", "Dark"];
  var TRIGGER_DISPLAY = /^(SkillAttack|SkillFixed|SkillCure|ShieldBy|CD$|BreakResilience)/;

  /* ---------- the battlefield (C.grid, from the stage prefab): 21 x 20 cells, Y up, Manhattan distance ---------- */
  var GRID = C.grid;
  var BLOCKED = {};
  (GRID.blocked || []).forEach(function (c) { BLOCKED[c[0] + "," + c[1]] = true; });
  function dist(a, b) { return Math.abs(a.x - b.x) + Math.abs(a.y - b.y); }
  function inGrid(x, y) { return x >= 0 && y >= 0 && x < GRID.w && y < GRID.h && !BLOCKED[x + "," + y]; }
  function inZone(side, x, y) { var z = GRID.zones[side]; return x >= z.x0 && x <= z.x1 && y >= z.y0 && y <= z.y1; }

  /* ---------- curves and prop folding (as the duel page, but every skill keeps its own rank/level) ---------- */
  var RANKID = null;
  function rankIdOf(displayName) {
    if (!RANKID) {
      RANKID = {};
      var ids = Object.keys(DATA.lpidOf[Object.keys(DATA.lpidOf)[0]] || {});
      C.ranks.forEach(function (r, i) { RANKID[r.name] = ids[i]; });
    }
    return RANKID[displayName];
  }
  function curveValue(entry, srank, slevel, rankName) {
    if (entry.v !== undefined) return entry.v;
    if (entry.m === undefined || !CURVES) return 0;
    var lp = (DATA.lpidOf[String(entry.g)] || {})[rankIdOf(rankName)];
    var curve = CURVES[lp];
    if (!curve) return 0;
    var row = curve[String(slevel)];
    return row && row[entry.k] !== undefined ? row[entry.k] * entry.m : 0;
  }
  function flatOf(rowsEntry, fxKey, fgKey, curveProp, slevel, rankName) {
    if (!rowsEntry || rowsEntry[fxKey] === undefined || !CURVES) return 0;
    var lp = (DATA.lpidOf[String(rowsEntry[fgKey])] || {})[rankIdOf(rankName)];
    var curve = CURVES[lp];
    if (!curve) return 0;
    var c = curve[String(slevel)];
    return c && c[curveProp] !== undefined ? c[curveProp] * rowsEntry[fxKey] : 0;
  }
  var PROP2FIELD = {
    ElementMaster: "mast", KongFuMaster: "kfm", ElementResistance: "eres", KongFuResistance: "kfr",
    Attack: "atk", MaxHp: "hp", Defence: "def", Speed: "spd",
    CritRatePercent: "cr", CritPowerPercent: "cd", CritAvoidPercent: "critres",
    DmgAddPercent: "boost", DmgReducePercent: "dmgres", BlockPercent: "blockrate", BlockValuePercent: "blockeff",
    BlockAvoidPercent: "blockavoid", FinalDamageReducePercent: "dmgres", EffectRate: "erate", EffectDodge: "edodge",
    StatusDmgAddPer: "boost", StatusDmgReducePer: "dmgres", DmgVulnerable: "vuln", StatusDmgVulnerablePer: "vuln",
    CureAddPercent: "cureadd"
  };
  var PROP2ELE = {};
  ELES.forEach(function (e) { PROP2ELE[e + "DamageAdd"] = ["aff", e]; PROP2ELE[e + "DamageReduce"] = ["aegis", e]; });
  var PROP2SCALE = { AttackScale: "atk", DefenceScale: "def", MaxHpScale: "hp", SpeedScale: "spd" };
  var PROP2RATIO = {
    CritRatePercentValue: ["cr", "BaseCritRatePercentValue"],
    CritAvoidPercentValue: ["critres", "BaseCritAvoidPercentValue"],
    BlockPercentValue: ["blockrate", "BaseBlockPercentValue"],
    BlockAvoidPercentValue: ["blockavoid", "BaseBlockAvoidPercentValue"]
  };
  var PROP2FLAT = { FixedStatusDmgAdd: "fadd", FixedDmgAdd: "fadd", DmgAdd: "fadd",
                    FixedStatusDmgReduce: "fred", FixedDmgReduce: "fred", DmgReduce: "fred",
                    FixedDmgVulnerable: "fvuln", FixedstatusDmgVulnerable: "fvuln" };
  var PCT_FIELDS = ["cr", "cd", "critres", "boost", "dmgres", "blockrate", "blockeff", "blockavoid", "pvpadd", "pvpres", "cureadd", "vuln"];

  /* fold one prop row (a status's numbers) into a working sheet, in percent units */
  function foldProps(e, row, srank, slevel, rank) {
    Object.keys(row).forEach(function (prop) {
      if (TRIGGER_DISPLAY.test(prop)) return;
      var v = curveValue(row[prop], srank, slevel, rank.name);
      if (!v) return;
      var f;
      if ((f = PROP2FIELD[prop])) { e[f] = (e[f] || 0) + v; return; }
      if ((f = PROP2ELE[prop])) { e[f[0]][f[1]] = (e[f[0]][f[1]] || 0) + v; return; }
      if ((f = PROP2SCALE[prop])) { e[f] *= (1 + v / 100); return; }
      var r = PROP2RATIO[prop];
      if (r) { e[r[0]] += v / rank[r[1]] * 100; return; }
      if ((f = PROP2FLAT[prop])) { e[f] = (e[f] || 0) + v; return; }
    });
  }

  /* the fighter's sheet as reported by the server, with the per-rank bases it carries */
  function sheetOf(f) {
    var base = C.ranks[f.rank] || C.ranks[0];
    var rank = {};
    Object.keys(base).forEach(function (k) { rank[k] = base[k]; });
    Object.keys(f.sheet.bases || {}).forEach(function (k) { if (f.sheet.bases[k]) rank[k] = f.sheet.bases[k]; });
    var s = { rank: rank, vuln: 0, fadd: 0, fred: 0, fvuln: 0, aff: {}, aegis: {} };
    ["hp", "atk", "def", "spd", "mast", "kfm", "eres", "kfr", "erate", "edodge", "move",
     "cr", "cd", "critres", "boost", "dmgres", "blockrate", "blockeff", "blockavoid", "pvpadd", "pvpres", "cureadd"]
      .forEach(function (k) { s[k] = f.sheet[k] || 0; });
    ELES.forEach(function (e) { s.aff[e] = (f.sheet.aff || {})[e] || 0; s.aegis[e] = (f.sheet.aegis || {})[e] || 0; });
    s.hp = Math.max(1, s.hp); s.atk = Math.max(1, s.atk); s.spd = Math.max(1, s.spd);
    return s;
  }

  /* the sheet right now: base plus every live status, then back to fractions */
  function eff(u, ents) {
    var b = u.s, e = { aff: {}, aegis: {} };
    Object.keys(b).forEach(function (k) { if (k !== "aff" && k !== "aegis") e[k] = b[k]; });
    ELES.forEach(function (x) { e.aff[x] = b.aff[x]; e.aegis[x] = b.aegis[x]; });
    PCT_FIELDS.forEach(function (f) { e[f] = (b[f] || 0) * 100; });
    u.st.forEach(function (st) {
      var props = st.meta.props || st.props, times = st.meta.stack ? (st.stacks || 1) : 1;
      if (!props) return;
      var row = props[String(st.rank)];
      if (row) for (var i = 0; i < times; i++) foldProps(e, row, st.rank, st.level, ents[st.creator].s.rank);
    });
    PCT_FIELDS.forEach(function (f) { e[f] /= 100; });
    e.atk = Math.max(1, e.atk); e.spd = Math.max(1, e.spd); e.def = Math.max(0, e.def);
    e.hpMax = u.s.hp;
    return e;
  }
  function interval(e) {
    var scale = C.speedScale[e.rank.name] || 1;
    return 100000 / Math.sqrt(Math.max(1, e.spd) * scale);
  }

  /* ---------- Damage() per hit, up to the rolls ---------- */
  function hitParts(att, def, sk, rows, slevel) {
    var row = sk.id === 0 ? { SkillAttack1: 100 } : (rows || {});
    var ec = sk.ec || null;
    var ele = sk.ele || "None";
    var elemental = ele !== "Physical" && ele !== "None";
    var mast = elemental ? att.mast : att.kfm;
    var aff = elemental ? (att.aff[ele] || 0) : 0;
    var foeMasterBase = elemental ? def.rank.BaseElementResistance : def.rank.BaseKongFuResistance;
    var myMasterBase = elemental ? att.rank.BaseElementMaster : att.rank.BaseKongFuMaster;
    var res = elemental ? def.eres : def.kfr;
    var eNum = 1 + aff / def.rank.BaseElementReduce + mast / foeMasterBase;
    var eDen = 1 + (elemental ? (def.aegis[ele] || 0) / att.rank.BaseElementAdd : 0) + res / myMasterBase;
    var pct = (1 + att.boost + (att.pvpadd || 0) + def.vuln) / Math.max(0.1, 1 + def.dmgres + (def.pvpres || 0));
    var defTerm = att.atk / (att.atk + def.def);
    var psdr = 1 + (def.rank.PlayerSkillDmgReduceScale || 0) / 10000;
    var prosdr = 1 + (def.rank.ProSkillDmgReduceScale || 0) / 10000;
    var pvp = (sk.pvp || 10000) / 10000;
    var flat = flatOf(row, "fx", "fg", "SkillFixedAttack1", slevel, att.rank.name);
    var out = { hits: [], heal: 0 };
    if (ec && ec.skillType === "Cure" || (row.SkillCureByHp && !row.SkillAttack1)) {
      out.heal = ((row.SkillCureByHp || 0) / 100 * att.hpMax +
                  flatOf(row, "SkillFixedCure", "SkillFixedCure_g", "SkillFixedCure", slevel, att.rank.name)) * pvp * (1 + (att.cureadd || 0));
      return out;
    }
    function one(coef, withFlat, on, ignoreShield, at) {
      var base = (att.atk * coef / psdr + (withFlat ? flat : 0)) * defTerm;
      var add = ((att.fadd || 0) + (def.fvuln || 0) - (def.fred || 0)) * coef / psdr;
      add = Math.max(-0.9 * base, add);
      out.hits.push({ d: (base + add) / prosdr * (eNum / eDen) * pct * pvp, on: on || [], ignoreShield: !!ignoreShield, at: at || 0 });
    }
    if (ec && ec.hits && ec.hits.length) {
      ec.hits.forEach(function (h, i) { one((row[h.prop] || 0) / 100, i === 0, h.on, h.ignoreShield, h.at); });
    } else {
      var coef = ((row.SkillAttack1 || 0) + (row.SkillAttack2 || 0) + (row.SkillAttack3 || 0) + (row.SkillAttack4 || 0)) / 100;
      var cnt = sk.hits || 1;
      for (var k = 0; k < cnt; k++) one(coef / cnt, k === 0, [], false, 0.3 + k * 0.15);
    }
    return out;
  }
  function critChance(att, def) { return Math.min(1, Math.max(0, 0.05 + att.cr - def.critres)); }
  function critMult(att, def) { return Math.max(C.minCrit, 1 + att.cd - def.critres); }
  function blockChance(att, def) { return Math.min(1, Math.max(0, def.blockrate - att.blockavoid)); }
  function blockDiv(def) { return Math.max(C.minBlock, 1 + def.blockeff); }
  function landChance(base, byProp, statusType, att, def) {
    if (!byProp) return base;
    var br = att.rank.BaseEffectRate || 1, bd = def.rank.BaseEffectDodge || 1;
    var rate = base * (1 + (att.erate || 0) / br) / Math.max(0.1, 1 + (def.edodge || 0) / bd);
    if (statusType === "AbnormalDebuff" && br <= bd) rate *= Math.pow(br / bd, 3);
    return Math.max(0, rate);
  }

  /* PVPSkillPropsScaleOnBattleProcessor over every fighter in the fight */
  function pvpGovernor(sheets) {
    var G = C.pvp; if (!G) return { scale: 1, parts: {} };
    var minBlockAvoid = Math.min.apply(null, sheets.map(function (s) { return s.blockavoid; }));
    var minCritAvoid = Math.min.apply(null, sheets.map(function (s) { return s.critres; }));
    var ratio = Math.min.apply(null, sheets.map(function (s) {
      var p = Math.min(1, Math.max(0, 0.05 + s.cr - minCritAvoid));
      var m = Math.max(s.cd - minCritAvoid, 1.3);
      var b = Math.min(1, Math.max(0, s.blockrate - minBlockAvoid));
      var bv = Math.max(s.blockeff - minBlockAvoid, 1.5);
      var r = s.atk * s.atk / (s.atk + s.def) / s.hp;
      r *= 1 - p + p * m;
      r /= 1 - b + b * bv;
      var affAvg = ELES.reduce(function (a, e) { return a + s.aff[e]; }, 0) / ELES.length;
      var aegAvg = ELES.reduce(function (a, e) { return a + s.aegis[e]; }, 0) / ELES.length;
      var addTerm = affAvg / s.rank.BaseElementAdd, redTerm = aegAvg / s.rank.BaseElementReduce;
      var mast = (s.kfm / s.rank.BaseKongFuMaster + s.mast / s.rank.BaseElementMaster) / 2;
      var res = (s.kfr / s.rank.BaseKongFuResistance + s.eres / s.rank.BaseElementResistance) / 2;
      r *= (1 + addTerm + mast) / (1 + redTerm + res);
      r *= (1 + s.boost + s.pvpadd) / (1 + s.dmgres + s.pvpres);
      return r;
    }));
    var survival = ratio > G.minSurvival ? G.minSurvival / ratio : 1;
    var ranksAll = [];
    sheets.forEach(function (s) { (s.skillRanks || []).forEach(function (r) { ranksAll.push(r); }); });
    var fightRank = ranksAll.length ? Math.round(ranksAll.reduce(function (a, b) { return a + b; }, 0) / ranksAll.length) : 0;
    var days = Math.max(0, Math.round(parseFloat($("serverdays").value) || 0));
    var keys = Object.keys(G.avgSkillRank).map(Number).sort(function (a, b) { return a - b; });
    var serverRank = G.avgSkillRank[String(Math.min(days, keys[keys.length - 1]))] || G.avgSkillRank[String(keys[keys.length - 1])];
    var dFight = G.decay[String(fightRank)] || 0, dServer = G.decay[String(serverRank)] || 0;
    var rankScale = dFight > 0 ? Math.min(1, dServer / dFight) : 1;
    var bal = sheets.map(function (s) {
      var row = G.balance[String(s.rank.rankEnum)];
      var v = row && row[String(s.slevel)];
      return v ? v / 10000 : G.defaultBalance;
    });
    var balance = bal.reduce(function (a, b) { return a + b; }, 0) / bal.length;
    return { scale: survival * rankScale * balance, parts: { survival: survival, ratio: ratio, rankScale: rankScale, fightRank: fightRank, serverRank: serverRank, balance: balance } };
  }

  var BASIC = { id: 0, name: "Basic attack", ele: "Physical", hits: 1, r: {},
                ec: { target: "Enemy", skillType: "Attack", range: [[1, 0], [-1, 0], [0, 1], [0, -1]], hits: [{ prop: "SkillAttack1", cells: [[0, 0]], on: [], onSource: false }] } };
  function shieldSize(meta, creator, holder, rank, level) {
    var row = meta.props && meta.props[String(rank)];
    if (!row) return 0;
    var amt = 0;
    Object.keys(row).forEach(function (prop) {
      var v = curveValue(row[prop], rank, level, creator.s.rank.name);
      if (prop === "ShieldByDefence") amt += v / 100 * holder.s.def;
      else if (prop === "ShieldByTargetHp") amt += v / 100 * holder.s.hp;
      else if (prop === "ShieldByConvertedCurHp") amt += v / 100 * holder.hp;
      else if (prop === "SkillFixedShield" || prop === "StatusFixedShieldAdd") amt += v;
    });
    return amt;
  }
  function redundant(sk, me, foe) {
    if (!sk.ec || !sk.ec.hits.length) return false;
    var selfTarget = sk.ec.target === "Ally" || sk.ec.target === "Me" || sk.ec.target === "Self";
    var any = false, all = true;
    sk.ec.hits.forEach(function (h) {
      h.on.forEach(function (o) {
        var mt = DATA.statuses[String(o.status)];
        if (!mt || mt.falloff) return;
        any = true;
        var tgt = (o.target === "DamageTarget" && !selfTarget) ? foe : me;
        if (!tgt) { all = false; return; }
        var up = tgt.st.some(function (x) { return x.id === o.status && (x.dur !== 0); });
        if (mt.shield && tgt.shield <= 0) up = false;
        if (!up) all = false;
      });
    });
    return any && all && sk.ec.skillType !== "Attack";
  }
  var SKIP_ACTIONS = { Stun: 1, Frozen: 1 };
  function cdOf(t) { var row = t.sk.r[String(t.rank)] || {}; return Math.max(0, Math.round(row.CD || 0)); }
  function cdStartOf(charms) {
    var cut = 0;
    charms.forEach(function (ch) {
      (ch && ch.sk.passive || []).forEach(function (pv) {
        pv.triggers.forEach(function (t) {
          var tr = DATA.trig[String(t.skill)];
          if (!tr || !tr.ec) return;
          tr.ec.hits.forEach(function (h) { h.on.forEach(function (o) { var mt = DATA.statuses[String(o.status)]; if (mt && mt.cdStart) cut += mt.cdStart; }); });
        });
      });
    });
    return cut;
  }
  function openingCds(techs, charms) {
    var cut = cdStartOf(charms);
    return techs.map(function (t) {
      if (!t) return 0;
      if (t.sk.ec && t.sk.ec.resetCdAtStart) return 0;
      return Math.max(0, cdOf(t) + 1 + cut);
    });
  }
  function statusName(meta, lent) {
    if (meta.action === "Blinding") return "Blind";
    if (meta.action && meta.action !== "Status" && meta.action !== "PassiveStatus" && meta.action !== "None") return meta.action;
    if (meta.shield) return "Shield";
    var src = meta.props || lent;
    var p = src && src["22"];
    var k = p && Object.keys(p).filter(function (x) { return !TRIGGER_DISPLAY.test(x); })[0];
    if (k) {
      var LAB = { StatusDmgReducePer: "DMG RES", FixedStatusDmgReduce: "DMG RES", StatusDmgAddPer: "DMG Boost",
                  AttackScale: "ATK", DefenceScale: "DEF", SpeedScale: "SPD", MaxHpScale: "HP",
                  DmgAddPercent: "DMG Boost", DmgReducePercent: "DMG RES", CritRatePercent: "Crit Rate",
                  CritPowerPercent: "Crit DMG", BlockPercent: "Block Rate", StatusDmgVulnerablePer: "Vulnerable",
                  DmgVulnerable: "Vulnerable", CritAvoidPercent: "Crit RES", ElementMaster: "Mastery" };
      return (meta.type === "Debuff" || meta.type === "AbnormalDebuff" ? "−" : "+") + (LAB[k] || k);
    }
    if (meta.stack) return meta.type === "Debuff" ? "Mark" : "Stack";
    return meta.type === "Debuff" ? "Debuff" : meta.type === "Buff" ? "Buff" : "Effect";
  }

  /* ---------- entities ---------- */
  function makeEntity(f, side, idx, pos) {
    var s = sheetOf(f);
    s.slevel = f.level || 1;
    function bind(list) {
      return list.map(function (t) { var sk = SKILL[t.id]; return sk ? { sk: sk, rank: t.rank || 1, level: t.level || 1, id: sk.id, name: sk.name } : null; });
    }
    var techs = bind(f.techs || []), charms = bind(f.charms || []);
    while (techs.length < 4) techs.push(null);
    while (charms.length < 4) charms.push(null);
    s.skillRanks = techs.concat(charms).filter(Boolean).map(function (t) { return t.rank; });
    return { i: idx, side: side, name: f.name, cls: f.cls, f: f, s: s, techs: techs, charms: charms,
             hp: s.hp, shield: 0, st: [], cd: openingCds(techs, charms), uses: techs.map(function () { return 0; }),
             t: interval(s), turns: 0, pos: { x: pos.x, y: pos.y }, alive: true, charmFired: {}, techCasts: 0, order: idx, taunt: null };
  }

  /* ---------- one fight ---------- */
  function oneFight(fighters, positions, rng, wantLog, maxRounds, gov) {
    var GOV = gov || 1;
    var ents = fighters.map(function (f, i) { return makeEntity(f, i < 4 ? 0 : 1, i, positions[i]); });
    var log = [], turns = 0, MAXT = 2400, capped = false, events = null;
    function alive(side) { return ents.filter(function (u) { return u.alive && (side === undefined || u.side === side); }); }
    function enemiesOf(u) { return alive(1 - u.side); }
    function alliesOf(u) { return alive(u.side); }

    function applyStatus(tgt, sid, creator, rank, level, lent) {
      var meta = DATA.statuses[String(sid)];
      if (!meta || meta.falloff || meta.dur === 0) return null;
      var have = tgt.st.filter(function (x) { return x.id === sid; })[0];
      if (have) {
        if (meta.stack) have.stacks = Math.min(have.stacks + 1, meta.maxStack > 0 ? meta.maxStack : 99);
        have.dur = meta.dur; have.rank = rank; have.level = level;
        return have;
      }
      var st = { id: sid, meta: meta, dur: meta.dur, creator: creator.i, rank: rank, level: level, stacks: 1, props: lent || null };
      tgt.st.push(st);
      return st;
    }
    function removeStatus(holder, st) {
      var i = holder.st.indexOf(st);
      if (i >= 0) holder.st.splice(i, 1);
      if (st.meta.shield && !holder.st.some(function (x) { return x.meta.shield; })) holder.shield = 0;
    }
    function kill(u) {
      if (u.hp > 0 || !u.alive) return;
      u.alive = false; u.hp = 0; u.st = []; u.shield = 0;
      if (events) events.push({ kind: "down", who: u.i });
    }

    /* a trigger skill (poison tick, expiry heal, charm proc) from src onto tgt */
    function fireSkill(skillId, src, tgt, tag, rank, level) {
      var entry = DATA.trig[String(skillId)];
      if (!entry || !tgt || !tgt.alive) return;
      var rows = (entry.r || {})[String(rank)] || {};
      var srcE = eff(src, ents), tgtE = eff(tgt, ents);
      var fake = { id: skillId, name: entry.name, ele: (entry.ec && entry.ec.ele) || "None", ec: entry.ec, hits: 1, r: entry.r || {}, pvp: entry.pvp || 10000 };
      var parts = hitParts(srcE, tgtE, fake, rows, level);
      if (parts.heal) {
        var before = tgt.hp;
        tgt.hp = Math.min(tgt.s.hp, tgt.hp + parts.heal * GOV);
        if (events) events.push({ kind: "heal", who: tgt.i, amount: tgt.hp - before, tag: tag });
        return;
      }
      var total = landHits(parts, src, tgt, srcE, tgtE, fake, null, rank, level);
      if (events && total > 0) events.push({ kind: "dmg", who: tgt.i, amount: total, tag: tag });
      parts.hits.forEach(function (h) {
        h.on.forEach(function (o) {
          var meta = DATA.statuses[String(o.status)];
          if (!meta || meta.falloff) return;
          var target = (o.target === "DamageTarget") ? tgt : src;
          if (rng() < landChance(o.chance, o.byProp, meta.type, srcE, tgtE)) {
            var st = applyStatus(target, o.status, src, rank, level);
            if (st && meta.shield) { var amt = shieldSize(meta, src, target, rank, level) * GOV; if (amt > 0) target.shield = Math.max(target.shield, amt); }
            if (st && events) events.push({ kind: "status", who: target.i, name: statusName(meta) });
          }
        });
      });
      kill(tgt);
    }
    function charmStrike(ch, holder, tgt) {
      var hE = eff(holder, ents), tE = eff(tgt, ents);
      var rows = (ch.sk.r || {})[String(ch.rank)] || {};
      var fake = { id: ch.id, name: ch.name, ele: ch.sk.ele || "Physical", hits: 1, r: ch.sk.r || {}, pvp: ch.sk.pvp || 10000 };
      var parts = hitParts(hE, tE, fake, rows, ch.level);
      if (parts.heal) {
        var before = holder.hp; holder.hp = Math.min(holder.s.hp, holder.hp + parts.heal * GOV);
        if (events) events.push({ kind: "heal", who: holder.i, amount: holder.hp - before, tag: ch.name });
        return;
      }
      var total = landHits(parts, holder, tgt, hE, tE, fake, null, ch.rank, ch.level);
      if (events && total > 0) events.push({ kind: "dmg", who: tgt.i, amount: total, tag: ch.name });
      kill(tgt);
    }
    function firePassive(pv, ch, holder, enemy, trig) {
      var key = ch.id + ":" + pv.kind + ":" + pv.status;
      if (pv.maxCount > 0 && (holder.charmFired[key] || 0) >= pv.maxCount) return false;
      holder.charmFired[key] = (holder.charmFired[key] || 0) + 1;
      function pick(t) {
        if (t === "Enemy") return enemy || nearest(holder, enemiesOf(holder));
        if (t === "TriggerSource" || t === "TriggerTarget") return trig || holder;
        return holder;
      }
      (pv.triggers || []).forEach(function (t) {
        if (rng() < pv.rate * t.chance) fireSkill(t.skill, holder, pick(t.target), ch.name, ch.rank, ch.level);
      });
      (pv.statuses || []).forEach(function (o) {
        var meta = DATA.statuses[String(o.status)]; if (!meta) return;
        if (rng() >= pv.rate * (o.chance === undefined ? 1 : o.chance)) return;
        var tgt = pick(o.target);
        if (!tgt || !tgt.alive) return;
        var lent = (meta.props || (pv.stackTrigger && pv.stackTrigger.status === o.status)) ? null : (ch.sk.props || null);
        var st = applyStatus(tgt, o.status, holder, ch.rank, ch.level, lent);
        if (!st) return;
        if (meta.shield) { var amt = shieldSize(meta, holder, tgt, ch.rank, ch.level) * GOV; if (amt > 0) tgt.shield = Math.max(tgt.shield, amt); }
        if (events) events.push({ kind: "status", who: tgt.i, name: statusName(meta, lent) + (st.stacks > 1 ? " ×" + st.stacks : ""), tag: ch.name });
        if (pv.stackTrigger && pv.stackTrigger.status === o.status && st.stacks >= pv.stackTrigger.count) {
          st.stacks -= pv.stackTrigger.count;
          if (st.stacks <= 0) removeStatus(tgt, st);
          charmStrike(ch, holder, tgt);
        }
      });
      return true;
    }
    function procs(holder, kind, enemy, trig, filter) {
      if (!holder.alive) return;
      holder.charms.forEach(function (ch) {
        (ch && ch.sk.passive || []).forEach(function (pv) {
          if (pv.kind !== kind) return;
          if (filter && !filter(pv)) return;
          firePassive(pv, ch, holder, enemy, trig);
        });
      });
    }
    function deathSave(who) {
      var out = null;
      who.charms.forEach(function (ch) {
        (ch && ch.sk.passive || []).forEach(function (pv) {
          if (out || pv.kind !== "deathSave") return;
          var key = ch.id + ":saved:" + pv.status;
          if ((who.charmFired[key] || 0) >= (pv.maxCount > 0 ? pv.maxCount : 1)) return;
          who.charmFired[key] = (who.charmFired[key] || 0) + 1;
          out = { limit: pv.limit || 1, ch: ch, pv: pv, heal: 0 };
          var row = ch.sk.props && ch.sk.props[String(ch.rank)];
          if (row) {
            if (row.SkillCureByHp) out.heal += curveValue(row.SkillCureByHp, ch.rank, ch.level, who.s.rank.name) / 100 * who.s.hp;
            if (row.SkillFixedCure) out.heal += curveValue(row.SkillFixedCure, ch.rank, ch.level, who.s.rank.name);
            out.heal *= GOV;
          }
        });
      });
      return out;
    }
    function afterDamage(who, from) {
      who.charms.forEach(function (ch) {
        (ch && ch.sk.passive || []).forEach(function (pv) {
          if (pv.kind === "hpUnit") {
            var key = ch.id + ":units:" + pv.status;
            var units = Math.floor((1 - who.hp / who.s.hp) / pv.unit + 1e-9);
            if (pv.maxCount > 0) units = Math.min(units, pv.maxCount);
            while ((who.charmFired[key] || 0) < units) {
              who.charmFired[key] = (who.charmFired[key] || 0) + 1;
              firePassive(pv, ch, who, from, from);
            }
          } else if (pv.kind === "hpBelow") {
            var k2 = ch.id + ":below:" + pv.status;
            if (who.hp < pv.pct * who.s.hp) {
              if (!who.charmFired[k2]) { who.charmFired[k2] = 1; firePassive(pv, ch, who, from, from); }
            } else who.charmFired[k2] = 0;
          }
        });
      });
    }

    function landHits(parts, me, foe, meE, foeE, pick, rolled, rank, level) {
      var p = critChance(meE, foeE), m = critMult(meE, foeE);
      var b = blockChance(meE, foeE), bd = blockDiv(foeE);
      var total = 0, fallCount = 0;
      var blind = me.st.filter(function (x) { return x.meta.action === "Blinding"; })[0];
      parts.hits.forEach(function (h, hi) {
        if (!foe.alive || !(h.d > 0)) return;   /* a status-only hit has nothing to roll */
        var d = h.d * GOV, crit = false, block = false, absorbed = 0, blinded = false;
        var fo = null;
        h.on.forEach(function (o) { var mt = DATA.statuses[String(o.status)]; if (mt && mt.falloff) fo = mt.falloff; });
        if (fo) {
          var steps = Math.max(0, fallCount - (fo.start - 1));
          if (fo.max > 0) steps = Math.min(steps, fo.max);
          d *= Math.pow(1 - fo.pct, steps);
          fallCount++;
        }
        if (blind && pick.ec && pick.ec.skillType === "Attack") { d = 0; blinded = true; }
        else if (rng() < b) { d /= bd; block = true; }
        else if (rng() < p) { d *= m; crit = true; }
        if (foe.shield > 0 && !h.ignoreShield && d > 0) {
          absorbed = Math.min(foe.shield, d); foe.shield -= absorbed; d -= absorbed;
          if (foe.shield <= 0) foe.st.filter(function (x) { return x.meta.shield; }).forEach(function (x) { removeStatus(foe, x); });
        }
        var saved = null;
        if (d > 0 && d >= foe.hp) { saved = deathSave(foe); if (saved) d = Math.max(0, foe.hp - saved.limit); }
        foe.hp -= d; total += d;
        if (rolled) rolled.push({ d: d, crit: crit, block: block, absorbed: absorbed, blinded: blinded, at: h.at || 0, saved: !!saved, who: foe.i, hi: hi });
        if (saved) {
          if (events) events.push({ kind: "save", who: foe.i, tag: saved.ch.name });
          if (saved.heal > 0) {
            var b0 = foe.hp; foe.hp = Math.min(foe.s.hp, foe.hp + saved.heal);
            if (events) events.push({ kind: "heal", who: foe.i, amount: foe.hp - b0, tag: saved.ch.name });
          }
          firePassive(saved.pv, saved.ch, foe, me, me);
        } else if (d > 0) afterDamage(foe, me);
      });
      return total;
    }
    function tickEnd(me) {
      me.st.slice().forEach(function (st) {
        if (st.dur > 0) {
          st.dur--;
          if (st.dur === 0) {
            (st.meta.onEnd || []).forEach(function (t) {
              var src = t.source === "Creator" ? ents[st.creator] : me;
              var tgt = t.target === "Creator" ? ents[st.creator] : me;
              if (rng() < (t.byProp ? landChance(t.chance, true, null, eff(src, ents), eff(tgt, ents)) : t.chance))
                fireSkill(t.skill, src, tgt, statusName(st.meta, st.props) + " ends", st.rank, st.level);
            });
            removeStatus(me, st);
          }
        }
      });
    }

    /* ---------- the spatial layer ----------
       Skill.range: offsets from the caster where the aim point may go (prefab, near to far).
       Hit.cells: offsets from the hit centre (the aim point, or the caster's cell when onSource),
       authored facing Up and turned to face the aim (Pos2d.LookDirection + CalcLocalToWorldDir). */
    function facing(from, to) {
      var dx = to.x - from.x, dy = to.y - from.y;
      if (!dx && !dy) return "U";
      return Math.abs(dy) >= Math.abs(dx) ? (dy > 0 ? "U" : "D") : (dx > 0 ? "R" : "L");
    }
    function turn(c, dir, flip) {
      var x = flip ? -c[0] : c[0], y = c[1];
      if (dir === "U") return [x, y];
      if (dir === "D") return [-x, -y];
      if (dir === "L") return [-y, x];
      return [y, -x];
    }
    function unitAt() { var m = {}; ents.forEach(function (u) { m[u.pos.x + "," + u.pos.y] = u; }); return m; }
    function isAlly(sk) { var t = (sk.ec || {}).target; return t === "Me" || t === "Friend" || t === "FriendNotMe" || t === "Ally" || t === "Self"; }
    /* the best (aim, targets) for a skill cast from `pos`, or null */
    function plan(me, sk, pos, occ) {
      var ec = sk.ec || {};
      var selfish = isAlly(sk);
      var pool = selfish ? alliesOf(me) : enemiesOf(me);
      if (ec.target === "FriendNotMe") pool = pool.filter(function (u) { return u !== me; });
      if (!pool.length) return null;
      var range = (ec.range && ec.range.length) ? ec.range : [[0, 0]];
      var hits = (ec.hits && ec.hits.length) ? ec.hits : [{ cells: [[0, 0]], onSource: false }];
      var taunt = me.taunt && !selfish ? me.taunt : null;
      var best = null;
      if (sk._reach === undefined) {          /* the farthest any area cell sits from its centre */
        var far = 0; hits.forEach(function (h) { (h.cells || [[0, 0]]).forEach(function (c) { far = Math.max(far, Math.abs(c[0]) + Math.abs(c[1])); }); });
        sk._reach = far;
      }
      var anySrc = hits.some(function (h) { return h.onSource; }), allSrc = hits.every(function (h) { return h.onSource; });
      if (anySrc && !pool.some(function (u) { return dist(u.pos, pos) <= sk._reach; }) && allSrc) return null;
      for (var ri = 0; ri < range.length; ri++) {
        var ax = pos.x + range[ri][0], ay = pos.y + range[ri][1];
        if (ax < 0 || ay < 0 || ax >= GRID.w || ay >= GRID.h) continue;
        var aim = { x: ax, y: ay };
        if (!anySrc) { var near = false; for (var pi = 0; pi < pool.length; pi++) if (Math.abs(pool[pi].pos.x - ax) + Math.abs(pool[pi].pos.y - ay) <= sk._reach) { near = true; break; } if (!near) continue; }
        var dir = (ax === pos.x && ay === pos.y) ? facing(pos, (taunt || nearest(me, pool) || me).pos) : facing(pos, aim);
        var flip = ax < pos.x;
        var perHit = [], seen = {}, union = [];
        for (var hi = 0; hi < hits.length; hi++) {
          var h = hits[hi], centre = h.onSource ? pos : aim, list = [];
          var cells = (h.cells && h.cells.length) ? h.cells : [[0, 0]];
          for (var ci = 0; ci < cells.length; ci++) {
            var w = turn(cells[ci], dir, flip);
            var u = occ[(centre.x + w[0]) + "," + (centre.y + w[1])];
            if (u && u.alive && pool.indexOf(u) >= 0 && list.indexOf(u) < 0) { list.push(u); if (!seen[u.i]) { seen[u.i] = 1; union.push(u); } }
          }
          perHit.push(list);
        }
        if (!union.length) continue;
        if (taunt && union.indexOf(taunt) < 0) continue;          /* under Ridicule every attack goes at the taunter */
        var lowest = Math.min.apply(null, union.map(function (u) { return u.hp / u.s.hp; }));
        var score = [union.length, -lowest, -dist(pos, aim)];
        if (!best || better(score, best.score)) best = { aim: aim, dir: dir, perHit: perHit, union: union, score: score, primary: union.slice().sort(function (a, b) { return a.hp / a.s.hp - b.hp / b.s.hp; })[0] };
      }
      return best;
    }
    function better(a, b) { for (var i = 0; i < a.length; i++) { if (a[i] > b[i]) return true; if (a[i] < b[i]) return false; } return false; }
    /* every cell reachable in up to `steps` 4-way moves through free cells; living and fallen bodies block */
    function reachable(me, steps) {
      var occ = unitAt(), out = {}, key = me.pos.x + "," + me.pos.y;
      out[key] = { x: me.pos.x, y: me.pos.y, d: 0, from: null };
      var frontier = [out[key]];
      while (frontier.length) {
        var c = frontier.shift();
        if (c.d >= steps) continue;
        [[1, 0], [-1, 0], [0, 1], [0, -1]].forEach(function (d) {
          var nx = c.x + d[0], ny = c.y + d[1], k = nx + "," + ny;
          if (!inGrid(nx, ny) || out[k]) return;
          var u = occ[k];
          if (u && u !== me) return;                    /* players and their corpses both block (DestroyOnDie = false) */
          out[k] = { x: nx, y: ny, d: c.d + 1, from: c };
          frontier.push(out[k]);
        });
      }
      return out;
    }
    /* the plan for `sk`: from where the fighter stands if anything is in reach, else from the nearest cell it
       can walk to that puts something in reach (ShorterMoveDist), the most targets among cells at that distance */
    function planWithMove(me, sk, reach, occ) {
      var here = reach[me.pos.x + "," + me.pos.y];
      var p0 = plan(me, sk, me.pos, occ);
      if (p0) return { plan: p0, cell: here, score: p0.score };
      var cells = Object.keys(reach).map(function (k) { return reach[k]; }).filter(function (c) { return c.d > 0; }).sort(function (a, b) { return a.d - b.d; });
      var best = null, occ2 = {};
      Object.keys(occ).forEach(function (x) { occ2[x] = occ[x]; });
      delete occ2[me.pos.x + "," + me.pos.y];
      for (var i = 0; i < cells.length; i++) {
        var c = cells[i];
        if (best && c.d > best.cell.d) break;
        var k = c.x + "," + c.y;
        occ2[k] = me;
        var p = plan(me, sk, c, occ2);
        delete occ2[k];
        if (p && (!best || better(p.score, best.plan.score))) best = { plan: p, cell: c, score: p.score };
      }
      return best;
    }
    function walkTo(me, cell) {
      var path = [];
      for (var c = cell; c; c = c.from) path.unshift([c.x, c.y]);
      me.pos = { x: cell.x, y: cell.y };
      return path.length - 1;
    }
    /* no cast possible anywhere in reach: walk toward the nearest enemy (or the taunter) as far as allowed */
    function approach(me, reach) {
      var goal = me.taunt || nearest(me, enemiesOf(me));
      if (!goal) return 0;
      var best = null, bd = dist(me.pos, goal.pos);
      Object.keys(reach).forEach(function (k) { var c = reach[k]; var d = dist(c, goal.pos); if (d < bd || (d === bd && best && c.d < best.d)) { bd = d; best = c; } });
      return best ? walkTo(me, best) : 0;
    }
    function nearest(u, list) {
      var best = null, bd = 1e9;
      list.forEach(function (v) { var d = dist(u.pos, v.pos); if (d < bd) { bd = d; best = v; } });
      return best;
    }
    function lowestHp(list) { return list.slice().sort(function (a, b) { return a.hp / a.s.hp - b.hp / b.s.hp; })[0]; }

    var winner = -1, order = 0, rounds = 0;
    while (turns < MAXT) {
      var A = alive(0), B = alive(1);
      if (!A.length || !B.length) { winner = A.length ? 0 : 1; break; }
      if (maxRounds > 0 && rounds >= maxRounds) { capped = true; break; }
      /* the SPD clock: earliest NextTime acts; equal times keep queue order (FIFO) */
      var me = null;
      A.concat(B).forEach(function (u) { if (!me || u.t < me.t - 1e-9 || (Math.abs(u.t - me.t) < 1e-9 && u.order < me.order)) me = u; });
      turns++; me.turns++; rounds++; me.order = ++order;
      events = wantLog ? [] : null;
      var moved = 0;
      me.taunt = null;
      me.st.forEach(function (x) { if (x.meta.action === "Ridicule" && ents[x.creator].alive && ents[x.creator].side !== me.side) me.taunt = ents[x.creator]; });

      me.st.slice().forEach(function (st) {
        (st.meta.roundStart || []).forEach(function (t) {
          var src = t.source === "Creator" ? ents[st.creator] : me;
          var tgt = t.target === "Creator" ? ents[st.creator] : me;
          if (rng() < t.chance) fireSkill(t.skill, src, tgt, statusName(st.meta, st.props), st.rank, st.level);
        });
      });
      procs(me, "roundStart", null, me);
      if (!me.alive) { if (wantLog) log.push(entry(me, null, -1, [], 0, events, "start", 0, moved)); continue; }

      var skip = me.st.filter(function (x) { return SKIP_ACTIONS[x.meta.action]; })[0];
      var frozenCd = me.st.some(function (x) { return x.meta.cdFreeze; });
      if (!frozenCd) for (var c = 0; c < me.cd.length; c++) if (me.cd[c] > 0) me.cd[c]--;

      function cast(t, slot, pl) {
        var pick = t.sk, rolled = [], total = 0;
        var isAttack = !pick.ec || pick.ec.skillType === "Attack" || pick.id === 0;
        var selfish = isAlly(pick);
        if (slot >= 0) procs(me, "skillStart", pl.primary, pl.primary);
        var meE = eff(me, ents);
        var rows = pick.id === 0 ? {} : (pick.r[String(t.rank)] || {});
        var hitsCfg = (pick.ec && pick.ec.hits && pick.ec.hits.length) ? pick.ec.hits : null;
        pl.union.forEach(function (foe) {
          if (!foe.alive) return;
          var foeE = eff(foe, ents);
          var parts = hitParts(meE, foeE, pick, rows, t.level);
          if (parts.heal) {
            var before = foe.hp; foe.hp = Math.min(foe.s.hp, foe.hp + parts.heal * GOV);
            if (events) events.push({ kind: "heal", who: foe.i, amount: foe.hp - before, tag: pick.name });
          }
          /* only the hits whose area covers this target land on it */
          var mine = [];
          parts.hits.forEach(function (h, hi) { var lst = pl.perHit[hitsCfg ? hi : 0]; if (!lst || lst.indexOf(foe) >= 0) mine.push({ h: h, hi: hi }); });
          var here = 0, r0 = [];
          if (mine.length && !selfish) { here = landHits({ hits: mine.map(function (m) { return m.h; }) }, me, foe, meE, foeE, pick, r0, t.rank, t.level); rolled = rolled.concat(r0); total += here; }
          mine.forEach(function (m, k) {
            if (r0.some(function (x) { return x.hi === k && x.blinded; })) return;
            m.h.on.forEach(function (o) {
              var meta = DATA.statuses[String(o.status)];
              if (!meta || meta.falloff) return;
              var tgt = (o.target === "DamageTarget" || selfish) ? foe : me;
              if (!tgt.alive) return;
              var chance = landChance(o.chance, o.byProp, meta.type, meE, foeE);
              tgt.st.forEach(function (x) {
                var bo = x.meta.boosts;
                if (bo && bo.actions.indexOf(meta.action) >= 0 && x.meta.props) {
                  var r = x.meta.props[String(x.rank)] || {};
                  if (r[bo.prop]) chance += curveValue(r[bo.prop], x.rank, x.level, ents[x.creator].s.rank.name) / 100;
                }
              });
              if (rng() < chance) {
                var st = applyStatus(tgt, o.status, me, t.rank, t.level);
                if (st && meta.shield) { var amt = shieldSize(meta, me, tgt, t.rank, t.level) * GOV; if (amt > 0) tgt.shield = Math.max(tgt.shield, amt); }
                if (st && events) events.push({ kind: "status", who: tgt.i, name: statusName(meta) });
              }
            });
          });
          if (here > 0) { procs(me, "hit", foe, foe, function (pv) { return !(pv.onlyAttack && !isAttack); }); procs(foe, "damaged", me, me); }
          kill(foe);
        });
        var bl = me.st.filter(function (x) { return x.meta.action === "Blinding"; })[0];
        if (bl && isAttack) removeStatus(me, bl);
        if (slot >= 0) {
          me.cd[slot] = cdOf(t) + 1; me.uses[slot]++; me.techCasts++;
          procs(me, "skillEnd", pl.primary, pl.primary, function (pv) { return me.techCasts % pv.every === 0; });
        }
        return { rolled: rolled, total: total, targets: pl.union.map(function (u) { return u.i; }), aim: [pl.aim.x, pl.aim.y] };
      }

      var casts = 0, sub = 0;
      if (skip) {
        if (wantLog) log.push(entry(me, null, -1, [], 0, events, skip.meta.action, 0, moved));
      } else {
        var reach = reachable(me, me.s.move || GRID.defaultMove), occ = unitAt();
        for (var k = 0; k < me.techs.length && me.alive; k++) {
          var cand = me.techs[k];
          if (!cand || me.cd[k] !== 0) continue;
          if (!enemiesOf(me).length) break;
          var lim = cand.sk.ec ? cand.sk.ec.limitedTimes : -1;
          if (lim > 0 && me.uses[k] >= lim) continue;
          var pl;
          if (moved) pl = plan(me, cand.sk, me.pos, occ);
          else {
            var pm = planWithMove(me, cand.sk, reach, occ);
            if (pm && pm.cell.d > 0) {
              /* out of reach where it stands: move up to MoveDist, then cast (IsReleaseSkillAfterMove) */
              moved = walkTo(me, pm.cell); occ = unitAt();
              if (events) events.push({ kind: "move", who: me.i, to: [me.pos.x, me.pos.y] });
            }
            pl = pm ? pm.plan : null;
          }
          if (!pl) continue;
          if (redundant(cand.sk, me, pl.primary)) continue;
          events = wantLog ? [] : null;
          var r = cast(cand, k, pl);
          casts++;
          if (wantLog) log.push(entry(me, cand.sk, k, r.rolled, r.total, events, null, sub++, moved, r.targets));
        }
        if (casts === 0 && me.alive && enemiesOf(me).length) {
          events = wantLog ? [] : null;
          var pb = moved ? plan(me, BASIC, me.pos, occ) : null;
          if (!moved) {
            var pmb = planWithMove(me, BASIC, reach, occ);
            if (pmb) { if (pmb.cell.d > 0) { moved = walkTo(me, pmb.cell); occ = unitAt(); if (events) events.push({ kind: "move", who: me.i, to: [me.pos.x, me.pos.y] }); } pb = pmb.plan; }
            else { moved = approach(me, reach); if (moved && events) events.push({ kind: "move", who: me.i, to: [me.pos.x, me.pos.y] }); }
          }
          if (pb) {
            var rb = cast({ sk: BASIC, rank: 1, level: 1, id: 0, name: BASIC.name }, -1, pb);
            procs(me, "roundCheck", pb.primary, me);
            if (wantLog) log.push(entry(me, BASIC, -1, rb.rolled, rb.total, events, null, 0, moved, rb.targets));
          } else if (wantLog) log.push(entry(me, null, -1, [], 0, events, "moved", 0, moved));
        }
      }
      procs(me, "roundEnd", null, me);
      tickEnd(me);
      me.t += interval(eff(me, ents));
    }
    if (winner < 0 && turns >= MAXT) capped = true;
    function entry(me, pick, slot, rolled, total, ev, note, sub, moved, targets) {
      return { t: Math.round(me.t), who: me.i, side: me.side, slot: slot, sub: sub || 0,
               skill: pick ? pick.name : (note === "start" ? "—" : note === "moved" ? "moved, no one in reach" : note + " — no action"),
               skillId: pick ? pick.id : 0, ele: pick ? pick.ele : "None", hits: rolled, dmg: total, targets: targets || [],
               dur: pick && pick.ec && pick.ec.dur ? pick.ec.dur : 0.8, events: ev || [], turn: me.turns, note: note, moved: moved || 0,
               hp: ents.map(function (u) { return Math.max(0, u.hp); }), sh: ents.map(function (u) { return Math.round(u.shield); }),
               pos: ents.map(function (u) { return [u.pos.x, u.pos.y]; }),
               st: ents.map(function (u) { return u.st.map(function (x) { return { n: statusName(x.meta, x.props), d: x.dur, s: x.stacks, t: x.meta.type }; }); }) };
    }
    var hpLeft = ents.map(function (u) { return Math.max(0, u.hp); });
    if (winner < 0) {
      var ra = alive(0).reduce(function (a, u) { return a + u.hp / u.s.hp; }, 0), rb = alive(1).reduce(function (a, u) { return a + u.hp / u.s.hp; }, 0);
      winner = ra === rb ? -1 : (ra > rb ? 0 : 1);
    }
    return { winner: winner, capped: capped, turns: turns, log: log, hp: hpLeft, alive: ents.map(function (u) { return u.alive; }) };
  }

  function mulberry(seed) {
    return function () {
      seed |= 0; seed = seed + 0x6D2B79F5 | 0;
      var t = Math.imul(seed ^ seed >>> 15, 1 | seed);
      t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
      return ((t ^ t >>> 14) >>> 0) / 4294967296;
    };
  }
  function fmt(v) { return Math.round(v).toLocaleString("en-US"); }
  function short(v) { return v >= 1e6 ? (v / 1e6).toFixed(2) + "M" : v >= 1e3 ? Math.round(v / 1e3) + "K" : fmt(v); }

  /* ---------- state: leaderboard, teams, positions ---------- */
  var ROSTER = [];                 /* every fightable player, leaderboard order */
  var TEAM = [[null, null, null, null], [null, null, null, null]];
  var POS = [];                    /* positions by team slot index 0..7 */
  var RESULT = null, PLAY = null, TIMERS = [];
  var PICK = null;                 /* tapped leaderboard row (fighter id) awaiting a slot */

  function byId(id) { return ROSTER.filter(function (f) { return f.id === id; })[0] || null; }
  function defaultPositions() {
    POS = [];
    for (var i = 0; i < 8; i++) { var z = GRID.start[i < 4 ? 0 : 1][i % 4]; POS.push({ x: z[0], y: z[1] }); }
  }
  function saveState() {
    try { localStorage.setItem("pw_team", JSON.stringify({ t: TEAM.map(function (t) { return t.map(function (f) { return f ? f.id : null; }); }), p: POS })); } catch (e) {}
  }
  function loadState() {
    try {
      var st = JSON.parse(localStorage.getItem("pw_team") || "null");
      if (!st || !st.t || !st.p || st.p.length !== 8) return false;
      TEAM = st.t.map(function (ids) { return ids.map(byId); });
      POS = st.p.map(function (p, i) { return inZone(i < 4 ? 0 : 1, p.x, p.y) ? p : { x: GRID.start[i < 4 ? 0 : 1][i % 4][0], y: GRID.start[i < 4 ? 0 : 1][i % 4][1] }; });
      return true;
    } catch (e) { return false; }
  }
  function fightersFlat() { return TEAM[0].concat(TEAM[1]); }
  function ready() { return fightersFlat().every(Boolean); }
  function slotOf(id) { var k = -1; fightersFlat().forEach(function (f, i) { if (f && f.id === id) k = i; }); return k; }
  function freeCell(side, avoid) {
    var taken = {};
    POS.forEach(function (p, i) { if (i !== avoid && fightersFlat()[i]) taken[p.x + "," + p.y] = true; });
    var starts = GRID.start[side];
    for (var k = 0; k < starts.length; k++) if (!taken[starts[k][0] + "," + starts[k][1]]) return { x: starts[k][0], y: starts[k][1] };
    var z = GRID.zones[side];
    for (var y = z.y0; y <= z.y1; y++) for (var x = z.x0; x <= z.x1; x++) if (!taken[x + "," + y]) return { x: x, y: y };
    return { x: starts[0][0], y: starts[0][1] };
  }
  /* put fighter id into team slot i (0..7); the fighter leaves any slot it held */
  function assign(i, id) {
    var f = byId(id);
    if (!f) return;
    var was = slotOf(id);
    var side = i < 4 ? 0 : 1, prev = fightersFlat()[i];
    if (was >= 0 && was !== i) {
      TEAM[was < 4 ? 0 : 1][was % 4] = prev || null;             /* swap with whatever sat in the target slot */
      if (prev) POS[was] = inZone(was < 4 ? 0 : 1, POS[was].x, POS[was].y) ? POS[was] : freeCell(was < 4 ? 0 : 1, was);
    }
    TEAM[side][i % 4] = f;
    if (!inZone(side, POS[i].x, POS[i].y) || POS.some(function (p, k) { return k !== i && fightersFlat()[k] && p.x === POS[i].x && p.y === POS[i].y; })) POS[i] = freeCell(side, i);
    PICK = null; saveState(); invalidate();
  }
  function unassign(i) { TEAM[i < 4 ? 0 : 1][i % 4] = null; saveState(); invalidate(); }

  /* ---------- board ---------- */
  var DRAG = null;   /* {kind:"token", i} or {kind:"lb", id} */
  function playing() { return !!(PLAY && PLAY.playing); }   /* edits are blocked only while a fight is being played back */
  function drawBoard() {
    var b = $("board"), v = GRID.view;
    b.style.gridTemplateColumns = "repeat(" + (v.x1 - v.x0 + 1) + ", 1fr)";
    var h = "";
    for (var y = v.y1; y >= v.y0; y--) for (var x = v.x0; x <= v.x1; x++) {
      var cls = inZone(0, x, y) ? " z0" : inZone(1, x, y) ? " z1" : " out";
      if (BLOCKED[x + "," + y]) cls += " blk";
      h += '<div class="cell' + cls + '" data-x="' + x + '" data-y="' + y + '" title="column ' + (x + 1) + ", row " + (y + 1) + '"></div>';
    }
    b.innerHTML = h;
    placeTokens(null);
  }
  function tokenHtml(f, i, cur) {
    var side = i < 4 ? 0 : 1;
    var hp = cur ? cur.hp[i] : f.sheet.hp, pct = Math.max(0, Math.min(1, hp / f.sheet.hp));
    var dead = cur && !cur.alive[i];
    return '<div class="token s' + side + (dead ? " down" : "") + '" draggable="' + (cur ? "false" : "true") + '" data-i="' + i + '" title="' + esc(f.name) + '">' +
      '<span class="tname">' + esc(f.name) + '</span><span class="tcls">' + esc(f.cls) + '</span>' +
      '<span class="thp"><i style="width:' + (pct * 100).toFixed(1) + '%"></i></span></div>';
  }
  function placeTokens(cur) {
    document.querySelectorAll("#board .cell").forEach(function (c) { c.innerHTML = ""; });
    fightersFlat().forEach(function (f, i) {
      if (!f) return;
      var p = cur ? { x: cur.pos[i][0], y: cur.pos[i][1] } : POS[i];
      var cell = document.querySelector('#board .cell[data-x="' + p.x + '"][data-y="' + p.y + '"]');
      if (cell) cell.innerHTML = tokenHtml(f, i, cur);
    });
  }
  function moveToken(i, x, y) {
    var side = i < 4 ? 0 : 1;
    if (!inZone(side, x, y)) return false;
    var occ = -1;
    POS.forEach(function (p, k) { if (k !== i && p.x === x && p.y === y && fightersFlat()[k]) occ = k; });
    if (occ >= 0) { if ((occ < 4) !== (i < 4)) return false; POS[occ] = { x: POS[i].x, y: POS[i].y }; }
    POS[i] = { x: x, y: y };
    saveState(); placeTokens(null); invalidate();
    return true;
  }
  function boardEvents() {
    var b = $("board");
    b.addEventListener("dragstart", function (ev) {
      var t = ev.target.closest ? ev.target.closest(".token") : null;
      if (!t || playing()) { ev.preventDefault(); return; }
      DRAG = { kind: "token", i: parseInt(t.getAttribute("data-i"), 10) };
      ev.dataTransfer.setData("text/plain", "token:" + DRAG.i);
      ev.dataTransfer.effectAllowed = "move";
    });
    b.addEventListener("dragover", function (ev) {
      var c = ev.target.closest ? ev.target.closest(".cell") : null;
      if (!c || !DRAG) return;
      var x = +c.getAttribute("data-x"), y = +c.getAttribute("data-y");
      var side = DRAG.kind === "token" ? (DRAG.i < 4 ? 0 : 1) : (inZone(0, x, y) ? 0 : 1);
      if (inZone(side, x, y)) { ev.preventDefault(); c.classList.add("over"); }
    });
    b.addEventListener("dragleave", function (ev) { var c = ev.target.closest ? ev.target.closest(".cell") : null; if (c) c.classList.remove("over"); });
    b.addEventListener("drop", function (ev) {
      var c = ev.target.closest ? ev.target.closest(".cell") : null;
      if (!c || !DRAG) return;
      ev.preventDefault(); c.classList.remove("over");
      var x = +c.getAttribute("data-x"), y = +c.getAttribute("data-y");
      if (DRAG.kind === "token") moveToken(DRAG.i, x, y);
      else dropFromBoard(DRAG.id, x, y);
      DRAG = null;
    });
    b.addEventListener("click", function (ev) {
      if (playing()) return;
      var t = ev.target.closest ? ev.target.closest(".token") : null;
      var c = ev.target.closest ? ev.target.closest(".cell") : null;
      if (t) { PICK = { token: parseInt(t.getAttribute("data-i"), 10) }; paintPick(); return; }
      if (c && PICK) {
        var x = +c.getAttribute("data-x"), y = +c.getAttribute("data-y");
        if (PICK.token !== undefined) { moveToken(PICK.token, x, y); PICK = null; paintPick(); }
        else if (PICK.id !== undefined) { dropFromBoard(PICK.id, x, y); PICK = null; paintPick(); }
      }
    });
  }
  /* a leaderboard fighter dropped on a cell: join that side (first free slot) and stand there */
  function dropFromBoard(id, x, y) {
    if (!inZone(0, x, y) && !inZone(1, x, y)) return;
    var side = inZone(0, x, y) ? 0 : 1;
    var i = slotOf(id);
    if (i < 0 || (i < 4) !== (side === 0)) {
      var free = -1;
      TEAM[side].forEach(function (f, k) { if (!f && free < 0) free = k; });
      if (free < 0) free = 3;
      i = side * 4 + free;
      if (slotOf(id) >= 0) TEAM[slotOf(id) < 4 ? 0 : 1][slotOf(id) % 4] = null;
      TEAM[side][free] = byId(id);
    }
    if (!moveToken(i, x, y)) { POS[i] = freeCell(side, i); }
    saveState(); invalidate();
  }
  function paintPick() {
    document.querySelectorAll("#board .token").forEach(function (x) { x.classList.toggle("picked", !!(PICK && PICK.token === +x.getAttribute("data-i"))); });
    document.querySelectorAll("#lb .row").forEach(function (x) { x.classList.toggle("picked", !!(PICK && PICK.id === +x.getAttribute("data-id"))); });
  }

  /* ---------- team cards and the leaderboard ---------- */
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function iconOf(sk) { return sk ? '<img src="../assets/skills/skill_' + sk.id + '.png" alt="" loading="lazy">' : ""; }
  function cardHtml(f, i) {
    var side = i < 4 ? 0 : 1;
    if (!f) return '<div class="tslot" data-i="' + i + '">slot ' + (i % 4 + 1) + ' &mdash; drop a fighter</div>';
    var s = f.sheet;
    function sk(list) {
      return list.map(function (t) { var k = SKILL[t.id]; return k ? '<span class="sk" title="' + esc(k.name) + ' · rank ' + t.rank + ' · Lv ' + t.level + '">' + iconOf(k) + '<b>' + t.rank + '</b></span>' : ""; }).join("");
    }
    return '<div class="tcard s' + side + '" data-i="' + i + '" draggable="true">' +
      '<div class="thead"><span class="tname">' + esc(f.name) + '</span>' +
      '<span class="tmeta">' + esc(f.cls) + ' · Lv ' + f.level + ' · ' + esc((C.ranks[f.rank] || {}).name || "") + ' · ' + short(f.rating || 0) + ' CR</span>' +
      '<button type="button" class="tremove" data-i="' + i + '" title="Remove">&#10005;</button></div>' +
      '<div class="hpbar small"><div class="hpfill" id="hp' + i + '"></div><div class="shfill" id="sh' + i + '" hidden></div><span class="hptext" id="hpt' + i + '"></span></div>' +
      '<div class="statusrow" id="st' + i + '"></div>' +
      '<div class="tstats"><span>ATK ' + short(s.atk) + '</span><span>DEF ' + short(s.def) + '</span><span>HP ' + short(s.hp) + '</span><span>SPD ' + short(s.spd) + '</span>' +
      '<span>Crit ' + (s.cr * 100).toFixed(1) + '%</span><span>Block ' + (s.blockrate * 100).toFixed(0) + '%</span><span>Move ' + (s.move || GRID.defaultMove) + '</span></div>' +
      '<div class="tskills"><span class="lab">Techniques</span>' + sk(f.techs) + '</div>' +
      '<div class="tskills"><span class="lab">Charms</span>' + sk(f.charms) + '</div></div>';
  }
  function drawCards() {
    [0, 1].forEach(function (side) {
      $("team" + side).innerHTML = TEAM[side].map(function (f, k) { return cardHtml(f, side * 4 + k); }).join("");
    });
    fightersFlat().forEach(function (f, i) { if (f) hpSet(i, f.sheet.hp, f.sheet.hp, 0); });
    drawLb();
  }
  function drawLb() {
    var q = ($("lbfind").value || "").toLowerCase();
    var inTeam = {};
    fightersFlat().forEach(function (f) { if (f) inTeam[f.id] = true; });
    $("lb").innerHTML = ROSTER.filter(function (f) { return !q || f.name.toLowerCase().indexOf(q) >= 0 || f.cls.toLowerCase().indexOf(q) >= 0; })
      .map(function (f) {
        return '<div class="row' + (inTeam[f.id] ? " inteam" : "") + '" draggable="true" data-id="' + f.id + '">' +
          '<span class="pos">' + (f.rankPos ? "#" + f.rankPos : "") + '</span>' +
          '<span class="who"><b>' + esc(f.name) + '</b><span>' + esc(f.cls) + ' · Lv ' + f.level + '</span></span>' +
          '<span class="cr">' + short(f.rating || 0) + '</span></div>';
      }).join("") || '<div class="row"><span></span><span class="who">No captured players yet &mdash; load a roster export below.</span><span></span></div>';
    paintPick();
  }
  function teamEvents() {
    var side = $("arena");
    side.addEventListener("dragstart", function (ev) {
      var r = ev.target.closest ? ev.target.closest("#lb .row, .tcard") : null;
      if (!r || playing()) return;
      var id = r.classList.contains("row") ? parseInt(r.getAttribute("data-id"), 10) : (fightersFlat()[+r.getAttribute("data-i")] || {}).id;
      if (!id) { ev.preventDefault(); return; }
      DRAG = { kind: "lb", id: id };
      ev.dataTransfer.setData("text/plain", "lb:" + id);
      ev.dataTransfer.effectAllowed = "move";
    });
    side.addEventListener("dragover", function (ev) {
      var s = ev.target.closest ? ev.target.closest(".tslot, .tcard, .teamcol") : null;
      if (!s || !DRAG || DRAG.kind !== "lb") return;
      ev.preventDefault(); s.classList.add("over");
    });
    side.addEventListener("dragleave", function (ev) { var s = ev.target.closest ? ev.target.closest(".tslot, .tcard, .teamcol") : null; if (s) s.classList.remove("over"); });
    side.addEventListener("drop", function (ev) {
      var s = ev.target.closest ? ev.target.closest(".tslot, .tcard, .teamcol") : null;
      if (!s || !DRAG || DRAG.kind !== "lb") return;
      ev.preventDefault(); s.classList.remove("over");
      var i = s.hasAttribute("data-i") ? +s.getAttribute("data-i") : -1;
      if (i < 0) {                       /* dropped on the column: first free slot of that team */
        var sd = +s.getAttribute("data-side");
        TEAM[sd].forEach(function (f, k) { if (!f && i < 0) i = sd * 4 + k; });
        if (i < 0) i = sd * 4 + 3;
      }
      assign(i, DRAG.id); DRAG = null;
    });
    side.addEventListener("click", function (ev) {
      if (playing()) return;
      var rm = ev.target.closest ? ev.target.closest(".tremove") : null;
      if (rm) { unassign(+rm.getAttribute("data-i")); return; }
      var r = ev.target.closest ? ev.target.closest("#lb .row") : null;
      if (r) { var id = parseInt(r.getAttribute("data-id"), 10); PICK = (PICK && PICK.id === id) ? null : { id: id }; paintPick(); return; }
      var s = ev.target.closest ? ev.target.closest(".tslot, .tcard") : null;
      if (s && PICK && PICK.id !== undefined) { assign(+s.getAttribute("data-i"), PICK.id); }
    });
    $("lbfind").addEventListener("input", drawLb);
    $("fill").addEventListener("click", function () {
      var have = ROSTER.slice(0, 8);
      TEAM = [[null, null, null, null], [null, null, null, null]];
      have.forEach(function (f, k) { TEAM[k < 4 ? 0 : 1][k % 4] = f; });
      defaultPositions(); PICK = null; saveState(); invalidate();
    });
  }
  function hpSet(i, cur, max, shield) {
    var fill = $("hp" + i), t = $("hpt" + i), sh = $("sh" + i);
    if (!fill) return;
    var pct = Math.max(0, Math.min(1, cur / max));
    fill.style.width = (pct * 100).toFixed(1) + "%";
    fill.className = "hpfill" + (pct < 0.25 ? " low" : pct < 0.5 ? " mid" : "");
    t.textContent = short(cur) + " / " + short(max) + (shield > 0 ? " +" + short(shield) : "");
    sh.hidden = !(shield > 0);
    if (shield > 0) sh.style.width = Math.min(100, shield / max * 100).toFixed(1) + "%";
  }
  function chips(i, list) {
    var el = $("st" + i); if (!el) return;
    el.innerHTML = (list || []).map(function (s) { return '<span class="chip ' + (s.t === "Debuff" || s.t === "AbnormalDebuff" ? "bad" : "good") + '">' + esc(s.n) + (s.s > 1 ? " ×" + s.s : "") + (s.d > 0 ? " ·" + s.d : "") + '</span>'; }).join("");
  }

  /* ---------- running ---------- */
  function invalidate() {
    RESULT = null; stopPlayback();
    $("result").hidden = true; $("detail").hidden = true;
    $("play").disabled = true; $("step").disabled = true;
    $("run").disabled = !ready() || !DATA;
    $("combatlog").innerHTML = '<li class="empty">' + (ready() ? "Run the fight, then watch or step through it." : "Fill both teams to run a fight.") + '</li>';
    $("banner").hidden = true;
    placeTokens(null); drawCards();
  }
  function run() {
    if (!ready() || !DATA) return;
    var F = fightersFlat(), P = POS.map(function (p) { return { x: p.x, y: p.y }; });
    var maxRounds = Math.max(0, parseInt($("maxrounds").value, 10) || 0);
    var sheets = F.map(function (f) { var s = sheetOf(f); s.slevel = f.level; s.skillRanks = f.techs.concat(f.charms).map(function (t) { return t.rank; }); return s; });
    var gov = pvpGovernor(sheets);
    var N = 1000, wins = [0, 0, 0], turnsSum = 0, survive = F.map(function () { return 0; });
    var rng = mulberry(12345);
    for (var i = 0; i < N; i++) {
      var r = oneFight(F, P, rng, false, maxRounds, gov.scale);
      wins[r.winner < 0 ? 2 : r.winner]++;
      turnsSum += r.turns;
      r.alive.forEach(function (a, k) { if (a) survive[k]++; });
    }
    var sample = oneFight(F, P, mulberry(777), true, maxRounds, gov.scale);
    RESULT = { wins: wins, N: N, turns: turnsSum / N, survive: survive, sample: sample, gov: gov };
    showResult();
  }
  function showResult() {
    var R = RESULT, pa = R.wins[0] / R.N, pb = R.wins[1] / R.N;
    $("oddsa").style.width = (pa * 100).toFixed(1) + "%"; $("oddsa").textContent = SIDE_NAME[0] + " " + (pa * 100).toFixed(1) + "%";
    $("oddsb").style.width = (pb * 100).toFixed(1) + "%"; $("oddsb").textContent = SIDE_NAME[1] + " " + (pb * 100).toFixed(1) + "%";
    var F = fightersFlat();
    $("oddstext").innerHTML = "Over " + fmt(R.N) + " fights " + SIDE_NAME[0] + " wins <b>" + (pa * 100).toFixed(1) + "%</b>, " + SIDE_NAME[1] + " <b>" + (pb * 100).toFixed(1) + "%</b>" +
      (R.wins[2] ? ", " + (R.wins[2] / R.N * 100).toFixed(1) + "% undecided at the round cap" : "") + ". Average length " + R.turns.toFixed(1) + " actions. " +
      "Survival: " + F.map(function (f, i) { return esc(f.name) + " " + (R.survive[i] / R.N * 100).toFixed(0) + "%"; }).join(", ") + ".";
    var g = R.gov.parts;
    $("govnote").innerHTML = "PvP governor ×" + R.gov.scale.toFixed(3) + " (survival floor ×" + g.survival.toFixed(3) + ", skill-rank ×" + g.rankScale.toFixed(3) + " at fight rank " + g.fightRank + " vs server " + g.serverRank + ", balance ×" + g.balance.toFixed(3) + ").";
    $("result").hidden = false; $("detail").hidden = false;
    $("play").disabled = false; $("step").disabled = false;
    PLAY = { sample: R.sample, i: 0, playing: false, busy: false };
    sceneReset();
    fillTable(R.sample);
  }
  function hitText(h) { return (h.blinded ? "blind" : short(h.d)) + (h.crit ? " crit" : "") + (h.block ? " blocked" : "") + (h.absorbed ? " (−" + short(h.absorbed) + " shield)" : ""); }
  function fillTable(sample) {
    var F = fightersFlat();
    $("logbody").innerHTML = sample.log.map(function (l) {
      var tg = (l.targets || []).map(function (i) { return esc(F[i].name); }).join(", ");
      return "<tr><td class=num>" + l.t + "</td><td class=num>" + l.turn + "</td><td><span class='dot s" + l.side + "'></span>" + esc(F[l.who].name) + "</td><td>" + esc(l.skill) + (l.moved ? " <span class=hint>(moved " + l.moved + ")</span>" : "") + "</td><td>" + tg + "</td><td>" + l.hits.map(hitText).join(", ") + "</td><td class=num>" + (l.dmg ? short(l.dmg) : "") + "</td></tr>";
    }).join("");
  }

  /* ---------- playback ---------- */
  function later(fn, ms) { var t = setTimeout(fn, Math.max(0, ms)); TIMERS.push(t); return t; }
  function clearTimers() { TIMERS.forEach(clearTimeout); TIMERS = []; }
  function speedMs() { return parseInt($("speed").value, 10); }
  function stopPlayback() { clearTimers(); if (PLAY) { PLAY.playing = false; PLAY.busy = false; } $("play").innerHTML = "&#9654; Watch the fight"; }
  function sceneReset() {
    clearTimers();
    var F = fightersFlat();
    F.forEach(function (f, i) { hpSet(i, f.sheet.hp, f.sheet.hp, 0); chips(i, []); });
    placeTokens(null);
    $("combatlog").innerHTML = "";
    $("banner").hidden = true;
    if (PLAY) { PLAY.i = 0; PLAY.busy = false; }
  }
  function applyEntry(l) {
    var F = fightersFlat();
    F.forEach(function (f, i) { hpSet(i, l.hp[i], f.sheet.hp, l.sh[i]); chips(i, l.st[i]); });
    placeTokens({ hp: l.hp, pos: l.pos, alive: l.hp.map(function (h) { return h > 0; }) });
    document.querySelectorAll("#board .token").forEach(function (t) { t.classList.toggle("acting", +t.getAttribute("data-i") === l.who); });
    (l.targets || []).forEach(function (i) { var t = document.querySelector('#board .token[data-i="' + i + '"]'); if (t) t.classList.add("hit"); });
    var tg = (l.targets || []).map(function (i) { return esc(F[i].name); }).join(", ");
    var hits = l.hits.map(function (h) { return (h.blinded ? "blind" : short(h.d)) + (h.crit ? "!" : "") + (h.block ? " blk" : ""); }).join(" ");
    var ev = l.events.map(function (e) {
      if (e.kind === "dmg") return esc(F[e.who].name) + " takes " + short(e.amount) + " from " + esc(e.tag);
      if (e.kind === "heal") return esc(F[e.who].name) + " heals " + short(e.amount) + (e.tag ? " (" + esc(e.tag) + ")" : "");
      if (e.kind === "status") return esc(F[e.who].name) + ": " + esc(e.name) + (e.tag ? " (" + esc(e.tag) + ")" : "");
      if (e.kind === "save") return esc(F[e.who].name) + " survives at 1 HP (" + esc(e.tag) + ")";
      if (e.kind === "down") return esc(F[e.who].name) + " is down";
      if (e.kind === "move") return esc(F[e.who].name) + " moves to column " + (e.to[0] + 1) + ", row " + (e.to[1] + 1);
      return "";
    }).filter(Boolean).join("; ");
    var li = document.createElement("li");
    li.className = "s" + l.side;
    li.innerHTML = "<b>" + esc(F[l.who].name) + "</b> " + esc(l.skill) + (tg ? " → " + tg : "") + (hits ? " <span class=hits>" + hits + "</span>" : "") + (l.dmg ? " = " + short(l.dmg) : "") + (ev ? "<br><span class=hint>" + ev + "</span>" : "");
    $("combatlog").appendChild(li);
    $("combatlog").scrollTop = $("combatlog").scrollHeight;
  }
  function stepOnce(done) {
    if (!PLAY || PLAY.i >= PLAY.sample.log.length) { finish(); return; }
    var l = PLAY.sample.log[PLAY.i++];
    applyEntry(l);
    if (done) done(l);
  }
  function finish() {
    var s = PLAY.sample;
    $("banner").hidden = false;
    $("banner").textContent = s.winner < 0 ? "Undecided at the round cap" : SIDE_NAME[s.winner] + " wins";
    stopPlayback();
  }
  function togglePlay() {
    if (!PLAY) return;
    if (PLAY.playing) { stopPlayback(); return; }
    if (PLAY.i >= PLAY.sample.log.length) sceneReset();
    PLAY.playing = true; $("play").innerHTML = "&#10074;&#10074; Pause";
    (function loop() {
      if (!PLAY || !PLAY.playing) return;
      if (PLAY.i >= PLAY.sample.log.length) { finish(); return; }
      stepOnce(function (l) {
        var ms = speedMs();
        if (ms === 0) loop(); else later(loop, ms * (l.dur || 0.8));
      });
    })();
  }

  /* ---------- import ---------- */
  function importJson(text) {
    var arr;
    try { arr = JSON.parse(text); } catch (e) { $("importmsg").textContent = "That is not JSON."; return; }
    if (!Array.isArray(arr)) arr = [arr];
    var added = 0;
    arr.forEach(function (f) {
      if (!f || !f.sheet || !f.techs) return;
      var k = ROSTER.findIndex(function (x) { return x.id === f.id; });
      if (k >= 0) ROSTER[k] = f; else ROSTER.push(f);
      added++;
    });
    ROSTER.sort(function (a, b) { return (a.rankPos || 999) - (b.rankPos || 999) || (b.rating || 0) - (a.rating || 0); });
    if (added) { $("importmsg").textContent = added + " fighter(s) loaded."; invalidate(); }
  }

  function boot() {
    DATA.skills.forEach(function (s) { SKILL[s.id] = s; });
    if (!loadState()) { TEAM = [[null, null, null, null], [null, null, null, null]]; defaultPositions(); }
    drawBoard(); boardEvents(); teamEvents();
    $("run").addEventListener("click", run);
    $("play").addEventListener("click", togglePlay);
    $("step").addEventListener("click", function () { if (!PLAY) return; PLAY.playing = false; $("play").innerHTML = "&#9654; Watch the fight"; if (PLAY.i >= PLAY.sample.log.length) sceneReset(); stepOnce(); });
    $("reset").addEventListener("click", function () { try { localStorage.removeItem("pw_team"); } catch (e) {} TEAM = [[null, null, null, null], [null, null, null, null]]; defaultPositions(); PICK = null; invalidate(); });
    $("swap").addEventListener("click", function () {
      TEAM = [TEAM[1], TEAM[0]];
      var p = POS.slice(4).concat(POS.slice(0, 4));
      var mid = GRID.zones[0].y0 + GRID.zones[1].y1;
      POS = p.map(function (q) { return { x: q.x, y: mid - q.y }; });   /* mirror across the line between the two boxes */
      saveState(); invalidate();
    });
    $("importbtn").addEventListener("click", function () { importJson($("importtext").value); });
    ["maxrounds", "serverdays"].forEach(function (id) { $(id).addEventListener("change", invalidate); });
    invalidate();
  }

  Promise.all([
    fetch("../assets/duel.json?v=" + (C.v || "")).then(function (r) { return r.json(); }),
    fetch("../assets/curves.json?v=" + (C.v || "")).then(function (r) { return r.json(); }),
    C.fightersUrl ? fetch(C.fightersUrl + "?v=" + (C.v || "")).then(function (r) { return r.ok ? r.json() : []; }).catch(function () { return []; }) : Promise.resolve([])
  ]).then(function (v) {
    DATA = v[0]; CURVES = v[1];
    DATA.statuses = DATA.statuses || {}; DATA.trig = DATA.trig || {};
    ROSTER = (v[2] || []).filter(function (f) { return f && f.sheet && f.techs; });
    boot();
  }).catch(function (e) { $("run").textContent = "Could not load skill data"; });
})();
