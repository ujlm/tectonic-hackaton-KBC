// Scale benchmark: runs the same decide() used for Sarah and Jos on 2.3M synthetic customers.
// Run: node engine/bench.js
const { decide, run } = require('./engine');
const base = require('./data/customers.json').customers;

let seed = 20260930;
const rnd = () => { seed |= 0; seed = seed + 0x6D2B79F5 | 0; let t = Math.imul(seed ^ seed >>> 15, 1 | seed); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };

const N = 2_300_000;
const count = { silent: 0, ask: 0, act: 0, wait: 0, noSignal: 0 };
const t0 = process.hrtime.bigint();
for (let i = 0; i < N; i++) {
  if (rnd() > 0.09) { count.noSignal++; continue; }           // no life-moment signal tonight
  const confidence = 0.35 + rnd() * 0.6;
  const usedBudget = rnd() < 0.18 ? 2 : 0;                     // some customers already got 2 suggestions this week
  count[decide(confidence, usedBudget)]++;
}
const ms = Number(process.hrtime.bigint() - t0) / 1e6;

const f = n => n.toLocaleString('en-GB');
console.log(`\nScored ${f(N)} customers in ${ms.toFixed(0)} ms on one core (${f(Math.round(N / (ms / 1000)))} customers/s)\n`);
console.log(`  no signal tonight   ${f(count.noSignal)}`);
console.log(`  stay silent         ${f(count.silent)}`);
console.log(`  ask a question      ${f(count.ask)}`);
console.log(`  wait (budget used)  ${f(count.wait)}`);
console.log(`  act (LLM writes)    ${f(count.act)}  → ${(100 * count.act / N).toFixed(1)}% of customers, ~€${f(Math.round(count.act * 0.0006))} LLM cost at €0.0006/message\n`);

// Full pipeline (signals → moment → decision → blindspots → layout) on 200,000 varied customers, extrapolated to 2.3M
const SAMPLE = 200_000;
const variants = [];
for (let i = 0; i < 64; i++) {
  const b = base[i % base.length];
  variants.push({ ...b, consent: { ...b.consent, peerPatterns: rnd() > 0.1, appUsage: rnd() > 0.08 }, checkins: rnd() < 0.2 ? ['moving'] : [] });
}
const t1 = process.hrtime.bigint(); let acts = 0;
for (let i = 0; i < SAMPLE; i++) { if (run(variants[i & 63]).decision === 'act') acts++; }
const ms2 = Number(process.hrtime.bigint() - t1) / 1e6;
const perSec = SAMPLE / (ms2 / 1000);
console.log(`Full engine: ${f(SAMPLE)} customers in ${ms2.toFixed(0)} ms → ${f(Math.round(perSec))} customers/s`);
console.log(`→ all 2.3M customers in ~${(N / perSec).toFixed(0)} s on ONE laptop core (nightly batch window: hours)\n`);
