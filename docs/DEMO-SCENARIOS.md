# Kaat demo: screen-recording script

Six scenarios of about 6 minutes, plus a 30-second opening and closing. Every chat line, number and card below was
run against the engine (`/engine/state`, `/op`, `/parse`, `/context`, `/resolve`, `/whatif`) on 30 Sep 2026, using
`engine/data/bank.duckdb` (200,000 synthetic customers, models trained 2026-09-30 20:58). If the bank is regenerated
or the models are retrained, the showcase customers and numbers change, so verify everything again.

Reference codes (SNCB-…, BUF-…) depend on how many actions the customer's session already holds. The codes quoted
here come from a clean take in this order.

| # | Scenario | Customer (demo bar) | Lang · mode | Time |
|---|---|---|---|---|
| 1 | Proactive opener, one-tap action | Renter moving out · Joris | EN · Simple | ~50 s |
| 2 | Correct an assumption, Simple vs Detailed | Renovation signal · Romain | EN · Simple → Detailed | ~60 s |
| 3 | Kaat tab: generated components | Self-employed, unpaid invoices · Ruben | EN · Simple · Spec on | ~75 s |
| 4 | Plain words in Dutch and French | Joris, then Volatile income · Élise | NL, then FR · Simple | ~75 s |
| 5 | "I don't need a car" | Young driver, no car yet · Thomas | EN · Simple | ~55 s |
| 6 | Privacy and control | Thomas (continued) | EN · Simple | ~40 s |

## Before you record

1. Start `engine` (port 8001) and `web` (port 3000) from `.claude/launch.json`, then open http://localhost:3000.
2. Clear old sessions: DevTools → Application → Local Storage → `localhost:3000` → delete the `kate.session.v1.*` keys,
   then reload. Alternatively, select each customer you will use and press **Reset**.
3. On load, **Ruben is already selected**, in NL, Simple, with Spec off and **LLM on**.
4. Paste chat lines from this file so the apostrophes stay straight.
5. **About Kaat's wording:** with **LLM on**, Gemini writes each reply, so the sentences vary a little between takes.
   The numbers stay the same: they come from the engine and are checked before anything is shown. The quotes below are
   from the deterministic path. For word-for-word identical takes, switch **LLM off** in the demo bar.
6. A reply with LLM on takes about 2–4 s for a question and about 5 s for a correction. Kaat shows typing dots
   meanwhile.

## Opening (30 s)

Screen: Joris's Home in NL, as it loads.

**Say:** "This is Kaat, a proactive assistant for a bank's mobile app. Everything here is synthetic: 200,000 made-up
customers, and partner services that are simulated. Kaat predicts five moments: moving, buying a car, renovating,
starting to invest, and a tight month. It raises one topic at a time, shows why, lets you correct it, and does nothing
until you tap."

## 1 · The proactive opener and a one-tap action (~50 s)

**Joris · EN · Simple · Spec off**

1. **Do:** click **Renter moving out · Joris**, then **EN**.
   **See:** "Good evening, Joris". The navy card shows "Kaat · Moving house · Doing" and *"Moving soon? Here's how to
   register at your new address (within 8 working days) and update it in KBC Mobile."* with **Show me** / **Why?** /
   **Not now**. Under *Your moments*: Moving house shows "For you: about 7 in 10" and "about 1 in 10 people like you";
   Starting to invest shows "For you: about 8 in 10" and "about 9 in 100 people like you".
   **Say:** "Kaat picked one topic for Joris this month. It puts his chance of moving at about 7 in 10. For people
   like him, it's about 1 in 10."
