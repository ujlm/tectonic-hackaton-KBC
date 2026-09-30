# Kate Pulse: a bank that notices, asks, and then stays quiet

Tectonic Hackathon 2026 · KBC challenge

Today Kate mostly waits for a question, or pushes offers that look like everyone else's. **Pulse** keeps a living picture of each customer, built from four kinds of signals and confirmed by the customer. It follows one rule:

> **Act when sure. Ask when unsure. Stay silent otherwise.**

Each customer sees one thing that matters today, including the blindspot they'd otherwise miss, in a layout learned from how they use the app. The same picture prepares advisor meetings and, added up across 2.3M customers, tells KBC what to build next.

## Try it (no install needed)

| What | How |
|---|---|
| Landing page | open `index.html` |
| Customer app (Sarah, Jos, KBC view) | open `app/index.html`, use ‹ › in the dark bar to follow the demo |
| Insights dashboard (big data + Conveo) | open `insights/index.html`, click **Ask why** or **Run study** |
| Decision engine | `node engine/engine.js` (Node 18+). Writes `engine/output/pulse-data.js`, which the app reads |
| Scale benchmark | `node engine/bench.js` |
| Voice-over (ElevenLabs) | `cp .env.example .env`, add your key, then `ELEVENLABS_API_KEY=... node voice/generate.js` |

## How we answer KBC's five questions

**1. What signals help us understand what customers need?**
Four layers, each tagged with its source and the consent it needs (`engine/engine.js`, `MOMENT_RULES`):
- **Told:** one-tap check-ins, goals and "not for me" answers. These always outrank what we infer.
- **Money:** a notary deposit, a first salary, a falling balance, a new payee.
- **Behaviour:** simulators opened, searches, what customers act on or ignore, when they open the app.
- **Context:** product gaps, deadlines (deed date) and anonymous patterns from similar customers.

At the macro level, **big data** shows *what* 2.3M customers do and **Conveo** AI video interviews explain *why* (`insights/index.html`).

**2. How are customers recognised by situation, behaviour and intent?**
Signals add up to a **life moment with a confidence score**. Sarah is 62% likely to be buying a home, so Kate *asks*. After one tap she's at 92%, so Kate *acts*. Intent is confirmed, not guessed. The advisor brief marks every fact as *confirmed* or *inferred*.

**3. How do experiences adapt automatically?**
- **Content:** blindspots are ranked by cost to *this* customer, not by product margin.
- **Timing:** pushes are sent at each customer's learned best moment, capped by a weekly *attention budget*.
- **Form:** the layout is learned from behaviour, never assigned by age. Jos gets big text and one thing at a time; Sarah gets shortcuts and Kate as her guide.
- **Feedback:** "not now" snoozes an item, "not for me" removes it for good, and switching a signal off lowers the confidence live.

**4. How does this work across products, services and channels?**
There's **one customer picture**, and every channel reads from it: the app card, push, Kate chat, the voice read-aloud (ElevenLabs) and the advisor. Journeys cross product lines, like mortgage → home insurance → income protection → shared account. The advisor brief means nobody asks twice.

**5. How do we create impact for millions at once?**
There are three speeds: **real-time** for risky payments (rules only, under 2 s), a **nightly batch** for life moments, and a **precomputed card** when the app opens (no model call). Cheap rules score everyone, and the LLM only writes the ~3% of messages that go out.
- `node engine/bench.js` measures ~280k customers/s for the full engine on one laptop core. That's **~8 s for all 2.3M customers**, and about €40 of LLM cost a night.
- Guardrails: consent is enforced before scoring, one central attention budget, amounts come from data rather than the LLM, advice goes to a human, and there's a fairness check across age groups.
- The insights loop (**what → why → change → measure**) turns every customer's behaviour into better products for everyone.

## What's real and what's simulated

- **Real:** the decision engine (signals, confidence, ask/act/silent, blindspot ranking, real-time fraud check, layout choice). Its output drives the confidence and the fraud check in the app. The scale benchmark is real, and so is the ElevenLabs script.
- **Simulated:** all customer data is synthetic. The insights figures, Conveo interviews and quotes, A/B results and cost per message are illustrative assumptions. No LLM is called; card texts are pre-written.

## Security notes (Aikido)

No API keys in the repo: `.env` is git-ignored and `.env.example` holds placeholders. The prototype has no backend and no customer-ID endpoints (so there's no IDOR surface), and it collects no credentials or personal data. The engine reads only local synthetic JSON.

## Unfinished / next steps

- Real LLM phrasing (Gemini on Google Cloud), grounded in the engine output, with a number validator.
- An event-stream backend for the real-time lane, and a feature store for the nightly batch.
- Privacy-preserving compute for data that leaves KBC (for example encrypted processing, such as KU Leuven spin-off Belfort).
- A Conveo integration triggered by anomalies from the insights dashboard.
- A Dutch/French interface.

## Structure

```
index.html            landing page
app/index.html        customer app prototype (mobile first)
insights/index.html   KBC insights dashboard (browser first)
engine/engine.js      decision engine   engine/bench.js  2.3M benchmark
engine/data/          synthetic customers
engine/output/        generated engine output (read by the app)
docs/voiceover.json   demo voice-over script
voice/generate.js     ElevenLabs text-to-speech
```

Hackathon concept. Not a KBC product.
