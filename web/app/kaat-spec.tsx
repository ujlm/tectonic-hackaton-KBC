"use client";

/**
 * Renders Kaat's json-render specs with our own component registry. Every number on screen comes from the
 * `data` the server resolved from engine state (or from live engine calls such as the what-if slider).
 */
import type { Spec } from "@json-render/core";
import { type ComponentRegistry, type ComponentRenderProps, JSONUIProvider, Renderer } from "@json-render/react";
import { createContext, type ReactNode, useContext, useEffect, useMemo, useRef, useState } from "react";

type Lang = "nl" | "fr" | "en";
type AnyCard = { id: string; service?: string; action?: string; status: string; feature?: string } & Record<string, unknown>;
type Forecast = {
  months: string[]; low: number[]; tightest_index: number; summary: string; below_zero: boolean;
  buffer: { monthly: number; low: number[]; covered: boolean } | null;
};

export type Bridge = {
  lang: Lang;
  detail: "simple" | "detailed";
  busy: boolean;
  liveActions: AnyCard[];
  liveCards: AnyCard[];
  renderAction: (card: AnyCard) => ReactNode;
  renderAssumption: (card: AnyCard) => ReactNode;
  whatif: (kind: string, id: string, value: number) => Promise<{ forecast?: Forecast } | null>;
  prepare: (service: string, action: string, params: Record<string, unknown>) => Promise<void>;
};

const BridgeCtx = createContext<Bridge | null>(null);
const useBridge = () => useContext(BridgeCtx)!;

const TXT = {
  en: { balance: "Your balance, the coming months", you: "You", peers: "People like you", why: "Why Kaat thinks this",
        up: "makes it more likely", down: "makes it less likely", buffer: "A buffer, set aside each month",
        setAside: "Set aside {amount} each month", withBuffer: "with the buffer", pts: "pts", spec: "json-render spec" },
  nl: { balance: "Je saldo, de komende maanden", you: "Jij", peers: "Mensen zoals jij", why: "Waarom Kaat dit denkt",
        up: "maakt het waarschijnlijker", down: "maakt het minder waarschijnlijk", buffer: "Een buffer, elke maand opzij",
        setAside: "Zet elke maand {amount} opzij", withBuffer: "met de buffer", pts: "ptn", spec: "json-render-spec" },
  fr: { balance: "Votre solde, les prochains mois", you: "Vous", peers: "Personnes comme vous", why: "Pourquoi Kaat pense cela",
        up: "rend plus probable", down: "rend moins probable", buffer: "Une réserve, mise de côté chaque mois",
        setAside: "Mettre {amount} de côté chaque mois", withBuffer: "avec la réserve", pts: "pts", spec: "spec json-render" },
} as const;