2. **Do:** tap **Why?** (this opens My picture), then tap **Home** again.
   **See:** *"You sent 1 registered e-mail(s) to your landlord in the last 3 months"* (with That's right / Not true) and
   *"You started 7 parking sessions in Leuven via 4411 in the last 3 months"* (from our records, so no buttons).
   **Say:** "Why? shows the evidence: a registered e-mail to his landlord, and seven parking sessions in Leuven."
3. **Do:** tap **Show me**.
   **See:** *"Commuter pass for your new commute: From Leuven your commute changes. Shall I prepare an SNCB commuter
   pass Leuven ↔ Antwerp?"* with a **Prepare** button.
4. **Do:** tap **Prepare**.
   **See:** a card reading "SNCB / NMBS · simulated", "Buy a commuter pass", *"Commuter pass Leuven ↔ Antwerp for 1
   month(s)."* and "€198", with **Confirm & pay · €198** / **Cancel**.
   **Say:** "Kaat prepares the pass. Nothing is bought yet."
5. **Do:** tap **Confirm & pay · €198**.
   **See:** "Commuter pass Leuven ↔ Antwerp · 1 month(s)", "Reference: SNCB-ZQVYWF" and a QR placeholder. The toast
   reads "A tight month: less likely now".
   **Say:** "One tap, and the pass is there with its QR code. Payment and ticket are simulated."

## 2 · Correct an assumption: Simple vs Detailed (~60 s)

**Renovation signal · Romain · EN (kept from scenario 1) · Simple, then Detailed**

1. **Do:** click **Renovation signal · Romain**.
   **See:** the hero shows "Kaat · Renovating · Doing" and *"Works under way? Keep every invoice: you'll need them for
   the Primes Habitation."* Your moments shows Renovating ("For you: about 8 in 10", "about 7 in 100 people like
   you") and Starting to invest ("about 5 in 10", "about 9 in 100 people like you").
   **Say:** "Romain looks like he's renovating: about 8 in 10, while people like him are at 7 in 100."
2. **Do:** tap **Why?**
   **See:** the top card reads *"You spent €4,709 at DIY and building suppliers since July"*, with the evidence line
   "8 payments at DIY and building suppliers since July; €4,709 over the last 12 months".
3. **Do:** tap **Change**, select all, type `0`, then tap **Save**.
   **See:** the toast *"Starting to invest: more likely now · Renovating: less likely now · Moving house: more likely
   now"*. The card now reads "Changed by you (was €4,709)" and *"You spent nothing at DIY or building suppliers since
   July"*.
   **Say:** "Those purchases were for his parents. After one correction the model rescores him on the spot. Simple
   mode puts the change into words."
4. **Do:** tap **Home**.
   **See:** Renovating is gone. The hero now shows "Kaat · Starting to invest · Deciding" and *"Before you invest,
   here's what to expect from different risk levels."*
   **Say:** "Kaat drops the renovation topic and moves on."
5. **Do:** click **Detailed**, then **Reset**.
   **See:** the toast *"Renovating: 2% → 82% · Starting to invest: 53% → 49% · Moving house: 2% → 1%"*. Home now
   shows Renovating at 82%, with a bar, "Mark: people like you · 7%", and "Why this stage: works under way (≥ €1,500
   at building suppliers since July) or you told us the month".
   **Say:** "Detailed mode is for people who want the numbers. Same customer, back to the start."
6. **Do:** tap **My picture**. On the DIY card, tap **Change**, type `0`, then tap **Save**.
   **See:** before saving, the card shows the chips "+79 pts · Renovating" and "+3 pts · Starting to invest", and the
   payments Facq −€1,968, Hubo −€1,239 and Tollens −€573. After saving, the toast reads *"Starting to invest: 49% →
   53% · Renovating: 82% → 2% · Moving house: 1% → 2%"*.
   **Say:** "It's the same correction, now with numbers: renovating drops from 82 to 2 percent."

*Chat alternative (verified):* in the Kaat tab, type `The Hubo and Facq payments were for my parents house`. Kaat
replies *"Updated: “You spent nothing at DIY or building suppliers since July”. Renovating went from 82% to 2%.
Starting to invest went from 49% to 53%. Moving house went from 1% to 2%."*

## 3 · Kaat tab: generated components (~75 s)

**Ruben · EN · Simple · Spec on**

