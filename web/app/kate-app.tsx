"use client";

import type { Spec } from "@json-render/core";
import { useCallback, useEffect, useRef, useState } from "react";

import { type Bridge, KaatSpecView } from "./kaat-spec";

type Lang = "nl" | "fr" | "en";
type Detail = "simple" | "detailed";
type Tab = "home" | "picture" | "kate";

type HelpAction = { service: string; action: string; params: Record<string, unknown> };
type HelpItem = { id: string; kind: string; title: string; say: string; action: HelpAction | null };
type Conv = { moment: string; stage: string; lead: HelpItem; items: HelpItem[] };
type Journey = { moment: string; label_local: string; stage: string | null; stage_label: string; rule: string };
type Pred = {
  moment: string; label_local: string; probability: number; neighbour_rate: number | null;
  declared: boolean; declared_label: string | null;
};
type Txn = { date: string; merchant: string; amount: number };
type Card = {
  feature: string; sentence: string; evidence: { text: string; transactions: Txn[] }; value: unknown;
  value_display: string; type: string; editable: boolean; options: string[] | null; source: string;
  status: string; original_display: string | null; effects: { moment: string; label: string; pts: number }[];
  source_key: string;
};
type ActionCard = {
  id: string; service_name: string; action_name: string; summary: string; price_text: string; sends: boolean;
  button: string; status: string; result: Record<string, string | number | boolean | null | undefined>;
};
type State = {
  user_id: number; lang: string;
  profile: { first_name: string; region: string; city: string; employment_type: string; renting: boolean };
  forecast: { months_long: string[] };
  predictions: Pred[]; journeys: Journey[]; kate: { passed: Conv[] }; cards: Card[]; actions: ActionCard[];
  signals_not_used: string[];
};
type Showcase = { key: string; label: string; user_id: number; first_name: string; region: string };
type Trace = {
  components?: number; dropped?: unknown[]; ms: number; author?: string; reason?: string;
  calls?: { step: string; model: string; ms: number; inputTokens: number; outputTokens: number; costUsd: number }[];
  grounding?: { ok: boolean; checked: number; unknown: string[] } | null;
};
type Msg = { role: "k" | "u"; text?: string; actions?: string[]; spec?: Spec; trace?: Trace };

