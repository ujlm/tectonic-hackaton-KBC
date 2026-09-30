/**
 * Deterministic specs per topic and depth (the fallback that also works with the LLM off).
 * Same catalog, same grounding: text comes from context-pack facts, data from references.
 */
import type { Spec } from "@json-render/core";

type Lang = "nl" | "fr" | "en";
export type ContextPack = {
  lang: Lang;
  depth: "simple" | "detailed";
  topic: {
    moment: string;
    label: string;
    stage: string;
    stage_label: string;
    lead: { id: string; kind: string; title: string; say: string; action: string | null };
    items: { id: string; kind: string; title: string; say: string; action: string | null }[];
  } | null;
  facts: { id: string; text: string }[];
  allowed: { assumptions: string[]; services: string[]; products: string[]; plans: string[]; forecast: boolean; peers: string[] };
};

const S = {
  en: { yes: "Yes, show me", show: "Show me more", why: "Why?", notNow: "Not now",
        detail: "Here's what I based this on. Correct anything that's wrong.",
        quiet: "Hi {name}. Nothing needs your attention right now. I'll stay quiet until something changes.",
        profile: "What Kaat thinks about you", adviser: "Talk to a person" },
  nl: { yes: "Ja, toon me", show: "Toon me meer", why: "Waarom?", notNow: "Niet nu",
        detail: "Hierop baseer ik me. Pas aan wat niet klopt.",
        quiet: "Dag {name}. Er is nu niets dat je aandacht vraagt. Ik blijf stil tot er iets verandert.",
        profile: "Wat Kaat over jou denkt", adviser: "Praat met iemand" },
  fr: { yes: "Oui, montrez-moi", show: "En voir plus", why: "Pourquoi ?", notNow: "Pas maintenant",
        detail: "Voici sur quoi je me base. Corrigez ce qui ne va pas.",
        quiet: "Bonjour {name}. Rien ne demande votre attention pour l'instant. Je reste discrète jusqu'à ce que quelque chose change.",
        profile: "Ce que Kaat pense de vous", adviser: "Parler à quelqu'un" },
} as const;

function builder() {
  const elements: Spec["elements"] = {};
  let n = 0;
  const add = (type: string, props: Record<string, unknown>, extra: Partial<Spec["elements"][string]> = {}) => {
    const id = `${type.charAt(0).toLowerCase()}${type.slice(1)}-${++n}`;
    elements[id] = { type, props, children: [], ...extra };
    return id;
  };
  return { elements, add };
}

export function buildSpec(ctx: ContextPack): Spec {
  const s = S[ctx.lang];
  const fact = (id: string) => ctx.facts.find((f) => f.id === id)?.text ?? "";
  const { elements, add } = builder();
  const t = ctx.topic;
  const kids: string[] = [];
  const replies: string[] = [];

  if (!t) {
    kids.push(add("KaatMessage", { text: s.quiet.replace("{name}", fact("customer.first_name")) }));
    replies.push(add("QuickReply", { label: s.profile, primary: true }, { on: { press: { action: "open_profile", params: {} } } }));
  } else if (ctx.depth === "simple") {
    kids.push(add("KaatMessage", { text: t.lead.say }));
    if (ctx.allowed.forecast) kids.push(add("ForecastMini", { ref: "forecast" }));
    else if (ctx.allowed.peers.includes(t.moment)) kids.push(add("CompareToPeers", { moment: t.moment, ref: `peers:${t.moment}` }));
    const [service, action] = (t.lead.action ?? "").split(".");
    replies.push(t.lead.action && ctx.allowed.services.includes(t.lead.action)
      ? add("QuickReply", { label: s.yes, primary: true }, { on: { press: { action: "prepare_service_action", params: { service, action } } } })
      : add("QuickReply", { label: s.show, primary: true }, { on: { press: { action: "show_details", params: { moment: t.moment } } } }));
    if (t.lead.action) replies.push(add("QuickReply", { label: s.why }, { on: { press: { action: "show_details", params: { moment: t.moment } } } }));
    replies.push(add("QuickReply", { label: s.notNow }, { on: { press: { action: "not_now", params: { moment: t.moment } } } }));
  } else {
    kids.push(add("KaatMessage", { text: s.detail }));
    if (ctx.allowed.peers.includes(t.moment)) kids.push(add("CompareToPeers", { moment: t.moment, ref: `peers:${t.moment}` }));
    if (ctx.allowed.forecast) kids.push(add("ForecastMini", { ref: "forecast" }));
    kids.push(add("WhyPanel", { moment: t.moment, ref: `why:${t.moment}` }));
    for (const f of ctx.allowed.assumptions.slice(0, 3)) kids.push(add("AssumptionCard", { feature: f, ref: `assumption:${f}` }));
    if (ctx.allowed.plans.includes("buffer_monthly")) kids.push(add("WhatIfSlider", { plan: "buffer_monthly", ref: "plan:buffer_monthly" }));
    for (const p of ctx.allowed.products.slice(0, 1)) kids.push(add("ProductCard", { product: p, ref: `product:${p}` }));
    const lead = t.lead.action && ctx.allowed.services.includes(t.lead.action) && !ctx.allowed.plans.length ? t.lead.action : null;
    if (lead) {
      const [service, action] = lead.split(".");
      replies.push(add("QuickReply", { label: s.yes, primary: true }, { on: { press: { action: "prepare_service_action", params: { service, action } } } }));
    }
    if (ctx.allowed.products.length) replies.push(add("QuickReply", { label: s.adviser }, { on: { press: { action: "talk_to_person", params: {} } } }));
    replies.push(add("QuickReply", { label: s.notNow }, { on: { press: { action: "not_now", params: { moment: t.moment } } } }));
  }
  const qr = add("QuickReplies", {});
  elements[qr].children = replies;
  kids.push(qr);
  const root = add("Stack", {});
  elements[root].children = kids;
  return { root, elements };
}