1. **Do:** click **Simple**, then **Self-employed, unpaid invoices · Ruben**.
   **See:** the hero shows "Kaat · A tight month · Forecast".
2. **Do:** tap the **Kaat** orb.
   **See:** *"Money may get tight in the coming months. Want to set aside a small buffer on payday? It tops
   up your account automatically if it would go below zero."* Below it is a sparkline titled "Your balance, the
   coming months" with Dec marked in red, and *"Your tightest month looks like December 2026: your balance could dip to
   about −€1,610."* Then the quick replies **Yes, show me** / **Why?** / **Not now**, and the starter chips
   "I want to start investing in January" and "Train ticket to Brussels tomorrow".
   **Say:** "The Kaat tab opens with a message built for Ruben. His balance could dip to minus 1,610 euros in
   December."
3. **Do:** click **{ } Spec** and expand the line under the message.
   **See:** "json-render spec · 7 · 0 dropped · … ms", and JSON containing `"ref": "forecast"` but no amounts.
   **Say:** "Each message is a json-render spec that holds only references. The engine fills in the numbers, and any
   reference that doesn't resolve is dropped."
4. **Do:** tap **Why?**
   **See:** a second message, *"Here's what I based this on. Correct anything that's wrong."*, followed by:
   - people icons for "A tight month": You "about 4 in 10", People like you "about 2 in 10";
   - the sparkline again;
   - "Why Kaat thinks this · A tight month", with reason bars: "Your lowest balance this year was −€127" and "4 of your
     invoices in Billit are overdue" (both "makes it more likely"), then "You have about €8,914 in savings" and "Your
     net income is about €3,295 a month" (both "makes it less likely");
   - three assumption cards: the first two are from our records and have no buttons, and the savings card has That's
     right / Change;
   - the slider "A buffer, set aside each month", starting at €300 (its maximum), and the spec line "11 · 0 dropped".

   **Say:** "Why? adds the detail: how he compares with people like him, the reasons and their weight, and the
   assumptions he can correct."
5. **Do:** drag the slider to **€200** and let go.
   **See:** a second line appears on the chart, and the text reads *"Your tightest month looks like December 2026: your
   balance could dip to about −€1,610. With €200 a month set aside, the buffer covers part of it."*
   **Say:** "The slider asks the engine live. At 200 euros a month, the buffer covers part of the dip."
6. **Do:** tap **Set aside €200 each month**.
   **See:** a card reading "Automatic buffer · simulated", "Start an automatic buffer", *"Set aside €200 on payday,
   every month. If your current account would go below zero, the buffer tops it up. You can stop it at any time."*
   and "free", with **Set aside €200 each month** / **Cancel**.
7. **Do:** tap **Set aside €200 each month**.
   **See:** "Buffer started: €200 a month", "First set-aside on payday, 25 Oct 2026" and "Reference: BUF-NVT9MQ".
   The toast reads "Thanks, noted."
   **Say:** "Confirmed with a tap. It's a free account feature, not a product."

## 4 · Plain words in Dutch and French (~75 s)

**Part A: Joris · NL · Simple · Spec off.** This works whether or not scenario 1 was recorded first: moving is at
71% in both cases.

1. **Do:** click **{ } Spec** (to turn it off), then **NL**, then **Renter moving out · Joris**, then tap **Kaat**.
   **See:** *"Verhuis je binnenkort? Zo schrijf je je in op je nieuwe adres (binnen 8 werkdagen) en pas je het aan in
   KBC Mobile."* with the people icons "Jij: ongeveer 7 op de 10" and "Mensen zoals jij: ongeveer 1 op de 10".