// ---------------------------------------------------------------------------------------------
// Fixed UI text (no numbers: every amount and percentage comes from engine state)
// ---------------------------------------------------------------------------------------------
const T = {
  en: {
    greeting: "Good evening, {name}", home: "Home", picture: "My picture", kate: "Kaat",
    prepare: "Prepare", showMe: "Show me", hide: "Hide", why: "Why?", notNow: "Not now",
    allSet: "You're all set. Kaat stays quiet until something changes.", moments: "Your moments",
    cancel: "Cancel", sends: "This sends something on your behalf.", simulated: "simulated",
    cancelled: "Cancelled. Nothing was sent or paid.", reference: "Reference",
    right: "That's right", notTrue: "Not true", change: "Change", save: "Save", records: "From our records",
    confirmed: "Confirmed", changed: "Changed by you (was {orig})", notUsed: "Signals we don't use",
    less: "less likely now", more: "more likely now", noted: "Thanks, noted.",
    ask: "Ask Kaat…", send: "Send", hello: "Hi {name}, what can I help you with?",
    pictureIntro: "What Kaat thinks about you. Correct anything that's wrong.", whyStage: "Why this stage: ",
    down: "The engine is not reachable. Start it and try again.", loading: "Loading…",
    customers: "Customers", random: "Random", reset: "Reset", simple: "Simple", detailed: "Detailed", pts: "pts",
    tick: "Mark: people like you", forYou: "For you: {freq}", spec: "Spec",
    paused: "Okay, I won't bring this up for a while.", typing: "Kaat is typing…", adviser: "An adviser will call you back (simulated).",
  },
  nl: {
    greeting: "Goedenavond, {name}", home: "Start", picture: "Mijn beeld", kate: "Kaat",
    prepare: "Klaarzetten", showMe: "Toon me", hide: "Verbergen", why: "Waarom?", notNow: "Niet nu",
    allSet: "Alles in orde. Kaat blijft stil tot er iets verandert.", moments: "Jouw momenten",
    cancel: "Annuleren", sends: "Hiermee wordt iets verstuurd in jouw naam.", simulated: "gesimuleerd",
    cancelled: "Geannuleerd. Er werd niets verstuurd of betaald.", reference: "Referentie",
    right: "Klopt", notTrue: "Klopt niet", change: "Wijzigen", save: "Bewaren", records: "Uit onze gegevens",
    confirmed: "Bevestigd", changed: "Door jou gewijzigd (was {orig})", notUsed: "Signalen die we niet gebruiken",
    less: "nu minder waarschijnlijk", more: "nu waarschijnlijker", noted: "Bedankt, genoteerd.",
    ask: "Vraag het Kaat…", send: "Versturen", hello: "Dag {name}, waarmee kan ik je helpen?",
    pictureIntro: "Wat Kaat over jou denkt. Pas aan wat niet klopt.", whyStage: "Waarom deze fase: ",
    down: "De engine is niet bereikbaar. Start hem en probeer opnieuw.", loading: "Laden…",
    customers: "Klanten", random: "Willekeurig", reset: "Reset", simple: "Eenvoudig", detailed: "Gedetailleerd", pts: "ptn",
    tick: "Streepje: mensen zoals jij", forYou: "Voor jou: {freq}", spec: "Spec",
    paused: "Oké, ik kom hier een tijd niet op terug.", typing: "Kaat is aan het typen…", adviser: "Een adviseur belt je terug (gesimuleerd).",
  },
  fr: {
    greeting: "Bonsoir, {name}", home: "Accueil", picture: "Mon profil", kate: "Kaat",
    prepare: "Préparer", showMe: "Voir", hide: "Masquer", why: "Pourquoi ?", notNow: "Pas maintenant",
    allSet: "Tout est en ordre. Kaat reste discrète jusqu'à ce que quelque chose change.", moments: "Vos moments",
    cancel: "Annuler", sends: "Ceci envoie quelque chose en votre nom.", simulated: "simulé",
    cancelled: "Annulé. Rien n'a été envoyé ni payé.", reference: "Référence",
    right: "C'est exact", notTrue: "Pas vrai", change: "Modifier", save: "Enregistrer", records: "D'après nos données",
    confirmed: "Confirmé", changed: "Modifié par vous (avant : {orig})", notUsed: "Signaux que nous n'utilisons pas",
    less: "moins probable maintenant", more: "plus probable maintenant", noted: "Merci, c'est noté.",
    ask: "Demandez à Kaat…", send: "Envoyer", hello: "Bonjour {name}, comment puis-je vous aider ?",
    pictureIntro: "Ce que Kaat pense de vous. Corrigez ce qui ne va pas.", whyStage: "Pourquoi cette étape : ",
    down: "Le moteur n'est pas joignable. Démarrez-le et réessayez.", loading: "Chargement…",
    customers: "Clients", random: "Au hasard", reset: "Réinitialiser", simple: "Simple", detailed: "Détaillé", pts: "pts",
    tick: "Repère : personnes comme vous", forYou: "Pour vous : {freq}", spec: "Spec",
    paused: "D'accord, je n'en reparlerai pas avant un moment.", typing: "Kaat écrit…", adviser: "Un conseiller vous rappellera (simulé).",
  },
} as const;

const LOCALE: Record<Lang, string> = { nl: "nl-BE", fr: "fr-BE", en: "en-GB" };

/**
 * Conversation starters that fit this customer and that the offline parser understands. Month names come from the
 * engine's outlook; nothing here is a number.
 */
const STARTERS = {
  en: { move: "We're moving in {month}", invest: "I want to start investing in {month}", stable: "My income is stable now",
        diy: "The DIY purchases were for my parents", noCar: "I don't need a car", train: "Train ticket to {city} tomorrow",
        pass: "Commuter pass to {city}" },
  nl: { move: "We verhuizen in {month}", invest: "Ik wil beginnen met beleggen in {month}", stable: "Mijn inkomen is nu stabiel",
        diy: "De doe-het-zelfaankopen waren voor mijn ouders", noCar: "Ik heb geen auto nodig", train: "Treinticket naar {city} morgen",
        pass: "Abonnement naar {city}" },
  fr: { move: "Nous déménageons en {month}", invest: "Je veux commencer à investir en {month}", stable: "Mon revenu est stable maintenant",
        diy: "Les achats de bricolage étaient pour mes parents", noCar: "Je n'ai plus besoin de voiture",
        train: "Un billet de train pour {city} demain", pass: "Un abonnement pour {city}" },
} as const;
const TRAIN_CITY: Record<Lang, [string, string]> = { en: ["Brussels", "Antwerp"], nl: ["Brussel", "Antwerpen"], fr: ["Bruxelles", "Anvers"] };

