# tectonic-hackaton-KBC · Kate: explainable prediction assumptions

A working toy of a bank personalisation engine, built for a KBC hackathon. It runs as if inside **Kate**, the
assistant in KBC Mobile. This is a hackathon prototype, not an official KBC application. All data is synthetic
and every partner integration is simulated.

1. **Synthetic bank**: N customers (default 200,000, also works with 2.3M) with profiles, 12 months of
   behaviour, usage of third-party services in KBC Mobile, and realised outcomes.
2. **Interpretable models**: one LightGBM classifier per key moment in the next 12 months (moving house,
   buying a car, renovating, starting to invest, cash squeeze). They combine personal features, service-usage
   signals and aggregated data from similar customers (cohort rates and 500 nearest neighbours).
3. **Assumptions**: the most salient features become sentences the customer can confirm, reject or edit, with
   buttons or in the chat. Every correction rescores the customer live, in milliseconds.
4. **Kate action layer**: predictions become journeys (exploring → deciding → doing → after). Each stage has
   help items: free information first, then one-tap service actions (tickets, parking, a registered letter,
   invoice collection…), and only later a KBC product. An orchestrator keeps Kate to about one proactive
   message a month.

Time frame: today is 1 October 2026. Features come from Oct 2025 – Sep 2026; labels from Oct 2026 – Sep 2027.

## Setup

> **Phase 2 in progress** (Kate conversation with generative UI + Guardian). The Python engine now lives in
> `engine/` and is an API only; the new customer app is being built in `web/`. Locked decisions are in
> [docs/DECISIONS.md](docs/DECISIONS.md). This README is rewritten at the end of the phase.

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/) (or any Python with the dependencies from
`engine/pyproject.toml`, plus the `train` and `dev` groups).

```bash
cd engine && uv sync --all-groups
```

```bash
cd engine && uv run python -m app.generate --n 200000
```

```bash
cd engine && uv run python -m app.train
```

```bash
cd engine && uv run uvicorn app.server:app --port 8000
```

```bash
cd engine && uv run pytest
```

The engine serves `/engine/*` (state, ops, context packs, reference resolution, what-if, and the offline parser).
Every request carries the customer's session; the engine keeps none.

## Performance (MacBook, 10 cores)

| Step | 200k customers | 2.3M customers |
|---|---|---|
| `app.generate` | ~2 s | ~25 s |
| `app.train` (400k sample max, scores everyone) | ~20 s | ~45 s |
| Rescore one customer after a correction or action | 20–60 ms | 20–60 ms |

Test AUCs (200k, seed 42): move house 0.84 · buy car 0.74 · renovation 0.85 · start investing 0.83 · cash squeeze 0.84.

## How it works

```
app/
  common.py            paths, time frame, feature lists, cities, cohort banding
  generate.py          synthetic bank -> data/bank.duckdb (vectorised numpy)
  evidence.py          per-customer synthetic transactions (seeded by user_id, never stored)
  train.py             LightGBM per moment, cohort features, calibration, scores, neighbour pool
  assumptions.py       feature catalogue, assumption cards, overrides, declared events, live rescoring, session state
  journeys.py          readable stage rules + help items per stage (info → service → product → advisor)
  orchestrator.py      attention budget, suppression, bundling, channel; scale view
  services/registry.py the KBC Mobile services: signals, actions, parameters, cost/send flags
  services/mock.py     mock backend: validation, prices, confirmation cards, realistic results
  chat.py              Kate: Claude tool use + offline parser
  server.py            FastAPI
  static/index.html    one-page UI, vanilla JS, KBC styling, light and dark mode
```

**Generator.** Each customer has hidden state that is never stored: a life stage, four latent intents (move,
car, renovation, invest) and, for the self-employed, clients who pay late. These leak noisy signals into the
observation window:

- a lease ending soon, furniture spend, DIY and building-supplier spend, big car repairs, savings growth, visits
  to the Invest pages, a maturing term deposit
- **service usage in KBC Mobile**, linked to the moments as follows:

| Service signal | Linked to |
|---|---|
| Parking in another city via 4411 (house hunting) | moving ↑ |
| Registered e-mail to the landlord | moving ↑ |
| MyHome valuations | moving and renovation ↑ |
| Driving-licence preparation (young, no car) | buying a car ↑ |
| Movesmart lease car | buying a car ↓ |
| Cambio use | buying a car (mildly) |
| Overdue Billit invoices | cash squeeze ↑ (self-employed) |
| Financial news reads | starting to invest ↑ |
| SNCB tickets, commuter pass, fuel spend, service vouchers, Brussels Airport passes | context, mostly noise |

About 70% of intents are realised, plus rare spontaneous events. `cash_squeeze` means the simulated
current-account balance goes below zero in the outcome window. It is driven by income volatility, the fixed-cost
ratio, a low buffer, late-paying clients, the cost of other realised moments and random bills.

**Tables** in `data/bank.duckdb`:

| Table | Contents |
|---|---|
| `profiles` | one row per customer, incl. city |
| `features` | interpretable columns, incl. 15 service-usage features |
| `monthly` | LIST columns of 12 values: balance, income and 6 spend categories |
| `outcomes` | one boolean per moment |
| `scores` | written by training |