2. **Do:** type `We verhuizen in december naar Leuven`
   **See:** *"Genoteerd: Verhuizen in december 2026. Verhuizen ging van 71% naar 95%. Omdat je huurt, heb ik ook de
   aangetekende e-mail aan je verhuurder klaargezet. Ik heb dit voor je klaargezet: Stuur de aangetekende e-mail 'Opzeg
   van het huurcontract' naar je verhuurder (verhuis op 1 dec 2026). Er gebeurt niets tot je op “Aangetekende e-mail
   versturen · € 4,95” tikt."* A card follows, with "Hiermee wordt iets verstuurd in jouw naam." The toast reads
   "Verhuizen: nu waarschijnlijker".
   **Say:** "Joris gives Kaat the month in his own words. Moving goes to 95 percent, and because he rents, Kaat
   prepares the registered e-mail to his landlord."
3. **Do:** tap **Aangetekende e-mail versturen · € 4,95**.
   **See:** "Aangetekende e-mail verstuurd: Opzeg van het huurcontract", "Afgeleverd · wacht op leesbevestiging" and
   "Referentie: RE-AUGS5R". The toast reads "Bedankt, genoteerd."
4. **Do:** type `Parkeren in Leuven voor 2 uur`
   **See:** *"Ik heb dit voor je klaargezet: Parkeer in Leuven gedurende 120 min met 2-PNC-281. Je betaalt per minuut.
   Er gebeurt niets tot je op “Start parkeren · € 4,80” tikt."* The card shows "≈ € 4,80 (€ 2,40/u)". Confirming is
   optional; it shows "Parkeren in Leuven tot …".
   **Say:** "Parking works the same way. Kaat knows his number plate, and he taps to start."

**Part B: Élise · FR · Simple**

5. **Do:** click **FR**, then **Volatile income · Élise**, then tap **Kaat**. Go straight to typing (see *Avoid on
   camera*).
6. **Do:** type `Depuis septembre j'ai un CDI, mes revenus sont stables`
   **See:** *"Mis à jour : « Vos revenus varient d'environ 5 % d'un mois à l'autre ». Un mois serré passe de 35 % à
   20 %. Acheter une voiture passe de 4 % à 3 %."* The toast reads "Un mois serré: moins probable maintenant · Acheter
   une voiture: moins probable maintenant".
   **Say:** "Élise corrects Kaat in French: she now has a permanent contract. Her risk of a tight month drops from 35
   to 20 percent."
7. **Do:** type `Nous voulons rénover la cuisine en mai`
   **See:** *"C'est noté : Rénover en mai 2027. Rénover passe de 4 % à 95 %."* The toast reads "Rénover: plus probable
   maintenant".
   **Say:** "A plan with a month becomes something Kaat can work with."

## 5 · "I don't need a car" (~55 s)

**Young driver, no car yet · Thomas · EN · Simple**

1. **Do:** click **EN**, then **Young driver, no car yet · Thomas**, then tap **Kaat**.
   **See:** *"A small car often costs €350–€500 a month once you count depreciation, insurance, tax, fuel and
   parking."* with people icons for "Buying a car": You "about 3 in 10", People like you "about 6 in 100".
   **Say:** "Thomas is preparing for his driving licence, so Kaat thinks he may buy a car. It starts with the true
   cost, not with a car loan."
2. **Do:** type `We no longer need a car, I bike to work`
   **See:** *"Noted: Buying a car is not planned. Buying a car went from 29% to 5%. Curious what car sharing would cost
   you instead? I've prepared this for you: Compare the monthly cost of Cambio and of owning a car at 6,000 km a year.
   Nothing happens until you tap “Show comparison”."* The toast reads "Buying a car: less likely now".
3. **Do:** tap **Show comparison**.
   **See:** "Cheaper for you: Cambio", then *"At 6,000 km a year, Cambio costs about €218 a month versus €458 for owning
   a small car. Owning only pays off from roughly 14,000 km a year."* and "Reference: CMB-GLQ959".
   **Say:** "Kaat will tell him not to buy a car when that's the cheaper option."
4. **Do:** type `Train ticket from Leuven to Brussels tomorrow`
   **See:** *"I've prepared this for you: Train ticket Leuven → Brussels on 2 Oct 2026, 2nd class. Nothing happens until
   you tap “Confirm & pay · €10.25”."*