function startersFor(st: State, lang: Lang): string[] {
  const s = STARTERS[lang];
  const staged = new Set(st.journeys.filter((j) => j.stage).map((j) => j.moment));
  const month = (st.forecast?.months_long?.[3] ?? "").split(" ")[0];
  const out: string[] = [];
  const topic = st.kate.passed[0]?.moment;
  const order = [topic, ...st.journeys.map((j) => j.moment)].filter((m, i, a) => m && a.indexOf(m) === i) as string[];
  for (const m of order) {
    if (!staged.has(m)) continue;
    if (m === "move_house" && month) out.push(fill(s.move, { month }));
    if (m === "start_investing" && month) out.push(fill(s.invest, { month }));
    if (m === "cash_squeeze" && st.profile.employment_type === "self_employed") out.push(s.stable);
    if (m === "renovation") out.push(s.diy);
    if (m === "buy_car") out.push(s.noCar);
  }
  const [capital, other] = TRAIN_CITY[lang];
  out.push(fill(s.train, { city: st.profile.city === "Brussels" ? other : capital }));
  return out.filter((x, i) => out.indexOf(x) === i).slice(0, 3);
}

function fill(s: string, vars: Record<string, string>) {
  return s.replace(/\{(\w+)\}/g, (_, k) => vars[k] ?? "");
}

/** Natural frequency parts for a probability from the engine: 10 → "in 10", small → "in 100". */
function freqParts(p: number): { k: number; n: number } | "all" | "few" {
  if (p >= 0.095) {
    const k = Math.min(10, Math.max(1, Math.round(p * 10)));
    return k === 10 ? "all" : { k, n: 10 };
  }
  const k = Math.round(p * 100);
  return k < 1 ? "few" : { k, n: 100 };
}

function freq(p: number, lang: Lang): string {
  const f = freqParts(p);
  if (f === "all") return { en: "almost everyone", nl: "bijna iedereen", fr: "presque tout le monde" }[lang];
  if (f === "few") return { en: "fewer than 1 in 100", nl: "minder dan 1 op de 100", fr: "moins de 1 sur 100" }[lang];
  return { en: `about ${f.k} in ${f.n}`, nl: `ongeveer ${f.k} op de ${f.n}`, fr: `environ ${f.k} sur ${f.n}` }[lang];
}

function peopleLikeYou(p: number, lang: Lang): string {
  const f = freqParts(p);
  if (f === "all") return { en: "almost everyone like you", nl: "bijna iedereen zoals jij", fr: "presque tout le monde comme vous" }[lang];
  if (f === "few")
    return { en: "fewer than 1 in 100 people like you", nl: "minder dan 1 op de 100 mensen zoals jij", fr: "moins d'1 personne sur 100 comme vous" }[lang];
  return {
    en: `about ${f.k} in ${f.n} people like you`,
    nl: `ongeveer ${f.k} op de ${f.n} mensen zoals jij`,
    fr: `environ ${f.k} personnes sur ${f.n} comme vous`,
  }[lang];
}