**Models.** Cohort features are the outcome rate per moment within age band × household-size band × region,
computed on the training split only. "People like you" is the realised outcome rate of the 500 nearest
neighbours. The neighbours come from 12 standardised float32 features, searched brute-force in numpy.

**Assumptions.** Card effects come from `predict(..., pred_contrib=True)`. A card's effect on a moment, in
percentage points, is `sigmoid(logit) − sigmoid(logit − contribution)`. The five cards with the largest total
absolute effect are shown. Service features name the service in their sentence and evidence, for example "You
started 7 parking sessions in Gent via 4411 in the last 3 months". Confirmed or edited cards stay visible, and
card order is stable within a session.

**Declared events** are applied after the model. The moment is shown as "told by you" at 95% (or at most 5% if
you say it's not planned), and the model's own estimate stays visible. A birth can only be declared, never
predicted.

### Services (simulated integrations)

Every service in `services/registry.py` has an id, name, category, description, the `signals` it contributes, and
`actions`. Each action has typed parameters with defaults from the customer's context (city, number plate,
overdue invoices…), a cost flag, a sends-something flag, a confirmation text and a mock result.

| Category | Services (id: actions) |
|---|---|
| Mobility | `4411`: start/stop parking · `qpark`: link plate · `sncb`: ticket, 10-journey card, commuter pass · `delijn`, `stib`: ticket · `shared_bike`: day bike (Mobit, Blue-bike, Velo Antwerpen) · `cambio`: book car, compare with owning · `q8`: link plate for fuel · `movesmart`: lease status · `driving_licence`: book lesson · `brussels_airport`: Fast Lane, lounge |
| Household & payments | `service_vouchers`: order · `split_expenses`: create group, request repayment · `wero`: request money |
| Home | `myhome`: estimate value, renovation checklist |
| Administration | `registered_email`: send from template (e.g. lease termination) |
| Self-employed | `billit`: list overdue, send reminders · `gosolid`: start collection · `expenses`: submit receipts |
| Info | `financial_news`: read articles |

**Kate prepares, the customer taps.** Kate (and the help items) only ever *prepare* an action. The result is a
confirmation card showing the summary, the price and whether it sends something. Nothing executes until the
customer taps the card's button. Results are realistic confirmation objects stored in the customer's session:

- a ticket with a QR placeholder
- a parking session with zone and end time
- a booking reference
- a registered e-mail with its delivery status
- an invoice list, a collection case, a cost comparison

Executed actions also feed back into the signals, e.g. a commuter pass sets `has_commuter_pass`.

Never used as signals, and listed under "Signals we don't use": Helena (medical data), charity donations,
digital safe contents, eBox document contents.

### Journeys and help items (`journeys.py`)

`STAGE_RULES` is a readable table: for each moment, the first row that matches sets the stage. A few examples:

| Moment | Stage | Rule |
|---|---|---|
| moving | doing | you told us the month, or you e-mailed your landlord and moving is likely (≥ 40%) |
| buying a car | exploring | ≥ 8% likely, or preparing a driving licence, or frequent Cambio use |
| renovation | doing | ≥ €1,500 at building suppliers since July |
| investing | doing | a term deposit matures within 2 months and investing is likely (≥ 40%) |
| cash squeeze | forecast / short | ≥ 25% forecast / already below zero 15+ days and ≥ 50% |

`HELP_ITEMS` maps every stage to help, in this order of preference: free information, a service action, a KBC
product (only from *deciding* on; for cash squeeze only when *short*), then an advisor. A check at import time
enforces the product rule. Examples:

- **Buying a car, exploring:** Cambio vs. owning comparison, which may recommend not buying. The car loan is held
  back until deciding.
- **Moving, deciding:** a registered e-mail to the landlord, or MyHome for owners.
- **Moving, doing:** address change, and an SNCB commuter pass for the new commute.
- **Cash squeeze, forecast:** automatic set-aside, Split expenses, Wero, and Billit reminders or Go Solid for the
  self-employed. Short-term credit only comes when *short*.

### Orchestrator (`orchestrator.py`)

All candidate help items go through one orchestrator:

- **Budget:** 1 proactive Kate conversation per month. Time-critical items (a predicted dip, a lease-notice or
  term-deposit deadline) may exceed it.
- **Channel:** in-app Kate card by default; push only for deadlines.
- **Suppression:** items built on an assumption the customer corrected disappear. "Not now" pauses a topic for 60
  days.
- **Bundling:** items for the same moment become one conversation.

The UI strip "What Kate would say this quarter" shows what passed next to what was held back, with the reason:
budget, suppressed, bundled, or not the right stage yet.

**Scale view.** Across 5,000 sampled customers, the orchestrator brings proactive messages from about **9.6** to
**3.9** per customer per year. This assumes each customer's stages stay constant for the year.

## API