const LOCALE: Record<Lang, string> = { nl: "nl-BE", fr: "fr-BE", en: "en-GB" };
const eur = (v: number, lang: Lang) =>
  new Intl.NumberFormat(LOCALE[lang], { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(v);

function dataOf<T>(props: ComponentRenderProps["element"]["props"]): T {
  return (props as { data: T }).data;
}

// --- Visual building blocks --------------------------------------------------------------------
function ForecastLine({ f, lang }: { f: Forecast; lang: Lang }) {
  const W = 300, H = 120, padX = 16, top = 12, bottom = 26;
  const series = [f.low, ...(f.buffer ? [f.buffer.low] : [])];
  const all = series.flat();
  const min = Math.min(0, ...all), max = Math.max(0, ...all);
  const span = max - min || 1;
  const x = (i: number) => padX + (i * (W - 2 * padX)) / (f.low.length - 1);
  const y = (v: number) => top + ((max - v) / span) * (H - top - bottom);
  const path = (vals: number[]) => vals.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const k = f.tightest_index;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="spark" role="img" aria-label={f.summary}>
      <line x1={padX} x2={W - padX} y1={y(0)} y2={y(0)} className="zero" />
      <path d={path(f.low)} className="line" />
      {f.buffer ? <path d={path(f.buffer.low)} className="line buf" /> : null}
      <circle cx={x(k)} cy={y(f.low[k])} r={5} className={f.low[k] < 0 ? "dot warn" : "dot"} />
      {f.months.map((m, i) => (
        <text key={m} x={x(i)} y={H - 8} textAnchor="middle" className={i === k ? "lbl on" : "lbl"}>
          {m.split(" ")[0]}
        </text>
      ))}
      <title>{f.summary}{f.buffer ? ` (${TXT[lang].withBuffer})` : ""}</title>
    </svg>
  );
}

function People({ p, label, text, you }: { p: number; label: string; text: string; you?: boolean }) {
  const k = Math.min(10, Math.max(0, Math.round(p * 10)));
  return (
    <div className="people">
      <div className="who"><b>{label}</b><span>{text}</span></div>
      {p >= 0.095 ? (
        <div className="icons" aria-hidden="true">
          {Array.from({ length: 10 }, (_, i) => (
            <svg key={i} viewBox="0 0 12 18" className={i < k ? (you ? "on you" : "on") : ""}>
              <circle cx="6" cy="4" r="3.2" /><path d="M1 17c0-4 2.2-7 5-7s5 3 5 7z" />
            </svg>
          ))}
        </div>
      ) : null}
    </div>
  );
}

// --- Catalog components ------------------------------------------------------------------------
const Stack = ({ children }: ComponentRenderProps) => <div className="spec-stack">{children}</div>;

const KaatMessage = ({ element }: ComponentRenderProps) => (
  <div className="msg k with-av">
    <span className="kate-av sm" aria-hidden="true" />
    <span>{String((element.props as { text: string }).text)}</span>
  </div>
);

const ForecastMini = ({ element }: ComponentRenderProps) => {
  const { lang } = useBridge();
  const f = dataOf<Forecast>(element.props);
  return (
    <div className="card viz">
      <p className="meta">{TXT[lang].balance}</p>
      <ForecastLine f={f} lang={lang} />
      <p className="sub">{f.summary}</p>
    </div>
  );
};

const CompareToPeers = ({ element }: ComponentRenderProps) => {
  const { lang } = useBridge();
  const d = dataOf<{ label: string; you: string; peers: string; you_p: number; peers_p: number }>(element.props);
  return (
    <div className="card viz">
      <p className="meta">{d.label}</p>
      <People p={d.you_p} label={TXT[lang].you} text={d.you} you />
      <People p={d.peers_p} label={TXT[lang].peers} text={d.peers} />
    </div>
  );
};

const WhyPanel = ({ element }: ComponentRenderProps) => {
  const { lang, detail } = useBridge();
  const d = dataOf<{ label: string; reasons: { feature: string; sentence: string; pts: number }[] }>(element.props);
  const maxPts = Math.max(1, ...d.reasons.map((r) => Math.abs(r.pts)));
  return (
    <details className="card viz why" open>
      <summary><b>{TXT[lang].why}</b> <span className="meta">· {d.label}</span></summary>
      {d.reasons.map((r) => (
        <div className="reason" key={r.feature}>
          <span>{r.sentence}</span>
          <div className="rbar" title={r.pts > 0 ? TXT[lang].up : TXT[lang].down}>
            <i className={r.pts > 0 ? "up" : "down"} style={{ width: `${(Math.abs(r.pts) / maxPts) * 100}%` }} />
          </div>
          <span className={`meta ${r.pts > 0 ? "warn" : "ok-plain"}`}>
            {r.pts > 0 ? TXT[lang].up : TXT[lang].down}
            {detail === "detailed" ? ` · ${r.pts > 0 ? "+" : "−"}${Math.abs(Math.round(r.pts))} ${TXT[lang].pts}` : ""}
          </span>
        </div>
      ))}
    </details>
  );
};

const AssumptionCard = ({ element }: ComponentRenderProps) => {
  const b = useBridge();
  const d = dataOf<AnyCard>(element.props);
  const live = b.liveCards.find((c) => c.feature === d.feature) ?? d;
  return <>{b.renderAssumption(live)}</>;
};

const ServiceActionCard = ({ element }: ComponentRenderProps) => {
  const b = useBridge();
  const d = dataOf<AnyCard>(element.props);
  const live = b.liveActions.find((a) => a.id === d.id) ?? d;
  return <>{b.renderAction(live)}</>;
};

const ProductCard = ({ element }: ComponentRenderProps) => {
  const d = dataOf<{ title: string; say: string; kind_label: string }>(element.props);
  return (
    <div className="card">
      <p className="meta">{d.kind_label}</p>
      <b>{d.title}</b>
      <p className="sub">{d.say}</p>
    </div>
  );
};

const WhatIfSlider = ({ element }: ComponentRenderProps) => {
  const b = useBridge();
  const d = dataOf<{ min: number; max: number; step: number; value: number }>(element.props);
  const [amount, setAmount] = useState(d.value);
  const [f, setF] = useState<Forecast | null>(null);
  const [preparedId, setPreparedId] = useState<string | null>(null);
  const seen = useRef<Set<string>>(new Set(b.liveActions.map((a) => a.id)));
  const run = (v: number) => b.whatif("plan", "buffer_monthly", v).then((r) => r?.forecast && setF(r.forecast));
  useEffect(() => {
    run(d.value);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    const fresh = b.liveActions.find((a) => a.service === "buffer" && a.action === "start" && !seen.current.has(a.id));
    if (fresh) setPreparedId(fresh.id);
  }, [b.liveActions]);
  const card = preparedId ? b.liveActions.find((a) => a.id === preparedId) : undefined;
  return (
    <div className="card viz">
      <p className="meta">{TXT[b.lang].buffer}</p>
      <div className="slider">
        <input type="range" min={d.min} max={d.max} step={d.step} value={amount} aria-label={TXT[b.lang].buffer}
          aria-valuetext={eur(amount, b.lang)}
          onChange={(e) => setAmount(Number(e.target.value))}
          onPointerUp={() => run(amount)} onKeyUp={() => run(amount)} />
        <b>{eur(amount, b.lang)}</b>
      </div>
      {f ? (
        <>
          <ForecastLine f={f} lang={b.lang} />
          <p className="sub">{f.summary}</p>
        </>
      ) : null}
      {card ? b.renderAction(card) : (
        <button className="btn" disabled={b.busy} onClick={() => b.prepare("buffer", "start", { amount })}>
          {TXT[b.lang].setAside.replace("{amount}", eur(amount, b.lang))}
        </button>
      )}
    </div>
  );
};

const QuickReplies = ({ children }: ComponentRenderProps) => <div className="opts">{children}</div>;

const QuickReply = ({ element, emit }: ComponentRenderProps) => {
  const { busy } = useBridge();
  const p = element.props as { label: string; primary?: boolean };
  return <button className={p.primary ? "pri" : ""} disabled={busy} onClick={() => emit("press")}>{p.label}</button>;
};

const registry: ComponentRegistry = {
  Stack, KaatMessage, ForecastMini, CompareToPeers, WhyPanel, AssumptionCard, ServiceActionCard, ProductCard,
  WhatIfSlider, QuickReplies, QuickReply,
};

/** The spec as authored: references only, without the data the server filled in. */
function authored(spec: Spec): Spec {
  const elements = Object.fromEntries(Object.entries(spec.elements).map(([id, el]) => {
    const { data: _data, ...props } = el.props as Record<string, unknown>;
    return [id, { ...el, props }];
  }));
  return { root: spec.root, elements };
}

export function KaatSpecView({ spec, handlers, bridge, showSpec, trace, traceText }: {
  spec: Spec;
  handlers: Record<string, (params: Record<string, unknown>) => unknown>;
  bridge: Bridge;
  showSpec: boolean;
  trace?: { components?: number; dropped?: unknown[]; ms: number; author?: string } & Record<string, unknown>;
  traceText?: string;
}) {
  const shown = useMemo(() => (showSpec ? JSON.stringify(authored(spec), null, 1) : ""), [spec, showSpec]);
  return (
    <BridgeCtx.Provider value={bridge}>
      <JSONUIProvider registry={registry} handlers={handlers}>
        <Renderer spec={spec} registry={registry} />
      </JSONUIProvider>
      {showSpec ? (
        <details className="spec">
          <summary>{TXT[bridge.lang].spec} · {trace?.components ?? Object.keys(spec.elements).length} · {trace?.dropped?.length ?? 0} dropped{traceText ? ` · ${traceText}` : ""}</summary>
          <pre>{shown}</pre>
        </details>
      ) : null}
    </BridgeCtx.Provider>
  );
}
