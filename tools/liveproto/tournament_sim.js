// Tournament simulation on the team engine (web/dist/assets/team.js), from tools/liveproto/tournament.py output.
//   node tools/liveproto/tournament_sim.js out/liveproto/tournament.json out/liveproto/tournament_fighters.json out/liveproto/tournament_result.json [fightsPerMatch]
// Plays every bracket match whose two teams have full sheets for all four members; a match with an incomplete team is
// decided by the game's own Power rank (team CombatRatingRank) and marked so. Division winners are then projected
// through the Knockouts and Finals the same way. Nothing here is a rule of the game beyond the bracket it was given.
const fs = require('fs'), path = require('path');
const ROOT = path.resolve(__dirname, '..', '..'), DIST = path.join(ROOT, 'web', 'dist');
const [tourPath, fightersPath, outPath, nStr] = process.argv.slice(2);
const N = parseInt(nStr || '300', 10);
const html = fs.readFileSync(path.join(DIST, 'combat/team.html'), 'utf8');
const cfgText = html.match(/id="teamdata">(.*?)<\/script>/s)[1].replace(/<\\\//g, '</');
const C = JSON.parse(cfgText);
const DATA = JSON.parse(fs.readFileSync(path.join(DIST, 'assets/duel.json'), 'utf8'));
const CURVES = JSON.parse(fs.readFileSync(path.join(DIST, 'assets/curves.json'), 'utf8'));
const FIGHTERS = JSON.parse(fs.readFileSync(fightersPath, 'utf8'));
const T = JSON.parse(fs.readFileSync(tourPath, 'utf8'));
let src = fs.readFileSync(path.join(DIST, 'assets/team.js'), 'utf8');
src = src.replace(/\n  Promise\.all\(\[[\s\S]*$/, '\n  global.__engine = { oneFight, sheetOf, eff, pvpGovernor, mulberry, setData: function (d, c) { DATA = d; CURVES = c; d.skills.forEach(function (s) { SKILL[s.id] = s; }); } };\n})();\n');
const els = {};
global.window = global;
global.localStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} };
global.document = {
  getElementById: (id) => els[id] || (els[id] = { textContent: id === 'teamdata' ? cfgText : '', value: id === 'serverdays' ? '150' : id === 'maxrounds' ? '100' : '', addEventListener: () => {}, style: {}, classList: { toggle: () => {}, add: () => {}, remove: () => {} }, innerHTML: '', hidden: false, disabled: false, querySelectorAll: () => [], querySelector: () => null, getBoundingClientRect: () => ({}) }),
  querySelectorAll: () => [], querySelector: () => null, addEventListener: () => {}, createElement: () => ({ style: {}, classList: { add: () => {} }, appendChild: () => {} })
};
eval(src);
const E = global.__engine;
E.setData(DATA, CURVES);
const byId = {}; FIGHTERS.forEach(f => { byId[String(f.id)] = f; });
const P = C.grid.start[0].concat(C.grid.start[1]).map(c => ({ x: c[0], y: c[1] }));

function teamFighters(tid) {
  const t = T.teams[String(tid)]; if (!t || !t.players) return null;
  const fs_ = t.players.map(p => byId[String(p)]);
  return fs_.every(Boolean) && fs_.length === 4 ? fs_ : null;
}
function play(aId, bId) {
  const A = teamFighters(aId), B = teamFighters(bId);
  if (!A || !B) return null;
  const F = A.concat(B);
  const sheets = F.map(f => { const s = E.sheetOf(f); s.slevel = f.level; s.skillRanks = f.techs.concat(f.charms).map(t => t.rank); return s; });
  const gov = E.pvpGovernor(sheets);
  let wins = 0, len = 0;
  for (let i = 0; i < N; i++) {
    const r = E.oneFight(F, P, E.mulberry(1000 + i), false, 100, gov.scale);
    if (r.winner === 0) wins++;
    len += r.turns || 0;
  }
  return { a: wins / N, b: 1 - wins / N, turns: len / N, governor: gov.scale };
}
function rankOf(tid) { const t = T.teams[String(tid)]; return t && t.combatRatingRank ? t.combatRatingRank : 9999; }
function nameOf(tid) { const t = T.teams[String(tid)]; return t ? (t.name || String(tid)) : String(tid); }
const isBye = (id) => !id || id === 0 || id === '0';
function decide(aId, bId) {
  if (isBye(bId)) return { winner: aId, how: 'bye' };
  if (isBye(aId)) return { winner: bId, how: 'bye' };
  const sim = play(aId, bId);
  if (sim) return { winner: sim.a >= 0.5 ? aId : bId, how: 'simulated', odds: sim };
  return { winner: rankOf(aId) <= rankOf(bId) ? aId : bId, how: 'power-rank' };
}
function runBracket(teamIds, firstPairs) {
  // first round from the real tree when given, later rounds pair winners in order (standard single elimination)
  let pairs = firstPairs && firstPairs.length ? firstPairs.map(p => [p[0], p[1] === undefined ? '0' : p[1]]) : [];
  if (!pairs.length) { const ids = teamIds.slice(); pairs = []; while (ids.length) pairs.push([ids.shift(), ids.length ? ids.shift() : '0']); }
  const rounds = [];
  let alive = null;
  while (true) {
    const res = pairs.map(([a, b]) => Object.assign({ a, b }, decide(a, b)));
    rounds.push(res);
    alive = res.map(r => r.winner);
    if (alive.length <= 1) break;
    pairs = []; while (alive.length) pairs.push([alive.shift(), alive.length ? alive.shift() : '0']);
  }
  return { rounds, winner: alive[0] };
}

const out = { fightsPerMatch: N, divisions: {}, knockouts: null, finals: null, notes: [] };
const winners = [];
Object.values(T.divisions).sort((a, b) => a.id - b.id).forEach(d => {
  const first = d.tree && (d.tree.First || d.tree['1']) ? (d.tree.First || d.tree['1']) : null;
  const r = runBracket(d.teamIds, first);
  out.divisions[d.id] = { id: d.id, round: d.round, teams: d.teamIds.map(t => ({ id: t, name: nameOf(t), rank: rankOf(t), complete: !!teamFighters(t) })), rounds: r.rounds, winner: r.winner, winnerName: nameOf(r.winner) };
  winners.push(r.winner);
  process.stderr.write(`division ${d.id}: ${nameOf(r.winner)} (${r.rounds.map(x => x.map(m => m.how[0]).join('')).join('/')})\n`);
});
// Knockouts: the card says up to 4 divisions of 16 and the winners meet in the Finals. How the 64 winners are split
// is not in the client, so this projection seeds them by Power rank in snake order across four groups (an assumption).
const sorted = winners.slice().sort((a, b) => rankOf(a) - rankOf(b));
const groups = [[], [], [], []];
sorted.forEach((t, i) => { const k = i % 8 < 4 ? i % 4 : 3 - (i % 4); groups[k].push(t); });
out.notes.push('Knockout groups are an assumption: the 64 projected winners seeded by Power rank in snake order into four groups; the game does not publish its rule.');
out.knockouts = groups.map((g, i) => { const r = runBracket(g, null); return { group: i + 1, teams: g.map(t => ({ id: t, name: nameOf(t), rank: rankOf(t), complete: !!teamFighters(t) })), rounds: r.rounds, winner: r.winner, winnerName: nameOf(r.winner) }; });
const four = out.knockouts.map(k => k.winner);
const match = (a, b) => Object.assign({ a, b }, decide(a, b));
const semi1 = match(four[0], four[3]), semi2 = match(four[1], four[2]);
const final = match(semi1.winner, semi2.winner);
const third = match(semi1.winner === four[0] ? four[3] : four[0], semi2.winner === four[1] ? four[2] : four[1]);
out.finals = { semis: [semi1, semi2], third, final, champion: final.winner, championName: nameOf(final.winner) };
out.matches = { simulated: 0, powerRank: 0, byes: 0 };
const count = (r) => { r.forEach(m => { if (m.how === 'simulated') out.matches.simulated++; else if (m.how === 'power-rank') out.matches.powerRank++; else out.matches.byes++; }); };
Object.values(out.divisions).forEach(d => d.rounds.forEach(count)); out.knockouts.forEach(k => k.rounds.forEach(count)); count([semi1, semi2, third, final]);
fs.writeFileSync(outPath, JSON.stringify(out));
console.log(`champion: ${nameOf(final.winner)}; matches simulated ${out.matches.simulated}, by power rank ${out.matches.powerRank}, byes ${out.matches.byes}`);