5. **Do:** tap **Confirm & pay · €10.25**.
   **See:** "Leuven → Brussels · 2nd class", "Reference: SNCB-MLKAC3" and a QR placeholder. A small side-effect toast
   reads "Starting to invest: more likely now" (6% → 7%).
   **Say:** "And here's tomorrow's train ticket, with its QR code."

## 6 · Privacy and control (~40 s)

**Thomas (continued) · EN · Simple**

1. **Do:** type `I want a train commuter pass from Leuven to Brussels`, then tap **Cancel** on the card.
   **See:** *"I've prepared this for you: Commuter pass Leuven ↔ Brussels for 1 month(s). Nothing happens until you tap
   “Confirm & pay · €133”."* After Cancel: "Cancelled. Nothing was sent or paid."
   **Say:** "Kaat only ever prepares. Without a tap, nothing is bought or sent."
2. *(Optional)* **Do:** type `We are expecting a baby in April`
   **See:** *"Noted: A new baby in April 2027. No probabilities changed noticeably."*
   **Say:** "Kaat never guesses a pregnancy from payments. Only the customer can tell it."
3. **Do:** tap **My picture** and scroll to **Signals we don't use**.
   **See:** a list that includes "Health: payments to hospitals, doctors, pharmacies or health insurers", "Pregnancy or
   births (a birth can only be declared by you)", religion, trade-union fees, ethnicity, political opinions, sexual
   orientation, gender, "Your age, for how Kaat talks to you", "Security checks on your payments (Guardian): used only
   to protect you, never for offers", and the contents of Helena, charity donations, Digital safe and eBox. Higher up,
   the card *"Customers like you (aged 25–34, household of 1 person, Flanders) often go through these moments"* is
   marked "From our records" and has no buttons.
   **Say:** "This is what Kaat is not allowed to use. Facts from our own records have no buttons. Anything Kaat
   inferred, you can confirm or correct."
4. **Do:** tap **Home**, then **Not now** on the card *"Curious about investing? Here's a 3-minute explainer on risk,
   return and spreading."*
   **See:** "You're all set. Kaat stays quiet until something changes."
   **Say:** "Not now means quiet. The topic is paused for 60 days."

## Closing (30 s)

Screen: Thomas's quiet Home.

**Say:** "So Kaat raises one topic at a time. Across a sample of 5,000 synthetic customers, that cuts proactive messages
from about 9 to under 4 a year. Every prediction comes with its reasons, and people can correct them with a tap or in
their own words, in Dutch, French or English. Kaat prepares, and the customer decides. Everything you saw runs on
synthetic data with simulated partners. The chat is a small offline rule-based parser, with no language model
involved."

The 9.3 → 3.7 figure comes from `/engine/scale` (5,000-customer sample, assuming journey stages stay constant for a
year).

## Reset checklist between takes

- [ ] **Reset** acts only on the selected customer. It clears corrections, declared plans, prepared and confirmed
      actions, and "Not now" pauses, and it shows a toast.
- [ ] Reset also clears the chat: the Kaat tab starts again with a fresh opener. Switching **Simple/Detailed** or
      the language restarts the Kaat tab too.
- [ ] A language button stays selected for every customer until you click another one.
- [ ] Put the demo bar back as each scenario needs it: **Spec** on only for scenario 3, and **Detailed** only in
      scenario 2.
- [ ] For a full clean start, clear the `kate.session.v1.*` keys in local storage and reload.

## Avoid on camera

- **Curly apostrophes** (don’t) break the "don't need a car" rule when LLM is off. The scripted line has no apostrophe.
- The **"Registered e-mail"** service name stays in English in every language (it's the service's name).
- With LLM on, the first reply after a cold start can take a few seconds longer. Do one warm-up message before
  recording.

## Known limits (say so if asked)

