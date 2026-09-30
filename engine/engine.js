// Kate Pulse decision engine (hackathon prototype).
// Turns raw customer data into: life moments + confidence, an ask/act/silent decision,
// blindspots ranked by cost to the customer, a real-time fraud check, and a UI layout.
// Pure functions, no dependencies, no network. Run: node engine/engine.js

const fs = require('fs');
const path = require('path');

// ---------- 1. Signals: each one has a weight, a source and the consent it needs ----------
const MOMENT_RULES = {
  moving: {
    label: 'Buying a home',
    signals: [
      { id: 'checkin',  weight: 0.40, consent: null,          test: c => c.checkins.includes('moving'),
        text: () => 'You told us you’re buying a home', source: 'Check-in' },
      { id: 'notary',   weight: 0.22, consent: 'transactions', test: c => c.transactions.some(t => t.category === 'notary' && t.amount <= -5000),
        text: c => `Notary deposit of €${Math.abs(c.transactions.find(t => t.category === 'notary').amount).toLocaleString('en-GB')}`, source: 'Transactions' },
      { id: 'sim',      weight: 0.15, consent: 'appUsage',     test: c => c.appEvents.filter(e => e.tool === 'mortgage').length >= 3,
        text: c => `Mortgage simulator opened ${c.appEvents.filter(e => e.tool === 'mortgage').length}×`, source: 'App use' },
      { id: 'search',   weight: 0.10, consent: 'appUsage',     test: c => !c.checkins.includes('moving') && c.appEvents.some(e => e.type === 'search' && /insurance|home|house/.test(e.query)),
        text: () => 'Searched for home insurance', source: 'App use' },
      { id: 'gap',      weight: 0.10, consent: 'products',     test: c => c.products.includes('mortgage_offer') && !c.products.includes('income_protection'),
        text: () => 'Mortgage offer without income protection', source: 'Products you hold' },
      { id: 'peers',    weight: 0.05, consent: 'peerPatterns', test: () => true,
        text: () => 'Similar first-time buyers', source: 'Anonymous patterns' }
    ]
  },
  first_job: {
    label: 'First job',
    signals: [
      { id: 'first_salary', weight: 0.55, consent: 'transactions', test: c => c.transactions.some(t => t.category === 'salary' && t.firstTime),
        text: () => 'First salary from a new employer', source: 'Transactions' },
      { id: 'search_sav',   weight: 0.15, consent: 'appUsage', test: c => c.appEvents.some(e => e.type === 'search' && /saving/.test(e.query)),
        text: () => 'Searched for savings', source: 'App use' }
    ]
  },
  cash_squeeze: {
    label: 'Cash squeeze',
    signals: [
      { id: 'balance_down', weight: 0.45, consent: 'transactions', test: c => (c.balanceTrend || []).length >= 3 && c.balanceTrend.at(-1) < 0,
        text: () => 'Balance below zero after 4 months of decline', source: 'Transactions' },
      { id: 'overdraft_fee', weight: 0.20, consent: 'transactions', test: c => c.transactions.some(t => t.category === 'fees'),
        text: () => 'Overdraft interest charged', source: 'Transactions' },
      { id: 'energy_spike', weight: 0.15, consent: 'transactions', test: c => c.transactions.some(t => t.category === 'energy' && t.amount <= -250),
        text: () => 'Energy bill much higher than usual', source: 'Transactions' }
    ]
  }
};

const THRESHOLD = { ask: 0.50, act: 0.70 };

function scoreMoments(c) {
  const out = [];
  for (const [key, rule] of Object.entries(MOMENT_RULES)) {
    const used = [], blocked = [];
    for (const s of rule.signals) {
      if (!s.test(c)) continue;
      const allowed = !s.consent || c.consent[s.consent];
      (allowed ? used : blocked).push({ id: s.id, weight: s.weight, text: s.text(c), source: s.source });
    }
    if (!used.length || (used.length === 1 && used[0].id === 'peers')) continue;
    const confidence = Math.min(0.99, used.reduce((a, s) => a + s.weight, 0));
    out.push({ moment: key, label: rule.label, confidence: +confidence.toFixed(2), signals: used, blockedByConsent: blocked });
  }
  return out.sort((a, b) => b.confidence - a.confidence);
}

// ---------- 2. Decision: act when sure, ask when unsure, stay silent otherwise ----------
function decide(confidence, suggestionsThisWeek = 0, budget = 2) {
  if (confidence < THRESHOLD.ask) return 'silent';
  if (confidence < THRESHOLD.act) return 'ask';
  if (suggestionsThisWeek >= budget) return 'wait';
  return 'act';
}