const pct = (p: number, lang: Lang) => new Intl.NumberFormat(LOCALE[lang], { style: "percent", maximumFractionDigits: 0 }).format(p);
const money = (v: number, lang: Lang) =>
  new Intl.NumberFormat(LOCALE[lang], { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(v);

// ---------------------------------------------------------------------------------------------
// Session storage (client-held; the engine keeps nothing)
// ---------------------------------------------------------------------------------------------
const sessionKey = (uid: number) => `kate.session.v1.${uid}`;
function readSession(uid: number): unknown {
  try {
    const raw = window.localStorage.getItem(sessionKey(uid));
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}
function writeSession(uid: number, s: unknown) {
  try {
    window.localStorage.setItem(sessionKey(uid), JSON.stringify(s));
  } catch {
    /* private mode or storage blocked: the session just isn't remembered */
  }
}
function dropSession(uid: number) {
  try {
    window.localStorage.removeItem(sessionKey(uid));
  } catch {
    /* ignore */
  }
}

async function api<R>(path: string, body?: unknown): Promise<R> {
  const res = await fetch(`/api/engine/${path}`, body === undefined ? { cache: "no-store" } : {
    method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error((data as { detail?: string; error?: string }).detail ?? (data as { error?: string }).error ?? `HTTP ${res.status}`);
  return data as R;
}

const langForRegion = (region: string): Lang => (region === "Flanders" ? "nl" : "fr");

/** Demo-only: who wrote a Kaat message and what it cost. */
export function traceLine(tr: Trace): string {
  const calls = tr.calls ?? [];
  const tokens = calls.reduce((n, c) => n + c.inputTokens + c.outputTokens, 0);
  const cost = calls.reduce((n, c) => n + c.costUsd, 0);
  const g = tr.grounding ? ` · grounding ${tr.grounding.ok ? "ok" : `failed (${tr.grounding.unknown.join(", ")})`}` : "";
  const who = tr.author ?? "template";
  return `${who}${calls.length ? ` · ${calls[0].model} · ${calls.length} call(s) · ${tokens} tokens · $${cost.toFixed(4)}` : ""}${g}${tr.reason ? ` · ${tr.reason}` : ""} · ${tr.ms} ms`;
}

type PictureProps = {
  c: Card; t: (typeof T)[Lang]; detail: Detail; lang: Lang; busy: boolean;
  op: (name: string, args?: Record<string, unknown>) => Promise<unknown>;
};

function PictureCard({ c, t, detail, lang, busy, op }: PictureProps) {
  const [editing, setEditing] = useState(false);
  const [val, setVal] = useState(c.value === null || c.value === undefined ? "" : String(c.value));
  const isBool = c.type === "bool";
  // Activity counts ("you sent 1 registered e-mail") are either right or not; profile counts get a new value.
  const activity = c.type === "count" && ["services", "app"].includes(c.source_key);
  const countNotTrue = activity && c.editable && typeof c.value === "number" && c.value > 0;
  const canChange = c.editable && !isBool && !activity;
  const status = c.status === "confirmed" ? t.confirmed
    : (c.status === "overridden" || c.status === "implied") && c.original_display ? fill(t.changed, { orig: c.original_display }) : null;
  return (
    <div className="card">
      {/* Information is plain text; only what you can act on looks tappable. */}
      <p className="meta">{c.editable ? c.source : `${t.records} · ${c.source}`}</p>
      {status ? <p className={`meta ${c.status === "confirmed" ? "ok" : "warn"}`}>{status}</p> : null}
      <b>{c.sentence}</b>
      <p className="sub">{c.evidence.text}</p>
      {detail === "detailed" && (
        <>
          {c.effects.length > 0 && (
            <div className="chips">
              {c.effects.slice(0, 4).map((e) => (
                <span key={e.moment} className={`fx ${e.pts > 0 ? "up" : "down"}`}>
                  {e.pts > 0 ? "+" : "−"}{Math.abs(Math.round(e.pts))} {t.pts} · {e.label}
                </span>
              ))}
            </div>
          )}
          {c.evidence.transactions.slice(0, 3).map((x, i) => (
            <div className="tx" key={i}><span>{x.date} · {x.merchant}</span><b>{money(x.amount, lang)}</b></div>
          ))}
        </>
      )}
      {editing ? (
        <div className="edit">
          {c.type === "choice" && c.options ? (
            <select value={val} onChange={(e) => setVal(e.target.value)} aria-label={c.sentence}
              style={{ flex: 1, minHeight: "var(--tap)", borderRadius: "0.5rem", border: "1.5px solid var(--line)" }}>
              {c.options.map((o) => <option key={o} value={o}>{o.replace("_", " ")}</option>)}
            </select>
          ) : (
            <input value={val} inputMode="decimal" onChange={(e) => setVal(e.target.value)} aria-label={c.sentence} />
          )}
          <button className="btn" style={{ width: "auto" }} disabled={busy}
            onClick={async () => { if (await op("override", { feature: c.feature, value: val })) setEditing(false); }}>
            {t.save}
          </button>
        </div>
      ) : !c.editable ? null : (
        // Facts from our own records have nothing to confirm or fix here: no buttons.
        <div className="row">
          {c.status !== "confirmed" && (
            <button className="btn sec" disabled={busy} onClick={() => op("confirm", { feature: c.feature })}>{t.right}</button>
          )}
          {isBool && (
            <button className="btn sec" disabled={busy} onClick={() => op("override", { feature: c.feature, value: !c.value })}>{t.notTrue}</button>
          )}
          {countNotTrue && (
            <button className="btn sec" disabled={busy} onClick={() => op("override", { feature: c.feature, value: 0 })}>{t.notTrue}</button>
          )}
          {canChange && (
            <button className="btn sec" onClick={() => setEditing(true)}>{t.change}</button>
          )}
        </div>
      )}
    </div>
  );
}


// ---------------------------------------------------------------------------------------------
export default function KateApp() {
  const [showcase, setShowcase] = useState<Showcase[]>([]);
  const [uid, setUid] = useState<number | null>(null);
  const [lang, setLang] = useState<Lang>("nl");
  const [langManual, setLangManual] = useState(false);
  const [detail, setDetail] = useState<Detail>("simple");
  const [tab, setTab] = useState<Tab>("home");
  const [st, setSt] = useState<State | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [showMore, setShowMore] = useState(false);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [showSpec, setShowSpec] = useState(false);
  const [llmOn, setLlmOn] = useState(true);
  const [typing, setTyping] = useState(false);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mainRef = useRef<HTMLElement | null>(null);
  const t = T[lang];

  const flash = useCallback((text: string) => {
    setToast(text);
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 4500);
  }, []);

  // Showcase customers, then the first one.
  useEffect(() => {
    api<Showcase[]>("showcase")
      .then((list) => {
        setShowcase(list);
        if (list[0]) {
          setLang(langForRegion(list.find((s) => s.key === "landlord_email")?.region ?? list[0].region));
          setUid((list.find((s) => s.key === "landlord_email") ?? list[0]).user_id);
        }
      })
      .catch(() => setError("down"));
  }, []);

  // Load the customer's state whenever the customer or the language changes.
  useEffect(() => {
    if (uid === null) return;
    let cancelled = false;
    setError(null);
    api<{ state: State; session: unknown }>("state", { user_id: uid, session: readSession(uid), lang })
      .then((r) => {
        if (cancelled) return;
        writeSession(uid, r.session);
        const want = langForRegion(r.state.profile.region);
        if (!langManual && want !== lang) {
          setLang(want);
          return;
        }
        setSt(r.state);
      })
      .catch(() => !cancelled && setError("down"));
    return () => {
      cancelled = true;
    };
  }, [uid, lang, langManual]);

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);
  useEffect(() => {
    document.documentElement.style.fontSize = detail === "simple" ? "112.5%" : "";
  }, [detail]);
  useEffect(() => {
    mainRef.current?.scrollTo({ top: 0 });
  }, [tab, uid]);
  // In the Kaat tab, follow the conversation: show the newest message.
  useEffect(() => {
    if (tab !== "kate" || (msgs.length < 2 && !typing)) return;
    const el = mainRef.current;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    requestAnimationFrame(() => el?.scrollTo({ top: el.scrollHeight, behavior: reduce ? "auto" : "smooth" }));
  }, [msgs.length, tab, typing]);

  const pickCustomer = (id: number, region?: string) => {
    if (region && !langManual) setLang(langForRegion(region));
    setShowMore(false);
    setMsgs([]);
    setTab("home");
    if (id === uid) return; // same customer: keep the loaded state (clearing it would never reload)
    setSt(null);
    setUid(id);
  };

  const describeChange = (before: Pred[], after: Pred[]): string => {
    const parts: string[] = [];
    for (const a of after) {
      const b = before.find((x) => x.moment === a.moment);
      if (!b || Math.round(b.probability * 100) === Math.round(a.probability * 100)) continue;
      parts.push(detail === "simple"
        ? `${a.label_local}: ${a.probability < b.probability ? t.less : t.more}`
        : `${a.label_local}: ${pct(b.probability, lang)} → ${pct(a.probability, lang)}`);
    }
    return parts.join(" · ");
  };

  const op = async (name: string, args: Record<string, unknown> = {}) => {
    if (uid === null || busy) return null;
    setBusy(true);
    const before = st?.predictions ?? [];
    try {
      const r = await api<{ state: State; session: unknown; result: unknown }>("op", {
        user_id: uid, session: readSession(uid), lang, op: name, args,
      });
      if (name === "reset") dropSession(uid);
      writeSession(uid, r.session);
      setSt(r.state);
      if (["confirm", "override", "declare", "confirm_action", "reset"].includes(name)) {
        flash(describeChange(before, r.state.predictions) || t.noted);
      }
      return r;
    } catch (e) {
      flash(String((e as Error).message));
      return null;
    } finally {
      setBusy(false);
    }
  };

  const sendChat = async (text: string) => {
    const msg = text.trim();
    if (!msg || uid === null || busy) return;
    setMsgs((m) => [...m, { role: "u", text: msg }]);
    setBusy(true);
    setTyping(true);
    const before = st?.predictions ?? [];
    try {
      const res = await fetch("/api/kaat/reply", {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ user_id: uid, session: readSession(uid), lang, depth: detail, message: msg, llm: llmOn,
          moment: st?.kate.passed[0]?.moment }),
      });
      const r = (await res.json()) as { spec?: Spec; text?: string; prepared: string[]; session: unknown; state: State; trace: Trace; error?: string };
      if (!res.ok) throw new Error(r.error ?? `HTTP ${res.status}`);
      writeSession(uid, r.session);
      setSt(r.state);
      setMsgs((m) => [...m, { role: "k", spec: r.spec, text: r.spec ? undefined : r.text, actions: r.prepared, trace: r.trace }]);
      const change = describeChange(before, r.state.predictions);
      if (change) flash(change);
    } catch (e) {
      setMsgs((m) => [...m, { role: "k", text: String((e as Error).message) }]);
    } finally {
      setBusy(false);
      setTyping(false);
    }
  };

  // --- render helpers ------------------------------------------------------------------------
  const journeyOf = (m: string) => st?.journeys.find((j) => j.moment === m);

  const renderAction = (a: ActionCard) => (
    <div className="card" key={a.id}>
      <span className="sim">{a.service_name} · {t.simulated}</span>
      <b>{a.action_name}</b>
      <p className="sub" style={{ color: "var(--text)" }}>{a.summary}</p>
      {a.price_text ? <p className="sub">{a.price_text}</p> : null}
      {a.sends ? <p className="sub">{t.sends}</p> : null}
      {a.status === "prepared" && (
        <div className="row">
          <button className="btn" disabled={busy} onClick={() => op("confirm_action", { action_id: a.id })}>{a.button}</button>
          <button className="btn sec" disabled={busy} onClick={() => op("cancel_action", { action_id: a.id })}>{t.cancel}</button>
        </div>
      )}
      {a.status === "done" && (
        <>
          <p className="done-line">{String(a.result.title ?? "")}</p>
          {a.result.recommendation ? <p className="sub">{String(a.result.recommendation)}</p> : null}
          {a.result.what && a.result.what !== a.result.title ? <p className="sub">{String(a.result.what)}</p> : null}
          {a.result.status ? <p className="sub">{String(a.result.status)}</p> : null}
          <p className="sub">{t.reference}: <b>{String(a.result.reference ?? "")}</b></p>
          {a.result.qr_svg ? <div className="qr" dangerouslySetInnerHTML={{ __html: String(a.result.qr_svg) }} /> : null}
        </>
      )}
      {a.status === "cancelled" && <p className="sub">{t.cancelled}</p>}
    </div>
  );

  const renderHome = () => {
    if (!st) return null;
    const conv = st.kate.passed[0];
    const j = conv ? journeyOf(conv.moment) : undefined;
    const others = conv ? conv.items.slice(1) : [];
    const recent = st.actions.filter((a) => a.status === "prepared").concat(st.actions.filter((a) => a.status !== "prepared").slice(0, 3));
    const staged = st.journeys.filter((x) => x.stage);
    return (
      <>
        {conv ? (
          <section className="hero" aria-label={t.kate}>
            <div className="top">
              <div className="kate-av" aria-hidden="true" />
              <div>
                <small>{t.kate} · {j?.label_local} · {j?.stage_label}</small>
              </div>
            </div>
            <p className="big">{conv.lead.say}</p>
            <div className="row">
              {conv.lead.action ? (
                <button className="btn" disabled={busy}
                  onClick={() => op("prepare_action", { service: conv.lead.action!.service, action: conv.lead.action!.action, params: conv.lead.action!.params })}>
                  {t.prepare}
                </button>
              ) : (
                <button className="btn" onClick={() => setShowMore((v) => !v)}>{showMore ? t.hide : t.showMe}</button>
              )}
              <button className="btn sec" onClick={() => setTab("picture")}>{t.why}</button>
            </div>
            {showMore && others.length > 0 && (
              <div className="more">
                {others.map((it) => (
                  <div key={it.id}>
                    <b>{it.title}</b>
                    <p className="sub" style={{ color: "#fff", opacity: 0.85 }}>{it.say}</p>
                    {it.action && (
                      <button className="btn" disabled={busy}
                        onClick={() => op("prepare_action", { service: it.action!.service, action: it.action!.action, params: it.action!.params })}>
                        {t.prepare}
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
            <button className="btn link" style={{ color: "#fff", alignSelf: "flex-start" }} disabled={busy}
              onClick={() => op("ignore", { moment: conv.moment })}>{t.notNow}</button>
          </section>
        ) : (
          <div className="card"><p className="sub">{t.allSet}</p></div>
        )}

        {recent.map(renderAction)}

        <div className="sechead">{t.moments}</div>
        <div className="card">
          {staged.map((jj) => {
            const p = st.predictions.find((x) => x.moment === jj.moment);
            if (!p) return null;
            return (
              <div className="mom" key={jj.moment}>
                <div className="t">
                  <span>{p.label_local}</span>
                  {detail === "detailed" ? <span>{pct(p.probability, lang)}</span> : null}
                </div>
                <p className="meta">{jj.stage_label}{p.declared_label ? ` · ${p.declared_label}` : ""}</p>
                {detail === "simple" ? (
                  <>
                    <p className="sub">{fill(t.forYou, { freq: freq(p.probability, lang) })}</p>
                    {p.neighbour_rate !== null ? <p className="sub">{peopleLikeYou(p.neighbour_rate, lang)}</p> : null}
                  </>
                ) : (
                  <>
                    <div className="bar" role="img"
                      aria-label={`${pct(p.probability, lang)}${p.neighbour_rate !== null ? ` · ${peopleLikeYou(p.neighbour_rate, lang)}` : ""}`}>
                      <i style={{ width: `${Math.round(p.probability * 100)}%` }} />
                      {p.neighbour_rate !== null ? <b style={{ left: `${Math.round(p.neighbour_rate * 100)}%` }} /> : null}
                    </div>
                    {p.neighbour_rate !== null ? <p className="sub">{t.tick} · {pct(p.neighbour_rate, lang)}</p> : null}
                    <p className="sub">{t.whyStage}{jj.rule}</p>
                  </>
                )}
              </div>
            );
          })}
        </div>
      </>
    );
  };

  const renderPicture = () => {
    if (!st) return null;
    return (
      <>
        <p className="sub">{t.pictureIntro}</p>
        {st.cards.map((c) => <PictureCard key={c.feature} c={c} t={t} detail={detail} lang={lang} busy={busy} op={op} />)}
        <div className="sechead">{t.notUsed}</div>
        <div className="card">
          <ul className="list">{st.signals_not_used.map((s) => <li key={s}>{s}</li>)}</ul>
        </div>
      </>
    );
  };

  /** A Kaat message as a json-render spec, built and resolved on the server. */
  const fetchSpec = async (depth: Detail, moment?: string): Promise<Msg | null> => {
    if (uid === null) return null;
    const res = await fetch("/api/kaat/open", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ user_id: uid, session: readSession(uid), lang, depth, moment }),
    });
    if (!res.ok) return null;
    const r = (await res.json()) as { spec: Spec; session: unknown; trace: Trace };
    writeSession(uid, r.session);
    return { role: "k", spec: r.spec, trace: r.trace };
  };

  // Opening the Kaat tab: the proactive opener for this customer (or a quiet greeting), in the current depth.
  useEffect(() => {
    if (tab !== "kate" || !st || msgs.length) return;
    let cancelled = false;
    setTyping(true);
    fetchSpec(detail)
      .then((m) => {
        if (!cancelled) setMsgs([m ?? { role: "k", text: fill(t.hello, { name: st.profile.first_name }) }]);
      })
      .finally(() => !cancelled && setTyping(false));
    return () => {
      cancelled = true;
      setTyping(false);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, st?.user_id, msgs.length, lang, detail]);

  const handlers: Record<string, (params: Record<string, unknown>) => unknown> = {
    prepare_service_action: async (p) => {
      const r = await op("prepare_action", { service: p.service, action: p.action, params: {} });
      const id = (r?.result as { card?: { id: string } } | undefined)?.card?.id;
      if (id) setMsgs((m) => [...m, { role: "k", actions: [id] }]);
    },
    show_details: async (p) => {
      setTyping(true);
      try {
        const m = await fetchSpec("detailed", String(p.moment));
        if (m) setMsgs((x) => [...x, m]);
      } finally {
        setTyping(false);
      }
    },
    not_now: async (p) => {
      if (await op("ignore", { moment: p.moment })) setMsgs((m) => [...m, { role: "k", text: t.paused }]);
    },
    open_profile: () => setTab("picture"),
    talk_to_person: () => flash(t.adviser),
  };

  const bridge: Bridge = {
    lang, detail, busy,
    liveActions: (st?.actions ?? []) as unknown as Bridge["liveActions"],
    liveCards: (st?.cards ?? []) as unknown as Bridge["liveCards"],
    renderAction: (a) => renderAction(a as unknown as ActionCard),
    renderAssumption: (c) => <PictureCard c={c as unknown as Card} t={t} detail={detail} lang={lang} busy={busy} op={op} />,
    whatif: async (kind, id, value) => {
      if (uid === null) return null;
      try {
        const r = await api<{ whatif: { forecast?: Parameters<Bridge["whatif"]> extends never ? never : any } }>("whatif", {
          user_id: uid, session: readSession(uid), lang, kind, id, value,
        });
        return r.whatif;
      } catch {
        return null;
      }
    },
    prepare: async (service, action, params) => {
      await op("prepare_action", { service, action, params });
    },
  };

  const renderKate = () => {
    if (!st) return null;
    return (
      <div className="msgs">
        {msgs.map((m, i) => (
          <div key={i} className="turn">
            {m.spec ? <KaatSpecView spec={m.spec} handlers={handlers} bridge={bridge} showSpec={showSpec} trace={m.trace} traceText={m.trace ? traceLine(m.trace) : undefined} /> : null}
            {m.text ? <div className={`msg ${m.role}`}>{m.text}</div> : null}
            {showSpec && m.role === "k" && !m.spec && m.trace ? <p className="spec">{traceLine(m.trace)}</p> : null}
            {(m.actions ?? []).map((id) => {
              const a = st.actions.find((x) => x.id === id);
              return a ? renderAction(a) : null;
            })}
          </div>
        ))}
        {typing && (
          <div className="msg k with-av typing" role="status" aria-live="polite">
            <span className="kate-av sm" aria-hidden="true" />
            <span className="dots" aria-hidden="true"><i /><i /><i /></span>
            <span className="sr-only">{t.typing}</span>
          </div>
        )}
        {!typing && msgs.length > 0 && !msgs.some((m) => m.role === "u") && (
          <div className="starter">
            {startersFor(st, lang).map((s) => <button key={s} disabled={busy} onClick={() => sendChat(s)}>{s}</button>)}
          </div>
        )}
      </div>
    );
  };

  const [draft, setDraft] = useState("");
  const title = tab === "home" ? fill(t.greeting, { name: st?.profile.first_name ?? "" }) : tab === "picture" ? t.picture : t.kate;

  return (
    <div className="stage">
      <nav className="demo" aria-label="Demo controls">
        <div className="grp">
          <span className="lbl">{t.customers}</span>
          {showcase.map((s) => (
            <button key={s.key} className={uid === s.user_id ? "on" : ""} onClick={() => pickCustomer(s.user_id, s.region)}>
              {s.label} · {s.first_name}
            </button>
          ))}
          <button onClick={() => api<{ user_id: number }>("users/random").then((r) => pickCustomer(r.user_id)).catch(() => setError("down"))}>
            {t.random}
          </button>
          <button disabled={busy || uid === null} onClick={() => op("reset")}>{t.reset}</button>
        </div>
        <div className="sep" />
        <div className="grp">
          <button className={detail === "simple" ? "on" : ""} aria-pressed={detail === "simple"} onClick={() => { setDetail("simple"); setMsgs([]); }}>{t.simple}</button>
          <button className={detail === "detailed" ? "on" : ""} aria-pressed={detail === "detailed"} onClick={() => { setDetail("detailed"); setMsgs([]); }}>{t.detailed}</button>
          {(["nl", "fr", "en"] as Lang[]).map((l) => (
            <button key={l} className={lang === l ? "on" : ""} aria-pressed={lang === l}
              onClick={() => { setLangManual(true); setLang(l); setMsgs([]); }}>{l.toUpperCase()}</button>
          ))}
          <button className={showSpec ? "on" : ""} aria-pressed={showSpec} onClick={() => setShowSpec((v) => !v)}>{"{ }"} {t.spec}</button>
          <button className={llmOn ? "on" : ""} aria-pressed={llmOn} onClick={() => setLlmOn((v) => !v)}>LLM {llmOn ? "on" : "off"}</button>
        </div>
      </nav>

      <div className={`app ${detail}`}>
        <header className="hdr">
          <h1>{st ? title : t.loading}</h1>
        </header>
        <main className="main" ref={mainRef}>
          {error ? <div className="card"><p className="sub">{t.down}</p></div> : !st ? <p className="sub">{t.loading}</p> : null}
          {st && tab === "home" && renderHome()}
          {st && tab === "picture" && renderPicture()}
          {st && tab === "kate" && renderKate()}
        </main>
        {tab === "kate" && st && (
          <form className="composer" onSubmit={(e) => { e.preventDefault(); const d = draft; setDraft(""); sendChat(d); }}>
            <input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder={t.ask} aria-label={t.ask} />
            <button className="btn" type="submit" disabled={busy || !draft.trim()}>{t.send}</button>
          </form>
        )}
        {toast && <div className="toast" role="status">{toast}</div>}
        <nav className="tabs" aria-label="Tabs">
          {([["home", t.home, "M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z"],
            ["kate", t.kate, ""],
            ["picture", t.picture, "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zm-8 9a8 8 0 0 1 16 0"]] as [Tab, string, string][]).map(([id, label, d]) => (
            <button key={id} className={`tab ${id === "kate" ? "center" : ""} ${tab === id ? "on" : ""}`}
              aria-current={tab === id ? "page" : undefined} onClick={() => setTab(id)}>
              {id === "kate" ? <span className="kate-av tab-orb" aria-hidden="true" /> : <svg viewBox="0 0 24 24" aria-hidden="true"><path d={d} /></svg>}
              {label}
            </button>
          ))}
        </nav>
      </div>
    </div>
  );
}
