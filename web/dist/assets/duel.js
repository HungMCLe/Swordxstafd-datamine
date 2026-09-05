/* Duel simulator: SpeedToTime for the clock, Damage() for every hit, statuses
   from the decoded prefabs, and a scene that plays one fight back. */
(function () {
  "use strict";
  var C;
  try { C = JSON.parse(document.getElementById("dueldata").textContent); }
  catch (e) { return; }

  var $ = function (id) { return document.getElementById(id); };
  var TECH = 4, CHARM = 4;   /* the game gives exactly four of each */
  var DATA = null, CURVES = null, LOAD = { a: [null, null, null, null, null, null, null, null],
                                           b: [null, null, null, null, null, null, null, null] };
  var FIELDS = ["hp", "atk", "def", "spd", "mast", "kfm", "aff", "eres", "aegis",
                "cr", "cd", "critres", "boost", "dmgres", "blockrate", "blockeff", "acc", "erate", "edodge",
                "pvpadd", "pvpres"];
  var PCT_FIELDS = ["cr", "cd", "critres", "boost", "dmgres", "blockrate", "blockeff", "pvpadd", "pvpres"];
  var A_COL = "#b8863b", B_COL = "#3d6ea8";
  var SIDE = ["a", "b"], WHO = ["You", "Opponent"];

  function n(id) { var el = $(id); if (!el) return 0; var v = parseFloat(el.value); return isFinite(v) ? v : 0; }

  /* PropType -> the sheet field it feeds (percent props land in percent units) */
  var PROP2FIELD = {
    ElementMaster: "mast", KongFuMaster: "kfm", ElementResistance: "eres",
    Attack: "atk", MaxHp: "hp", Defence: "def", Speed: "spd",
    CritRatePercent: "cr", CritPowerPercent: "cd",
    CritAvoidPercent: "critres", DmgAddPercent: "boost", DmgReducePercent: "dmgres",
    BlockPercent: "blockrate", BlockValuePercent: "blockeff",
    WindDamageAdd: "aff", WaterDamageAdd: "aff", FireDamageAdd: "aff",
    LightDamageAdd: "aff", DarkDamageAdd: "aff",
    WindDamageReduce: "aegis", WaterDamageReduce: "aegis", FireDamageReduce: "aegis",
    LightDamageReduce: "aegis", DarkDamageReduce: "aegis",
    FinalDamageReducePercent: "dmgres", EffectRate: "erate", EffectDodge: "edodge",
    /* the status-written variants of the percentage block */
    StatusDmgAddPer: "boost", StatusDmgReducePer: "dmgres", DmgVulnerable: "vuln",
    StatusDmgVulnerablePer: "vuln"
  };
  /* multiplicative scales statuses apply to the main stats */
  var PROP2SCALE = { AttackScale: "atk", DefenceScale: "def", MaxHpScale: "hp", SpeedScale: "spd" };
  /* flat "value" forms divide by their per-rank base before joining the percentage */
  var PROP2RATIO = {
    CritRatePercentValue: ["cr", "BaseCritRatePercentValue"],
    CritAvoidPercentValue: ["critres", "BaseCritAvoidPercentValue"],
    BlockPercentValue: ["blockrate", "BaseBlockPercentValue"]
  };
  /* flat additive block of Damage(): (adds - reduces) x coef, floored at -90% of base */
  var PROP2FLAT = { FixedStatusDmgAdd: "fadd", FixedDmgAdd: "fadd", DmgAdd: "fadd",
                    FixedStatusDmgReduce: "fred", FixedDmgReduce: "fred", DmgReduce: "fred",
                    FixedDmgVulnerable: "fvuln", FixedstatusDmgVulnerable: "fvuln" };
  var UNMODELLED = {
    DamageByDamage: "reflected damage", FixedDamageByDamage: "reflected damage",
    SkillCureByHp: "healing", SkillFixedCure: "healing",
    SkillFixedShield: "shields", StatusFixedShieldAdd: "shields",
    ShieldByDefence: "shields", ShieldByTargetHp: "shields",
    CureAddPercent: "healing", BeCureAddPercent: "healing", CureAdd: "healing"
  };

  function curveValue(entry, srank, slevel, rankName) {
    if (entry.v !== undefined) return entry.v;
    if (entry.m === undefined || !CURVES) return 0;
    var lp = (DATA.lpidOf[String(entry.g)] || {})[rankIdOf(rankName)];
    var curve = CURVES[lp];
    if (!curve) return 0;
    var row = curve[String(slevel)];
    return row && row[entry.k] !== undefined ? row[entry.k] * entry.m : 0;
  }

  /* a Charm's row also carries the display numbers of the skills it triggers
     (SkillAttack1, SkillFixedCure ...); those fire as procs, not as stats */
  var TRIGGER_DISPLAY = /^(SkillAttack|SkillFixed|SkillCure|ShieldBy|CD$|BreakResilience)/;

  /* fold one prop row into a sheet; unplaceable props are noted on s.ignored */
  function foldProps(s, row, srank, slevel, rank, tally) {
    Object.keys(row).forEach(function (prop) {
      if (TRIGGER_DISPLAY.test(prop)) return;
      var v = curveValue(row[prop], srank, slevel, rank.name);
      if (!v) return;
      var f;
      if ((f = PROP2FIELD[prop])) { s[f] = (s[f] || 0) + v; if (tally) tally[f] = (tally[f] || 0) + v; return; }
      if ((f = PROP2SCALE[prop])) { s[f] *= (1 + v / 100); if (tally) tally[f + "%"] = (tally[f + "%"] || 0) + v; return; }
      var r = PROP2RATIO[prop];
      if (r) { var add = v / rank[r[1]] * 100; s[r[0]] += add; if (tally) tally[r[0]] = (tally[r[0]] || 0) + add; return; }
      if ((f = PROP2FLAT[prop])) { s[f] = (s[f] || 0) + v; if (tally) tally[f] = (tally[f] || 0) + v; return; }
      if (s.ignored) s.ignored[UNMODELLED[prop] || prop] = true;
    });
  }

  function sheet(side) {
    var r = C.ranks[parseInt($(side + "_rank").value, 10)] || C.ranks[0];
    var s = { rank: r, srank: Math.round(n(side + "_srank")), slevel: Math.round(n(side + "_slevel")),
              vuln: 0, fadd: 0, fred: 0, fvuln: 0, charmAdds: {}, ignored: {} };
    FIELDS.forEach(function (f) { s[f] = n(side + "_" + f); });
    /* Charms are passive stats: CalcSkillPassiveProps, added to the typed sheet */
    LOAD[side].slice(TECH).forEach(function (ch) {
      if (!ch || !ch.props) return;
      var row = ch.props[String(s.srank)];
      if (row) foldProps(s, row, s.srank, s.slevel, r, s.charmAdds);
    });
    PCT_FIELDS.forEach(function (f) { s[f] /= 100; });
    s.vuln /= 100;
    s.hp = Math.max(1, s.hp); s.atk = Math.max(1, s.atk); s.spd = Math.max(1, s.spd);
    return s;
  }

  /* the sheet as it stands right now, with every live status folded in */
  function eff(side, sides) {
    var base = side.s, e = {};
    Object.keys(base).forEach(function (k) { e[k] = base[k]; });
    PCT_FIELDS.forEach(function (f) { e[f] = base[f] * 100; });
    e.vuln = base.vuln * 100; e.ignored = null;
    side.st.forEach(function (st) {
      var props = st.meta.props;
      if (!props) return;
      var cs = sides[st.creator].s;
      var row = props[String(cs.srank)];
      if (row) foldProps(e, row, cs.srank, cs.slevel, cs.rank, null);
    });
    PCT_FIELDS.forEach(function (f) { e[f] /= 100; });
    e.vuln /= 100;
    e.atk = Math.max(1, e.atk); e.spd = Math.max(1, e.spd); e.def = Math.max(0, e.def);
    return e;
  }

  /* interval = 100000 / sqrt(SPD x rankSpeedScale) */
  function interval(s) {
    var scale = C.speedScale[s.rank.name] || 1;
    return 100000 / Math.sqrt(Math.max(1, s.spd) * scale);
  }

  function flatOf(rowsEntry, fxKey, fgKey, curveProp, slevel, rankName) {
    if (!rowsEntry || rowsEntry[fxKey] === undefined || !CURVES) return 0;
    var lp = (DATA.lpidOf[String(rowsEntry[fgKey])] || {})[rankIdOf(rankName)];
    var curve = CURVES[lp];
    if (!curve) return 0;
    var c = curve[String(slevel)];
    return c && c[curveProp] !== undefined ? c[curveProp] * rowsEntry[fxKey] : 0;
  }
  var RANKID = null;
  function rankIdOf(displayName) {
    if (!RANKID) {
      RANKID = {};
      var ids = Object.keys(DATA.lpidOf[Object.keys(DATA.lpidOf)[0]] || {});
      C.ranks.forEach(function (r, i) { RANKID[r.name] = ids[i]; });
    }
    return RANKID[displayName];
  }

  /* one action's numbers, per hit, through Damage() up to the rolls */
  function hitParts(att, def, sk, rows) {
    var row = sk.id === 0 ? { SkillAttack1: 100 } : (rows || {});
    var ec = sk.ec || null;
    var elemental = sk.ele !== "Physical" && sk.ele !== "None";
    var mast = elemental ? att.mast : att.kfm;
    var aff = elemental ? att.aff : 0;
    var foeMasterBase = elemental ? def.rank.BaseElementResistance : def.rank.BaseKongFuResistance;
    var myMasterBase = elemental ? att.rank.BaseElementMaster : att.rank.BaseKongFuMaster;
    var eNum = 1 + aff / def.rank.BaseElementReduce + mast / foeMasterBase;
    var eDen = 1 + (elemental ? def.aegis / att.rank.BaseElementAdd : 0) + def.eres / myMasterBase;
    var pct = (1 + att.boost + (att.pvpadd || 0) + def.vuln) / Math.max(0.1, 1 + def.dmgres + (def.pvpres || 0));
    var defTerm = att.atk / (att.atk + def.def);
    /* this is a player hitting a player: Damage() divides by the target's two
       per-rank PvP scalers, and the few skills with a PvpPropScale shrink too */
    var psdr = 1 + (def.rank.PlayerSkillDmgReduceScale || 0) / 10000;
    var prosdr = 1 + (def.rank.ProSkillDmgReduceScale || 0) / 10000;
    var pvp = (sk.pvp || 10000) / 10000;
    var flat = flatOf(row, "fx", "fg", "SkillFixedAttack1", att.slevel, att.rank.name);
    var out = { hits: [], heal: 0 };
    if (ec && ec.skillType === "Cure" || (row.SkillCureByHp && !row.SkillAttack1)) {
      out.heal = ((row.SkillCureByHp || 0) / 100 * att.hpMax +
                  flatOf(row, "SkillFixedCure", "SkillFixedCure_g", "SkillFixedCure", att.slevel, att.rank.name)) * pvp;
      return out;
    }
    function one(coef, withFlat, on, ignoreShield, at) {
      var base = (att.atk * coef / psdr + (withFlat ? flat : 0)) * defTerm;
      var add = ((att.fadd || 0) + (def.fvuln || 0) - (def.fred || 0)) * coef / psdr;
      add = Math.max(-0.9 * base, add);              /* FixedDmgLimitPercent */
      out.hits.push({ d: (base + add) / prosdr * (eNum / eDen) * pct * pvp, on: on || [],
                      ignoreShield: !!ignoreShield, at: at || 0 });
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
  function blockChance(att, def) {
    return Math.min(1, Math.max(0, def.blockrate - att.acc / att.rank.BaseBlockAvoidPercentValue));
  }
  function blockDiv(def) { return Math.max(C.minBlock, 1 + def.blockeff); }

  /* BattleFormulaHandler.EffectRate */
  function landChance(base, byProp, statusType, att, def) {
    if (!byProp) return base;
    var br = att.rank.BaseEffectRate || 1, bd = def.rank.BaseEffectDodge || 1;
    var rate = base * (1 + (att.erate || 0) / br) / Math.max(0.1, 1 + (def.edodge || 0) / bd);
    if (statusType === "AbnormalDebuff" && br <= bd) rate *= Math.pow(br / bd, 3);
    return Math.max(0, rate);
  }

  /* PVPSkillPropsScaleOnBattleProcessor: the final scale on every skill hit in a PvP fight */
  function pvpGovernor(A, B, loadA, loadB) {
    var G = C.pvp; if (!G) return { scale: 1, parts: {} };
    /* 1. survival floor: the lowest burst-to-HP ratio, held to MinSurvivalRatio */
    var sheets = [A, B];
    var minBlockAvoid = Math.min.apply(null, sheets.map(function (s) { return s.acc / s.rank.BaseBlockAvoidPercentValue; }));
    var minCritAvoid = Math.min.apply(null, sheets.map(function (s) { return s.critres; }));
    var ratio = Math.min.apply(null, sheets.map(function (s) {
      var p = Math.min(1, Math.max(0, 0.05 + s.cr - minCritAvoid));
      var m = Math.max(s.cd - minCritAvoid, 1.3);
      var b = Math.min(1, Math.max(0, s.blockrate - minBlockAvoid));
      var bv = Math.max(s.blockeff - minBlockAvoid, 1.5);
      var r = s.atk * s.atk / (s.atk + s.def) / s.hp;
      r *= 1 - p + p * m;
      r /= 1 - b + b * bv;
      var addTerm = s.aff / s.rank.BaseElementAdd, redTerm = s.aegis / s.rank.BaseElementReduce;
      var mast = (s.kfm / s.rank.BaseKongFuMaster + s.mast / s.rank.BaseElementMaster) / 2;
      var res = (0 / s.rank.BaseKongFuResistance + s.eres / s.rank.BaseElementResistance) / 2;
      r *= (1 + addTerm + mast) / (1 + redTerm + res);
      r *= (1 + s.boost + s.pvpadd) / (1 + s.dmgres + s.pvpres);
      return r;
    }));
    var survival = ratio > G.minSurvival ? G.minSurvival / ratio : 1;
    /* 2. skill-rank decay: the fight's average skill rank against the server's expected one */
    function avgRank(load) {
      var rs = load.filter(Boolean).map(function () { return 0; });
      return rs.length ? 0 : 0;
    }
    var mine = A.srank, theirs = B.srank;                /* every equipped skill shares the side's rank */
    var fightRank = Math.round((Math.max(mine, 0) + Math.max(theirs, 0)) / 2);
    var days = Math.max(0, Math.round(n("serverdays")));
    var keys = Object.keys(G.avgSkillRank).map(Number).sort(function (a, b) { return a - b; });
    var serverRank = G.avgSkillRank[String(Math.min(days, keys[keys.length - 1]))] || G.avgSkillRank[String(keys[keys.length - 1])];
    var dFight = G.decay[String(fightRank)] || 0, dServer = G.decay[String(serverRank)] || 0;
    var rankScale = dFight > 0 ? Math.min(1, dServer / dFight) : 1;
    /* 3. balance value by level and rank enum; rows only exist from Saint up */
    var bal = sheets.map(function (s) {
      var row = G.balance[String(s.rank.rankEnum)];
      var v = row && row[String(s.slevel)];
      return v ? v / 10000 : G.defaultBalance;
    });
    var balance = (bal[0] + bal[1]) / 2;
    return { scale: survival * rankScale * balance,
             parts: { survival: survival, ratio: ratio, rankScale: rankScale, fightRank: fightRank, serverRank: serverRank, balance: balance } };
  }

  var BASIC = { id: 0, name: "Basic attack", ele: "Physical", hits: 1, r: {} };

  /* the size of a shield status, from its entity_prop_status row */
  function shieldSize(meta, creator, holder) {
    var row = meta.props && meta.props[String(creator.s.srank)];
    if (!row) return 0;
    var cs = creator.s, amt = 0;
    Object.keys(row).forEach(function (prop) {
      var v = curveValue(row[prop], cs.srank, cs.slevel, cs.rank.name);
      if (prop === "ShieldByDefence") amt += v / 100 * holder.s.def;
      else if (prop === "ShieldByTargetHp") amt += v / 100 * holder.s.hp;
      else if (prop === "ShieldByConvertedCurHp") amt += v / 100 * holder.hp;
      else if (prop === "SkillFixedShield" || prop === "StatusFixedShieldAdd") amt += v;
    });
    return amt;
  }

  /* is every status this skill would put on its target already up there? */
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
        var up = tgt.st.some(function (x) { return x.id === o.status && (x.dur !== 0); });
        if (mt.shield && tgt.shield <= 0) up = false;
        if (!up) all = false;
      });
    });
    /* a skill that only applies statuses, all of which are still active, is a wasted turn */
    var dealsDamage = sk.ec.skillType === "Attack";
    return any && all && !dealsDamage;
  }
  var SKIP_ACTIONS = { Stun: 1, Frozen: 1 };

  function cdOf(sk, srank) {
    var row = sk.r[String(srank)] || {};
    return Math.max(0, Math.round(row.CD || 0));
  }

  /* a Charm whose proc chain ends in a cdStart status (Rapid Cast) cuts every
     Technique's opening cooldown; returns the total cut, as a negative number */
  function cdStartOf(charms) {
    var cut = 0;
    charms.forEach(function (ch) {
      (ch && ch.passive || []).forEach(function (pv) {
        pv.triggers.forEach(function (t) {
          var tr = DATA.trig[String(t.skill)];
          if (!tr || !tr.ec) return;
          tr.ec.hits.forEach(function (h) {
            h.on.forEach(function (o) {
              var mt = DATA.statuses[String(o.status)];
              if (mt && mt.cdStart) cut += mt.cdStart;
            });
          });
        });
      });
    });
    return cut;
  }
  function isCdStartCharm(ch) { return cdStartOf([ch]) !== 0; }

  /* FightSkillData: ready when Round - LastRound > CD. In countdown terms a skill
     waits CD + 1 turns after a cast (CD 1 = out for one full turn), starts the
     fight at CD + 1 unless it is ResetCDAtStart, and a Rapid Cast cut comes off
     that opening count. The count ticks at the start of each of its owner's turns
     and the skill is castable at 0. */
  function openingCds(techs, charms, srank) {
    var cut = cdStartOf(charms);
    return techs.map(function (sk) {
      if (!sk) return 0;
      if (sk.ec && sk.ec.resetCdAtStart) return 0;
      return Math.max(0, cdOf(sk, srank) + 1 + cut);
    });
  }

  function statusName(meta) {
    if (meta.action === "Blinding") return "Blind";
    if (meta.action && meta.action !== "Status" && meta.action !== "PassiveStatus") return meta.action;
    if (meta.shield) return "Shield";
    var p = meta.props && meta.props["22"];
    if (p) {
      var k = Object.keys(p)[0];
      var LAB = { StatusDmgReducePer: "DMG RES", FixedStatusDmgReduce: "DMG RES", StatusDmgAddPer: "DMG Boost",
                  AttackScale: "ATK", DefenceScale: "DEF", SpeedScale: "SPD", MaxHpScale: "HP",
                  DmgAddPercent: "DMG Boost", DmgReducePercent: "DMG RES", CritRatePercent: "Crit Rate",
                  CritPowerPercent: "Crit DMG", BlockPercent: "Block Rate", StatusDmgVulnerablePer: "Vulnerable",
                  DmgVulnerable: "Vulnerable", CritAvoidPercent: "Crit RES", ElementMaster: "Mastery" };
      return (meta.type === "Debuff" || meta.type === "AbnormalDebuff" ? "−" : "+") + (LAB[k] || k);
    }
    return meta.type === "Debuff" ? "Debuff" : meta.type === "Buff" ? "Buff" : "Effect";
  }

  /* ---------- the fight ---------- */
  function oneFight(A, B, loadA, loadB, rng, wantLog, maxRounds, gov) {
    var GOV = gov || 1;
    function side(S, load, idx) {
      var techs = load.slice(0, TECH);
      return {
        s: S, load: techs, charms: load.slice(TECH), hp: S.hp, t: interval(S), idx: idx, turns: 0,
        cd: openingCds(techs, load.slice(TECH), S.srank),
        uses: techs.map(function () { return 0; }),
        st: [], shield: 0, charmFired: {}
      };
    }
    var sides = [side(A, loadA, 0), side(B, loadB, 1)];
    var log = [], turns = 0, MAXT = 600, capped = false, events;

    function applyStatus(tgt, sid, creatorIdx) {
      var meta = DATA.statuses[String(sid)];
      if (!meta || meta.falloff || meta.dur === 0) return null;
      var have = tgt.st.filter(function (x) { return x.id === sid; })[0];
      if (have) {
        if (meta.stack) have.stacks = Math.min(have.stacks + 1, meta.maxStack > 0 ? meta.maxStack : 99);
        have.dur = meta.dur; have.skills = meta.skillCount || 0;
        return have;
      }
      var st = { id: sid, meta: meta, dur: meta.dur, skills: meta.skillCount || 0, creator: creatorIdx, stacks: 1 };
      tgt.st.push(st);
      return st;
    }

    function removeStatus(holder, st) {
      var i = holder.st.indexOf(st);
      if (i >= 0) holder.st.splice(i, 1);
      if (st.meta.shield && !holder.st.some(function (x) { return x.meta.shield; })) holder.shield = 0;
    }

    /* a trigger skill (poison tick, expiry heal, charm proc) resolved against a target */
    function fireSkill(skillId, src, tgt, tag) {
      var entry = DATA.trig[String(skillId)];
      if (!entry) return;
      var rows = (entry.r || {})[String(src.s.srank)] || {};
      var srcE = eff(src, sides), tgtE = eff(tgt, sides);
      srcE.hpMax = src.s.hp; tgtE.hpMax = tgt.s.hp;
      var fake = { id: skillId, name: entry.name, ele: (entry.ec && entry.ec.ele) || "None", ec: entry.ec, hits: 1, r: entry.r || {}, pvp: entry.pvp || 10000 };
      var parts = hitParts(srcE, tgtE, fake, rows);
      if (parts.heal) {
        /* a heal from a trigger targets whoever the cfg says; fireSkill is called with that as tgt */
        var before = tgt.hp;
        tgt.hp = Math.min(tgt.s.hp, tgt.hp + parts.heal);
        if (events) events.push({ kind: "heal", who: tgt.idx, amount: tgt.hp - before, tag: tag });
        return;
      }
      var total = landHits(parts, src, tgt, srcE, tgtE, fake);
      if (events && total > 0) events.push({ kind: "dmg", who: tgt.idx, amount: total, tag: tag });
      /* trigger skills can carry statuses of their own (Frost Guard's Icebound) */
      parts.hits.forEach(function (h) {
        h.on.forEach(function (o) {
          var meta = DATA.statuses[String(o.status)];
          if (!meta || meta.falloff) return;
          var target = (o.target === "DamageTarget") ? tgt : src;
          if (rng() < landChance(o.chance, o.byProp, meta.type, srcE, tgtE)) {
            var st = applyStatus(target, o.status, src.idx);
            if (st && events) events.push({ kind: "status", who: target.idx, name: statusName(meta) });
          }
        });
      });
    }

    /* roll every hit of one skill: falloff, blind, block, crit, shield */
    function landHits(parts, me, foe, meE, foeE, pick, rolled) {
      var p = critChance(meE, foeE), m = critMult(meE, foeE);
      var b = blockChance(meE, foeE), bd = blockDiv(foeE);
      var total = 0, fallCount = 0;
      var blind = me.st.filter(function (x) { return x.meta.action === "Blinding"; })[0];
      parts.hits.forEach(function (h) {
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
        foe.hp -= d; total += d;
        if (rolled) rolled.push({ d: d, crit: crit, block: block, absorbed: absorbed, blinded: blinded, at: h.at || 0 });
      });
      return total;
    }

    function tickEnd(me) {
      /* statuses on me count down at the end of my turn; expiry fires onEnd */
      me.st.slice().forEach(function (st) {
        if (st.dur > 0) {
          st.dur--;
          if (st.dur === 0) {
            (st.meta.onEnd || []).forEach(function (t) {
              var src = t.source === "Creator" ? sides[st.creator] : me;
              var tgt = t.target === "Creator" ? sides[st.creator] : me;
              if (rng() < (t.byProp ? landChance(t.chance, true, null, eff(src, sides), eff(tgt, sides)) : t.chance))
                fireSkill(t.skill, src, tgt, statusName(st.meta) + " ends");
            });
            removeStatus(me, st);
          }
        }
      });
    }

    while (sides[0].hp > 0 && sides[1].hp > 0 && turns < MAXT) {
      if (maxRounds > 0 && Math.min(sides[0].turns, sides[1].turns) >= maxRounds) { capped = true; break; }
      var gap = sides[0].t - sides[1].t;
      var i = Math.abs(gap) < 1e-9 ? (rng() < 0.5 ? 0 : 1) : (gap < 0 ? 0 : 1);
      var me = sides[i], foe = sides[1 - i];
      turns++; me.turns++;
      events = wantLog ? [] : null;

      /* round-start triggers: DoT ticks on me, regen charms */
      me.st.slice().forEach(function (st) {
        (st.meta.roundStart || []).forEach(function (t) {
          var src = t.source === "Creator" ? sides[st.creator] : me;
          var tgt = t.target === "Creator" ? sides[st.creator] : me;
          if (rng() < t.chance) fireSkill(t.skill, src, tgt, statusName(st.meta));
        });
      });
      me.charms.forEach(function (ch, ci) {
        (ch && ch.passive || []).forEach(function (pv) {
          if (pv.kind !== "roundStart") return;
          pv.triggers.forEach(function (t) {
            if (rng() < pv.rate * t.chance) fireSkill(t.skill, me, t.target === "Enemy" ? foe : me, ch.name);
          });
        });
      });
      if (me.hp <= 0 || foe.hp <= 0) { if (wantLog) log.push(entry(me, null, -1, [], 0, events, "start")); break; }

      var skip = me.st.filter(function (x) { return SKIP_ACTIONS[x.meta.action]; })[0];
      var frozenCd = me.st.some(function (x) { return x.meta.cdFreeze; });
      if (!frozenCd) for (var c = 0; c < me.cd.length; c++) if (me.cd[c] > 0) me.cd[c]--;

      /* one cast: hits, rolls, statuses, procs; returns what the log needs */
      function cast(pick, slot) {
        var rolled = [], total = 0;
        var meE = eff(me, sides), foeE = eff(foe, sides);
        meE.hpMax = me.s.hp; foeE.hpMax = foe.s.hp;
        var rows = pick.id === 0 ? {} : (pick.r[String(me.s.srank)] || {});
        var parts = hitParts(meE, foeE, pick, rows);
        var isAttack = !pick.ec || pick.ec.skillType === "Attack" || pick.id === 0;
        var target = (pick.ec && (pick.ec.target === "Ally" || pick.ec.target === "Me" || pick.ec.target === "Self")) ? me : foe;
        if (parts.heal) {
          var before = me.hp; me.hp = Math.min(me.s.hp, me.hp + parts.heal * GOV);
          if (events) events.push({ kind: "heal", who: me.idx, amount: me.hp - before, tag: pick.name });
        }
        if (parts.hits.length && target === foe) total = landHits(parts, me, foe, meE, foeE, pick, rolled);
        parts.hits.forEach(function (h, hi) {
          if (rolled[hi] && rolled[hi].blinded) return;
          h.on.forEach(function (o) {
            var meta = DATA.statuses[String(o.status)];
            if (!meta || meta.falloff) return;
            var tgt = (o.target === "DamageTarget" && target === foe) ? foe : me;
            var chance = landChance(o.chance, o.byProp, meta.type, meE, foeE);
            tgt.st.forEach(function (x) {
              var bo = x.meta.boosts;
              if (bo && bo.actions.indexOf(meta.action) >= 0 && x.meta.props) {
                var cs = sides[x.creator].s, r = x.meta.props[String(cs.srank)] || {};
                if (r[bo.prop]) chance += curveValue(r[bo.prop], cs.srank, cs.slevel, cs.rank.name) / 100;
              }
            });
            if (rng() < chance) {
              var st = applyStatus(tgt, o.status, me.idx);
              if (st && meta.shield) {
                var amt = shieldSize(meta, me, tgt) * GOV;
                if (amt > 0) tgt.shield = Math.max(tgt.shield, amt);
              }
              if (st && events) events.push({ kind: "status", who: tgt.idx, name: statusName(meta) });
            }
          });
        });
        /* Blind is spent by the first attack skill of the turn */
        var bl = me.st.filter(function (x) { return x.meta.action === "Blinding"; })[0];
        if (bl && isAttack) removeStatus(me, bl);
        if (total > 0) {
          me.charms.forEach(function (ch) {
            (ch && ch.passive || []).forEach(function (pv) {
              if (pv.kind !== "hit" || (pv.onlyAttack && !isAttack)) return;
              pv.triggers.forEach(function (t) {
                if (rng() < pv.rate * t.chance) fireSkill(t.skill, me, t.target === "Applicator" ? me : foe, ch.name);
              });
            });
          });
          foe.charms.forEach(function (ch) {
            (ch && ch.passive || []).forEach(function (pv) {
              if (pv.kind !== "damaged") return;
              pv.triggers.forEach(function (t) {
                if (rng() < pv.rate * t.chance) fireSkill(t.skill, foe, t.target === "Applicator" ? foe : me, ch.name);
              });
            });
          });
        }
        if (slot >= 0) { me.cd[slot] = cdOf(pick, me.s.srank) + 1; me.uses[slot]++; }
        return { rolled: rolled, total: total };
      }

      var casts = 0, sub = 0;
      if (skip) {
        if (wantLog) log.push(entry(me, null, -1, [], 0, events, skip.meta.action, 0));
      } else {
        /* every Technique that is ready goes, in slot order, each onto its own cooldown */
        for (var k = 0; k < me.load.length && foe.hp > 0 && me.hp > 0; k++) {
          var cand = me.load[k];
          if (!cand || me.cd[k] !== 0) continue;
          var lim = cand.ec ? cand.ec.limitedTimes : -1;
          if (lim > 0 && me.uses[k] >= lim) continue;
          if (redundant(cand, me, foe)) continue;
          events = wantLog ? [] : null;
          var r = cast(cand, k);
          casts++;
          if (wantLog) log.push(entry(me, cand, k, r.rolled, r.total, events, null, sub++));
        }
        if (casts === 0) {
          /* nothing ready: a basic attack, and the Charms that key off a Technique-less turn */
          events = wantLog ? [] : null;
          var rb = cast(BASIC, -1);
          me.charms.forEach(function (ch) {
            (ch && ch.passive || []).forEach(function (pv) {
              if (pv.kind !== "roundCheck") return;
              pv.triggers.forEach(function (t) { if (rng() < pv.rate * t.chance) fireSkill(t.skill, me, me, ch.name); });
            });
          });
          if (wantLog) log.push(entry(me, BASIC, -1, rb.rolled, rb.total, events, null, 0));
        }
      }
      tickEnd(me);
      me.t += interval(eff(me, sides));
    }
    function entry(me, pick, slot, rolled, total, ev, note, sub) {
      var foe = sides[1 - me.idx];
      return { t: Math.round(me.t), side: me.idx, who: WHO[me.idx], slot: slot, sub: sub || 0,
               skill: pick ? pick.name : (note === "start" ? "—" : note + " — no action"),
               skillId: pick ? pick.id : 0, ele: pick ? pick.ele : "None", hits: rolled, dmg: total,
               dur: pick && pick.ec && pick.ec.dur ? pick.ec.dur : 0.8,
               events: ev || [], turn: me.turns, cd: me.cd.slice(), note: note,
               hpA: Math.max(0, sides[0].hp), hpB: Math.max(0, sides[1].hp),
               shA: Math.round(sides[0].shield), shB: Math.round(sides[1].shield),
               stA: sides[0].st.map(function (x) { return { n: statusName(x.meta), d: x.dur, s: x.stacks, t: x.meta.type }; }),
               stB: sides[1].st.map(function (x) { return { n: statusName(x.meta), d: x.dur, s: x.stacks, t: x.meta.type }; }),
               left: Math.max(0, foe.hp) };
    }
    return { winner: sides[0].hp <= 0 ? 1 : (sides[1].hp <= 0 ? 0 : -1), capped: capped,
             turns: turns, log: log, hpA: Math.max(0, sides[0].hp), hpB: Math.max(0, sides[1].hp) };
  }

  function mulberry(seed) {
    return function () {
      seed |= 0; seed = seed + 0x6D2B79F5 | 0;
      var t = Math.imul(seed ^ seed >>> 15, 1 | seed);
      t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
      return ((t ^ t >>> 14) >>> 0) / 4294967296;
    };
  }

  function fmt(v) {
    if (v >= 1e6) return (v / 1e6).toFixed(2) + "M";
    if (v >= 1000) return (v / 1000).toFixed(1) + "K";
    return Math.round(v).toString();
  }

  /* ---------- the run ---------- */
  var PLAY = null, PLAYGOV = null;

  function currentSheets() {
    var A = sheet("a"), B;
    if ($("mirror").checked) { B = JSON.parse(JSON.stringify(A)); B.rank = A.rank; }
    else B = sheet("b");
    var loadB = $("mirror").checked ? LOAD.a.slice() : LOAD.b;
    return { A: A, B: B, loadA: LOAD.a, loadB: loadB };
  }

  function run() {
    if (!DATA || !CURVES) return;
    stopPlayback();
    var cs = currentSheets(), A = cs.A, B = cs.B;
    var N = 1000, winA = 0, draws = 0, turnList = [], rng = mulberry(12345);
    var maxR = parseInt(($("maxrounds") || {}).value, 10) || 0;
    var gov = pvpGovernor(A, B, cs.loadA, cs.loadB);
    PLAYGOV = gov;
    for (var i = 0; i < N; i++) {
      var r = oneFight(A, B, cs.loadA, cs.loadB, rng, false, maxR, gov.scale);
      if (r.winner === 0) winA++; else if (r.winner < 0) draws++;
      turnList.push(r.turns);
    }
    var sample = oneFight(A, B, cs.loadA, cs.loadB, mulberry(999), true, maxR, gov.scale);
    PLAY = { A: A, B: B, sample: sample, i: 0, timer: null };
    turnList.sort(function (x, y) { return x - y; });
    var med = turnList[Math.floor(turnList.length / 2)];
    var pa = winA / N, pb = (N - winA - draws) / N;
    $("result").hidden = false;
    $("oddsa").style.width = (pa * 100).toFixed(1) + "%";
    $("oddsb").style.width = (pb * 100).toFixed(1) + "%";
    $("oddsa").textContent = pa >= 0.08 ? "You " + (pa * 100).toFixed(0) + "%" : "";
    $("oddsb").textContent = pb >= 0.08 ? (pb * 100).toFixed(0) + "% Opponent" : "";
    $("oddstext").innerHTML = "<b>You win " + (pa * 100).toFixed(1) + "%</b> of 1,000 duels" +
      (draws ? ", " + (draws / N * 100).toFixed(1) + "% hit the round cap with both alive" : "") +
      ". Median fight length <b>" + med + " turns</b>, " + sample.log.length + " casts in the one shown. Your interval is <b>" +
      Math.round(interval(A)) + "</b> against theirs of <b>" + Math.round(interval(B)) +
      "</b>, so you act " + (interval(B) / interval(A)).toFixed(2) + "x as often." +
      (gov.scale < 0.999 ? " The PvP governor scales all skill damage by <b>" + gov.scale.toFixed(2) + "x</b>" +
        " (survival floor " + gov.parts.survival.toFixed(2) + " from a burst ratio of " + gov.parts.ratio.toFixed(2) +
        ", skill-rank decay " + gov.parts.rankScale.toFixed(2) + " for rank " + gov.parts.fightRank + " against a server average of " +
        gov.parts.serverRank + ", balance " + gov.parts.balance.toFixed(2) + ")." : " The PvP governor leaves damage at 1.00x.");
    var rows = sample.log.map(function (l) {
      var hits = l.hits.map(function (h) { return h.blinded ? "x" : h.block ? "B" : (h.crit ? "C" : "·"); }).join("");
      var ev = l.events.map(function (e) {
        return e.kind === "dmg" ? e.tag + " " + fmt(e.amount) : e.kind === "heal" ? e.tag + " +" + fmt(e.amount) : e.name + " on " + WHO[e.who];
      }).join("; ");
      return "<tr><td class=num>" + l.t + "</td><td class=num>" + l.turn + "</td><td>" + l.who +
        "</td><td>" + l.skill + (ev ? " <i>(" + ev + ")</i>" : "") +
        '</td><td class="mono">' + hits + "</td><td class=num>" + fmt(l.dmg) + "</td><td class=num>" + fmt(l.left) + "</td></tr>";
    }).join("");
    $("logbody").innerHTML = rows || '<tr><td colspan="7">no actions</td></tr>';
    $("detail").hidden = false;
    drawHp(sample, A, B);
    charmReport(A);
    sceneReset();
    $("play").disabled = false; $("step").disabled = false;
  }

  var LABEL = { hp: "HP", atk: "ATK", def: "DEF", spd: "SPD", mast: "Elemental Mastery",
                kfm: "Physical Mastery", aff: "Affinity", eres: "Elemental RES", aegis: "Aegis",
                cr: "Crit Rate", cd: "Crit DMG", critres: "Crit RES", boost: "DMG Boost",
                dmgres: "DMG RES", blockrate: "Block Rate", blockeff: "Block Efficiency",
                acc: "Accuracy", erate: "Effect Hit Rate", edodge: "Effect RES", vuln: "Vulnerability",
                fadd: "flat DMG add", fred: "flat DMG reduce" };
  var PCTF = { cr: 1, cd: 1, critres: 1, boost: 1, dmgres: 1, blockrate: 1, blockeff: 1, vuln: 1 };

  function charmReport(A) {
    var added = Object.keys(A.charmAdds).map(function (f) {
      var v = A.charmAdds[f];
      return "<b>+" + (PCTF[f] || /%$/.test(f) ? v.toFixed(1) + "%" : fmt(v)) + "</b> " + (LABEL[f] || f.replace("%", ""));
    });
    var procs = [];
    LOAD.a.slice(TECH).forEach(function (ch) {
      if (ch && isCdStartCharm(ch)) {
        procs.push("<b>" + ch.name + "</b> takes " + Math.abs(cdStartOf([ch])) +
                   " turn off every Technique's opening cooldown (the timing is from its prefab; the amount is from its text)");
        return;
      }
      (ch && ch.passive || []).forEach(function (pv) {
        var K = { hit: "on your hits", roundStart: "each of your turns", damaged: "when you are hit", roundCheck: "on a turn with no Technique", skillStart: "when a skill starts" };
        procs.push("<b>" + ch.name + "</b> fires " + (pv.triggers.map(function (t) {
          var tr = DATA.trig[String(t.skill)]; return tr ? tr.name : "a skill";
        }).join(", ")) + " " + (K[pv.kind] || pv.kind) + (pv.rate < 1 ? " (" + Math.round(pv.rate * 100) + "%)" : ""));
      });
    });
    var skipped = Object.keys(A.ignored);
    var html = added.length ? "Your Charms add " + added.join(", ") + " to the sheet." : "Your Charms add no flat stats.";
    if (procs.length) html += " " + procs.join(". ") + ".";
    if (skipped.length) html += " Not modelled from them: " + skipped.join(", ") + ".";
    $("charmnote").innerHTML = html;
  }

  function drawHp(sample, A, B) {
    var W = 680, H = 240, pl = 62, pr = 16, pb = 34, pt = 16;
    var seriesA = [[0, 1]], seriesB = [[0, 1]];
    sample.log.forEach(function (l, i) {
      seriesA.push([i + 1, Math.max(0, l.hpA / A.hp)]);
      seriesB.push([i + 1, Math.max(0, l.hpB / B.hp)]);
    });
    var x1 = Math.max(1, seriesA.length - 1);
    var px = function (x) { return pl + x / x1 * (W - pl - pr); };
    var py = function (y) { return H - pb - y * (H - pb - pt); };
    var o = "";
    for (var i = 0; i <= 4; i++) {
      var gy = i / 4;
      o += '<line class="grid" x1="' + pl + '" x2="' + (W - pr) + '" y1="' + py(gy).toFixed(1) + '" y2="' + py(gy).toFixed(1) + '"/>';
      o += '<text class="tick" x="' + (pl - 8) + '" y="' + (py(gy) + 4).toFixed(1) + '" text-anchor="end">' + (gy * 100).toFixed(0) + '%</text>';
    }
    o += '<line class="axis" x1="' + pl + '" x2="' + (W - pr) + '" y1="' + (H - pb) + '" y2="' + (H - pb) + '"/>';
    [[seriesA, A_COL], [seriesB, B_COL]].forEach(function (pair) {
      var d = pair[0].map(function (q, i) { return (i ? "L" : "M") + px(q[0]).toFixed(1) + " " + py(q[1]).toFixed(1); }).join(" ");
      o += '<path d="' + d + '" fill="none" stroke="' + pair[1] + '" stroke-width="2.2"/>';
    });
    o += '<text class="axlabel" x="' + pl + '" y="' + (pt - 3) + '">HP remaining</text>';
    o += '<text class="axlabel" x="' + (W - pr) + '" y="' + (H - 4) + '" text-anchor="end">actions</text>';
    $("hpchart").innerHTML = '<figure class="chartbox"><svg viewBox="0 0 ' + W + ' ' + H +
      '" class="chart" role="img" aria-label="HP over the fight">' + o +
      '</svg><div class="legend"><span class="key"><i style="background:' + A_COL + '"></i>You</span>' +
      '<span class="key"><i style="background:' + B_COL + '"></i>Opponent</span></div></figure>';
  }

  /* ---------- the scene ---------- */
  function rankBadge(srank) {
    var lab = C.rankLabels[String(srank)] || "", q = C.rankQuality[String(srank)] || "";
    var m = /\+(\d+)/.exec(lab);
    return { stars: m ? parseInt(m[1], 10) : 0, quality: q, label: lab };
  }

  function paint(side, slot) {
    var el = $(side + "_slot" + slot), sk = LOAD[side][slot];
    var kind = slot >= TECH ? "charm" : "tech";
    if (!sk) {
      el.className = "slot " + kind;
      el.innerHTML = '<span class="slotnum">' + (slot % TECH + 1) + '</span>';
      return;
    }
    var rb = rankBadge(Math.round(n(side + "_srank")));
    el.className = "slot filled " + kind + " ele-" + (sk.ele || "none").toLowerCase() + " q-" + rb.quality.toLowerCase();
    el.innerHTML =
      '<img src="../assets/skills/skill_' + sk.id + '.png" alt="" width="52" height="52" loading="lazy">' +
      '<span class="starbadge" title="' + rb.label + '">' + (rb.stars ? "★" + rb.stars : "★") + '</span>' +
      '<span class="cdov" hidden></span>' +
      '<span class="slotcap">' + sk.name + '</span>' +
      '<span class="slotlv">Lv. ' + Math.round(n(side + "_slevel")) + '</span>';
  }

  function paintAll() {
    SIDE.forEach(function (s) { for (var i = 0; i < TECH + CHARM; i++) paint(s, i); });
    portraits();
  }

  /* a realistic Champion-tier sheet for each line: the Mage one is a real
     Archmage's character screen; the Warrior one is invented to sit in the
     same range with the emphasis a plate-wearer has (DEF, HP, block, Physical Mastery) */
  var DEFAULTS = {
    Mage:    { hp: 2640000, atk: 494000, def: 392000, spd: 426000, mast: 86600, kfm: 15600, aff: 8040,
               eres: 9380, aegis: 7080, cr: 45, cd: 94.3, critres: 29.1, boost: 30.8, dmgres: 24,
               blockrate: 11.4, blockeff: 100, acc: 37700, erate: 13100, edodge: 63600, pvpadd: 9.6, pvpres: 9.6 },
    Warrior: { hp: 3420000, atk: 452000, def: 531000, spd: 381000, mast: 14200, kfm: 81500, aff: 6300,
               eres: 9100, aegis: 7400, cr: 39, cd: 86.5, critres: 31.5, boost: 26.4, dmgres: 29.5,
               blockrate: 27.8, blockeff: 118, acc: 33900, erate: 11800, edodge: 58900, pvpadd: 9.6, pvpres: 9.6 }
  };
  function rootOf(cls) { var cur = cls, g = 0; while (TREE[cur] && TREE[cur].pre && g++ < 10) cur = TREE[cur].pre; return cur; }
  function applyDefaults(side) {
    var d = DEFAULTS[rootOf(classOf(side))];
    if (!d) return;
    FIELDS.forEach(function (f) { var el = $(side + "_" + f); if (el && d[f] !== undefined) el.value = d[f]; });
  }

  /* the class each side plays, and its promotion line: the class itself and
     every class it promoted from — the tiers it can still draw skills from */
  var TREE = {};
  (C.classTree || []).forEach(function (c) { TREE[c.name] = c; });
  function classOf(side) {
    var el = $(side + "_cls");
    if ($("mirror").checked && side === "b") el = $("a_cls");
    return el ? el.value : null;
  }
  function lineOf(cls) {
    var out = {}, cur = cls, guard = 0;
    while (cur && TREE[cur] && guard++ < 10) { out[cur] = true; cur = TREE[cur].pre; }
    return out;
  }
  function inLine(side, sk) { return !!lineOf(classOf(side))[sk.cls]; }

  function portraits() {
    SIDE.forEach(function (side) {
      var cls = classOf(side), el = $(side + "_portrait"), icon = cls ? C.classIcon[cls] : null;
      if (icon) el.innerHTML = '<img src="../assets/skills/class_' + icon + '.png" alt="' + cls + '">';
      else el.innerHTML = '<span class="medallion-empty">' + (cls ? cls[0] : "?") + '</span>';
      if (side === "b") { $("b_cls").value = cls; $("b_cls").disabled = $("mirror").checked; }
      var r = C.ranks[parseInt($(side + "_rank").value, 10)];
      $(side + "_rankname").textContent = r ? r.name : "";
    });
  }

  function mirrorLoadout() {
    LOAD.b = LOAD.a.slice();
    for (var i = 0; i < TECH + CHARM; i++) paint("b", i);
  }

  /* fill any empty slot from the line, the class's own tier first — nobody
     walks into a fight with an empty bar */
  function seedLoadout(side) {
    var line = lineOf(classOf(side));
    var pool = DATA.skills.filter(function (s) { return line[s.cls]; })
      .sort(function (a, b) { return TREE[b.cls].tier - TREE[a.cls].tier || a.id - b.id; });
    var used = {};
    LOAD[side].forEach(function (sk) { if (sk) used[sk.id] = true; });
    for (var k = 0; k < TECH + CHARM; k++) {
      if (LOAD[side][k]) continue;
      var want = k < TECH ? "Technique" : "Charm";
      var next = pool.filter(function (s) { return s.kind === want && !used[s.id] && (want === "Technique" || (s.props && Object.keys(s.props).length) || s.passive); })[0];
      if (next) { LOAD[side][k] = next; used[next.id] = true; paint(side, k); }
    }
  }

  /* a class change drops anything the new line cannot equip, refills, and
     loads that line's sheet */
  function reclass(side) {
    LOAD[side].forEach(function (sk, k) {
      if (sk && !inLine(side, sk)) { LOAD[side][k] = null; paint(side, k); }
    });
    seedLoadout(side);
    applyDefaults(side);
    paintAll();
    if ($("mirror").checked && side === "a") mirrorLoadout();
    portraits();
    invalidate();
  }

  function hpSet(side, cur, max, shield, animate) {
    var f = $(side + "_hpfill"), pct = Math.max(0, Math.min(1, cur / max));
    f.style.transition = animate ? "width .45s ease" : "none";
    f.style.width = (pct * 100).toFixed(1) + "%";
    f.className = "hpfill" + (pct < 0.25 ? " low" : pct < 0.5 ? " mid" : "");
    var sh = $(side + "_shfill");
    if (sh) { sh.style.width = (Math.min(1, (shield || 0) / max) * 100).toFixed(1) + "%"; sh.hidden = !shield; }
    $(side + "_hptext").textContent = fmt(Math.max(0, cur)) + " / " + fmt(max) + (shield ? "  +" + fmt(shield) + " shield" : "");
  }

  function chips(side, list) {
    var el = $(side + "_status");
    if (!el) return;
    el.innerHTML = (list || []).map(function (s) {
      var cls = s.t === "Buff" ? "buff" : (s.t === "Debuff" || s.t === "AbnormalDebuff") ? "debuff" : "";
      return '<span class="chip ' + cls + '">' + s.n + (s.s > 1 ? " ×" + s.s : "") +
        (s.d > 0 ? '<i>' + s.d + '</i>' : "") + '</span>';
    }).join("");
  }

  function cdPaint(side, cd) {
    for (var k = 0; k < TECH; k++) {
      var el = $(side + "_slot" + k), ov = el.querySelector(".cdov");
      if (!ov) continue;
      var v = cd ? Math.max(0, cd[k] - 1) : 0;
      ov.hidden = !v; ov.textContent = v || "";
      el.classList.toggle("cooling", !!v);
    }
  }

  function orderStrip(from) {
    if (!PLAY) { $("orderstrip").innerHTML = ""; return; }
    var log = PLAY.sample.log, out = "";
    for (var i = from; i < Math.min(log.length, from + 10); i++) {
      var l = log[i];
      out += '<span class="ord ' + SIDE[l.side] + (i === from ? " now" : "") + '" title="' + l.who + " — " + l.skill + '">' +
        (l.skillId ? '<img src="../assets/skills/skill_' + l.skillId + '.png" alt="">' : '<b>' + (l.note ? "!" : l.who[0]) + '</b>') +
        '</span>';
    }
    if (from >= log.length) out = '<span class="ordend">end of fight</span>';
    $("orderstrip").innerHTML = out;
  }

  function float(side, text, cls) {
    var box = $(side + "_floats"), el = document.createElement("span");
    el.className = "float " + (cls || "");
    el.textContent = text;
    el.style.left = (18 + Math.random() * 64) + "%";
    box.appendChild(el);
    setTimeout(function () { if (el.parentNode) el.parentNode.removeChild(el); }, 1400);
  }

  function sceneReset() {
    if (!PLAY) return;
    clearTimers();
    PLAY.playing = false; PLAY.busy = false;
    hpSet("a", PLAY.A.hp, PLAY.A.hp, 0, false);
    hpSet("b", PLAY.B.hp, PLAY.B.hp, 0, false);
    SIDE.forEach(function (s, idx) {
      var load = idx === 0 ? LOAD.a : ($("mirror").checked ? LOAD.a : LOAD.b);
      var S = idx === 0 ? PLAY.A : PLAY.B;
      cdPaint(s, openingCds(load.slice(0, TECH), load.slice(TECH), S.srank));
      $(s + "_callout").textContent = "";
      $(s + "_floats").innerHTML = "";
      chips(s, []);
    });
    document.querySelectorAll(".slot.acting").forEach(function (e) { e.classList.remove("acting"); });
    $("banner").hidden = true;
    $("ribbon").hidden = true;
    $("combatlog").innerHTML = "";
    PLAY.i = 0;
    orderStrip(0);
  }

  /* ---------- playback: one action at a time, hits on the prefab's clock ---------- */
  var TIMERS = [];
  function later(fn, ms) { var t = setTimeout(fn, Math.max(0, ms)); TIMERS.push(t); return t; }
  function clearTimers() { TIMERS.forEach(clearTimeout); TIMERS = []; }
  function speedMs() { var v = parseInt($("speed").value, 10); return v; }   /* ms per game-second; 0 = instant */

  function ribbon(text, side) {
    var r = $("ribbon"); r.hidden = false; r.className = "ribbon " + side; r.textContent = text;
    r.classList.remove("in"); void r.offsetWidth; r.classList.add("in");
  }
  function pulse(el, cls, ms) {
    if (!el) return;
    cls.split(" ").forEach(function (c) { el.classList.remove(c); });
    void el.offsetWidth;
    cls.split(" ").forEach(function (c) { el.classList.add(c); });
    later(function () { cls.split(" ").forEach(function (c) { el.classList.remove(c); }); }, ms || 380);
  }
  function logLine(html, cls) {
    var ol = $("combatlog"), li = document.createElement("li");
    li.className = cls || ""; li.innerHTML = html; ol.appendChild(li);
    ol.scrollTop = ol.scrollHeight;
    return li;
  }
  function hitText(h) {
    if (h.blinded) return '<em class="miss">miss</em>';
    return fmt(h.d) + (h.crit ? ' <b class="crit">crit</b>' : h.block ? ' <i class="blk">block</i>' : '') +
      (h.absorbed ? ' <i class="blk">(' + fmt(h.absorbed) + ' to shield)</i>' : '');
  }
  function eventText(e) {
    if (e.kind === "heal") return '<span class="ev heal">' + WHO[e.who] + ' heals ' + fmt(e.amount) + ' <i>(' + e.tag + ')</i></span>';
    if (e.kind === "dmg") return '<span class="ev">' + e.tag + ' hits ' + WHO[e.who] + ' for ' + fmt(e.amount) + '</span>';
    return '<span class="ev st">\u2726 ' + e.name + ' on ' + WHO[e.who] + '</span>';
  }
  function headText(l) {
    return '<span class="who ' + SIDE[l.side] + '">' + l.who + '</span> <span class="tn">turn ' + l.turn +
      (l.sub ? ' \u00b7 cast ' + (l.sub + 1) : '') + '</span> \u2014 <b>' +
      (l.note && l.note !== "start" ? l.note + ', no action' : l.skill) + '</b>';
  }
  function sumText(l) {
    if (!l.hits.length) return "";
    return '<div class="sum">' + l.hits.length + (l.hits.length === 1 ? ' hit, ' : ' hits, ') + '<b>' + fmt(l.dmg) +
      '</b> \u2192 ' + WHO[1 - l.side] + ' at ' + fmt(l.left) + '</div>';
  }

  function playAction(l, k, done) {
    var me = SIDE[l.side], foe = SIDE[1 - l.side], f = speedMs() / 1000;
    var prev = k > 0 ? PLAY.sample.log[k - 1] : null;
    var hp = { a: prev ? prev.hpA : PLAY.A.hp, b: prev ? prev.hpB : PLAY.B.hp };
    var sh = { a: prev ? prev.shA : 0, b: prev ? prev.shB : 0 };
    var max = { a: PLAY.A.hp, b: PLAY.B.hp };
    document.querySelectorAll(".slot.acting").forEach(function (e) { e.classList.remove("acting"); });
    if (!l.sub) ribbon("Turn " + l.turn + " \u00b7 " + l.who, me);
    var li = logLine(headText(l), "turn " + me + (l.sub ? " cont" : ""));
    if (l.note && l.note !== "start") {
      $(me + "_callout").innerHTML = '<span class="ctl">' + l.note + '</span><small>turn ' + l.turn + '</small>';
      pulse($(me + "_portrait"), "stunned", 600 * f + 200);
      applyEvents(l, li, f, function () { finishAction(l, me, done, f); });
      return;
    }
    if (l.slot >= 0) $(me + "_slot" + l.slot).classList.add("acting");
    $(me + "_callout").innerHTML = '<span class="ele-' + (l.ele || "none").toLowerCase() + '">' + l.skill + '</span><small>turn ' + l.turn + '</small>';
    pulse($(me + "_portrait"), "lunge-" + me, 520 * f + 200);
    var hits = [], last = 0;
    var box = document.createElement("div"); box.className = "hits"; li.appendChild(box);
    l.hits.forEach(function (h) {
      var at = (0.15 + (h.at || 0)) * 1000 * f;
      last = Math.max(last, at);
      later(function () {
        var txt = h.blinded ? "MISS" : "\u2212" + fmt(h.d) + (h.crit ? " CRIT" : h.block ? " BLOCK" : "");
        float(foe, txt, h.blinded ? "block" : h.crit ? "crit" : h.block ? "block" : "");
        pulse($(foe + "_portrait"), h.crit ? "shake hard" : "shake", 320);
        if (h.crit) pulse($("arena"), "flash", 220);
        if (h.absorbed) sh[foe] = Math.max(0, sh[foe] - h.absorbed);
        hp[foe] = Math.max(0, hp[foe] - h.d);
        hpSet(foe, hp[foe], max[foe], sh[foe], true);
        hits.push(hitText(h));
        box.innerHTML = hits.join(" \u00b7 ");
        $("combatlog").scrollTop = $("combatlog").scrollHeight;
      }, at);
    });
    later(function () {
      li.innerHTML += sumText(l);
      applyEvents(l, li, f, function () { finishAction(l, me, done, f); });
    }, last + 240 * f);
  }

  function applyEvents(l, li, f, done) {
    l.events.forEach(function (e, k) {
      later(function () {
        var s = SIDE[e.who];
        if (e.kind === "heal") float(s, "+" + fmt(e.amount) + " " + e.tag, "heal");
        else if (e.kind === "dmg") { float(s, "\u2212" + fmt(e.amount) + " " + e.tag, ""); pulse($(s + "_portrait"), "shake", 300); }
        else float(s, e.name, "status");
        li.innerHTML += '<div class="evline">' + eventText(e) + '</div>';
        $("combatlog").scrollTop = $("combatlog").scrollHeight;
      }, k * 180 * f);
    });
    later(done, (l.events.length ? l.events.length * 180 + 120 : 0) * f);
  }

  function finishAction(l, me, done, f) {
    hpSet("a", l.hpA, PLAY.A.hp, l.shA, true);
    hpSet("b", l.hpB, PLAY.B.hp, l.shB, true);
    chips("a", l.stA); chips("b", l.stB);
    cdPaint(me, l.cd);
    PLAY.i++;
    orderStrip(PLAY.i);
    later(done, 300 * f);
  }

  function stepOnce() {
    if (!PLAY || PLAY.busy) return false;
    var log = PLAY.sample.log;
    if (PLAY.i >= log.length) { finish(); return false; }
    if (speedMs() === 0) { instant(); return false; }
    PLAY.busy = true;
    playAction(log[PLAY.i], PLAY.i, function () {
      PLAY.busy = false;
      if (PLAY.i >= PLAY.sample.log.length) finish();
      else if (PLAY.playing) stepOnce();
    });
    return true;
  }

  function instant() {
    var log = PLAY.sample.log;
    while (PLAY.i < log.length) {
      var l = log[PLAY.i]; PLAY.i++;
      var li = logLine(headText(l), "turn " + SIDE[l.side]);
      if (l.hits.length) li.innerHTML += '<div class="hits">' + l.hits.map(hitText).join(" \u00b7 ") + '</div>' + sumText(l);
      l.events.forEach(function (e) { li.innerHTML += '<div class="evline">' + eventText(e) + '</div>'; });
      hpSet("a", l.hpA, PLAY.A.hp, l.shA, false); hpSet("b", l.hpB, PLAY.B.hp, l.shB, false);
      chips("a", l.stA); chips("b", l.stB);
      cdPaint(SIDE[l.side], l.cd);
    }
    orderStrip(PLAY.i); finish();
  }

  function finish() {
    if (!PLAY) return;
    var s = PLAY.sample, b = $("banner");
    b.hidden = false;
    b.className = "banner " + (s.winner === 0 ? "wina" : s.winner === 1 ? "winb" : "draw");
    var text = s.winner === 0 ? "You win" : s.winner === 1 ? "Opponent wins"
      : (s.capped ? "Round cap reached \u2014 both standing" : "No result");
    b.innerHTML = text;
    logLine('<b>' + text + '</b> after ' + s.turns + ' actions', "end");
    $("ribbon").hidden = true;
    stopPlayback(true);
  }

  function stopPlayback(keepButtons) {
    if (PLAY) { PLAY.playing = false; PLAY.busy = false; }
    clearTimers();
    $("play").innerHTML = "&#9654; Watch one fight";
    if (!keepButtons) { $("play").disabled = !PLAY; $("step").disabled = !PLAY; }
  }

  function togglePlay() {
    if (!PLAY) return;
    if (PLAY.playing) { stopPlayback(); return; }
    if (PLAY.i >= PLAY.sample.log.length) sceneReset();
    PLAY.playing = true;
    $("play").innerHTML = "&#10074;&#10074; Pause";
    stepOnce();
  }

  /* ---------- slot picker ---------- */
  var current = null;
  function openPicker(side, slot) {
    current = { side: side, slot: slot };
    $("pickfind").value = "";
    /* the class filter offers the line, highest tier first */
    var line = Object.keys(lineOf(classOf(side))).sort(function (a, b) { return TREE[b].tier - TREE[a].tier; });
    $("pickclass").innerHTML = '<option value="">Whole line</option>' +
      line.map(function (c) { return '<option value="' + c + '">' + c + ' (T' + TREE[c].tier + ')</option>'; }).join("");
    fillList("");
    $("pickfind").placeholder = "Search " + (slot >= TECH ? "Charms" : "Techniques") + "…";
    $("pickele").hidden = slot >= TECH;
    $("picker").showModal();
    $("pickfind").focus();
  }
  function statusTags(s) {
    var tags = [];
    if (s.ec) {
      var seen = {};
      s.ec.hits.forEach(function (h) {
        h.on.forEach(function (o) {
          var mt = DATA.statuses[String(o.status)];
          if (!mt || seen[o.status]) return;
          seen[o.status] = 1;
          var nm = mt.falloff ? "falloff " + Math.round(mt.falloff.pct * 100) + "%/hit" : statusName(mt) + (mt.dur > 0 ? " " + mt.dur + "r" : "");
          tags.push(nm + (o.chance < 1 ? " " + Math.round(o.chance * 100) + "%" : ""));
        });
      });
    }
    (s.passive || []).forEach(function (pv) { tags.push("proc: " + pv.kind); });
    return tags.length ? " &middot; " + tags.join(", ") : "";
  }
  function fillList(q) {
    q = q.toLowerCase();
    var want = current && current.slot >= TECH ? "Charm" : "Technique";
    var line = lineOf(classOf(current.side));
    var wantCls = $("pickclass").value, wantEle = $("pickele").value;
    var matches = DATA.skills.filter(function (s) {
      if (s.kind !== want) return false;
      if (!line[s.cls]) return false;
      if (wantCls && s.cls !== wantCls) return false;
      if (wantEle && want === "Technique" && s.ele !== wantEle) return false;
      return !q || s.name.toLowerCase().indexOf(q) >= 0 || s.cls.toLowerCase().indexOf(q) >= 0;
    });
    $("pickcount").textContent = matches.length + " of " +
      DATA.skills.filter(function (s) { return s.kind === want && line[s.cls]; }).length +
      " in the " + classOf(current.side) + " line";
    var out = matches.slice(0, 200).map(function (s) {
      var on = LOAD[current.side].some(function (x, k) { return x && x.id === s.id && k !== current.slot; });
      var cdrow = s.r && s.r["22"] ? s.r["22"].CD : 0;
      var hits = s.ec && s.ec.hits ? s.ec.hits.length : (s.hits || 1);
      return '<button type="button" class="pick' + (on ? " equipped" : "") + '" data-id="' + s.id + '">' +
        '<img src="../assets/skills/skill_' + s.id + '.png" alt="" width="34" height="34" loading="lazy">' +
        '<span class="pn">' + s.name + '</span>' +
        '<span class="pm">' + s.cls + ' &middot; T' + s.tier +
        (s.kind === "Technique"
          ? ' &middot; ' + s.ele + (hits > 1 ? ' &middot; ' + hits + ' hits' : '') +
            (cdrow ? ' &middot; CD ' + cdrow : ' &middot; no CD') +
            (s.ec && s.ec.resetCdAtStart ? ' &middot; ready at start' : '')
          : ' &middot; Charm') + statusTags(s) +
        (on ? ' &middot; <b>equipped &mdash; picking moves it here</b>' : '') + '</span></button>';
    }).join("");
    $("picklist").innerHTML = out || '<p class="pickempty">Nothing matches.</p>';
  }

  function buildFilters() {
    var byTier = {}, eles = {};
    DATA.skills.forEach(function (s) {
      (byTier[s.tier] = byTier[s.tier] || {})[s.cls] = true;
      if (s.kind === "Technique") eles[s.ele] = true;
    });
    var html = '<option value="">All classes</option>';
    Object.keys(byTier).sort().forEach(function (t) {
      html += '<optgroup label="Tier ' + t + '">';
      Object.keys(byTier[t]).sort().forEach(function (c) { html += '<option value="' + c + '">' + c + '</option>'; });
      html += '</optgroup>';
    });
    var eh = '<option value="">Any element</option>';
    ["Physical", "Wind", "Water", "Fire", "Light", "Dark"].forEach(function (e) {
      if (eles[e]) eh += '<option value="' + e + '">' + e + '</option>';
    });
    $("pickele").innerHTML = eh;
  }

  /* ---------- hover cards ---------- */
  function tipHtml(side, sk) {
    var S = sheet(side), rows = sk.r[String(S.srank)] || {};
    var head = '<div class="tt-head"><img src="../assets/skills/skill_' + sk.id + '.png" alt=""><div><b>' + sk.name + '</b>' +
      '<span class="tt-meta">' + sk.kind + ' \u00b7 ' + sk.cls + ' T' + sk.tier +
      (sk.kind === "Technique" ? ' \u00b7 ' + sk.ele : '') + ' \u00b7 ' + (C.rankLabels[String(S.srank)] || "") + ' \u00b7 Lv ' + S.slevel + '</span></div></div>';
    var rowsHtml = "";
    if (sk.kind === "Technique") {
      var hits = sk.ec && sk.ec.hits.length ? sk.ec.hits.length : (sk.hits || 1);
      var cd = rows.CD || 0;
      rowsHtml += '<dt>Cooldown</dt><dd>' + (cd ? cd + ' turn' + (cd > 1 ? 's' : '') : 'none') + (sk.ec && sk.ec.resetCdAtStart ? ' \u00b7 ready at start' : '') + '</dd>';
      rowsHtml += '<dt>Hits</dt><dd>' + hits + '</dd>';
      ["SkillAttack1", "SkillAttack2", "SkillAttack3", "SkillAttack4"].forEach(function (k, i) {
        if (rows[k]) rowsHtml += '<dt>DMG' + (i ? ' ' + (i + 1) : '') + '</dt><dd>' + rows[k].toFixed(1) + '%</dd>';
      });
      var flat = flatOf(rows, "fx", "fg", "SkillFixedAttack1", S.slevel, S.rank.name);
      if (flat) rowsHtml += '<dt>Flat damage</dt><dd>+' + fmt(flat) + '</dd>';
      if (rows.SkillCureByHp) rowsHtml += '<dt>Heal</dt><dd>' + rows.SkillCureByHp.toFixed(1) + '% max HP</dd>';
    } else {
      var pr = sk.props && sk.props[String(S.srank)];
      if (pr) Object.keys(pr).forEach(function (prop) {
        if (TRIGGER_DISPLAY.test(prop)) return;
        var v = curveValue(pr[prop], S.srank, S.slevel, S.rank.name);
        if (!v) return;
        var f = PROP2FIELD[prop] || (PROP2RATIO[prop] || [])[0] || PROP2FLAT[prop] || PROP2SCALE[prop];
        var pct = pr[prop].pct || PROP2SCALE[prop];
        rowsHtml += '<dt>' + (LABEL[f] || prop) + '</dt><dd>+' + (pct ? v.toFixed(1) + '%' : fmt(v)) + '</dd>';
      });
      (sk.passive || []).forEach(function (pv) {
        var K = { hit: "on your hits", roundStart: "each turn", damaged: "when hit", roundCheck: "on a turn with no Technique", skillStart: "when a skill starts" };
        rowsHtml += '<dt>Proc</dt><dd>' + (K[pv.kind] || pv.kind) + (pv.rate < 1 ? ' ' + Math.round(pv.rate * 100) + '%' : '') + '</dd>';
      });
      if (isCdStartCharm(sk)) rowsHtml += '<dt>At battle start</dt><dd>all Technique CDs ' + cdStartOf([sk]) + '</dd>';
    }
    var st = statusTags(sk).replace(/^ &middot; /, "");
    return head + (rowsHtml ? '<dl class="tt-rows">' + rowsHtml + '</dl>' : '') +
      (sk.desc ? '<div class="tt-desc">' + sk.desc + '</div>' : '') +
      (st ? '<div class="tt-st">\u2726 ' + st + '</div>' : '');
  }
  function showTip(el) {
    var side = el.getAttribute("data-side"), slot = parseInt(el.getAttribute("data-slot"), 10);
    var sk = LOAD[side][slot], tip = $("skilltip");
    if (!sk) { tip.hidden = true; return; }
    tip.innerHTML = tipHtml(side, sk); tip.hidden = false;
    var r = el.getBoundingClientRect(), w = tip.offsetWidth, h = tip.offsetHeight;
    var x = r.right + 12, y = r.top - 8;
    if (x + w > window.innerWidth - 8) x = r.left - w - 12;
    if (x < 8) x = 8;
    if (y + h > window.innerHeight - 8) y = Math.max(8, window.innerHeight - h - 8);
    tip.style.left = x + "px"; tip.style.top = y + "px";
  }
  function hideTip() { $("skilltip").hidden = true; }

  function invalidate() {
    stopPlayback();
    PLAY = null;
    $("play").disabled = true; $("step").disabled = true;
    $("banner").hidden = true;
    $("orderstrip").innerHTML = '<span class="ordend">run the duel to see the order of play</span>';
    document.querySelectorAll(".slot.acting").forEach(function (e) { e.classList.remove("acting"); });
    SIDE.forEach(function (s) { cdPaint(s, null); $(s + "_callout").textContent = ""; chips(s, []); });
    var A = sheet("a"), B = $("mirror").checked ? A : sheet("b");
    hpSet("a", A.hp, A.hp, 0, false); hpSet("b", B.hp, B.hp, 0, false);
    portraits();
  }

  function boot() {
    buildFilters();
    $("pickclass").addEventListener("change", function () { fillList($("pickfind").value); });
    $("pickele").addEventListener("change", function () { fillList($("pickfind").value); });
    SIDE.forEach(function (side) {
      for (var i = 0; i < TECH + CHARM; i++) {
        (function (s, k) {
          var el = $(s + "_slot" + k);
          el.addEventListener("click", function () { hideTip(); openPicker(s, k); });
          el.addEventListener("mouseenter", function () { showTip(el); });
          el.addEventListener("mouseleave", hideTip);
          el.addEventListener("focus", function () { showTip(el); });
          el.addEventListener("blur", hideTip);
        })(side, i);
      }
    });
    window.addEventListener("scroll", hideTip, { passive: true });
    $("pickfind").addEventListener("input", function () { fillList(this.value); });
    $("pickclose").addEventListener("click", function () { $("picker").close(); });
    $("pickclear").addEventListener("click", function () {
      if (current) { LOAD[current.side][current.slot] = null; paint(current.side, current.slot); invalidate(); }
      $("picker").close();
    });
    $("picklist").addEventListener("click", function (ev) {
      var b = ev.target.closest ? ev.target.closest(".pick") : null;
      if (!b || !current) return;
      var id = parseInt(b.getAttribute("data-id"), 10);
      var picked = DATA.skills.filter(function (s) { return s.id === id; })[0] || null;
      if (picked) {
        LOAD[current.side].forEach(function (x, k) {
          if (x && x.id === picked.id && k !== current.slot) { LOAD[current.side][k] = null; paint(current.side, k); }
        });
      }
      LOAD[current.side][current.slot] = picked;
      paint(current.side, current.slot);
      if ($("mirror").checked && current.side === "a") mirrorLoadout();
      invalidate();
      $("picker").close();
    });
    $("run").addEventListener("click", run);
    $("play").addEventListener("click", togglePlay);
    $("step").addEventListener("click", function () {
      if (!PLAY) return;
      if (PLAY.busy) return;
      PLAY.playing = false; $("play").innerHTML = "&#9654; Watch one fight";
      if (PLAY.i >= PLAY.sample.log.length) sceneReset();
      stepOnce();
    });
    $("reset").addEventListener("click", function () {
      try { localStorage.removeItem("pw_duel"); } catch (e) {}
      location.reload();
    });
    $("mirror").addEventListener("change", function () {
      document.querySelector('.fighter[data-side="b"]').classList.toggle("dimmed", this.checked);
      document.querySelector('.duelstats details:nth-of-type(2)').classList.toggle("dimmed", this.checked);
      if (this.checked) mirrorLoadout();
      portraits();
      invalidate();
    });
    $("a_cls").addEventListener("change", function () { reclass("a"); });
    $("b_cls").addEventListener("change", function () { reclass("b"); });
    document.querySelector('.fighter[data-side="b"]').classList.toggle("dimmed", $("mirror").checked);
    document.querySelector('.duelstats details:nth-of-type(2)').classList.toggle("dimmed", $("mirror").checked);
    document.querySelectorAll(".duelstats input, .duelstats select").forEach(function (el) {
      el.addEventListener("change", function () { paintAll(); invalidate(); });
    });
  }

  Promise.all([
    fetch("../assets/duel.json?v=" + (C.v || "")).then(function (r) { return r.json(); }),
    fetch("../assets/curves.json?v=" + (C.v || "")).then(function (r) { return r.json(); })
  ]).then(function (v) {
    DATA = v[0]; CURVES = v[1];
    DATA.statuses = DATA.statuses || {}; DATA.trig = DATA.trig || {};
    boot();
    /* the opening matchup: an Archmage against a Berserker, each with a kit from
       its own line and its line's sheet. Both kits carry the same cooldown
       pattern (2, 1, 1, none) so the turn rhythm is easy to follow. Divine Wrath
       at this rank is a near one-shot even after the PvP scaling, so it is left
       for the picker rather than the opening demo */
    var KITS = {
      a: ["Aqua Vortex", "Howling Hurricane", "Fire Blast", "Meteoric Flames",
          "Rapid Cast", "Frost Guard", "Incarnation of Light", "Radiant Sear"],
      b: ["Heavy Impact", "Quadrant Slash", "Leap Attack", "Edge Strike",
          "Blade Siphon", "Soulfire Protection", "Blade Tempest", "Insightful Eye"]
    };
    SIDE.forEach(function (side) {
      KITS[side].forEach(function (nm, i) {
        var s = DATA.skills.filter(function (x) { return x.name === nm; })[0];
        if (s) LOAD[side][i] = s;
      });
      applyDefaults(side);
    });
    paintAll();
    invalidate();
    $("run").disabled = false;
  }).catch(function () {
    $("run").textContent = "Could not load skill data";
  });
})();