- **The chat is not an LLM.** Free text goes to the offline rule-based parser (`/engine/parse`). It understands:
  - corrections: income, savings, stable income or permanent contract (CDI), DIY purchases, car age or purchase,
    renting or owning, children, household size;
  - plans with a month: moving, buying a car, renovating, investing, a baby;
  - "no longer need a car";
  - starting and stopping parking;
  - train tickets and commuter passes, but only when the message says *train* or *trein*;
  - "that's right".

  Anything else gets its help text: "I'm in offline mode and understand simple corrections…". Dutch "ik verhuis…"
  isn't recognised; "we verhuizen…" and "ik ga verhuizen…" are.
- **Kaat replies in the language of each message,** whatever the UI language is set to.
- **Kaat tab messages come from deterministic templates,** rendered with json-render. No LLM writes them.
- **Everything is synthetic or simulated.** There are 200,000 generated customers, and the LightGBM models reach an
  AUC of 0.74–0.84 on synthetic labels. All partner integrations are simulated, including prices, number plates,
  references and QR codes. Nothing leaves the machine.
- **The engine keeps no state.** The session lives in the browser's local storage, one per customer.

## Spare verified lines (for swaps or retakes)

| Customer | Line | Engine result |
|---|---|---|
| Joris (NL) | `We gaan toch niet verhuizen` | "Verhuizen ging van 71% naar 5%." |
| Joris (NL) | `Een abonnement voor de trein van Leuven naar Antwerpen` | Card: "Abonnement Leuven ↔ Antwerpen voor 1 maand(en)." · € 198 |
| Joris (NL UI) | `Je dois me garer à Leuven pendant 2 heures` | French reply and card: "Stationner à Louvain pendant 120 min avec 2-PNC-281…" (the reply language follows the message) |
| Thomas (EN) | `I'm moving to Gent in March` | "Moving house went from 8% to 95%." + registered e-mail card (move-out 1 Mar 2027) |
| Thomas (NL) | `Ik heb geen auto nodig, ik fiets naar mijn werk` | "Een auto kopen ging van 29% naar 5%." + Cambio card (6.000 km) |
| Thomas (NL) | `Ik ga verhuizen in maart` | "Verhuizen ging van 8% naar 95%." + registered e-mail card |
| Thomas (EN) | `Park in Leuven for 90 minutes`, then confirm, then `Stop my parking session` | Card "…90 min with 1-RBE-916 · €3.60", then "Stop parking session P-…" |
| Griet (NL) | `Ik wil volgende maand beginnen met beleggen` | "Beginnen met beleggen in november 2026 … van 60% naar 95%." |
| Griet (NL) | `Ik wil niet beleggen, ik hou het op mijn spaarrekening` | "…ging van 60% naar 5%." |
| Griet (FR) | `Je veux réinvestir mon dépôt à terme en novembre` | "Commencer à investir passe de 60 % à 95 %." |
| Ruben (NL) | `Mijn spaargeld is 30.000 euro` | "Een krappe maand ging van 41% naar 31%. Beginnen met beleggen ging van 16% naar 28%…" |
| Ruben (EN) | `We are planning to renovate the bathroom in June` | "Renovating in June 2027. Renovating went from 1% to 95%." |
| Romain (FR) | `Les achats chez Brico étaient pour mes parents` | "Rénover passe de 82 % à 2 %…" |
| Romain (FR) | `Je veux commencer à investir en janvier` | "Commencer à investir passe de 49 % à 95 %." |
| Romain (NL) | `De aankopen bij Gamma waren eenmalig` | "Verbouwen ging van 82% naar 2%…" |
| Élise (FR) | `Je dois me garer à Ixelles pendant 2 heures` | Card "Stationner à Ixelles pendant 120 min avec 2-KRK-473… 4,80 €" |
| Élise (FR) | `Un billet de train pour Gand demain` | Card "Billet de train Anderlecht → Gand le 2 oct. 2026, 2e classe" · 7,10 € |
| Élise (FR) | `En fait nous louons notre appartement` | "Un mois serré passe de 35 % à 30 %… Déménager passe de 3 % à 18 %." |
