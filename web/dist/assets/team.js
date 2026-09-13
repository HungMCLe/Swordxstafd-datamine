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
    /* Damage() applies these three on their own stage, not inside the DmgAddPercent block */
    StatusDmgAddPer: "sadd", StatusDmgReducePer: "sred", StatusDmgVulnerablePer: "svuln",
    DmgVulnerable: "vuln",
    /* CalcDamageTypeImpl rolls the target's DodgePercent and the attacker's BlindingPercent per hit */
    DodgePercent: "dodge", BlindingPercent: "blind",
    /* the remaining Damage() terms: defence ignore, the two final scales, the missing-HP bonus */
    StatusIgnoreDefence: "defignore", FinalDamageScale: "finaldmg", FinalCharacterDamageScale: "finalchar",
    SkillDmgAddPerByTargetHp: "dmgbytargethp", SkillTargetReduceHpPer: "exstep",
    SkillDmgUnitAddPer: "exunit", SkillDmgMaxAddPer: "exmax",
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
                    FixedDmgVulnerable: "fvuln", FixedstatusDmgVulnerable: "fvuln",
                    /* the flat damage forms, which join the additive term only on a crit or a block */
                    CritPower: "critpowerv", BlockValue: "blockvaluev",
                    FixedStatusIgnoreDefence: "defignorev" };
  var PCT_FIELDS = ["cr", "cd", "critres", "boost", "dmgres", "blockrate", "blockeff", "blockavoid", "pvpadd", "pvpres", "cureadd", "becureadd", "finalcure", "dodge", "blind", "vuln", "sadd", "sred", "svuln",
                    "defignore", "finaldmg", "finalchar", "dmgbytargethp", "exstep", "exunit", "exmax"];

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
     "cr", "cd", "critres", "boost", "dmgres", "blockrate", "blockeff", "blockavoid", "pvpadd", "pvpres", "cureadd",
     "becureadd", "finalcure", "dodge", "blind", "sadd", "sred", "svuln",
     "defignore", "finaldmg", "finalchar", "dmgbytargethp", "exstep", "exunit", "exmax",
     "crv", "crav", "bv", "bav", "cureaddv", "becureaddv", "critpowerv", "blockvaluev", "defignorev"]
      .forEach(function (k) { s[k] = f.sheet[k] || 0; });
    /* CalcDamageTypeImpl: the flat value forms join their percent divided by the same side's base */
    if (rank.BaseCritRatePercentValue > 0) s.cr += s.crv / rank.BaseCritRatePercentValue;
    if (rank.BaseCritAvoidPercentValue > 0) s.critres += s.crav / rank.BaseCritAvoidPercentValue;
    if (rank.BaseBlockPercentValue > 0) s.blockrate += s.bv / rank.BaseBlockPercentValue;
    if (rank.BaseBlockAvoidPercentValue > 0) s.blockavoid += s.bav / rank.BaseBlockAvoidPercentValue;
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
    /* FightStatusActionExistComponent (Defensive Assault): a status that holds only while the wearer has a shield */
    if (u.shield > 0) (u.charms || []).filter(Boolean).forEach(function (ch) {
      (ch && ch.sk.passive || []).forEach(function (pv) {
        if (pv.kind !== "whileAction" || (pv.actions || []).indexOf("Shield") < 0) return;
        (pv.statuses || []).forEach(function (o) {
          var meta = DATA.statuses[String(o.status)], row = meta && meta.props && meta.props[String(ch.rank)];
          if (row) foldProps(e, row, ch.rank, ch.level, u.s.rank);
        });
      });
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
    /* Damage(): for ElementType.None the Affinity term is the mean of the five elemental Affinities and the
       Aegis term the mean of the five elemental resistances, over the same bases as an elemental hit */
    var mean = function (m) { return ELES.reduce(function (a, e) { return a + (m[e] || 0); }, 0) / ELES.length; };
    var aff = elemental ? (att.aff[ele] || 0) : mean(att.aff);
    var aeg = elemental ? (def.aegis[ele] || 0) : mean(def.aegis);
    var foeMasterBase = elemental ? def.rank.BaseElementResistance : def.rank.BaseKongFuResistance;
    var myMasterBase = elemental ? att.rank.BaseElementMaster : att.rank.BaseKongFuMaster;
    var res = elemental ? def.eres : def.kfr;
    var eNum = 1 + aff / def.rank.BaseElementReduce + mast / foeMasterBase;
    var eDen = 1 + aeg / att.rank.BaseElementAdd + res / myMasterBase;
    var pct = (1 + att.boost + (att.pvpadd || 0) + def.vuln) / Math.max(0.1, 1 + def.dmgres + (def.pvpres || 0));
    /* Damage(): num2 *= 1 + StatusDmgAddPer(src) + StatusDmgVulnerablePer(tgt); num2 /= max(0.1, 1 + StatusDmgReducePer(tgt)) */
    pct *= (1 + (att.sadd || 0) + (def.svuln || 0)) / Math.max(0.1, 1 + (def.sred || 0));
    /* FinalDamageScale, and FinalCharacterDamageScale because a PvP target is always a character */
    pct *= (1 + (att.finaldmg || 0)) * (1 + (att.finalchar || 0));
    /* Damage(): the target's Defence first loses the attacker's percent and flat defence ignore */
    var defUsed = Math.max(0, def.def - def.def * (att.defignore || 0) - (att.defignorev || 0));
    var defTerm = att.atk / (att.atk + defUsed);
    var psdr = 1 + (def.rank.PlayerSkillDmgReduceScale || 0) / 10000;
    var prosdr = 1 + (def.rank.ProSkillDmgReduceScale || 0) / 10000;
    var pvp = (sk.pvp || 10000) / 10000;
    var flat = flatOf(row, "fx", "fg", "SkillFixedAttack1", slevel, att.rank.name);
    var out = { hits: [], heal: 0 };
    var cureProp = ec && ec.hits && ec.hits.length ? ec.hits[0].prop : null;
    if ((ec && ec.skillType === "Cure") || /^SkillCureBy/.test(cureProp || "") || ((row.SkillCureByHp || row.SkillCureByAttack || row.SkillCureByTargetHp) && !row.SkillAttack1)) {
      /* Cure(): base = MaxHp x SkillCureByHp | Attack x SkillCureByAttack | target MaxHp x SkillCureByTargetHp, + SkillFixedCure;
         x (1 + CureAddPercent(src) + BeCureAddPercent(tgt) + CureAdd/BaseCureAdd + BeCureAdd/BaseBeCureAdd) x (1 + FinalCureScale) */
      var base = (row.SkillCureByHp || 0) / 100 * att.hpMax + (row.SkillCureByAttack || 0) / 100 * att.atk + (row.SkillCureByTargetHp || 0) / 100 * (def.hpMax || 0) +
                 flatOf(row, "SkillFixedCure", "SkillFixedCure_g", "SkillFixedCure", slevel, att.rank.name);
      var cadd = (att.cureadd || 0) + (def.becureadd || 0) +
                 (att.rank.BaseCureAdd > 0 ? (att.cureaddv || 0) / att.rank.BaseCureAdd : 0) +
                 (def.rank.BaseBeCureAdd > 0 ? (def.becureaddv || 0) / def.rank.BaseBeCureAdd : 0);
      out.heal = Math.max(0, base * pvp * (1 + cadd) * (1 + (att.finalcure || 0)));
      return out;
    }
    function one(coef, withFlat, on, ignoreShield, at) {
      var base = (att.atk * coef / psdr + (withFlat ? flat : 0)) * defTerm;
      var flatSum = (att.fadd || 0) + (def.fvuln || 0) - (def.fred || 0);
      /* Damage() num3: the flat adds, times the skill coefficient, over the target's PvP skill scaler, floored
         at minus FixedDmgLimitPercent of the base; the attacker's flat Crit Power joins it on a crit and the
         target's flat Block Value leaves it on a block, so those two cases carry their own figure */
      function done(extra) {
        var add = Math.max(-0.9 * base, (flatSum + extra) * coef / psdr);
        return (base + add) / prosdr * (eNum / eDen) * pct * pvp;
      }
      var hit = { d: done(0), on: on || [], ignoreShield: !!ignoreShield, at: at || 0 };
      if (att.critpowerv) hit.dc = done(att.critpowerv);
      if (def.blockvaluev) hit.db = done(-def.blockvaluev);
      out.hits.push(hit);
    }
    if (ec && ec.hits && ec.hits.length) {
      /* HitDamageType.None: the hit lands (statuses, child skills, forced moves) but CalcDamageType computes nothing
         for it, so it deals no damage; the flat term joins the first damaging hit */
      var flatDone = false;
      ec.hits.forEach(function (h, i) {
        if (h.type === "None") { out.hits.push({ d: 0, on: h.on || [], ignoreShield: !!h.ignoreShield, at: h.at || 0, noDamage: true }); return; }
        one((row[h.prop] || 0) / 100, !flatDone, h.on, h.ignoreShield, h.at); flatDone = true;
      });
    } else {
      var coef = ((row.SkillAttack1 || 0) + (row.SkillAttack2 || 0) + (row.SkillAttack3 || 0) + (row.SkillAttack4 || 0)) / 100;
      var cnt = sk.hits || 1;
      for (var k = 0; k < cnt; k++) one(coef / cnt, k === 0, [], false, 0.3 + k * 0.15);
    }
    return out;
  }
  /* CalcDamageTypeImpl: block is rolled first and a blocked hit never crits; the value forms are already folded */
  function critChance(att, def) { return Math.min(1, Math.max(0, 0.05 + att.cr - def.critres)); }
  function critMult(att, def) { return Math.max(C.minCrit, 1 + att.cd - def.critres); }
  function blockChance(att, def) { return Math.min(1, Math.max(0, def.blockrate - att.blockavoid)); }
  function blockDiv(att, def) { return Math.max(C.minBlock, 1 + def.blockeff - att.blockavoid); }
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
    /* SkillRankPropScaleCalculator: per faction the MAX over its members of their average skill rank, then the
       average of the faction maxima */
    var facMax = [0, 0];
    sheets.forEach(function (s, i) {
      var rs = s.skillRanks || [];
      var avg = rs.length ? rs.reduce(function (a, b) { return a + b; }, 0) / rs.length : 0;
      var f = i < 4 ? 0 : 1;
      facMax[f] = Math.max(facMax[f], avg);
    });
    var fightRank = Math.round((facMax[0] + facMax[1]) / 2);
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
    /* FightStatusPropByStatusComponent (Holy Aegis): the creator's shields that use one of IncludeProptypes grow by its StatusShieldAddPercent */
    if (amt > 0) (creator.charms || []).forEach(function (ch) {
      (ch && ch.sk && ch.sk.passive || []).forEach(function (pv) {
        if (pv.kind !== "shieldBoost" || !pv.isShield) return;
        if (!(pv.includeProps || []).some(function (p) { return row[p] !== undefined; })) return;
        var r = (ch.sk.props || {})[String(ch.rank)] || {};
        if (r.StatusShieldAddPercent) amt *= 1 + curveValue(r.StatusShieldAddPercent, ch.rank, ch.level, creator.s.rank.name) / 100;
      });
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
  /* state_mutex table: which of a fighter's own actions a status state discards. Stun, Frozen and PhoenixStasis
     discard both Move and Skill; Restrict and Immobilize discard Move only; the rest discard nothing */
  var SKIP_ACTIONS = { Stun: 1, Frozen: 1, PhoenixStasis: 1 };
  var NO_MOVE = { Stun: 1, Frozen: 1, PhoenixStasis: 1, Restrict: 1, Immobilize: 1 };
  function rooted(u) { return u.st.some(function (x) { return NO_MOVE[x.meta.action]; }); }
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
                  DmgVulnerable: "Vulnerable", CritAvoidPercent: "Crit RES", ElementMaster: "Mastery",
                  BlockAvoidPercent: "Accuracy", EffectRate: "Effect Hit", EffectDodge: "Effect RES", KongFuMaster: "Phys Mastery",
                  ElementResistance: "Elem RES", KongFuResistance: "Phys RES", CureAddPercent: "Healing", StatusAdd1: "Effect",
                  StatusAdd2: "Effect", CritRatePercentValue: "Crit Rate", BlockPercentValue: "Block Rate", CritAvoidPercentValue: "Crit RES" };
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
      return list.map(function (t) { var sk = t && SKILL[t.id]; return sk ? { sk: sk, rank: t.rank || 1, level: t.level || 1, id: sk.id, name: sk.name } : null; });
    }
    var techs = bind(f.techs || []), charms = bind(f.charms || []).filter(Boolean);
    while (techs.length < 4) techs.push(null);
    while (charms.length < 4) charms.push(null);
    s.skillRanks = techs.concat(charms).filter(Boolean).map(function (t) { return t.rank; });
    return { i: idx, side: side, name: f.name, cls: f.cls, f: f, s: s, techs: techs, charms: charms,
             hp: s.hp, shield: 0, st: [], cd: openingCds(techs, charms), uses: techs.map(function () { return 0; }),
             t: interval(s), turns: 0, pos: { x: pos.x, y: pos.y }, alive: true, charmFired: {}, techCasts: 0,
             order: idx, taunt: null, flip: side === 1 };   /* Team 2 starts facing down the board */
  }

  /* ---------- the grid rules the client ships ----------
     Pos2d.LookDirection: (0,0) -> Up; dx>0: Up if dy>dx, Down if dy<-dx, else Right; dx<0 mirrored -> Left.
     CalcFlipX: dx>0 -> not flipped, dx<0 -> flipped, dx==0 -> unchanged.
     CalcLocalToWorldDir: flip x, then rotate by the direction (Up id, Down negate, Left (-y,x), Right (y,-x)).
     MyMath.LoopOut: rings by Manhattan distance, each ring grown from the previous with FourDirs
     Down, Left, Up, Right; the first standable cell in that order wins. */
  function facing(from, to) {
    var dx = to.x - from.x, dy = to.y - from.y;
    if (!dx && !dy) return "U";
    if (dx > 0) return dy > dx ? "U" : (dy < -dx ? "D" : "R");
    return dy > -dx ? "U" : (dy < dx ? "D" : "L");
  }
  function flipFor(from, to, prev) { var dx = to.x - from.x; return dx > 0 ? false : (dx < 0 ? true : !!prev); }
  function turn(c, dir, flip) {
    var x = flip ? -c[0] : c[0], y = c[1];
    if (dir === "U") return [x, y];
    if (dir === "D") return [-x, -y];
    if (dir === "L") return [-y, x];
    return [y, -x];
  }
  var FOUR = [[0, -1], [-1, 0], [0, 1], [1, 0]];
  var RINGS = (function () {           /* offsets in LoopOut order, rings 0..10 */
    var out = [[0, 0]], seen = { "0,0": 1 }, ring = [[0, 0]];
    for (var d = 1; d <= 10; d++) {
      var next = [];
      ring.forEach(function (c) { FOUR.forEach(function (f) { var k = (c[0] + f[0]) + "," + (c[1] + f[1]); if (!seen[k]) { seen[k] = 1; next.push([c[0] + f[0], c[1] + f[1]]); } }); });
      out = out.concat(next); ring = next;
    }
    return out;
  })();
  function opposite(dir) { return dir === "U" ? "D" : dir === "D" ? "U" : dir === "L" ? "R" : "L"; }
  function dirVec(dir) { return dir === "U" ? [0, 1] : dir === "D" ? [0, -1] : dir === "L" ? [-1, 0] : [1, 0]; }

  /* ---------- one fight ---------- */
  function oneFight(fighters, positions, rng, wantLog, maxRounds, gov) {
    var GOV = gov || 1;
    var ents = fighters.map(function (f, i) { return makeEntity(f, i < 4 ? 0 : 1, i, positions[i]); });
    var log = [], turns = 0, MAXT = 2400, capped = false, events = null;
    var me = null;
    /* grid items: a cell-bound status with a MoveNear hook (a Burn cell), living on its creator's rounds */
    var gridFx = [];
    function fxAt(x, y) { return gridFx.filter(function (f) { return f.x === x && f.y === y; }); }
    function fxLabel(f) { return f.meta.ele && f.meta.ele !== "None" ? f.meta.ele.toUpperCase() : f.tag; }
    function fireGrid(f, unit) {
      var mn = f.meta.moveNear; if (!mn || !unit || !unit.alive) return;
      var creator = ents[f.creator];
      if (mn.target === "Enemy" && unit.side === creator.side) return;
      if ((mn.target === "Friend" || mn.target === "FriendNotMe") && unit.side !== creator.side) return;
      if (mn.maxCount > 0 && f.fired >= mn.maxCount) return;
      if (rng() >= mn.rate) return;
      f.fired++;
      (mn.skills || []).forEach(function (t) { if (rng() < t.chance) fireSkill(t.skill, creator, unit, f.tag, f.rank, f.level); });
    }
    function placeGrid(x, y, ids, creator, rank, level, tag) {
      if (!inGrid(x, y)) return;
      ids.forEach(function (sid) {
        var meta = DATA.statuses[String(sid)]; if (!meta || !meta.moveNear) return;
        var f = { x: x, y: y, id: sid, meta: meta, creator: creator.i, dur: meta.dur, rank: rank, level: level, tag: tag, fired: 0 };
        gridFx.push(f);
        if (events) events.push({ kind: "grid", x: x, y: y, tag: tag, label: fxLabel(f) });
        if (meta.moveNear.onStart) { var u = unitAt()[x + "," + y]; if (u) fireGrid(f, u); }   /* TryAtStart: whoever stands there now */
      });
    }
    function alive(side) { return ents.filter(function (u) { return u.alive && (side === undefined || u.side === side); }); }
    function enemiesOf(u) { return alive(1 - u.side); }
    function alliesOf(u) { return alive(u.side); }
    function unitAt() { var m = {}; ents.forEach(function (u) { if (u.gone) return; m[u.pos.x + "," + u.pos.y] = u; }); return m; }
    function standable(x, y, occ, mover) { if (!inGrid(x, y)) return false; var u = occ[x + "," + y]; return !u || u === mover; }
    function nearestStandable(cx, cy, occ, mover) {
      for (var i = 0; i < RINGS.length; i++) { var x = cx + RINGS[i][0], y = cy + RINGS[i][1]; if (standable(x, y, occ, mover)) return { x: x, y: y }; }
      return null;
    }
    function nearest(u, list) {
      var best = null, bd = 1e9;
      list.forEach(function (v) { var d = dist(u.pos, v.pos); if (d < bd) { bd = d; best = v; } });
      return best;
    }
    function isAlly(sk) { var t = (sk.ec || {}).target; return t === "Me" || t === "Friend" || t === "FriendNotMe" || t === "Ally" || t === "Self"; }
    function poolFor(u, sk) {
      var ec = sk.ec || {}, t = ec.target;
      if (t === "None") return [];
      if (t === "All") return alive();
      var pool = isAlly(sk) ? alliesOf(u) : enemiesOf(u);
      if (t === "FriendNotMe") pool = pool.filter(function (v) { return v !== u; });
      return pool;
    }

    /* ---- statuses ---- */
    function applyStatus(tgt, sid, creator, rank, level, lent, quiet) {
      var meta = DATA.statuses[String(sid)];
      if (!meta || meta.falloff || meta.dur === 0) return null;
      var have = tgt.st.filter(function (x) { return x.id === sid; })[0], st;
      if (have) {
        if (meta.stack) have.stacks = Math.min(have.stacks + 1, meta.maxStack > 0 ? meta.maxStack : 99);
        have.dur = meta.dur; have.rank = rank; have.level = level; have.skills = meta.skillCount || 0;
        st = have;
      } else {
        st = { id: sid, meta: meta, dur: meta.dur, creator: creator.i, rank: rank, level: level, stacks: 1, props: lent || null, skills: meta.skillCount || 0 };
        tgt.st.push(st);
      }
      if (meta.reduceLife && tgt.summon && tgt.life > 0) tgt.life = Math.max(1, tgt.life - (meta.reduceLife.rounds || 0));   /* FightStatusReduceStatusLifeComponent */
      var ri = meta.roundInterval;
      if (ri && (ri.rate === undefined || rng() < ri.rate)) {
        /* FightStatusRoundIntervalComponent: the holder's next turn moves by RoundIntervalPercent of its interval,
           earlier when FastForward ("Advances Action Bar by 20%") */
        var step = (ri.pct || 0) * interval(eff(tgt, ents));
        tgt.t += ri.fastForward ? -step : step;
        if (events) events.push({ kind: "bar", who: tgt.i, pct: ri.fastForward ? -(ri.pct || 0) : (ri.pct || 0) });
      }
      if (!quiet) onStatusApplied(creator, tgt, st);
      return st;
    }
    /* FightDamageComponentInfo.DisperseStatus: strip Count statuses of the listed types that allow it (CanDispersed) */
    function disperseStatuses(u, ds) {
      var cand = u.st.filter(function (x) { return x.meta.canDisperse && (ds.types || []).indexOf(x.meta.type) >= 0; });
      for (var n = 0; n < (ds.count || 1) && cand.length; n++) {
        var k = ds.random ? Math.floor(rng() * cand.length) : 0;
        var st = cand.splice(k, 1)[0];
        removeStatus(u, st);
        if (events) events.push({ kind: "status", who: u.i, name: statusName(st.meta, st.props) + " dispelled" });
      }
    }
    function removeStatus(holder, st) {
      var i = holder.st.indexOf(st);
      if (i >= 0) holder.st.splice(i, 1);
      if (st.meta.shield && !holder.st.some(function (x) { return x.meta.shield; })) { holder.shield = 0; onShieldGone(holder); }
    }
    function hasShield(u) { return u.shield > 0 && u.st.some(function (x) { return x.meta.shield; }); }
    function stealthed(u) { return u.st.some(function (x) { return x.meta.invisible; }); }
    function kill(u, by) {
      if (u.hp > 0 || !u.alive) return;
      var overflow = -u.hp;
      u.alive = false; u.hp = 0; u.st = []; u.shield = 0;
      if (u.summon && u.destroyOnDie) u.gone = true;                    /* FightRoleCharacterComponent.DestroyOnDie: the cell frees */
      if (u.summon) onSummonGone(u); else auraSettle();
      gridFx = gridFx.filter(function (f) { return !(f.creator === u.i && f.meta.removeAtRoundTargetDie); });   /* StatusAutoRemove: RemoveAtRoundTargetDie */
      if (events) events.push({ kind: "down", who: u.i });
      if (by) onKill(by, u, overflow);
      onDeath(u);
    }
    function heal(tgt, amount, tag) {
      if (!tgt.alive || !(amount > 0)) return 0;
      var before = tgt.hp; tgt.hp = Math.min(tgt.s.hp, tgt.hp + amount);
      if (events && tgt.hp > before) events.push({ kind: "heal", who: tgt.i, amount: tgt.hp - before, tag: tag });
      hpUnitsSettle(tgt);
      return tgt.hp - before;
    }
    function directDamage(tgt, amount, by, tag, ignoreShield) {
      if (!tgt.alive || !(amount > 0)) return 0;
      var d = amount, absorbed = 0;
      if (tgt.shield > 0 && !ignoreShield) { absorbed = Math.min(tgt.shield, d); tgt.shield -= absorbed; d -= absorbed; if (tgt.shield <= 0) tgt.st.filter(function (x) { return x.meta.shield; }).forEach(function (x) { removeStatus(tgt, x); }); }
      var saved = null;
      if (d > 0 && d >= tgt.hp) { saved = deathSave(tgt); if (saved) d = Math.max(0, tgt.hp - saved.limit); }
      tgt.hp -= d;
      if (events && d > 0) events.push({ kind: "dmg", who: tgt.i, amount: d, tag: tag });
      if (saved) { if (saved.heal > 0) heal(tgt, saved.heal, saved.ch.name); firePassive(saved.pv, saved.ch, tgt, by, by); }
      else if (d > 0) afterDamage(tgt, by);
      kill(tgt, by);
      return d;
    }

    /* ---- trigger skills (poison ticks, expiry heals, Charm procs) ---- */
    function fireSkill(skillId, src, tgt, tag, rank, level) {
      var entry = DATA.trig[String(skillId)];
      if (!entry || !tgt || !tgt.alive) return;
      var rows = (entry.r || {})[String(rank)] || {};
      var srcE = eff(src, ents), tgtE = eff(tgt, ents);
      var fake = { id: skillId, name: entry.name, ele: (entry.ec && entry.ec.ele) || "None", ec: entry.ec, hits: 1, r: entry.r || {}, pvp: entry.pvp || 10000, gov: entry.gov !== false,
                   noHooks: !!(entry.ec && entry.ec.canTriggerChild === false) };
      var parts = hitParts(srcE, tgtE, fake, rows, level);
      if (parts.heal) { heal(tgt, parts.heal, tag); return; }
      var total = landHits(parts, src, tgt, srcE, tgtE, fake, null, rank, level, null);
      if (events && total > 0) events.push({ kind: "dmg", who: tgt.i, amount: total, tag: tag });
      parts.hits.forEach(function (h) {
        h.on.forEach(function (o) {
          var meta = DATA.statuses[String(o.status)];
          if (!meta || meta.falloff) return;
          var target = (o.target === "DamageTarget") ? tgt : src;
          if (rng() < landChance(o.chance, o.byProp, meta.type, srcE, tgtE)) {
            var st = applyStatus(target, o.status, src, rank, level);
            if (st && meta.shield) { var amt = shieldSize(meta, src, target, rank, level); if (amt > 0) target.shield = Math.max(target.shield, amt); }
            if (st && events) events.push({ kind: "status", who: target.i, name: statusName(meta) });
          }
        });
      });
      forcedMoves(parts, fake, src, tgt, tgt.pos, facing(src.pos, tgt.pos), src.flip);
      kill(tgt, src);
    }
    /* a trigger skill with an area: every unit of the right side under its cells around `centre` */
    function fireSkillArea(skillId, src, centre, tag, rank, level, customDamage) {
      var entry = DATA.trig[String(skillId)];
      if (!entry || !entry.ec) return;
      var fake = { ec: entry.ec, id: skillId };
      var pool = poolFor(src, fake);
      var cellsHit = {};
      (entry.ec.hits || []).forEach(function (h) { (h.cells && h.cells.length ? h.cells : [[0, 0]]).forEach(function (c) { var w = turn(c, "U", false); cellsHit[(centre.x + w[0]) + "," + (centre.y + w[1])] = 1; }); });
      pool.forEach(function (u) {
        if (!cellsHit[u.pos.x + "," + u.pos.y]) return;
        if (customDamage !== undefined) directDamage(u, customDamage, src, tag, false);
        else fireSkill(skillId, src, u, tag, rank, level);
      });
    }
    function charmStrike(ch, holder, tgt) {
      var hE = eff(holder, ents), tE = eff(tgt, ents);
      var rows = (ch.sk.r || {})[String(ch.rank)] || {};
      var fake = { id: ch.id, name: ch.name, ele: ch.sk.ele || "Physical", hits: 1, r: ch.sk.r || {}, pvp: ch.sk.pvp || 10000, gov: ch.sk.gov !== false };
      var parts = hitParts(hE, tE, fake, rows, ch.level);
      if (parts.heal) { heal(holder, parts.heal, ch.name); return; }
      var total = landHits(parts, holder, tgt, hE, tE, fake, null, ch.rank, ch.level, null);
      if (events && total > 0) events.push({ kind: "dmg", who: tgt.i, amount: total, tag: ch.name });
      kill(tgt, holder);
    }
    function charmRow(ch, holder) { return (ch.sk.props || {})[String(ch.rank)] || null; }
    function charmVal(ch, holder, prop) { var row = charmRow(ch, holder); return row && row[prop] ? curveValue(row[prop], ch.rank, ch.level, holder.s.rank.name) : 0; }

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
        var chance = pv.rate * (o.chance === undefined ? 1 : o.chance);
        var tgt = pick(o.target);
        if (!tgt || !tgt.alive) return;
        if (o.byProp) chance = landChance(chance, true, meta.type, eff(holder, ents), eff(tgt, ents));
        if (rng() >= chance) return;
        var lent = (meta.props || (pv.stackTrigger && pv.stackTrigger.status === o.status)) ? null : (ch.sk.props || null);
        var st = applyStatus(tgt, o.status, holder, ch.rank, ch.level, lent);
        if (!st) return;
        if (meta.shield) { var amt = shieldSize(meta, holder, tgt, ch.rank, ch.level); if (amt > 0) tgt.shield = Math.max(tgt.shield, amt); }
        if (events) events.push({ kind: "status", who: tgt.i, name: statusName(meta, lent) + (st.stacks > 1 ? " ×" + st.stacks : ""), tag: ch.name });
        if (pv.stackTrigger && pv.stackTrigger.status === o.status && st.stacks >= pv.stackTrigger.count) {
          st.stacks -= pv.stackTrigger.count;
          if (st.stacks <= 0) removeStatus(tgt, st);
          charmStrike(ch, holder, tgt);
        }
      });
      return true;
    }
    function eachPassive(holder, fn) {
      if (!holder.alive) return;
      holder.charms.forEach(function (ch) { (ch && ch.sk.passive || []).forEach(function (pv) { fn(pv, ch); }); });
    }
    function procs(holder, kind, enemy, trig, filter) {
      eachPassive(holder, function (pv, ch) {
        if (pv.kind !== kind) return;
        if (filter && !filter(pv)) return;
        firePassive(pv, ch, holder, enemy, trig);
      });
    }
    function deathSave(who) {
      var out = null;
      eachPassive(who, function (pv, ch) {
        if (out || pv.kind !== "deathSave") return;
        var key = ch.id + ":saved:" + pv.status;
        if ((who.charmFired[key] || 0) >= (pv.maxCount > 0 ? pv.maxCount : 1)) return;
        who.charmFired[key] = (who.charmFired[key] || 0) + 1;
        out = { limit: pv.limit || 1, ch: ch, pv: pv, heal: 0 };
        var row = charmRow(ch, who);
        if (row) {
          if (row.SkillCureByHp) out.heal += curveValue(row.SkillCureByHp, ch.rank, ch.level, who.s.rank.name) / 100 * who.s.hp;
          if (row.SkillFixedCure) out.heal += curveValue(row.SkillFixedCure, ch.rank, ch.level, who.s.rank.name);
        }
      });
      return out;
    }
    /* HP-unit Charms: one stack per UnitHpPer of max HP missing; stacks come off as HP climbs back (HpIncreaseUnit) */
    function hpUnitsSettle(who) {
      eachPassive(who, function (pv, ch) {
        if (pv.kind !== "hpUnit") return;
        var key = ch.id + ":units:" + pv.status;
        var units = Math.floor((1 - who.hp / who.s.hp) / pv.unit + 1e-9);
        if (pv.maxCount > 0) units = Math.min(units, pv.maxCount);
        if ((who.charmFired[key] || 0) > units) {
          who.charmFired[key] = units;
          (pv.statuses || []).forEach(function (o) {
            var st = who.st.filter(function (x) { return x.id === o.status; })[0];
            if (st && st.stacks > units) { st.stacks = units; if (st.stacks <= 0) removeStatus(who, st); }
          });
        }
      });
    }
    function afterDamage(who, from) {
      eachPassive(who, function (pv, ch) {
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
    }
    /* hooks for the Charm components that watch other events */
    var applying = 0;
    function onStatusApplied(creator, tgt, st) {
      if (applying > 0 || !creator || !creator.alive) return;
      eachPassive(creator, function (pv, ch) {
        if (pv.kind !== "statusApplied") return;
        if (pv.when && st.meta.action !== pv.when) return;
        applying++;
        (pv.statuses || []).forEach(function (o) {
          var chance = o.chance === undefined ? 1 : o.chance;
          if (o.byProp) chance = landChance(chance, true, (DATA.statuses[String(o.status)] || {}).type, eff(creator, ents), eff(tgt, ents));
          if (rng() < chance) { var s2 = applyStatus(tgt, o.status, creator, ch.rank, ch.level, null, true); if (s2 && events) events.push({ kind: "status", who: tgt.i, name: statusName(s2.meta), tag: ch.name }); }
        });
        applying--;
      });
    }
    function onShieldGone(holder) {
      eachPassive(holder, function (pv, ch) {
        if (pv.kind !== "actionEnd" || (pv.actions || []).indexOf("Shield") < 0) return;
        if (rng() >= pv.rate) return;
        (pv.triggers || []).forEach(function (t) { fireSkillArea(t.skill, holder, holder.pos, ch.name, ch.rank, ch.level); });
      });
    }
    function onKill(by, victim, overflow) {
      eachPassive(by, function (pv, ch) {
        if (pv.kind !== "kill") return;
        var key = ch.id + ":kill:" + pv.status;
        if (pv.maxCount > 0 && (by.charmFired[key] || 0) >= pv.maxCount) return;
        if (rng() >= pv.rate) return;
        by.charmFired[key] = (by.charmFired[key] || 0) + 1;
        var pct = charmVal(ch, by, "DamageByDamage") / 100;
        (pv.triggers || []).forEach(function (t) {
          var dmg = pv.overflow ? overflow * pct : undefined;
          if (dmg !== undefined && !(dmg > 0)) return;
          fireSkillArea(t.skill, by, pv.atDiePos ? victim.pos : by.pos, ch.name, ch.rank, ch.level, dmg);
        });
      });
    }
    function onDeath(u) {
      /* Resurrection: an ally's death (or its own) revives the fallen at 1 HP, once per battle per wearer */
      ents.forEach(function (w) {
        if (!w.alive && w !== u) return;
        if (w.side !== u.side) return;
        eachPassive(w, function (pv, ch) {
          if (pv.kind !== "revive" || u.alive) return;
          var key = ch.id + ":revive:" + pv.status;
          if (pv.maxCount > 0 && (w.charmFired[key] || 0) >= pv.maxCount) return;
          w.charmFired[key] = (w.charmFired[key] || 0) + 1;
          u.alive = true; u.hp = 1; u.st = []; u.shield = 0;
          if (events) events.push({ kind: "status", who: u.i, name: "Revived", tag: ch.name });
          (pv.triggers || []).forEach(function (t) {
            var entry = DATA.trig[String(t.skill)];
            if (!entry) return;
            var isCure = entry.ec && entry.ec.skillType === "Cure";
            if (isCure) fireSkill(t.skill, w, u, ch.name, ch.rank, ch.level);
            else (entry.ec && entry.ec.hits || []).forEach(function (h) { h.on.forEach(function (o) { var meta = DATA.statuses[String(o.status)]; if (meta && meta.action !== "BackToLife") applyStatus(u, o.status, w, ch.rank, ch.level); }); });
          });
        });
      });
    }
    function afterMoved(mover, from) {
      /* Repelling Wind: an enemy stepping from outside to inside the wearer's zone triggers its strike */
      ents.forEach(function (w) {
        if (!w.alive || w === mover || w.side === mover.side) return;
        eachPassive(w, function (pv, ch) {
          if (pv.kind !== "proximity" || !pv.onEnter) return;
          var inside = pv.cells.some(function (c) { return w.pos.x + c[0] === mover.pos.x && w.pos.y + c[1] === mover.pos.y; });
          var was = pv.cells.some(function (c) { return w.pos.x + c[0] === from.x && w.pos.y + c[1] === from.y; });
          if (!inside || was) return;
          if (rng() >= pv.rate) return;
          (pv.triggers || []).forEach(function (t) { fireSkill(t.skill, w, mover, ch.name, ch.rank, ch.level); });
        });
      });
      /* grid items: arriving on one from another cell sets it off (TryAtEnterRange) */
      fxAt(mover.pos.x, mover.pos.y).forEach(function (f) { if (f.meta.moveNear.onEnter && !(from.x === f.x && from.y === f.y)) fireGrid(f, mover); });
      auraSettle();
    }
    /* forced moves: the caster's SourceMoveList and the victim's damage MoveCfg (FightSKillMoveCfg) */
    function forceMove(mover, cfg, caster, aim, dir, flip, who) {
      if (!mover.alive) return 0;
      if (mover !== caster && mover.st.some(function (x) { return x.meta.action === "Frozen" || x.meta.action === "Immobilize" || x.meta.action === "SuperArmor"; })) return 0;
      var occ = unitAt();
      var o = turn(cfg.offset || [0, 0], dir, flip);
      var base = cfg.dir === "RelativeToSource" ? caster.pos : aim;
      var anchor = { x: base.x + o[0], y: base.y + o[1] };
      var from = { x: mover.pos.x, y: mover.pos.y }, dest = null;
      if (cfg.distance === -1) {
        dest = nearestStandable(anchor.x, anchor.y, occ, mover);
      } else if (cfg.distance > 0) {
        var step = dirVec(cfg.towards ? facing(mover.pos, anchor) : opposite(facing(mover.pos, anchor)));
        if (cfg.dir === "TowardsPathSides") step = dirVec(facing(anchor, mover.pos));
        var cx = mover.pos.x, cy = mover.pos.y;
        for (var k = 0; k < cfg.distance; k++) {
          if (cfg.towards && cx + step[0] === anchor.x && cy + step[1] === anchor.y) break;
          if (!standable(cx + step[0], cy + step[1], occ, mover)) break;
          cx += step[0]; cy += step[1];
        }
        dest = { x: cx, y: cy };
      }
      if (!dest || (dest.x === from.x && dest.y === from.y)) return 0;
      mover.pos = dest;
      if (events) events.push({ kind: "move", who: mover.i, to: [dest.x, dest.y], forced: true, tag: who });
      afterMoved(mover, from);
      return dist(from, dest);
    }
    function forcedMoves(parts, pick, src, tgt, aim, dir, flip) {
      (pick.ec && pick.ec.hits || []).forEach(function (h) {
        if (h.move && !h.child && tgt.alive && rng() < (h.move.chance === undefined ? 1 : h.move.chance)) forceMove(tgt, h.move, src, aim, dir, flip, pick.name);
      });
    }

    /* the damage-event hooks (FightStatusDamageBaseComponentInfo / FightStatusHitBaseComponentInfo): every true
       flag restricts the event — Block = only a blocked hit, Crit = only a crit, Damage = only when damage landed;
       ConditionCount = every Nth event, EachRoundMaxCount = per round of the wearer */
    function hitMatch(pv, ev, holder, other) {
      if (pv.onlyAttack && !ev.isAttack) return false;
      if (pv.onBlock && !ev.block) return false;
      if (pv.onCrit && !ev.crit) return false;
      if (pv.onDamage !== false && !(ev.d + ev.absorbed > 0)) return false;
      if (pv.onCure) return false;
      if (pv.elements && pv.elements.length && pv.elements.indexOf(ev.ele) < 0) return false;
      if (pv.ignoreSkills && pv.ignoreSkills.length && pv.ignoreSkills.indexOf(ev.skillId) >= 0) return false;
      if (pv.onlySkills && pv.onlySkills.length && pv.onlySkills.indexOf(ev.skillId) < 0) return false;
      if (pv.skillTargetType === "Enemy" && holder.side === other.side) return false;
      if (pv.conditionCount > 1) { var ck = "cc:" + pv.status; holder.charmFired[ck] = (holder.charmFired[ck] || 0) + 1; if (holder.charmFired[ck] % pv.conditionCount !== 0) return false; }
      if (pv.eachRoundMax > 0) { var rk = "rm:" + pv.status, cur = holder.charmFired[rk]; if (!cur || cur.turn !== holder.turns) cur = holder.charmFired[rk] = { turn: holder.turns, n: 0 }; if (cur.n >= pv.eachRoundMax) return false; cur.n++; }
      return true;
    }
    var hookDepth = 0;
    function landHits(parts, me, foe, meE, foeE, pick, rolled, rank, level, fall) {
      var p = critChance(meE, foeE), m = critMult(meE, foeE);
      var b = blockChance(meE, foeE), bd = blockDiv(meE, foeE);
      var total = 0, fallCount = fall ? (fall[foe.i] || 0) : 0;
      /* CalcDamageTypeImpl: IsBlinding rolls the attacker's own BlindingPercent (the Blind status grants it),
         IsDodge rolls the target's DodgePercent; Damage() returns 0 for either */
      var blindPct = meE.blind || 0, dodgePct = foeE.dodge || 0;
      var gov = pick.gov === false ? 1 : GOV;
      var shielded = hasShield(foe);
      var isAttack = !pick.ec || !pick.ec.skillType || pick.ec.skillType === "Attack";
      parts.hits.forEach(function (h, hi) {
        if (!foe.alive || !(h.d > 0)) return;
        /* CalcDamageTypeImpl rolls each of these: the attacker's Blind chance, the target's Dodge, then block,
           and crit only when the hit was not blocked. Damage() returns 0 for a blind or a dodge. */
        var blinded = blindPct > 0 && rng() < blindPct;
        var dodged = !blinded && dodgePct > 0 && rng() < dodgePct;
        var block = rng() < b;
        var crit = !block && rng() < p;
        var d = (crit && h.dc !== undefined ? h.dc : block && h.db !== undefined ? h.db : h.d) * gov;
        var absorbed = 0;
        var fo = null;
        h.on.forEach(function (o) { var mt = DATA.statuses[String(o.status)]; if (mt && mt.falloff) fo = mt.falloff; });
        if (fo) {
          /* FightStatusDamageFalloffComponent: damage x (1 - per)^n, n = earlier hits of this root skill on this target */
          var steps = Math.max(0, fallCount - (fo.start - 1));
          if (fo.max > 0) steps = Math.min(steps, fo.max);
          d *= Math.pow(1 - fo.pct, steps);
          fallCount++;
        }
        if (blinded || dodged) d = 0;
        else if (block) d /= bd;
        else if (crit) d *= m;
        if (d > 0) {
          /* Damage() tail: a bonus per step of the target's missing HP, capped, then a share of its max HP */
          if (meE.exstep > 0) {
            var units = Math.floor((foe.s.hp - foe.hp) / foe.s.hp / meE.exstep);
            if (units > 0) d *= 1 + Math.min(meE.exmax || 0, (meE.exunit || 0) * units);
          }
          if (meE.dmgbytargethp) d += meE.dmgbytargethp * foe.s.hp;
        }
        if (foe.shield > 0 && !h.ignoreShield && d > 0) {
          absorbed = Math.min(foe.shield, d); foe.shield -= absorbed; d -= absorbed;
          if (foe.shield <= 0) foe.st.filter(function (x) { return x.meta.shield; }).forEach(function (x) { removeStatus(foe, x); });
        }
        var saved = null;
        if (d > 0 && d >= foe.hp) { saved = deathSave(foe); if (saved) d = Math.max(0, foe.hp - saved.limit); }
        foe.hp -= d; total += d;
        if (rolled) rolled.push({ d: d, crit: crit, block: block, absorbed: absorbed, blinded: blinded, dodged: dodged, at: h.at || 0, saved: !!saved, who: foe.i, hi: hi });
        if (saved) {
          if (events) events.push({ kind: "save", who: foe.i, tag: saved.ch.name });
          if (saved.heal > 0) heal(foe, saved.heal, saved.ch.name);
          firePassive(saved.pv, saved.ch, foe, me, me);
        } else if (d > 0) afterDamage(foe, me);
        if (pick.noHooks || hookDepth >= 4) return;      /* the skill's CanTriggerChild is off, or a hook chain runs too deep */
        hookDepth++;
        var ev = { d: d, absorbed: absorbed, block: block, crit: crit, blinded: blinded, dodged: dodged, ele: pick.ele || "None", skillId: pick.id, isAttack: isAttack };
        /* the attacker's on-hit Charms (Radiant Sear, Blade of Judgment, Shadow Erosion, ...) */
        if (me.alive) procs(me, "hit", foe, foe, function (pv) { return hitMatch(pv, ev, me, foe); });
        /* the victim's on-damaged Charms (Rebound on a block, Counter Blade, Eye for an Eye, ...) */
        if (foe.hp > 0) procs(foe, "damaged", me, me, function (pv) { return hitMatch(pv, ev, foe, me); });
        if (d > 0 && me.alive) eachPassive(me, function (pv, ch) {        /* Blade of Lament: lifesteal on damaging hits */
          if (pv.kind !== "lifesteal" || (pv.onlyAttack && !isAttack)) return;
          var pct = (charmVal(ch, me, "SuckHpByDamage") + charmVal(ch, me, "FixedSuckHp")) / 100;
          if (pct > 0) heal(me, d * pct, ch.name);
        });
        /* Reflective Armor: a shielded target strikes back with a share of the hit, shield-absorbed part included */
        if ((d + absorbed) > 0 && me.alive) eachPassive(foe, function (pv, ch) {
          if (pv.kind !== "reflect" || (pv.needShield && !shielded) || rng() >= pv.rate) return;
          var pct = charmVal(ch, foe, "DamageByDamage") / 100;
          if (pct > 0) directDamage(me, (d + absorbed) * pct, foe, ch.name, false);
        });
        hookDepth--;
      });
      if (fall) fall[foe.i] = fallCount;
      return total;
    }
    function tickEnd(u) {
      u.st.slice().forEach(function (st) {
        if (st.dur > 0) {
          st.dur--;
          if (st.dur === 0) {
            (st.meta.onEnd || []).forEach(function (t) {
              var src = t.source === "Creator" ? ents[st.creator] : u;
              var tgt = t.target === "Creator" ? ents[st.creator] : u;
              if (rng() < (t.byProp ? landChance(t.chance, true, null, eff(src, ents), eff(tgt, ents)) : t.chance))
                fireSkill(t.skill, src, tgt, statusName(st.meta, st.props) + " ends", st.rank, st.level);
            });
            removeStatus(u, st);
          }
        }
      });
      /* grid items count on their creator's rounds (RoundTarget Creator, RoundUpdateTiming End) */
      gridFx = gridFx.filter(function (f) { if (f.creator !== u.i) return true; if (f.dur > 0) f.dur--; return f.dur !== 0; });
      /* a summon's lifespan status (StatusEndComponent.RemoveApplyEntity) counts its own turn ends */
      if (u.summon && u.alive && u.life > 0) {
        u.life--;
        if (u.life === 0) { u.alive = false; u.hp = 0; u.st = []; u.shield = 0; u.gone = true; if (events) events.push({ kind: "expire", who: u.i }); onSummonGone(u); }
      }
    }
    /* statuses that last N of the holder's skill casts (DurationSkillCount) */
    function spendSkillStatuses(u, isAttack) {
      u.st.slice().forEach(function (st) {
        if (!(st.skills > 0)) return;
        if (st.meta.onlyAttack && !isAttack) return;
        st.skills--;
        if (st.skills <= 0) removeStatus(u, st);
      });
    }

    /* ---- geometry per skill: for every aim offset the cells each hit covers, relative to the caster ---- */
    function geo(sk) {
      if (sk._geo) return sk._geo;
      var ec = sk.ec || {};
      var range = (ec.range && ec.range.length) ? ec.range : [[0, 0]];
      var hits = (ec.hits && ec.hits.length) ? ec.hits : [{ cells: [[0, 0]], onSource: false }];
      var entries = [], byOff = {};
      function add(r, dir, flip, flipDep) {
        var perHit = [], all = {}, groups = {};
        hits.forEach(function (h, hi) {
          if (h.child) { perHit.push(null); return; }
          if (h.rnd) {
            var g = groups[h.rnd.g];
            if (!g) {
              g = groups[h.rnd.g] = { pool: [], subs: [], cfg: h.rnd };
              (h.rnd.cells || [[0, 0]]).forEach(function (c) { var w = turn(c, dir, flip); var ox = (h.rnd.onSource ? 0 : r[0]) + w[0], oy = (h.rnd.onSource ? 0 : r[1]) + w[1]; g.pool.push([ox, oy]); all[ox + "," + oy] = 1; });
            }
            var subCells = (h.cells && h.cells.length ? h.cells : [[0, 0]]).map(function (c) { return turn(c, dir, flip); });
            var pk = h.pick || 0;
            g.subs.push({ hi: hi, cells: subCells, pick: pk });
            g.n = Math.max(g.n || 0, pk + 1);
            perHit.push({ rnd: h.rnd.g });
            return;
          }
          var set = {};
          (h.cells && h.cells.length ? h.cells : [[0, 0]]).forEach(function (c) {
            var w = turn(c, dir, flip);
            var ox = (h.onSource ? 0 : r[0]) + w[0], oy = (h.onSource ? 0 : r[1]) + w[1];
            set[ox + "," + oy] = 1; all[ox + "," + oy] = 1;
          });
          perHit.push({ set: set });
        });
        var ei = entries.length;
        entries.push({ r: r, dir: dir, flip: flip, flipDep: flipDep, perHit: perHit, groups: groups });
        Object.keys(all).forEach(function (k) { (byOff[k] = byOff[k] || []).push(ei); });
      }
      range.forEach(function (r) {
        var dir = facing({ x: 0, y: 0 }, { x: r[0], y: r[1] });
        if (r[0] === 0) { add(r, dir, false, true); add(r, dir, true, true); }   /* flip follows the caster's current facing */
        else add(r, dir, r[0] < 0, false);
      });
      sk._geo = { entries: entries, byOff: byOff, hits: hits };
      return sk._geo;
    }
    /* every (aim, targets) a skill can take from `pos` */
    function plans(me, sk, pos, occ) {
      var ec = sk.ec || {};
      var selfish = isAlly(sk);
      var pool = poolFor(me, sk);
      var kind = ec.targetKind || "Pos";
      if (ec.target === "None") {
        /* HitTargetType.None (summons): no unit is aimed at; every reachable aim offset is a plan, and the area,
           the facing and the summon cell still follow the aim */
        var outN = [];
        var g0 = geo(sk);
        g0.entries.forEach(function (e) {
          if (e.flipDep && e.flip !== !!me.flip) return;
          var ax = pos.x + e.r[0], ay = pos.y + e.r[1];
          if (!inGrid(ax, ay)) return;
          if ((kind === "PosCanStand" || kind === "PosSkillDirectionCanStand") && !standable(ax, ay, occ, me)) return;
          outN.push({ aim: { x: ax, y: ay }, dir: e.dir, flip: e.flip, entry: e, perHit: e.perHit.map(function () { return []; }), union: [], onUnit: false, primary: null });
        });
        return outN;
      }
      if (!pool.length) return [];
      /* Stealth: "this unit cannot be selected as the main target for attacks or healing" while another unit of
         the pool can be; it can still sit under an area */
      var aimPool = pool.filter(function (u) { return !stealthed(u); });
      if (!aimPool.length) aimPool = pool;
      var g = geo(sk);
      var taunt = me.taunt && !selfish ? me.taunt : null;
      var offs = pool.map(function (u) { return (u.pos.x - pos.x) + "," + (u.pos.y - pos.y); });
      var cand = {};
      offs.forEach(function (k) { (g.byOff[k] || []).forEach(function (ei) { cand[ei] = 1; }); });
      var out = [];
      Object.keys(cand).forEach(function (ei) {
        var e = g.entries[ei];
        if (e.flipDep && e.flip !== !!me.flip) return;
        var ax = pos.x + e.r[0], ay = pos.y + e.r[1];
        if (ax < 0 || ay < 0 || ax >= GRID.w || ay >= GRID.h) return;
        var unitHere = occ[ax + "," + ay];
        if ((kind === "Entity" || kind === "EntityFollow") && !(unitHere && unitHere.alive && aimPool.indexOf(unitHere) >= 0)) return;
        if ((kind === "PosCanStand" || kind === "PosSkillDirectionCanStand") && !standable(ax, ay, occ, me)) return;
        var perHit = [], seen = {}, union = [];
        function take(u) { if (!seen[u.i]) { seen[u.i] = 1; union.push(u); } }
        for (var hi = 0; hi < e.perHit.length; hi++) {
          var ph = e.perHit[hi], list = [];
          if (ph && ph.set) for (var pi = 0; pi < pool.length; pi++) if (ph.set[offs[pi]]) { list.push(pool[pi]); take(pool[pi]); }
          if (ph && ph.rnd) { var grp = e.groups[ph.rnd]; for (var pj = 0; pj < pool.length; pj++) if (grp.pool.some(function (c) { return c[0] + "," + c[1] === offs[pj]; })) take(pool[pj]); }
          perHit.push(list);
        }
        if (!union.length) return;
        if (aimPool !== pool && !union.some(function (u) { return aimPool.indexOf(u) >= 0; })) return;
        if (taunt && union.indexOf(taunt) < 0) return;
        out.push({ aim: { x: ax, y: ay }, dir: e.dir, flip: e.flip, entry: e, perHit: perHit, union: union, onUnit: !!(unitHere && aimPool.indexOf(unitHere) >= 0),
                   primary: union.slice().sort(function (x, y) { return x.hp / x.s.hp - y.hp / y.s.hp; })[0] });
      });
      return out;
    }
    var DEFAULT_CHAIN = ["PriorGameCharacterType", "BiggerBodyRange", "MoreHitStatusCount", "MoreHitCount", "ShorterMoveDist", "LowerTargetHp", "ShorterEnemyTargetPosDistAndSameDir", "PriorTargetEntityPos"];
    var DEFAULT_LAST = ["PriorGameCharacterType", "BiggerBodyRange", "MoreHitStatusCount", "MoreHitCount", "SaferPos", "LowerTargetHp", "ShorterEnemyTargetPosDistAndSameDir", "PriorTargetEntityPos"];
    function isSummon(sk) { return ((sk.ec && sk.ec.hits) || []).some(function (h) { return h.summon; }); }
    function isDamaging(sk) { var t = (sk.ec || {}).skillType; return (!t || t === "Attack") && !isAlly(sk); }
    /* taunt: "Taunted enemies ... approach the caster when using damaging Techniques", so a taunted
       fighter never picks the keep-distance ordering for one, and closes on the taunter to break ties */
    function chainOf(sk, last, taunted) {
      var ec = sk.ec || {};
      if (taunted && isDamaging(sk)) {
        var base = (ec.aiPriority && ec.aiPriority.length) ? ec.aiPriority : DEFAULT_CHAIN;
        return base.filter(function (k) { return k !== "SaferPos"; }).concat(["ApproachRidiculer"]);
      }
      if (last && !ec.dontKeepDistance) return (ec.aiLast && ec.aiLast.length) ? ec.aiLast : DEFAULT_LAST;
      return (ec.aiPriority && ec.aiPriority.length) ? ec.aiPriority : DEFAULT_CHAIN;
    }
    function scoreOf(chain, me, cell, pl) {
      var enemies = enemiesOf(me), v = [];
      for (var i = 0; i < chain.length; i++) {
        var k = chain[i], x = 0;
        if (k === "MoreHitCount") x = pl.union.length;
        else if (k === "ShorterMoveDist" || k === "LeastMoveNearTarget") x = -cell.d;
        else if (k === "LowerTargetHp") x = pl.union.length ? -Math.min.apply(null, pl.union.map(function (u) { return u.hp / u.s.hp; })) : 0;
        else if (k === "ShorterTargetDist" || k === "ShorterMovedTargetDist" || k === "ShorterEnemyTargetPosDistAndSameDir") x = pl.union.length ? -dist(cell, pl.aim) : (enemies.length ? -Math.min.apply(null, enemies.map(function (u) { return dist(pl.aim, u.pos); })) : 0);
        else if (k === "SaferPos") x = enemies.length ? Math.min.apply(null, enemies.map(function (u) { return dist(cell, u.pos); })) : 0;
        else if (k === "ApproachRidiculer") x = me.taunt ? -dist(cell, me.taunt.pos) : 0;
        else if (k === "PriorTargetEntityPos") x = pl.onUnit ? 1 : 0;
        else if (k === "PriorCloserTeammate") { var mates = alliesOf(me).filter(function (u) { return u !== me; }); x = mates.length ? -Math.min.apply(null, mates.map(function (u) { return dist(cell, u.pos); })) : 0; }
        else if (k === "PriorRandom") x = rng();
        v.push(x);
      }
      return v;
    }
    function better(a, b) { for (var i = 0; i < a.length; i++) { if (a[i] > b[i]) return true; if (a[i] < b[i]) return false; } return false; }
    function plan(me, sk, pos, occ, last) {
      var all = plans(me, sk, pos, occ), chain = chainOf(sk, last, !!me.taunt), best = null, cell = { x: pos.x, y: pos.y, d: 0 };
      all.forEach(function (pl) { var sc = scoreOf(chain, me, cell, pl); if (!best || better(sc, best.score)) { best = pl; best.score = sc; } });
      return best;
    }
    function reachable(u, steps) {
      var occ = unitAt(), out = {}, key = u.pos.x + "," + u.pos.y;
      out[key] = { x: u.pos.x, y: u.pos.y, d: 0, from: null };
      var frontier = [out[key]];
      while (frontier.length) {
        var c = frontier.shift();
        if (c.d >= steps) continue;
        [[1, 0], [-1, 0], [0, 1], [0, -1]].forEach(function (d) {
          var nx = c.x + d[0], ny = c.y + d[1], k = nx + "," + ny;
          if (!inGrid(nx, ny) || out[k]) return;
          var v = occ[k];
          if (v && v !== u) return;
          out[k] = { x: nx, y: ny, d: c.d + 1, from: c };
          frontier.push(out[k]);
        });
      }
      return out;
    }
    function planWithMove(u, sk, reach, occ, last) {
      var chain = chainOf(sk, last, !!u.taunt);
      var pool = poolFor(u, sk);
      var noTarget = (sk.ec || {}).target === "None";          /* summons: no unit to reach, any cell will do */
      if (!pool.length && !noTarget) return null;
      var fp = geo(sk).byOff;
      var cells = Object.keys(reach).map(function (k) { return reach[k]; });
      var cand = [];
      cells.forEach(function (c) {
        var n = 0;
        for (var i = 0; i < pool.length; i++) { var v = pool[i]; if (v === u || fp[(v.pos.x - c.x) + "," + (v.pos.y - c.y)]) n++; }
        if (n || noTarget) cand.push({ c: c, n: n });
      });
      if (!cand.length) return null;
      cand.sort(function (x, y) { return (y.n - x.n) || (x.c.d - y.c.d); });
      var occ2 = {};
      Object.keys(occ).forEach(function (x) { occ2[x] = occ[x]; });
      delete occ2[u.pos.x + "," + u.pos.y];
      var best = null, bestHits = 0, moreHitsFirst = chain[0] === "MoreHitCount";
      for (var i = 0; i < cand.length; i++) {
        var c = cand[i].c;
        if (moreHitsFirst && best && cand[i].n < bestHits) break;
        var k = c.x + "," + c.y, saved = u.pos;
        occ2[k] = u; u.pos = { x: c.x, y: c.y };
        var all = plans(u, sk, c, occ2);
        u.pos = saved; delete occ2[k];
        for (var j = 0; j < all.length; j++) {
          var sc = scoreOf(chain, u, c, all[j]);
          if (!best || better(sc, best.score)) { best = { plan: all[j], cell: c, score: sc }; best.plan.score = sc; bestHits = all[j].union.length; }
        }
      }
      return best;
    }
    function walkTo(u, cell) {
      var from = { x: u.pos.x, y: u.pos.y };
      u.pos = { x: cell.x, y: cell.y };
      var n = cell.d || dist(from, cell);
      if (n) afterMoved(u, from);
      return n;
    }
    function approach(u, reach) {
      var goal = u.taunt || nearest(u, enemiesOf(u));
      if (!goal) return 0;
      var best = null, bd = dist(u.pos, goal.pos);
      Object.keys(reach).forEach(function (k) { var c = reach[k]; var d = dist(c, goal.pos); if (d < bd || (d === bd && best && c.d < best.d)) { bd = d; best = c; } });
      return best ? walkTo(u, best) : 0;
    }
    function moveBudget(u) { return rooted(u) ? 0 : (u.s.move || GRID.defaultMove); }

    /* ---- summoned creatures (FightHitSummon with a SummonId) ---- */
    /* BattleFormulaHandler.CalcSummonMonsterInheritProp: fixed props = the level curve x rank multiplier x the
       summon_monster_fix_prop factor, at the summoning skill's rank and level; inherited props = the caster's prop
       x summon_monster_add_prop share x summon_rank_additive_factor[rank]. "Summons cannot receive any stat boosts",
       so the caster's unbuffed sheet is the source */
    function summonSheet(cs, def, rank, level) {
      var s = { rank: cs.rank, vuln: 0, fadd: 0, fred: 0, fvuln: 0, aff: {}, aegis: {} };
      var rf = (def.rankFactor || {})[String(rank)] || {};
      function inh(prop) { var a = def.add[prop]; if (a === undefined) return 0; var f = rf[prop]; return a * (f === undefined ? 1 : f); }
      var fields = C.propFields || {};
      Object.keys(cs).forEach(function (k) { if (typeof cs[k] === "number") s[k] = 0; });
      Object.keys(fields).forEach(function (p) { var fld = fields[p]; if (typeof cs[fld] === "number") s[fld] = cs[fld] * inh(p); });
      ELES.forEach(function (e) { s.aff[e] = (cs.aff[e] || 0) * inh(e + "DamageAdd"); s.aegis[e] = (cs.aegis[e] || 0) * inh(e + "DamageReduce"); });
      var fx = (def.fixRows || {})[String(rank)] || {};
      Object.keys(fx).forEach(function (k) { var fld = fields[k]; if (fld) s[fld] = (s[fld] || 0) + curveValue(fx[k], rank, level, cs.rank.name); });
      s.move = def.moveDist || 0;
      s.hp = Math.max(1, s.hp || 0); s.atk = Math.max(1, s.atk || 0); s.spd = Math.max(1, s.spd || 0);
      return s;
    }
    function spawnSummon(caster, sm, x, y, rank, level, tag) {
      var def = sm.def; if (!def) return null;
      var occ = unitAt();
      var cell = standable(x, y, occ, null) ? { x: x, y: y } : nearestStandable(x, y, occ, null);
      if (!cell) return null;
      var s = summonSheet(caster.s, def, rank, level);
      s.slevel = level;
      function bindS(list) { return (list || []).map(function (rec) { return { sk: rec, rank: rank, level: level, id: rec.id, name: rec.name }; }); }
      var techs = bindS(def.skills), charms = bindS(def.passives);
      while (techs.length < 4) techs.push(null);
      var u = { i: ents.length, side: caster.side, name: def.name, cls: "Summon", f: { name: def.name, cls: "Summon", sheet: s, techs: [], charms: [] }, s: s,
                techs: techs, charms: charms, hp: s.hp, shield: 0, st: [], cd: openingCds(techs, charms), uses: techs.map(function () { return 0; }),
                /* SummonImmediateRound: it acts right after the caster's turn (same time, later in the queue) */
                t: caster.t, turns: 0, pos: { x: cell.x, y: cell.y }, alive: true, charmFired: {}, techCasts: 0, order: (caster.order || 0) + 0.5,
                taunt: null, flip: caster.flip, summon: true, owner: caster.i, life: sm.lifespan || 0, blocks: !!def.blocks, gone: false,
                destroyOnDie: def.destroyOnDie !== false };
      ents.push(u);
      (sm.initStatuses || []).forEach(function (sid) { applyStatus(u, sid, caster, rank, level, null, true); });
      if (events) events.push({ kind: "summon", who: caster.i, unit: u.i, name: def.name, to: [cell.x, cell.y] });
      /* FightStatusHitSummonComponent with Create: the owner's Charm puts its status on the new summon (Summoner's Frenzy, Soul Spark) */
      eachPassive(caster, function (pv, ch) {
        if (pv.kind !== "summonHook" || !pv.create || rng() >= pv.rate) return;
        (pv.statuses || []).forEach(function (o) {
          var st = applyStatus(u, o.status, caster, ch.rank, ch.level);
          if (st && events) events.push({ kind: "status", who: u.i, name: statusName(st.meta, st.props), tag: ch.name });
        });
      });
      auraSettle();
      return u;
    }
    /* FightStatusHitSummonComponent with Remove: a skill fired where the owner's summon fell or faded (Soul Impact) */
    function onSummonGone(u) {
      var owner = ents[u.owner]; if (!owner || !owner.alive) return;
      eachPassive(owner, function (pv, ch) {
        if (pv.kind !== "summonHook" || !pv.remove || rng() >= pv.rate) return;
        (pv.triggers || []).forEach(function (t) { fireSkillArea(t.skill, owner, { x: u.pos.x, y: u.pos.y }, ch.name, ch.rank, ch.level); });
      });
      auraSettle();
    }
    /* an aura (FightStatusMoveRangeComponent, TargetCloseTriggerStatus): units of the target kind inside the holder's
       range carry its status; checked when something is summoned or moves */
    function setKept(w, o, ch, on) {
      var have = w.st.filter(function (x) { return x.id === o.status; })[0];
      if (on && !have) { var st = applyStatus(w, o.status, w, ch.rank, ch.level); if (st && events) events.push({ kind: "status", who: w.i, name: statusName(st.meta, st.props), tag: ch.name }); }
      else if (!on && have) removeStatus(w, have);
    }
    function auraSettle() {
      ents.forEach(function (w) {
        if (!w.alive) return;
        eachPassive(w, function (pv, ch) {
          if (pv.kind === "enemyCount") {
            /* TargetCountAffectStatusOwnerSetting: met while the enemies inside the range number <= TargetCount */
            var n = 0;
            ents.forEach(function (u) {
              if (u === w || !u.alive || u.gone) return;
              if (pv.target === "Enemy" ? u.side === w.side : pv.target === "Friend" || pv.target === "FriendNotMe" ? u.side !== w.side : false) return;
              if ((pv.cells || []).some(function (c) { return w.pos.x + c[0] === u.pos.x && w.pos.y + c[1] === u.pos.y; })) n++;
            });
            var met = n <= (pv.count || 0);
            (pv.met || []).forEach(function (o) { setKept(w, o, ch, met); });
            (pv.notMet || []).forEach(function (o) { setKept(w, o, ch, !met); });
            return;
          }
          if (pv.kind === "summonCount") {
            /* FightStatusRoleSummonCountComponent: the status stays while the wearer has a summon on the field */
            var has = ents.some(function (u) { return u.summon && u.alive && !u.gone && u.owner === w.i; });
            (pv.statuses || []).forEach(function (o) { setKept(w, o, ch, has); });
            return;
          }
          if (pv.kind !== "aura") return;
          ents.forEach(function (u) {
            if (!u.alive || u === w) return;
            if (pv.target === "FriendNotMe" || pv.target === "Friend") { if (u.side !== w.side) return; }
            else if (pv.target === "Enemy") { if (u.side === w.side) return; }
            var inside = (pv.cells || []).some(function (c) { return w.pos.x + c[0] === u.pos.x && w.pos.y + c[1] === u.pos.y; });
            if (!inside) return;
            (pv.statuses || []).forEach(function (o) {
              if (u.st.some(function (x) { return x.id === o.status; })) return;
              if (rng() >= (o.chance === undefined ? 1 : o.chance)) return;
              var st = applyStatus(u, o.status, w, ch.rank, ch.level);
              if (st && events) events.push({ kind: "status", who: u.i, name: statusName(st.meta, st.props), tag: ch.name });
            });
          });
        });
      });
    }

    /* ---- one cast ---- */
    function cast(t, slot, pl) {
      var pick = t.sk, rolled = [], total = 0, targets = {};
      var ec = pick.ec || {};
      var isAttack = !ec.skillType || ec.skillType === "Attack";
      var selfish = isAlly(pick);
      var aim = pl.aim, dir = pl.dir;
      if (ec.flipSource !== false) me.flip = flipFor(me.pos, aim, me.flip);
      var flip = pl.flip;
      if (slot >= 0) procs(me, "skillStart", pl.primary, pl.primary, function (pv) { return !pv.elements || !pv.elements.length || pv.elements.indexOf(pick.ele) >= 0; });
      /* the caster's own displacement (SourceMoveList) comes first */
      (ec.sourceMove || []).forEach(function (cfg) { forceMove(me, cfg, me, aim, dir, flip, pick.name); });
      var occ = unitAt(), pool = poolFor(me, pick);
      var g = geo(pick), e = pl.entry, fall = {};
      var meE = eff(me, ents);
      /* Curse Resonance / Pursuit of Victory: an outgoing bonus sized by the target's debuffs, per target */
      function boostFor(foe) {
        var add = 0;
        eachPassive(me, function (pv, ch) {
          if (pv.kind !== "dmgAdd" || (pv.onlyAttack && !isAttack)) return;
          var n = 1;
          if (pv.needTargetStatus) {
            var ids = {}, cnt = 0;
            foe.st.forEach(function (x) { if ((pv.anyTypes || []).indexOf(x.meta.type) >= 0) { cnt++; ids[x.id] = 1; } });
            n = pv.countType === "EntityClassIdCount" ? Object.keys(ids).length : cnt;
            if (!n) return;
            if (!pv.scaleByCount) n = 1;
            if (pv.maxCount > 0) n = Math.min(n, pv.maxCount);
            n *= pv.unit || 1;
          }
          add += charmVal(ch, me, "StatusDmgAddPer") / 100 * n;
        });
        /* FightStatusHitApplyDamageComponent: one unit per HpDecreaseUnit of the target's max HP missing, at most MaxHpScale */
        eachPassive(me, function (pv, ch) {
          if (pv.kind !== "dmgAddByHp" || !(pv.unit > 0)) return;
          var missing = 1 - foe.hp / foe.s.hp, n = Math.floor(missing / pv.unit + 1e-9);
          if (pv.maxScale > 0) n = Math.min(n, pv.maxScale);
          if (n > 0) add += charmVal(ch, me, pv.prop || "StatusDmgAddPer") / 100 * n;
        });
        return add;
      }
      /* the target's own reduction stage against this attacker: Iron Will (attacker taunted), Aberrancy (attacker debuffed) */
      function reduceFor(foe) {
        var red = 0;
        eachPassive(foe, function (pv, ch) {
          if (pv.kind === "dmgProcess") {
            if (pv.checkEnemy && me.side === foe.side) return;
            if ((pv.sourceActions || []).length && !me.st.some(function (x) { return pv.sourceActions.indexOf(x.meta.action) >= 0; })) return;
            if (pv.reduceProp) red += charmVal(ch, foe, pv.reduceProp) / 100;
          } else if (pv.kind === "dmgReduceByStatus") {
            if (pv.skillTargetType === "Enemy" && me.side === foe.side) return;
            var n = 1;
            if (pv.needStatus) {
              var cnt = 0; me.st.forEach(function (x) { if ((pv.anyTypes || []).indexOf(x.meta.type) >= 0) cnt++; });
              if (!cnt) return;
              n = pv.scaleByCount ? cnt : 1;
              if (pv.maxCount > 0) n = Math.min(n, pv.maxCount);
              n *= pv.unit || 1;
            }
            red += charmVal(ch, foe, pv.prop || "StatusDmgReducePer") / 100 * n;
          }
        });
        return red;
      }
      var rows = pick.id === 0 ? {} : (pick.r[String(t.rank)] || {});
      var partsCache = {};
      function partsFor(foe) {
        if (partsCache[foe.i]) return partsCache[foe.i];
        var foeE = eff(foe, ents), mE = meE;
        var extra = boostFor(foe);
        if (extra) { mE = {}; Object.keys(meE).forEach(function (k) { mE[k] = meE[k]; }); mE.sadd = (meE.sadd || 0) + extra; }
        var red = reduceFor(foe);
        if (red) { var fE = {}; Object.keys(foeE).forEach(function (k) { fE[k] = foeE[k]; }); fE.sred = (foeE.sred || 0) + red; foeE = fE; }
        return partsCache[foe.i] = { E: foeE, mE: mE, parts: hitParts(mE, foeE, pick, rows, t.level) };
      }
      var hitTargets = {};      /* hit index -> units it damaged (for child skills) */
      function applyHit(hi, foe, p, mE, foeE, hrow, tag, gate, rankUsed, levelUsed) {
        if (!foe.alive) return 0;
        var h = p.hits[hi]; if (!h) return 0;
        var here = 0;
        if (h.d > 0 && !selfish) {
          var r0 = [];
          here = landHits({ hits: [h] }, me, foe, mE, foeE, { ec: ec, gov: gate, name: pick.name, id: pick.id, ele: pick.ele, noHooks: ec.canTriggerChild === false }, r0, rankUsed, levelUsed, fall);
          r0.forEach(function (x) { x.hi = hi; rolled.push(x); });
          total += here;
        }
        var blindedHit = rolled.some(function (x) { return x.hi === hi && x.who === foe.i && (x.blinded || x.dodged); });
        if (!blindedHit) h.on.forEach(function (o) {
          var meta = DATA.statuses[String(o.status)];
          if (!meta || meta.falloff) return;
          var tgt = (o.target === "DamageTarget" || selfish) ? foe : me;
          if (!tgt.alive) return;
          var chance = landChance(o.chance, o.byProp, meta.type, mE, foeE);
          tgt.st.forEach(function (x) {
            var bo = x.meta.boosts;
            if (bo && bo.actions.indexOf(meta.action) >= 0 && x.meta.props) {
              var r = x.meta.props[String(x.rank)] || {};
              if (r[bo.prop]) chance += curveValue(r[bo.prop], x.rank, x.level, ents[x.creator].s.rank.name) / 100;
            }
          });
          if (rng() < chance) {
            var st = applyStatus(tgt, o.status, me, rankUsed, levelUsed);
            if (st && meta.shield) { var amt = shieldSize(meta, me, tgt, rankUsed, levelUsed); if (amt > 0) tgt.shield = Math.max(tgt.shield, amt); }
            if (st && events) events.push({ kind: "status", who: tgt.i, name: statusName(meta) });
          }
        });
        (hitTargets[hi] = hitTargets[hi] || []).push(foe);      /* a child skill is cast on every unit the hit covers */
        var hc = g.hits[hi];
        if (hc && hc.move && !hc.child && foe.alive && rng() < (hc.move.chance === undefined ? 1 : hc.move.chance)) forceMove(foe, hc.move, me, aim, dir, flip, pick.name);
        if (hc && hc.disperse && foe.alive && rng() < (hc.disperse.chance === undefined ? 1 : hc.disperse.chance)) disperseStatuses(foe, hc.disperse);
        kill(foe, me);
        return here;
      }
      /* fixed hits, random groups and child skills, in prefab order */
      var doneGroups = {};
      g.hits.forEach(function (h, hi) {
        if (h.child) {
          /* a skill cast on every unit the parent hit damaged: its own rows, statuses and forced move */
          var parents = hitTargets[h.child.of] || [];
          if (!parents.length || rng() >= (h.child.chance === undefined ? 1 : h.child.chance)) return;
          var crow = (h.childRows || {})[String(t.rank)] || {};
          var fakeChild = { id: h.child.eid, name: pick.name, ele: h.childEle || pick.ele, ec: { hits: [h], skillType: "Attack", target: ec.target }, hits: 1, r: h.childRows || {}, pvp: h.childPvp || 10000, gov: h.childGov !== false };
          parents.forEach(function (foe) {
            if (!foe.alive) return;
            var foeE = eff(foe, ents);
            var cp = hitParts(meE, foeE, fakeChild, crow, t.level);
            if (cp.heal) { heal(foe, cp.heal, pick.name); }
            else if (cp.hits.length && cp.hits[0].d > 0) {
              var r1 = [];
              var dd = landHits({ hits: [cp.hits[0]] }, me, foe, meE, foeE, fakeChild, r1, t.rank, t.level, fall);
              r1.forEach(function (x) { x.hi = hi; rolled.push(x); });
              total += dd;
            }
            h.on.forEach(function (o) {
              var meta = DATA.statuses[String(o.status)]; if (!meta || meta.falloff) return;
              if (rng() < landChance(o.chance, o.byProp, meta.type, meE, foeE)) { var st = applyStatus(foe, o.status, me, t.rank, t.level); if (st && events) events.push({ kind: "status", who: foe.i, name: statusName(meta) }); }
            });
            if (h.move && foe.alive && rng() < (h.move.chance === undefined ? 1 : h.move.chance)) forceMove(foe, h.move, me, aim, dir, flip, pick.name);
            targets[foe.i] = 1;
            kill(foe, me);
          });
          return;
        }
        if (h.rnd) {
          if (doneGroups[h.rnd.g]) return;
          doneGroups[h.rnd.g] = 1;
          var grp = e.groups[h.rnd.g], cfg = grp.cfg;
          /* FightHitRandomTargetComponent: one pick per HitCfg with replacement from the pool cells */
          var cellsAll = grp.pool.map(function (c) { return { x: me.pos.x + c[0], y: me.pos.y + c[1] }; }).filter(function (c) { return c.x >= 0 && c.y >= 0 && c.x < GRID.w && c.y < GRID.h; });
          function occupied() { return cellsAll.filter(function (c) { var u = occ[c.x + "," + c.y]; return u && u.alive && pool.indexOf(u) >= 0; }); }
          var usedTargets = {}, usedCells = {};
          for (var k = 0; k < (grp.n || 1); k++) {
            var occNow = occupied();
            var need = k < (cfg.minHits || 0) || !cfg.allowEmpty;
            var from = need ? occNow : cellsAll;
            if (cfg.notSameTarget) from = from.filter(function (c) { var u = occ[c.x + "," + c.y]; return !u || !usedTargets[u.i]; });
            if (cfg.notSameGrid) from = from.filter(function (c) { return !usedCells[c.x + "," + c.y]; });
            if (!from.length) { if (need && cellsAll.length && cfg.allowEmpty) from = cellsAll; else continue; }
            var c = from[Math.floor(rng() * from.length)];
            usedCells[c.x + "," + c.y] = 1;
            /* every hit this pick expands to lands around the picked cell */
            grp.subs.filter(function (sb) { return sb.pick === k; }).forEach(function (sub) {
              sub.cells.forEach(function (w) {
                var u = occ[(c.x + w[0]) + "," + (c.y + w[1])];
                if (!u || !u.alive || pool.indexOf(u) < 0) return;
                usedTargets[u.i] = 1;
                var pf = partsFor(u);
                applyHit(sub.hi, u, pf.parts, pf.mE, pf.E, rows, pick.name, pick.gov !== false, t.rank, t.level);
                targets[u.i] = 1;
              });
            });
            occ = unitAt();
          }
          return;
        }
        if (h.chained && h.chained.links > 1) {
          /* FightHitChainedComponent: the first strike lands on the aim; each next link picks a random unit of the
             pool within the skill's own reach of the last victim, never one already struck (Repeat off) and never
             straight back (Back off), until the chain runs out or nobody is in reach */
          var first = (pl.perHit[hi] || []).filter(function (u) { return u.alive; })[0];
          var visited = {}, prevU = null, cur = first, hopRange = (ec.range && ec.range.length) ? ec.range : [[0, 0]];
          for (var link = 0; link < h.chained.links && cur; link++) {
            var pfc = partsFor(cur);
            applyHit(hi, cur, pfc.parts, pfc.mE, pfc.E, rows, pick.name, pick.gov !== false, t.rank, t.level);
            targets[cur.i] = 1; visited[cur.i] = 1;
            var from = cur;
            var nxt = pool.filter(function (u) {
              return u.alive && u !== from && (h.chained.repeat || !visited[u.i]) && (h.chained.back || u !== prevU) &&
                hopRange.some(function (r) { return from.pos.x + r[0] === u.pos.x && from.pos.y + r[1] === u.pos.y; });
            });
            prevU = cur; cur = nxt.length ? nxt[Math.floor(rng() * nxt.length)] : null;
          }
          occ = unitAt();
          return;
        }
        (pl.perHit[hi] || []).forEach(function (foe) {
          if (!foe.alive) return;
          var pf = partsFor(foe);
          if (pf.parts.heal && !targets[foe.i]) heal(foe, pf.parts.heal, pick.name);
          applyHit(hi, foe, pf.parts, pf.mE, pf.E, rows, pick.name, pick.gov !== false, t.rank, t.level);
          targets[foe.i] = 1;
        });
        if (h.summon && h.summon.gridItem && h.summon.gridStatuses && h.summon.gridStatuses.length) {
          /* FightHitSummon: every SummonScope cell rolls its own Rate for the grid item and its statuses */
          var origin = h.onSource ? me.pos : aim;
          (h.cells || []).forEach(function (c, ci) {
            var w = turn(c, dir, flip);
            var rate = (h.summon.rates || [])[ci]; if (rate === undefined) rate = h.summon.rate === undefined ? 1 : h.summon.rate;
            if (rng() < rate) placeGrid(origin.x + w[0], origin.y + w[1], h.summon.gridStatuses, me, t.rank, t.level, pick.name);
          });
        } else if (h.summon && h.summon.def) {
          /* FightHitSummon with a SummonId: the creature appears on each SummonScope cell (nearest free cell if taken) */
          var sOrigin = h.onSource ? me.pos : aim;
          (h.cells || []).forEach(function (c, ci) {
            var w2 = turn(c, dir, flip);
            var rate2 = (h.summon.rates || [])[ci]; if (rate2 === undefined) rate2 = h.summon.rate === undefined ? 1 : h.summon.rate;
            if (rng() < rate2) spawnSummon(me, h.summon, sOrigin.x + w2[0], sOrigin.y + w2[1], t.rank, t.level, pick.name);
          });
        } else if (h.summon && (h.summon.creature || (h.summon.pools && h.summon.pools.length))) {
          if (events) events.push({ kind: "info", who: me.i, text: "summons a creature — this creature's data is not exported" });
        }
        occ = unitAt();
      });
      var bl = me.st.filter(function (x) { return x.meta.action === "Blinding"; })[0];
      if (bl && isAttack) removeStatus(me, bl);
      if (slot >= 0) {
        me.cd[slot] = cdOf(t) + 1; me.uses[slot]++; me.techCasts++;
        spendSkillStatuses(me, isAttack);
        procs(me, "skillEnd", pl.primary, pl.primary, function (pv) { return me.techCasts % pv.every === 0; });
      }
      return { rolled: rolled, total: total, targets: Object.keys(targets).map(Number), aim: [aim.x, aim.y] };
    }

    /* ---- the PlayStart phase ---- */
    (function preBattle() {
      var queue = ents.map(function (u) { return u.techs.map(function (t, k) { return t && t.sk.startCast ? k : -1; }).filter(function (k) { return k >= 0; }); });
      var order = ents.slice().sort(function (x, y) { return (x.t - y.t) || (x.i - y.i); });
      for (var tick = 0; tick < 8; tick++) {
        var any = false;
        order.forEach(function (u) {
          if (!queue[u.i].length) return;
          var k = queue[u.i].shift(); any = true;
          me = u;
          if (!me.alive || !enemiesOf(me).length) return;
          me.taunt = null;
          me.st.forEach(function (x) { if (x.meta.action === "Ridicule" && ents[x.creator].alive && ents[x.creator].side !== me.side) me.taunt = ents[x.creator]; });
          events = wantLog ? [] : null;
          var pm = planWithMove(me, me.techs[k].sk, reachable(me, moveBudget(me)), unitAt());
          var moved0 = 0;
          if (!pm) return;
          if (pm.cell.d > 0) { moved0 = walkTo(me, pm.cell); if (events) events.push({ kind: "move", who: me.i, to: [me.pos.x, me.pos.y] }); }
          var r0 = cast(me.techs[k], k, pm.plan);
          if (wantLog) log.push(entry(me, me.techs[k].sk, k, r0.rolled, r0.total, events, "prebattle", 0, moved0, r0.targets));
        });
        if (!any) break;
      }
    })();

    /* ---- the fight ---- */
    var winner = -1, order = 0, rounds = 0;
    while (turns < MAXT) {
      var A = alive(0), B = alive(1);
      var Ap = A.filter(function (u) { return !u.summon; }), Bp = B.filter(function (u) { return !u.summon; });
      if (!Ap.length || !Bp.length) { winner = Ap.length ? 0 : 1; break; }   /* summons carry NotCheckFightResult */
      if (maxRounds > 0 && rounds >= maxRounds) { capped = true; break; }
      me = null;
      A.concat(B).forEach(function (u) { if (!me || u.t < me.t - 1e-9 || (Math.abs(u.t - me.t) < 1e-9 && u.order < me.order)) me = u; });
      turns++; me.turns++; if (!me.summon) rounds++; me.order = ++order;       /* the cap counts player activations */
      events = wantLog ? [] : null; var startEv = events;   /* round-start events ride with the first entry of the turn */
      var moved = 0;
      me.taunt = null;
      me.st.forEach(function (x) { if (x.meta.action === "Ridicule" && ents[x.creator].alive && ents[x.creator].side !== me.side) me.taunt = ents[x.creator]; });
      /* starting a round on a grid item (TryAtStandRound) */
      fxAt(me.pos.x, me.pos.y).forEach(function (f) { if (f.meta.moveNear.onStand) fireGrid(f, me); });
      auraSettle();

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

      var casts = 0, sub = 0;
      if (skip) {
        if (wantLog) log.push(entry(me, null, -1, [], 0, events, skip.meta.action, 0, moved));
      } else {
        var occ = unitAt(), reach = reachable(me, moveBudget(me));
        var ready = [];
        me.techs.forEach(function (t, k) {
          if (!t || me.cd[k] !== 0) return;
          var lim = t.sk.ec ? t.sk.ec.limitedTimes : -1;
          if (lim > 0 && me.uses[k] >= lim) return;
          /* "ally-targeting Techniques (grant buffs, healing, shields, etc.) are disabled while taunted";
             "Summoning Techniques remain available" */
          if (me.taunt && isAlly(t.sk) && !isSummon(t.sk)) return;
          ready.push(k);
        });
        for (var ri = 0; ri < ready.length && me.alive; ri++) {
          var k = ready[ri], cand = me.techs[k], last = ri === ready.length - 1;
          if (!enemiesOf(me).length) break;
          var pm = planWithMove(me, cand.sk, reach, occ, last);
          if (!pm) continue;
          events = wantLog ? (startEv && startEv.length ? startEv.splice(0) : []) : null;
          var hop = 0;
          if (pm.cell.d > 0) {
            hop = walkTo(me, pm.cell); moved += hop;
            if (events) events.push({ kind: "move", who: me.i, to: [me.pos.x, me.pos.y] });
          }
          var r = cast(cand, k, pm.plan);
          casts++;
          if (wantLog) log.push(entry(me, cand.sk, k, r.rolled, r.total, events, null, sub++, hop, r.targets));
          occ = unitAt(); reach = reachable(me, moveBudget(me));
        }
        if (casts === 0 && me.alive && enemiesOf(me).length) {
          /* nothing castable from anywhere in reach: there is no basic attack in the client. Whether an idle
             fighter walks is server-side; this walks toward the nearest enemy (or the taunter) and says so */
          events = wantLog ? (startEv && startEv.length ? startEv.splice(0) : []) : null;
          var hop0 = approach(me, reach); moved += hop0;
          if (hop0 && events) events.push({ kind: "move", who: me.i, to: [me.pos.x, me.pos.y] });
          if (wantLog) log.push(entry(me, null, -1, [], 0, events, hop0 ? "moved" : "idle", 0, hop0));
        }
      }
      procs(me, "roundEnd", null, me);
      tickEnd(me);
      me.t += interval(eff(me, ents));
    }
    if (winner < 0 && turns >= MAXT) capped = true;
    function entry(u, pick, slot, rolled, total, ev, note, sub, moved, targets) {
      return { t: Math.round(u.t), who: u.i, side: u.side, slot: slot, sub: sub || 0,
               skill: pick ? (note === "prebattle" ? pick.name + " (before battle)" : pick.name) : (note === "start" ? "—" : note === "moved" ? "no Technique ready — closes in" : note === "idle" ? "no Technique ready" : note + " — no action"),
               skillId: pick ? pick.id : 0, ele: pick ? pick.ele : "None", hits: rolled, dmg: total, targets: targets || [],
               dur: pick && pick.ec && pick.ec.dur ? pick.ec.dur : 0.8, events: ev || [], turn: u.turns, note: note, moved: moved || 0,
               hp: ents.map(function (x) { return Math.max(0, x.hp); }), sh: ents.map(function (x) { return Math.round(x.shield); }),
               pos: ents.map(function (x) { return [x.pos.x, x.pos.y]; }),
               fx: gridFx.map(function (f) { return [f.x, f.y, fxLabel(f), f.dur, f.tag]; }),
               st: ents.map(function (x) { return x.st.map(function (y) { return { n: statusName(y.meta, y.props), d: y.dur, s: y.stacks, t: y.meta.type }; }); }) };
    }
    var hpLeft = ents.map(function (u) { return Math.max(0, u.hp); });
    if (winner < 0) {
      var ra = alive(0).filter(function (u) { return !u.summon; }).reduce(function (a, u) { return a + u.hp / u.s.hp; }, 0),
          rb = alive(1).filter(function (u) { return !u.summon; }).reduce(function (a, u) { return a + u.hp / u.s.hp; }, 0);
      winner = ra === rb ? -1 : (ra > rb ? 0 : 1);
    }
    return { winner: winner, capped: capped, turns: turns, log: log, hp: hpLeft, alive: ents.map(function (u) { return u.alive; }),
             units: ents.map(function (u) { return { name: u.name, side: u.side, cls: u.cls, summon: !!u.summon, owner: u.owner, hpMax: u.s.hp }; }) };
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
  var PICK = null;                 /* tapped leaderboard row (fighter id) or token awaiting a cell */
  var VIEW = null;                 /* the window of the map the board shows */
  var OVER = {};                   /* fighter id -> {techs, charms}: a loadout the user changed on the card */

  /* a fighter as the teams use it: the roster entry with the user's loadout laid over it, four slots each */
  function withOverride(base) {
    var o = OVER[base.id], f = {};
    Object.keys(base).forEach(function (k) { f[k] = base[k]; });
    f.techs = (o ? o.techs : base.techs || []).slice(0, 4);
    f.charms = (o ? o.charms : base.charms || []).slice(0, 4);
    while (f.techs.length < 4) f.techs.push(null);
    while (f.charms.length < 4) f.charms.push(null);
    f.edited = !!o;
    return f;
  }
  function byId(id) { var base = ROSTER.filter(function (f) { return f.id === id; })[0]; return base ? withOverride(base) : null; }
  function defaultPositions() {
    POS = [];
    for (var i = 0; i < 8; i++) { var z = GRID.start[i < 4 ? 0 : 1][i % 4]; POS.push({ x: z[0], y: z[1] }); }
  }
  function saveState() {
    try { localStorage.setItem("pw_team", JSON.stringify({ t: TEAM.map(function (t) { return t.map(function (f) { return f ? f.id : null; }); }), p: POS, o: OVER })); } catch (e) {}
  }
  function loadState() {
    try {
      var st = JSON.parse(localStorage.getItem("pw_team") || "null");
      if (!st || !st.t || !st.p || st.p.length !== 8) return false;
      OVER = st.o && typeof st.o === "object" ? st.o : {};
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
  function assign(i, id) {
    var f = byId(id);
    if (!f) return;
    var was = slotOf(id);
    var side = i < 4 ? 0 : 1, prev = fightersFlat()[i];
    if (was >= 0 && was !== i) {
      TEAM[was < 4 ? 0 : 1][was % 4] = prev || null;
      if (prev) POS[was] = inZone(was < 4 ? 0 : 1, POS[was].x, POS[was].y) ? POS[was] : freeCell(was < 4 ? 0 : 1, was);
    }
    TEAM[side][i % 4] = f;
    if (!inZone(side, POS[i].x, POS[i].y) || POS.some(function (p, k) { return k !== i && fightersFlat()[k] && p.x === POS[i].x && p.y === POS[i].y; })) POS[i] = freeCell(side, i);
    PICK = null; saveState(); invalidate();
  }
  function unassign(i) { TEAM[i < 4 ? 0 : 1][i % 4] = null; saveState(); invalidate(); }

  /* ---------- the board ---------- */
  var DRAG = null;
  function playing() { return !!(PLAY && PLAY.playing); }
  function baseView() { return { x0: GRID.view.x0, x1: GRID.view.x1, y0: GRID.view.y0, y1: GRID.view.y1 }; }
  function viewFor(positions) {
    var v = baseView();
    (positions || []).forEach(function (p) { v.x0 = Math.min(v.x0, p[0]); v.x1 = Math.max(v.x1, p[0]); v.y0 = Math.min(v.y0, p[1]); v.y1 = Math.max(v.y1, p[1]); });
    return v;
  }
  function drawBoard(view) {
    view = view || baseView();
    if (VIEW && VIEW.x0 === view.x0 && VIEW.x1 === view.x1 && VIEW.y0 === view.y0 && VIEW.y1 === view.y1) return;
    VIEW = view;
    var b = $("board");
    b.style.gridTemplateColumns = "repeat(" + (view.x1 - view.x0 + 1) + ", 1fr)";
    var h = "";
    for (var y = view.y1; y >= view.y0; y--) for (var x = view.x0; x <= view.x1; x++) {
      var cls = inZone(0, x, y) ? " z0" : inZone(1, x, y) ? " z1" : " out";
      if (BLOCKED[x + "," + y]) cls += " blk";
      h += '<div class="cell' + cls + '" data-x="' + x + '" data-y="' + y + '" title="column ' + (x + 1) + ", row " + (y + 1) + '"></div>';
    }
    b.innerHTML = h;
  }
  function cellAt(x, y) { return document.querySelector('#board .cell[data-x="' + x + '"][data-y="' + y + '"]'); }
  /* a status as a badge above the head: what the game marks with an icon over the unit */
  var BADGE = { Ridicule: ["TAUNT", "ctl"], Stun: ["STUN", "ctl"], Frozen: ["FROZEN", "ctl"], Blind: ["BLIND", "ctl"], Fear: ["FEAR", "ctl"],
                Confusion: ["CONFUSED", "ctl"], Restrict: ["ROOTED", "ctl"], Immobilize: ["ROOTED", "ctl"], SlowAction: ["SLOW", "bad"],
                Poisoned: ["POISON", "bad"], Burn: ["BURN", "bad"], Chill: ["CHILL", "bad"], Damp: ["DAMP", "bad"], Shield: ["SHIELD", "good"],
                Mark: ["MARK", "bad"], Stack: ["STACK", "good"], Buff: ["BUFF", "good"], Debuff: ["DEBUFF", "bad"], Effect: ["EFFECT", "good"] };
  function badgeOf(st) {
    var b = BADGE[st.n];
    if (!b) b = [st.n, (st.t === "Debuff" || st.t === "AbnormalDebuff") ? "bad" : "good"];
    return '<span class="badge ' + b[1] + '" title="' + esc(st.n) + (st.d > 0 ? " · " + st.d + " turn" + (st.d > 1 ? "s" : "") + " left" : "") + '">' + esc(b[0]) + (st.s > 1 ? "×" + st.s : "") + (st.d > 0 ? '<i>' + st.d + '</i>' : "") + '</span>';
  }
  function tokenHtml(f, i, cur) {
    var side = i < 4 ? 0 : 1;
    var hp = cur ? cur.hp[i] : f.sheet.hp, pct = Math.max(0, Math.min(1, hp / f.sheet.hp));
    var dead = cur && !cur.alive[i];
    var sh = cur ? cur.sh[i] : 0;
    var badges = (cur && cur.st[i] && !dead) ? cur.st[i].slice(0, 3).map(badgeOf).join("") : "";
    var taunted = cur && cur.st[i] && cur.st[i].some(function (s) { return s.n === "Ridicule"; });
    return '<div class="token s' + side + (dead ? " down" : "") + (taunted ? " taunted" : "") + '" draggable="' + (cur ? "false" : "true") + '" data-i="' + i + '" title="' + esc(f.name) + '">' +
      '<div class="tstat">' + badges + '</div>' +
      '<span class="tname">' + esc(f.name) + '</span><span class="tcls">' + esc(f.cls) + '</span>' +
      '<span class="thp"><i style="width:' + (pct * 100).toFixed(1) + '%"></i>' + (sh > 0 ? '<b style="width:' + Math.min(100, sh / f.sheet.hp * 100).toFixed(1) + '%"></b>' : "") + '</span>' +
      '<span class="thpn">' + (dead ? "down" : short(hp)) + '</span></div>';
  }
  function placeTokens(cur) {
    drawBoard(cur ? viewFor(cur.pos) : baseView());
    document.querySelectorAll("#board .cell").forEach(function (c) { c.innerHTML = ""; c.classList.remove("from", "aim", "fx"); c.removeAttribute("data-fx"); });
    ((cur && cur.fx) || []).forEach(function (f) {
      var c = cellAt(f[0], f[1]); if (!c) return;
      c.classList.add("fx"); c.setAttribute("data-fx", f[2] + (f[3] > 0 ? " " + f[3] : ""));
      c.title = f[4] + " · " + f[2].toLowerCase() + (f[3] > 0 ? " · " + f[3] + " turn" + (f[3] === 1 ? "" : "s") + " of the caster left" : "");
    });
    fightersFlat().forEach(function (f, i) {
      if (!f) return;
      var p = cur ? { x: cur.pos[i][0], y: cur.pos[i][1] } : POS[i];
      var cell = cellAt(p.x, p.y);
      if (cell) cell.innerHTML = tokenHtml(f, i, cur);
    });
    /* summoned creatures: extra units beyond the eight fighters, drawn while they are on the field */
    if (cur && PLAY && PLAY.sample && PLAY.sample.units) for (var si = fightersFlat().length; si < cur.pos.length; si++) {
      if (!cur.alive[si]) continue;
      var su = PLAY.sample.units[si]; if (!su) continue;
      var sc = cellAt(cur.pos[si][0], cur.pos[si][1]);
      var spct = Math.max(0, Math.min(1, cur.hp[si] / (su.hpMax || 1)));
      if (sc) sc.innerHTML = '<div class="token summon s' + su.side + '" data-i="' + si + '" title="' + esc(su.name) + ' · summoned by ' + esc(unitName(fightersFlat(), su.owner)) + '"><span class="tname">' + esc(su.name) + '</span><span class="thp"><i style="width:' + (spct * 100).toFixed(1) + '%"></i></span></div>';
    }
  }
  function moveToken(i, x, y) {
    var side = i < 4 ? 0 : 1;
    if (!inZone(side, x, y)) return false;
    var occ = -1;
    POS.forEach(function (p, k) { if (k !== i && p.x === x && p.y === y && fightersFlat()[k]) occ = k; });
    if (occ >= 0) { if ((occ < 4) !== (i < 4)) return false; POS[occ] = { x: POS[i].x, y: POS[i].y }; }
    POS[i] = { x: x, y: y };
    saveState(); invalidate();
    return true;
  }
  function boardEvents() {
    var b = $("board");
    b.addEventListener("dragstart", function (ev) {
      var t = ev.target.closest ? ev.target.closest(".token") : null;
      if (!t || playing() || RESULT) { ev.preventDefault(); return; }
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
      if (t) { if (RESULT) return; PICK = { token: parseInt(t.getAttribute("data-i"), 10) }; paintPick(); return; }
      if (c && PICK) {
        var x = +c.getAttribute("data-x"), y = +c.getAttribute("data-y");
        if (PICK.token !== undefined) { moveToken(PICK.token, x, y); PICK = null; paintPick(); }
        else if (PICK.id !== undefined) { dropFromBoard(PICK.id, x, y); PICK = null; paintPick(); }
      }
    });
  }
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
    /* the eight slots are buttons: tap one to swap the skill, clear it, or set its rank and level */
    function sk(list, kind) {
      var out = "";
      for (var k = 0; k < 4; k++) {
        var t = list[k], sc = t ? SKILL[t.id] : null;
        out += sc
          ? '<button type="button" class="sk" data-i="' + i + '" data-kind="' + kind + '" data-k="' + k + '" title="' + esc(sc.name) + ' · rank ' + t.rank + ' · Lv ' + t.level + ' · tap to change">' + iconOf(sc) + '<b>' + t.rank + '</b></button>'
          : '<button type="button" class="sk empty" data-i="' + i + '" data-kind="' + kind + '" data-k="' + k + '" title="Empty ' + (kind === "tech" ? "Technique" : "Charm") + ' slot ' + (k + 1) + ' · tap to pick one">+</button>';
      }
      return out;
    }
    return '<div class="tcard s' + side + '" data-i="' + i + '" draggable="true">' +
      '<div class="thead"><span class="tname">' + esc(f.name) + '</span>' +
      '<span class="tmeta">' + esc(f.cls) + ' · Lv ' + f.level + ' · ' + esc((C.ranks[f.rank] || {}).name || "") + ' · ' + short(f.rating || 0) + ' CR</span>' +
      (f.edited ? '<span class="tedit" title="This loadout differs from the captured one">edited</span>' +
                  '<button type="button" class="trestore" data-i="' + i + '" title="Restore the captured loadout">&#8635;</button>' : '') +
      '<button type="button" class="tremove" data-i="' + i + '" title="Remove">&#10005;</button></div>' +
      '<div class="hpbar small"><div class="hpfill" id="hp' + i + '"></div><div class="shfill" id="sh' + i + '" hidden></div><span class="hptext" id="hpt' + i + '"></span></div>' +
      '<div class="statusrow" id="st' + i + '"></div>' +
      '<div class="tstats"><span>ATK ' + short(s.atk) + '</span><span>DEF ' + short(s.def) + '</span><span>HP ' + short(s.hp) + '</span><span>SPD ' + short(s.spd) + '</span>' +
      '<span>Crit ' + (s.cr * 100).toFixed(1) + '%</span><span>Block ' + (s.blockrate * 100).toFixed(0) + '%</span><span>Move ' + (s.move || GRID.defaultMove) + '</span></div>' +
      '<div class="tskills"><span class="lab">Techniques</span>' + sk(f.techs, "tech") + '</div>' +
      '<div class="tskills"><span class="lab">Charms</span>' + sk(f.charms, "charm") + '</div></div>';
  }

  /* ---------- the loadout picker: swap a slot's skill, clear it, or set its rank and level ---------- */
  var SKP = null;                  /* {i, kind, k}: the slot being edited */
  var TREE = {};
  (C.classTree || []).forEach(function (c) { TREE[c.name] = c; });
  function lineOf(cls) { var out = {}, cur = cls, guard = 0; while (cur && TREE[cur] && guard++ < 10) { out[cur] = true; cur = TREE[cur].pre; } return out; }
  function listOf(f, kind) { return kind === "tech" ? f.techs : f.charms; }
  function padEntries(list) { var o = []; for (var k = 0; k < 4; k++) { var t = list[k]; o.push(t ? [t.id, t.rank || 1, t.level || 1] : null); } return JSON.stringify(o); }
  function setSlot(i, kind, k, entry) {
    var f = fightersFlat()[i]; if (!f) return;
    var techs = f.techs.slice(), charms = f.charms.slice(), list = kind === "tech" ? techs : charms;
    if (entry) list.forEach(function (t, j) { if (t && t.id === entry.id && j !== k) list[j] = null; });   /* one copy of a skill per fighter */
    list[k] = entry;
    var base = ROSTER.filter(function (x) { return x.id === f.id; })[0];
    if (base && padEntries(techs) === padEntries(base.techs || []) && padEntries(charms) === padEntries(base.charms || [])) delete OVER[f.id];
    else OVER[f.id] = { techs: techs, charms: charms };
    TEAM[i < 4 ? 0 : 1][i % 4] = byId(f.id);
    saveState(); invalidate();
  }
  function restoreLoadout(i) {
    var f = fightersFlat()[i]; if (!f) return;
    delete OVER[f.id];
    TEAM[i < 4 ? 0 : 1][i % 4] = byId(f.id);
    saveState(); invalidate();
  }
  function skTitle() {
    var f = fightersFlat()[SKP.i], cur = listOf(f, SKP.kind)[SKP.k], sc = cur ? SKILL[cur.id] : null;
    $("sktitle").textContent = f.name + " · " + (SKP.kind === "tech" ? "Technique" : "Charm") + " slot " + (SKP.k + 1) +
      (sc ? " · now " + sc.name + " (rank " + cur.rank + ", Lv " + cur.level + ")" : " · empty");
  }
  function openSkPick(i, kind, k) {
    var f = fightersFlat()[i]; if (!f) return;
    SKP = { i: i, kind: kind, k: k };
    var cur = listOf(f, kind)[k], others = listOf(f, kind).filter(Boolean);
    var rank = cur ? cur.rank : (others.length ? others[0].rank : 1), level = cur ? cur.level : (others.length ? others[0].level : 1);
    var rl = C.rankLabels || {}, keys = Object.keys(rl).map(Number).sort(function (a, b) { return a - b; });
    if (!keys.length) keys = [rank];
    $("skrank").innerHTML = keys.map(function (r) { return '<option value="' + r + '">' + r + (rl[String(r)] ? ' · ' + esc(rl[String(r)]) : '') + '</option>'; }).join("");
    $("skrank").value = String(rank); $("sklevel").value = level;
    var line = Object.keys(lineOf(f.cls)).sort(function (a, b) { return TREE[b].tier - TREE[a].tier; });
    $("skclass").innerHTML = '<option value="">' + esc(f.cls) + ' line</option>' +
      line.map(function (c) { return '<option value="' + esc(c) + '">' + esc(c) + ' (T' + TREE[c].tier + ')</option>'; }).join("") +
      '<option value="*">Any class</option>';
    $("skfind").value = "";
    $("skele").hidden = kind !== "tech"; $("skele").value = "";
    $("skfind").placeholder = "Search " + (kind === "tech" ? "Techniques" : "Charms") + "\u2026";
    skTitle(); fillSkList();
    $("skpick").showModal(); $("skfind").focus();
  }
  function fillSkList() {
    if (!SKP) return;
    var f = fightersFlat()[SKP.i]; if (!f) return;
    var want = SKP.kind === "tech" ? "Technique" : "Charm";
    var q = ($("skfind").value || "").toLowerCase(), wantCls = $("skclass").value, wantEle = $("skele").value;
    var line = lineOf(f.cls), have = {};
    listOf(f, SKP.kind).forEach(function (t, k) { if (t && k !== SKP.k) have[t.id] = k + 1; });
    var pool = DATA.skills.filter(function (s) {
      if (s.kind !== want) return false;
      if (wantCls === "*") { /* any class */ } else if (wantCls) { if (s.cls !== wantCls) return false; } else if (!line[s.cls]) return false;
      if (wantEle && want === "Technique" && s.ele !== wantEle) return false;
      return !q || s.name.toLowerCase().indexOf(q) >= 0 || s.cls.toLowerCase().indexOf(q) >= 0;
    }).sort(function (a, b) { return ((TREE[b.cls] || {}).tier || 0) - ((TREE[a.cls] || {}).tier || 0) || a.id - b.id; });
    $("skcount").textContent = pool.length + " " + want + (pool.length === 1 ? "" : "s");
    $("sklist").innerHTML = pool.slice(0, 250).map(function (s) {
      var cdrow = s.r && s.r["22"] ? s.r["22"].CD : 0;
      var hits = s.ec && s.ec.hits ? s.ec.hits.length : (s.hits || 1);
      var on = have[s.id];
      return '<button type="button" class="pick' + (on ? " equipped" : "") + '" data-id="' + s.id + '">' +
        '<img src="../assets/skills/skill_' + s.id + '.png" alt="" width="34" height="34" loading="lazy">' +
        '<span class="pn">' + esc(s.name) + '</span>' +
        '<span class="pm">' + esc(s.cls) + ' \u00b7 T' + s.tier +
        (s.kind === "Technique"
          ? ' \u00b7 ' + esc(s.ele) + (hits > 1 ? ' \u00b7 ' + hits + ' hits' : '') + (cdrow ? ' \u00b7 CD ' + cdrow : ' \u00b7 no CD') + (s.startCast === "ai" ? ' \u00b7 casts before battle' : '')
          : ' \u00b7 Charm' + (s.unmodelled && !s.passive ? ' \u00b7 <b>effect not in the sim yet</b>' : '')) +
        (on ? ' \u00b7 <b>in slot ' + on + ' \u2014 picking moves it here</b>' : '') + '</span></button>';
    }).join("") || '<div class="pickempty">Nothing matches.</div>';
  }
  function skPickEvents() {
    $("skfind").addEventListener("input", fillSkList);
    $("skclass").addEventListener("change", fillSkList);
    $("skele").addEventListener("change", fillSkList);
    function rankLevel() {
      if (!SKP) return;
      var f = fightersFlat()[SKP.i], cur = f && listOf(f, SKP.kind)[SKP.k];
      if (!cur) return;
      var rank = parseInt($("skrank").value, 10) || cur.rank, level = Math.max(1, parseInt($("sklevel").value, 10) || cur.level);
      setSlot(SKP.i, SKP.kind, SKP.k, { id: cur.id, rank: rank, level: level });
      skTitle(); fillSkList();
    }
    $("skrank").addEventListener("change", rankLevel);
    $("sklevel").addEventListener("change", rankLevel);
    $("sklist").addEventListener("click", function (ev) {
      var b = ev.target.closest ? ev.target.closest(".pick") : null;
      if (!b || !SKP) return;
      var id = parseInt(b.getAttribute("data-id"), 10);
      if (!SKILL[id]) return;
      setSlot(SKP.i, SKP.kind, SKP.k, { id: id, rank: parseInt($("skrank").value, 10) || 1, level: Math.max(1, parseInt($("sklevel").value, 10) || 1) });
      $("skpick").close();
    });
    $("skclear").addEventListener("click", function () { if (SKP) setSlot(SKP.i, SKP.kind, SKP.k, null); $("skpick").close(); });
    $("skclose").addEventListener("click", function () { $("skpick").close(); });
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
      if (i < 0) {
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
      var sb = ev.target.closest ? ev.target.closest(".tskills .sk") : null;
      if (sb) { openSkPick(+sb.getAttribute("data-i"), sb.getAttribute("data-kind"), +sb.getAttribute("data-k")); return; }
      var rs = ev.target.closest ? ev.target.closest(".trestore") : null;
      if (rs) { restoreLoadout(+rs.getAttribute("data-i")); return; }
      var r = ev.target.closest ? ev.target.closest("#lb .row") : null;
      if (r) { var id = parseInt(r.getAttribute("data-id"), 10); PICK = (PICK && PICK.id === id) ? null : { id: id }; paintPick(); return; }
      var s = ev.target.closest ? ev.target.closest(".tslot, .tcard") : null;
      if (s && PICK && PICK.id !== undefined) { assign(+s.getAttribute("data-i"), PICK.id); }
    });
    $("lbfind").addEventListener("input", drawLb);
    $("fill").addEventListener("click", function () {
      var have = ROSTER.slice(0, 8).map(function (f) { return byId(f.id); });
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
    RESULT = null; stopPlayback(); PLAY = null;
    $("result").hidden = true; $("detail").hidden = true; $("timeline").hidden = true;
    $("play").disabled = true; $("step").disabled = true;
    $("run").disabled = !ready() || !DATA;
    $("combatlog").innerHTML = '<li class="empty">' + (ready() ? "Run the fight, then watch it, step through it, or drag the timeline." : "Fill both teams to run a fight.") + '</li>';
    $("banner").hidden = true;
    VIEW = null; placeTokens(null); drawCards();
  }
  function run() {
    if (!ready() || !DATA) return;
    var F = fightersFlat(), P = POS.map(function (p) { return { x: p.x, y: p.y }; });
    var maxRounds = Math.max(0, parseInt($("maxrounds").value, 10) || 0);
    var sheets = F.map(function (f) { var s = sheetOf(f); s.slevel = f.level; s.skillRanks = f.techs.concat(f.charms).filter(Boolean).map(function (t) { return t.rank; }); return s; });
    var gov = pvpGovernor(sheets);
    var N = 1000, wins = [0, 0, 0], turnsSum = 0, survive = F.map(function () { return 0; });
    var rng = mulberry(12345);
    for (var i = 0; i < N; i++) {
      var r = oneFight(F, P, rng, false, maxRounds, gov.scale);
      wins[r.winner < 0 ? 2 : r.winner]++;
      turnsSum += r.turns;
      r.alive.forEach(function (a, k) { if (a && k < survive.length) survive[k]++; });
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
    $("result").hidden = false; $("detail").hidden = false; $("timeline").hidden = false;
    $("play").disabled = false; $("step").disabled = false;
    PLAY = { sample: R.sample, i: 0, playing: false };
    buildTimeline(R.sample);
    renderLog(R.sample);
    fillTable(R.sample);
    seekTo(0);
  }
  function hitText(h) { return (h.blinded ? "blind" : h.dodged ? "dodge" : short(h.d)) + (h.crit ? " crit" : "") + (h.block ? " blocked" : "") + (h.absorbed ? " (−" + short(h.absorbed) + " shield)" : ""); }
  function fillTable(sample) {
    var F = fightersFlat();
    $("logbody").innerHTML = sample.log.map(function (l) {
      var tg = (l.targets || []).map(function (i) { return esc(unitName(F, i)); }).join(", ");
      return "<tr><td class=num>" + l.t + "</td><td class=num>" + l.turn + "</td><td><span class='dot s" + l.side + "'></span>" + esc(unitName(F, l.who)) + "</td><td>" + esc(l.skill) + (l.moved ? " <span class=hint>(moved " + l.moved + ")</span>" : "") + "</td><td>" + tg + "</td><td>" + l.hits.map(hitText).join(", ") + "</td><td class=num>" + (l.dmg ? short(l.dmg) : "") + "</td></tr>";
    }).join("");
  }

  /* ---------- the timeline and the scene ---------- */
  function unitName(F, i) {
    if (i < F.length && F[i]) return F[i].name;
    var u = PLAY && PLAY.sample && PLAY.sample.units ? PLAY.sample.units[i] : null;
    return u ? u.name : "unit " + i;
  }
  function eventText(F, e) {
    if (e.kind === "summon") return esc(unitName(F, e.who)) + " summons " + esc(e.name) + " at column " + (e.to[0] + 1) + ", row " + (e.to[1] + 1);
    if (e.kind === "expire") return esc(unitName(F, e.who)) + " fades away";
    if (e.kind === "bar") return esc(unitName(F, e.who)) + (e.pct < 0 ? "'s next turn comes " + Math.round(-e.pct * 100) + "% sooner" : "'s next turn comes " + Math.round(e.pct * 100) + "% later");
    if (e.kind === "grid") return esc(e.tag) + " sets column " + (e.x + 1) + ", row " + (e.y + 1) + " on " + esc((e.label || "").toLowerCase());
    if (e.kind === "info") return esc(unitName(F, e.who)) + " " + esc(e.text);
    if (e.kind === "dmg") return esc(unitName(F, e.who)) + " takes " + short(e.amount) + " from " + esc(e.tag);
    if (e.kind === "heal") return esc(unitName(F, e.who)) + " heals " + short(e.amount) + (e.tag ? " (" + esc(e.tag) + ")" : "");
    if (e.kind === "status") return esc(unitName(F, e.who)) + ": " + esc(e.name) + (e.tag ? " (" + esc(e.tag) + ")" : "");
    if (e.kind === "save") return esc(unitName(F, e.who)) + " survives at 1 HP (" + esc(e.tag) + ")";
    if (e.kind === "down") return esc(unitName(F, e.who)) + " is down";
    if (e.kind === "move") return esc(unitName(F, e.who)) + " moves to column " + (e.to[0] + 1) + ", row " + (e.to[1] + 1);
    return "";
  }
  function buildTimeline(sample) {
    var F = fightersFlat(), n = sample.log.length;
    var tr = $("tltrack"), h = "";
    var lastTurn = -1;
    sample.log.forEach(function (l, k) {
      var cls = "seg s" + l.side + (l.turn === 0 ? " pre" : "") + (l.dmg ? " dmg" : "") + (l.turn !== lastTurn && l.sub === 0 ? " newturn" : "");
      lastTurn = l.turn;
      h += '<span class="' + cls + '" data-k="' + (k + 1) + '" title="' + esc(unitName(F, l.who) + ": " + l.skill) + '"></span>';
    });
    tr.innerHTML = h;
    var r = $("tlrange"); r.max = n; r.value = 0;
  }
  function renderLog(sample) {
    var F = fightersFlat();
    $("combatlog").innerHTML = sample.log.map(function (l, k) {
      var tg = (l.targets || []).map(function (i) { return esc(unitName(F, i)); }).join(", ");
      var hits = l.hits.map(function (h) { return (h.blinded ? "blind" : h.dodged ? "dodge" : short(h.d)) + (h.crit ? "!" : "") + (h.block ? " blk" : ""); }).join(" ");
      var ev = l.events.map(function (e) { return eventText(F, e); }).filter(Boolean).join("; ");
      return '<li class="s' + l.side + ' future" data-k="' + (k + 1) + '"><span class="tlk">' + (l.turn === 0 ? "pre" : "t" + l.turn) + '</span> <b>' + esc(unitName(F, l.who)) + "</b> " + esc(l.skill) + (l.moved ? " <span class=hint>(moved " + l.moved + ")</span>" : "") + (tg ? " → " + tg : "") + (hits ? " <span class=hits>" + hits + "</span>" : "") + (l.dmg ? " = " + short(l.dmg) : "") + (ev ? "<br><span class=hint>" + ev + "</span>" : "") + "</li>";
    }).join("");
  }
  /* show the fight as it stood after action k (0 = before the first) */
  function seekTo(k, animate) {
    if (!PLAY) return;
    var log = PLAY.sample.log, n = log.length;
    k = Math.max(0, Math.min(n, k)); PLAY.i = k;
    var F = fightersFlat();
    if (k === 0) {
      F.forEach(function (f, i) { hpSet(i, f.sheet.hp, f.sheet.hp, 0); chips(i, []); });
      VIEW = null; placeTokens(null);
      $("tlcaption").textContent = "Before the first action. Drag the bar, press play, or step.";
    } else {
      var l = log[k - 1], prev = k >= 2 ? log[k - 2] : null;
      F.forEach(function (f, i) { hpSet(i, l.hp[i], f.sheet.hp, l.sh[i]); chips(i, l.st[i]); });
      placeTokens({ hp: l.hp, sh: l.sh, pos: l.pos, st: l.st, fx: l.fx, alive: l.hp.map(function (h) { return h > 0; }) });
      var actor = document.querySelector('#board .token[data-i="' + l.who + '"]');
      if (actor) actor.classList.add("acting");
      (l.targets || []).forEach(function (i) { var t = document.querySelector('#board .token[data-i="' + i + '"]'); if (t) t.classList.add("hit"); });
      if (l.moved && prev) { var fc = cellAt(prev.pos[l.who][0], prev.pos[l.who][1]); if (fc) fc.classList.add("from"); }
      if (animate) floats(l, prev);
      var tg = (l.targets || []).map(function (i) { return unitName(F, i); }).join(", ");
      $("tlcaption").textContent = (l.turn === 0 ? "Before battle" : "Turn " + l.turn) + " · " + unitName(F, l.who) + ": " + l.skill + (tg ? " → " + tg : "") + (l.dmg ? " for " + short(l.dmg) : "") + " · " + k + " / " + n;
    }
    $("tlrange").value = k;
    document.querySelectorAll("#tltrack .seg").forEach(function (s) { var sk = +s.getAttribute("data-k"); s.classList.toggle("done", sk <= k); s.classList.toggle("now", sk === k); });
    document.querySelectorAll("#combatlog li").forEach(function (li) { var lk = +li.getAttribute("data-k"); li.classList.toggle("future", lk > k); li.classList.toggle("now", lk === k); });
    /* keep the current line visible inside the log box only; never scroll the page itself */
    var cur = document.querySelector('#combatlog li[data-k="' + k + '"]'), box = $("combatlog");
    if (cur) {
      var top = cur.offsetTop, bottom = top + cur.offsetHeight;
      if (top < box.scrollTop || bottom > box.scrollTop + box.clientHeight) box.scrollTop = Math.max(0, top - box.clientHeight / 2 + cur.offsetHeight / 2);
    }
    $("banner").hidden = !(k === n);
    if (k === n) $("banner").textContent = PLAY.sample.winner < 0 ? "Undecided at the round cap" : SIDE_NAME[PLAY.sample.winner] + " wins";
  }
  /* floating numbers over the tokens for one action */
  function floats(l, prev) {
    var F = fightersFlat(), per = {};
    l.events.forEach(function (e) {
      if (e.kind === "dmg") per[e.who] = (per[e.who] || []).concat(["−" + short(e.amount)]);
      if (e.kind === "heal") per[e.who] = (per[e.who] || []).concat(["+" + short(e.amount)]);
      if (e.kind === "status") per[e.who] = (per[e.who] || []).concat([e.name]);
      if (e.kind === "down") per[e.who] = (per[e.who] || []).concat(["DOWN"]);
    });
    if (prev) F.forEach(function (f, i) { var d = prev.hp[i] - l.hp[i]; if (d > 0 && !(per[i] || []).some(function (x) { return x.charAt(0) === "−"; })) per[i] = (per[i] || []).concat(["−" + short(d)]); });
    Object.keys(per).forEach(function (i) {
      var cell = document.querySelector('#board .token[data-i="' + i + '"]');
      if (!cell) return;
      var wrap = document.createElement("div"); wrap.className = "floats";
      per[i].slice(0, 3).forEach(function (txt, k) {
        var s = document.createElement("span"); s.className = "float" + (txt.charAt(0) === "+" ? " good" : txt.charAt(0) === "−" ? " bad" : " eff"); s.textContent = txt; s.style.animationDelay = (k * 0.15) + "s"; wrap.appendChild(s);
      });
      cell.appendChild(wrap);
    });
  }
  function later(fn, ms) { var t = setTimeout(fn, Math.max(0, ms)); TIMERS.push(t); return t; }
  function clearTimers() { TIMERS.forEach(clearTimeout); TIMERS = []; }
  function speedMs() { return parseInt($("speed").value, 10); }
  function stopPlayback() { clearTimers(); if (PLAY) PLAY.playing = false; $("play").innerHTML = "&#9654; Watch"; }
  function togglePlay() {
    if (!PLAY) return;
    if (PLAY.playing) { stopPlayback(); return; }
    if (PLAY.i >= PLAY.sample.log.length) seekTo(0);
    PLAY.playing = true; $("play").innerHTML = "&#10074;&#10074; Pause";
    (function loop() {
      if (!PLAY || !PLAY.playing) return;
      if (PLAY.i >= PLAY.sample.log.length) { stopPlayback(); return; }
      seekTo(PLAY.i + 1, true);
      var ms = speedMs(), l = PLAY.sample.log[PLAY.i - 1];
      if (ms === 0) loop(); else later(loop, ms * (l.dur || 0.8));
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
    boardEvents(); teamEvents();
    $("run").addEventListener("click", run);
    $("play").addEventListener("click", togglePlay);
    $("step").addEventListener("click", function () { if (!PLAY) return; stopPlayback(); seekTo(PLAY.i >= PLAY.sample.log.length ? 0 : PLAY.i + 1, true); });
    $("back").addEventListener("click", function () { if (!PLAY) return; stopPlayback(); seekTo(PLAY.i - 1); });
    $("tlrange").addEventListener("input", function () { if (!PLAY) return; stopPlayback(); seekTo(parseInt(this.value, 10)); });
    $("tltrack").addEventListener("click", function (ev) { var s = ev.target.closest ? ev.target.closest(".seg") : null; if (s && PLAY) { stopPlayback(); seekTo(+s.getAttribute("data-k"), true); } });
    $("combatlog").addEventListener("click", function (ev) { var li = ev.target.closest ? ev.target.closest("li[data-k]") : null; if (li && PLAY) { stopPlayback(); seekTo(+li.getAttribute("data-k"), true); } });
    $("reset").addEventListener("click", function () { try { localStorage.removeItem("pw_team"); } catch (e) {} OVER = {}; TEAM = [[null, null, null, null], [null, null, null, null]]; defaultPositions(); PICK = null; invalidate(); });
    skPickEvents();
    $("swap").addEventListener("click", function () {
      TEAM = [TEAM[1], TEAM[0]];
      var p = POS.slice(4).concat(POS.slice(0, 4));
      var mid = GRID.zones[0].y0 + GRID.zones[1].y1;
      POS = p.map(function (q) { return { x: q.x, y: mid - q.y }; });
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