// ---------- 3. Blindspots: gaps that matter for THIS moment, ranked by cost to the customer ----------
function blindspots(c, moment) {
  const list = [];
  if (moment === 'moving' && c.mortgage) {
    if (!c.products.includes('home_insurance'))
      list.push({ id: 'home_insurance', title: `Home insurance before ${c.mortgage.deedDate}`, why: 'The notary needs proof before the deed date.', costToCustomer: 5000, deadline: c.mortgage.deedDate });
    if (!c.products.includes('income_protection'))
      list.push({ id: 'income_protection', title: 'If one of you can’t work, the mortgage payment stays', why: `€${c.mortgage.monthly.toLocaleString('en-GB')} a month is ${Math.round(100 * c.mortgage.monthly / c.income.monthlyNet)}% of your net income on one salary.`, costToCustomer: c.mortgage.monthly * 12, blindspot: true });
    if (!c.feedback.notForMe.includes('shared_account'))
      list.push({ id: 'shared_account', title: 'Shared household account', why: 'Optional, handy after the move.', costToCustomer: 0 });
  }
  if (moment === 'first_job' && !c.products.includes('pension_saving'))
    list.push({ id: 'pension_saving', title: 'Start pension saving with tax benefit', why: 'Starting at 24 instead of 34 roughly doubles the result.', costToCustomer: 900, blindspot: true });
  if (moment === 'cash_squeeze')
    list.push({ id: 'budget_help', title: 'Talk to someone about your budget', why: 'Before overdraft interest adds up.', costToCustomer: 300 });
  return list.sort((a, b) => b.costToCustomer - a.costToCustomer || (a.deadline ? -1 : 1));
}

// ---------- 4. Real-time lane: a payment that doesn't look like this customer ----------
function fraudCheck(c) {
  const out = c.transactions.filter(t => t.amount < 0 && !t.newPayee).map(t => -t.amount).sort((a, b) => a - b);
  const median = out.length ? out[Math.floor(out.length / 2)] : 0;
  const hit = c.transactions.find(t => t.newPayee && -t.amount > Math.max(500, 10 * median));
  return hit ? { action: 'pause_and_ask', holdHours: 24, payment: hit, reason: `New payee and ${Math.round(-hit.amount / median)}× larger than a typical payment`, notify: c.trustedPerson || null } : null;
}

// ---------- 5. Layout: learned from behaviour, never assigned by age ----------
function layout(c) {
  const b = c.behaviour;
  if (b.menuUseRate < 0.1 || b.textZoom >= 1.4)
    return { mode: 'simple', reasons: [b.menuUseRate < 0.1 && 'rarely uses the menus', b.textZoom >= 1.4 && 'enlarged text on the phone', b.branchCalls90d >= 2 && 'prefers calling the branch'].filter(Boolean) };
  return { mode: 'full', reasons: [b.searchUseRate > 0.3 && 'uses search and shortcuts', b.avgReadSeconds < 8 && 'skims: keep it short'].filter(Boolean) };
}
function bestHour(c) {
  const h = c.appEvents.map(e => e.hour).filter(x => x != null);
  if (!h.length) return null;
  const f = {}; h.forEach(x => f[x] = (f[x] || 0) + 1);
  return +Object.entries(f).sort((a, b) => b[1] - a[1])[0][0];
}

function run(customer) {
  const moments = scoreMoments(customer);
  const top = moments[0] || null;
  return {
    id: customer.id, name: customer.name,
    fraud: fraudCheck(customer),
    topMoment: top,
    decision: top ? decide(top.confidence) : 'silent',
    blindspots: top ? blindspots(customer, top.moment) : [],
    layout: layout(customer),
    bestHour: bestHour(customer)
  };
}

module.exports = { scoreMoments, decide, blindspots, fraudCheck, layout, run, THRESHOLD };

// ---------- CLI: read data, write output for the app ----------
if (require.main === module) {
  const data = JSON.parse(fs.readFileSync(path.join(__dirname, 'data', 'customers.json'), 'utf8'));
  const results = {};
  for (const c of data.customers) {
    results[c.id] = run(c);
    // Same customer after confirming the check-in: shows how confidence changes
    if (results[c.id].decision === 'ask') {
      const confirmed = run({ ...c, checkins: [...c.checkins, results[c.id].topMoment.moment] });
      results[c.id].afterConfirm = { confidence: confirmed.topMoment.confidence, decision: confirmed.decision, signals: confirmed.topMoment.signals };
    }
  }
  const outDir = path.join(__dirname, 'output');
  fs.mkdirSync(outDir, { recursive: true });
  const payload = { generatedAt: new Date().toISOString(), thresholds: THRESHOLD, customers: results };
  fs.writeFileSync(path.join(outDir, 'pulse-data.json'), JSON.stringify(payload, null, 2));
  fs.writeFileSync(path.join(outDir, 'pulse-data.js'), '// Generated by engine/engine.js. Do not edit.\nwindow.PULSE = ' + JSON.stringify(payload) + ';\n');

  console.log('\nKate Pulse engine: decisions for', data.customers.length, 'customers\n');
  for (const r of Object.values(results)) {
    const m = r.topMoment;
    console.log(`• ${r.name.padEnd(6)} ${m ? `${m.label} (${Math.round(m.confidence * 100)}%)`.padEnd(26) : 'no moment'.padEnd(26)} → ${r.decision.toUpperCase().padEnd(6)}`
      + (r.afterConfirm ? ` → after check-in ${Math.round(r.afterConfirm.confidence * 100)}% ${r.afterConfirm.decision.toUpperCase()}` : '')
      + (r.fraud ? `  | REAL-TIME: pause €${-r.fraud.payment.amount} to ${r.fraud.payment.counterparty}` : '')
      + `  | layout: ${r.layout.mode}`);
    r.blindspots.forEach((b, i) => console.log(`    ${i + 1}. ${b.blindspot ? '[blindspot] ' : ''}${b.title}`));
  }
  console.log('\nWrote engine/output/pulse-data.js (loaded by app/index.html)\n');
}
