# Decisions: Kate conversation + Guardian

Last updated 30 September 2026. This file locks the decisions for this phase.

- **A. Decided by you:** final.
- **B. Recommended:** locked unless you object. To change one, edit its line or tell me.
- **C. Needs your action or OK:** nothing proceeds on these without you.

## A. Decided by you

| # | Topic | Decision |
|---|---|---|
| A1 | Sessions | **Held by the client.** The browser keeps the session in localStorage and sends it with every request. The engine is stateless. |
| A2 | Deploys | I may run `vercel link` and preview deploys. I never set Vercel or GCP secrets. The prototype was committed first as a baseline: [PR #1](https://github.com/ujlm/tectonic-hackaton-KBC/pull/1). |
| A3 | Installs | I may install the web npm dependencies, Playwright's Chromium and pytest (already in `.venv`). |
| A4 | Check-ins | Stop after M1 (data and engine) for a review, then continue through M6. |
| A5 | LLM provider | **Vercel AI Gateway**, not Vertex directly, because your GCP project has no access to `gemini-3.8-flash`. The key is `AI_GATEWAY_API_KEY` in `.env.local` at the repo root. I never open or read that file. |

## B. Recommended (locked unless you object)

### Hosting and runtime

| # | Topic | Decision | Why |
|---|---|---|---|
| B1 | Vercel layout | **One project using Vercel Services (beta).** `web/` (Next.js 16.3) is the public service. `engine/` (FastAPI) is private and reached through the binding `ENGINE_URL`. | One domain, no CORS setup, previews wired automatically, and the engine is never exposed publicly. |
| B2 | Region | `fra1` (Frankfurt) for both services. | Close to Belgium and to the EU inference region. |
| B3 | LightGBM on Vercel | Test it first with a spike: deploy the engine and run `import lightgbm` with one `pred_contrib` call. If it fails, fall back in this order: **(1)** bundle `libgomp.so.1` and preload it with `ctypes`; **(2)** run the engine on another host behind `ENGINE_URL`. | LightGBM's Linux wheels need the system library `libgomp`, and Vercel's Python runtime may not have it. It is not verified either way. |
| B4 | Runtime data (~75 MB of DB and models) | **Deploy from your machine with the Vercel CLI.** A `.vercelignore` includes `engine/data` and `engine/models`. The binaries stay out of git. | Git history stays small. Regenerating takes about 20 s and gives the same data every time (seed 42). |
| B5 | Python dependencies | Only runtime deps install on Vercel. `scikit-learn` sits in the `train` group and `pytest` in the `dev` group. The `anthropic` dependency is removed. | Keeps the bundle well under the 500 MB Python limit. |

### LLM (Gemini through AI Gateway)

| # | Topic | Decision | Why |
|---|---|---|---|
| B6 | Model | Set by env `GEMINI_MODEL`, default `google/gemini-3.8-flash`. A bare `gemini-3.8-flash` also works. The model id is never hardcoded anywhere else. | 3.8 Flash is a short-term-availability model. |
| B7 | EU processing | `providerOptions.gateway.inferenceRegion = { scope: 'zone', geoRegion: 'eu' }`. It fails closed: if the gateway can't serve the call in the EU, it returns an error and we use the template. | Inference stays in the EU. **Limitation:** the gateway's own request handling may happen in any Vercel region. The README will say so. |
| B8 | Call settings | 8 s timeout per call, `maxRetries: 0`, thinking level `low` (3.8 Flash rejects `minimal`). The whole turn is capped at about 10 s: if the first try is slow, skip the regeneration and use the template. | Keeps the app responsive. The template is always there as a fallback. |
| B9 | Auth | Locally: `AI_GATEWAY_API_KEY` from `.env.local`. On Vercel: **OIDC** (automatic), with no key stored in Vercel. | Keyless in production. |
| B10 | Price constant | $0.825 per 1M input tokens and $4.125 per 1M output (EU-pinned) until 31 Dec 2026, then $1.65 and $8.25. Kept in `web/lib/kate/pricing.ts` with the source URLs. The batch report prefers the cost the gateway reports per call (`providerMetadata.gateway.cost`). | Measured cost beats computed cost. |
| B11 | Delivery to the client | **Validate first, then send.** The model's output never streams to the client. The server compiles the spec, strips `/state` patches, validates each element's props, resolves references, applies gating, runs the grounding check, then sends. The UI shows a typing indicator. | A streamed sentence can't be taken back if the grounding check fails. Openers are stored anyway. |
| B12 | json-render | Pin exactly `0.21.0` (core and react). Use our own prompt template through `defineSchema`, without the default "sample data" rules. We validate each component ourselves, because `catalog.validate()` doesn't check props when there are several components. Reference props are enums of the ids allowed in that turn. | json-render is pre-1.0, and these gaps are documented in its repo. |
| B13 | Kill switch and rate limits | `CHAT_ENABLED` (default `true`; `false` means templates and the offline parser only). A per-IP in-memory limit: `RATE_LIMIT_PER_MIN` (default 20) LLM calls per minute per IP. You can add one Vercel WAF rule on top. | Neither existed in the old code. This is the simplest version that works. |
| B14 | Local env file | I create a **symlink** `web/.env.local → ../.env.local` so Next.js finds your key. Only the path is linked; I don't read the file. | Next.js only loads `.env*` files from its own folder. |

### Product behaviour

| # | Topic | Decision | Why |
|---|---|---|---|
| B15 | Channel | Openers appear only in the app when it is opened, never as a push. Deadlines show as "time-critical" in the under-the-hood panel. | Matches the spec. |
| B16 | Products for cash squeeze | A product appears only in the **short** stage, which is stricter than the spec's "from deciding". Every other moment starts at deciding. | Cash squeeze has no deciding stage, and credit should never be pushed early. |
| B17 | Forecast | A **cautious 6-month outlook** built only from observed months: recent level, last year's pattern, the usual dip within a month, how much income varies, and overdue invoices. It never uses the hidden outcome window. | The engine had no forecast, and using the hidden outcomes would leak the labels. |
| B18 | Set-aside plan | A new mock service action, **"Automatic buffer"**: money is set aside on payday and tops up the account whenever it would go below zero. It is a free account feature, not a product. The `WhatIfSlider` plan id is `buffer_monthly` (€10–300). | Needed for the 3-tap flow in the spec. It is allowed in the forecast stage. |
| B19 | Customer-facing name | "Cash squeeze" becomes **"A tight month"** (NL "Een krappe maand", FR "Un mois serré"). The jury panel keeps "Cash squeeze". | Calmer for lay users. |
| B20 | Languages | Everything a customer sees is in NL, FR and EN, with Belgian number formats (`€ 3.200` / `3 200 €`). The default language follows the region: Flanders nl, Wallonia fr, Brussels fr. The under-the-hood panel stays in English. | Matches the spec. I wrote the NL and FR copy myself, so a native speaker should review it. |
| B21 | Step by step vs. "Not now" | In step-by-step mode the two quick replies are [main action] and [Not now]. "Why?" and "I don't understand" become small links under the message. | Both rules in the spec hold: at most 2 quick replies, and always "Not now". |
| B22 | Large text + detailed | When text is Large or bigger and detail is Detailed, the detailed content is spread over several Kate messages, one component each. | The one-component rule from the spec still holds. |
| B23 | Brand | Neutral design. "Kate" appears as text only. No KBC logos, and no partner logo drop-in; partner names appear as text. | Matches the spec. |
| B24 | Comfort defaults | Normal text, simple, compact, read aloud off, language by region. The first run asks one question with three previews. Nothing is ever set from age or other personal attributes. | Matches the spec. |

### Data and engine

| # | Topic | Decision | Why |
|---|---|---|---|
| B25 | Housing | Every customer either owns, rents, or lives with their parents (`housing` column). Living with parents is only possible up to age 30, and the household then counts the parents (so it is at least 2). | Fixes the "household of 1 but lives with family" contradiction. |
| B26 | Employment | Early retirement is possible from age 60, and everyone is retired from 66. Self-employment is rarer under 27. | Removes 48-year-old retirees. |
| B27 | Income | Self-employed income grows with age (from about €1,500 at 22). Monthly volatility is capped (σ ≤ 0.40). A good month is at most 2.2× usual income, and extreme base incomes are clipped. | Fixes the €73k monthly spikes. 9 consistency tests on 10,000 profiles pass. |
| B28 | Guardian data | A separate `payment_habits` table, drawn from its own random stream, is expanded into a seeded 12-month payment history. It is never a model feature, never used by the orchestrator, and never used for offers. Tests enforce this. | Separates security from personalisation. |
| B29 | Showcase people | After the regeneration the six showcase customers are Romain (34, renovation), Élise (42, volatile income), Griet (69, deposit maturing), Thomas (26, driving licence), Joris (32, moving out) and Ruben (47, unpaid invoices). The Guardian scenarios will be added in M2. | The data changed, so different people now match the showcase queries. |

### Guardian (M2)

| # | Topic | Decision | Why |
|---|---|---|---|
| B30 | Decision logic | Deterministic, with weights and thresholds in `engine/app/guardian/config.py` and no LLM involved. Gemini may only rephrase the explanation, and the template explanation must be good enough on its own. | Explainable and fast (under 150 ms). |
| B31 | Customer control | "Continue anyway" is always possible after an explicit acknowledgement. The cool-down option schedules the payment for tomorrow. Everything is labelled as simulated. | The customer stays in control. |
| B32 | Evaluation | About 2,000 sampled users: mostly normal payments, some legitimately unusual ones (car purchase, rental deposit), and injected scams for each pattern. Targets: friction on normal payments below 2%, with the pause rate reported separately. | Matches the spec. The sample is sized to run in seconds. |

### Build and workflow

| # | Topic | Decision | Why |
|---|---|---|---|
| B33 | Frontend stack | Next.js 16.3, React 19.2, TypeScript, and plain CSS with custom properties in `rem` (no Tailwind). Charts are inline SVG with a text summary. | Makes the comfort-size scaling simple and keeps dependencies few. |
| B34 | Tests | pytest (engine), vitest (catalog, grounding, gating, templates), Playwright (360 px at extra-large text, and the three flows). | Covers the acceptance list in the spec. |
| B35 | Branching | This work goes on `kate-conversation`, stacked on `kate-prototype` (PR #1). A draft PR opens at the M1 check-in. | You can review in steps. |

## C. Needs your action or OK

| # | What | My recommendation |
|---|---|---|
| C1 | **AI Gateway credits.** The gateway's model data marks `gemini-3.8-flash` as not available on the free tier, so calls will likely fail with 403 until the account has paid credits (which also needs a payment method). | Add a small credit balance in the Vercel dashboard (AI Gateway → Credits). Until then, everything runs on templates. |
| C2 | **Running the batch with your key.** Measuring real tokens and cost for about 1,000 openers means calling Gemini with your key. | OK me to run `npm run openers -- --llm` myself. Node reads the key from the env file at runtime; I never print or view it. The alternative is that you run that one command. |
| C3 | **Optional WAF rule.** | Add one Vercel Firewall rate-limit rule on `/api/kate/*`, for example 60 requests per minute per IP. Not required for the demo. |
| C4 | **Native-speaker review** of the NL and FR copy (`engine/app/i18n/` now, `web/lib/i18n/` later). | Before the jury demo. |