| Method | Path | |
|---|---|---|
| GET | `/api/users/random` | full state of a random customer |
| GET | `/api/users/showcase` | 6 curated customers |
| GET | `/api/users/{id}` | profile, chart, predictions, cards, journeys, Kate plan, actions, signals not used |
| POST | `/api/users/{id}/override` | `{feature, value}` → state + before/after diff |
| POST | `/api/users/{id}/confirm` | `{feature}` → mark an assumption as confirmed |
| POST | `/api/users/{id}/declare` | `{event, month}` (month `YYYY-MM`, a month name, or `none`) |
| POST | `/api/users/{id}/reset` | drop all corrections, actions and pauses |
| GET | `/api/services` | service registry (with logo files if present) and services never used |
| POST | `/api/users/{id}/actions` | `{service, action, params}` → prepared confirmation card (nothing executes) |
| POST | `/api/users/{id}/actions/{aid}/confirm` | the customer's tap: executes the simulated action |
| POST | `/api/users/{id}/actions/{aid}/cancel` | cancel a prepared action |
| POST | `/api/users/{id}/ignore` | `{moment}` → "Not now": pause the topic for 60 days |
| GET | `/api/scale` | proactive messages per customer per year, with vs. without the orchestrator |
| POST | `/api/chat` | `{user_id, message, history}` → reply, tool actions, prepared cards, state, diff |
| GET | `/api/meta` | chat mode, AUCs |

Kate's Claude tools: `get_state`, `update_feature`, `confirm_assumption`, `declare_life_event`,
`list_services`, `prepare_service_action` (returns a card, never executes) and `get_journey`.

## Demo script (about 4 minutes)

The showcase buttons in the bar under the header pick customers by query, so the people and numbers depend on
`--n` and `--seed`. The figures below are for `--n 200000 --seed 42`.

**Part 1: explainable assumptions (2 min)**

1. **Renovation signal, button correction.** Anne (25) is predicted to renovate at **79%**; people like her sit
   at about 8%. The top card is *"You spent €3,642 at DIY and building suppliers since July"*, with the
   building-supplier payments and **+76 pts renovating**. Click **Edit**, enter `0`, press Enter.
   - Renovating drops to about **2%**.
   - In the Kate strip, the renovation loan and invoice tips become *Suppressed: built on an assumption you
     corrected*.
2. **Volatile income, chat correction.** Sébastien (27, self-employed) has a **49%** cash-squeeze risk; one card
   reads *"Your income varies by about 47% from month to month"*. In Kate's chat, type *"J'ai maintenant un CDI,
   mon revenu est stable"*. Kate replies in French: cash squeeze **49% → 33%**.
3. **Retired, declared event.** Margaux (78) has a term deposit maturing in November, so the Kate strip shows a
   **push notification** (a deadline) that bypasses the monthly budget. Type *"Je veux réinvestir mon dépôt à terme
   en novembre"*. Starting to invest becomes *Told by you, 95%*; the model's estimate stays visible.

**Part 2: Kate's action layer (2 min)**

4. **Young driver, no car yet.** Marie (19) is preparing her driving licence, so buying a car sits at **29%**,
   stage *Exploring*.
   - The Kate strip leads with the true cost of a car, bundled with **Cambio vs. owning**. *Car loan* is held back
     as *not the right stage yet*.
   - Tap **Prepare** → **Show comparison**: Cambio ≈ €218/month vs. ≈ €458 for owning, and owning only pays off
     from about 14,000 km a year.
   - Type *"Ik heb geen auto nodig"*: buying a car drops to **5%** and the car journey closes.
5. **Renter moving out.** Tom (35) rents in Aalst, e-mailed his landlord and parked in Gent 7 times via 4411
   (house hunting). Moving is at **63%**, stage *Doing*.
   - Open **Help now** on Moving house: address change and an **SNCB commuter pass Gent ↔ Aalst**. Tap
     **Prepare**, then **Confirm & pay**: a ticket with a QR placeholder appears under *Your activity*.
   - Type *"We verhuizen in december"*: moving goes to 95%, and Kate prepares the registered lease-termination
     e-mail. It's only sent when you tap **Send registered e-mail · €4.95**.
6. **Self-employed, unpaid invoices.** Arthur (29) has **6 overdue Billit invoices (€5,190)** and a **55%** cash
   squeeze forecast, flagged time-critical.
   - The Kate conversation bundles a set-aside tip, Billit reminders and **Go Solid** collection. *Short-term
     credit* is held back until he is actually short.
   - Prepare Go Solid: the card shows the fee (12% of what's recovered) and that it sends something. Only the tap
     starts the collection.

Close on the scale view: **9.6 → 3.9 proactive messages per customer per year**. Then the footer: signals we
don't use, *All data is synthetic*, simulated integrations.

**Reset** undoes all corrections and actions for the current customer.

## Limitations (it's a hackathon toy)

- Sessions (overrides, prepared and executed actions, pauses) live in server memory: they are lost on restart and
  shared by everyone using the same server.
- Evidence transactions, invoices, prices and service results are generated on the fly. They are plausible, not
  real, and no request ever leaves the server.
- The offline parser understands only a handful of phrasings; Claude handles the rest.
- The scale view assumes each customer's journey stages stay constant for a year.
- Stop the server before regenerating or retraining: DuckDB allows one writer per file.
