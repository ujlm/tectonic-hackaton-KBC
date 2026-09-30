/**
 * The checks every spec passes before it reaches the client, whoever wrote it (template or Gemini):
 * only allowed components and actions, valid props, depth limits, and every reference resolved from engine state.
 */
import type { Spec } from "@json-render/core";

import { COMPONENTS, type ComponentType } from "./catalog";
import type { ContextPack } from "./templates";

type Drop = { id: string; type: string; reason: string };
const VISUAL = new Set(["ForecastMini", "CompareToPeers", "WhyPanel", "AssumptionCard", "WhatIfSlider", "ProductCard", "ServiceActionCard"]);

export function allowedRefs(ctx: ContextPack, prepared: { service: string; action: string }[]): Set<string> {
  const a = ctx.allowed;
  const refs = new Set<string>();
  if (a.forecast) refs.add("forecast");
  a.peers.forEach((m) => refs.add(`peers:${m}`));
  if (ctx.topic) refs.add(`why:${ctx.topic.moment}`);
  a.assumptions.forEach((f) => refs.add(`assumption:${f}`));
  a.plans.forEach((p) => refs.add(`plan:${p}`));
  a.products.forEach((p) => refs.add(`product:${p}`));
  prepared.forEach((p) => refs.add(`service:${p.service}.${p.action}`));
  return refs;
}

function actionAllowed(ctx: ContextPack, binding: unknown): boolean {
  const b = binding as { action?: string; params?: Record<string, unknown> } | undefined;
  if (!b?.action) return false;
  const p = b.params ?? {};
  switch (b.action) {
    case "open_profile":
    case "talk_to_person":
      return true;
    case "show_details":
    case "not_now":
      return !!ctx.topic && p.moment === ctx.topic.moment;
    case "prepare_service_action":
      return ctx.allowed.services.includes(`${p.service}.${p.action}`);
    default:
      return false;
  }
}

/** Keep only what the catalog, this turn's allow-list and the depth rules permit. */
export function sanitize(spec: Spec, ctx: ContextPack, refs: Set<string>): { spec: Spec; dropped: Drop[] } {
  const dropped: Drop[] = [];
  const elements: Spec["elements"] = {};
  let visuals = 0;
  const order = orderedIds(spec);
  for (const id of order) {
    const el = spec.elements[id];
    if (!el) continue;
    const def = COMPONENTS[el.type as ComponentType];
    const props = { ...((el.props ?? {}) as Record<string, unknown>) };
    delete props.data; // only the server fills data
    const why = !def ? "unknown component"
      : !def.props.safeParse(props).success ? "invalid props"
      : typeof props.ref === "string" && !refs.has(props.ref) ? `reference not allowed in this turn (${props.ref})`
      : el.type === "QuickReply" && !actionAllowed(ctx, (el.on as Record<string, unknown> | undefined)?.press) ? "action not allowed"
      : VISUAL.has(el.type) && ctx.depth === "simple" && visuals >= 1 ? "simple depth: one visual per message"
      : null;
    if (why) {
      dropped.push({ id, type: el.type, reason: why });
      continue;
    }
    if (VISUAL.has(el.type)) visuals++;
    elements[id] = { type: el.type, props, children: el.children ?? [], ...(el.on ? { on: el.on } : {}) };
  }
  prune(elements, ctx.depth === "simple" ? 3 : 4);
  return { spec: { root: spec.root, elements }, dropped };
}

function orderedIds(spec: Spec): string[] {
  const seen: string[] = [];
  const walk = (id: string) => {
    if (seen.includes(id) || !spec.elements[id]) return;
    seen.push(id);
    (spec.elements[id].children ?? []).forEach(walk);
  };
  walk(spec.root);
  return seen;
}

function prune(elements: Spec["elements"], maxReplies: number) {
  for (const el of Object.values(elements)) {
    el.children = (el.children ?? []).filter((c) => c in elements);
    if (el.type === "QuickReplies") el.children = el.children.slice(0, maxReplies);
  }
}

/** Fill `data` from resolved references; drop what didn't resolve. */
export function resolveAndValidate(spec: Spec, resolved: Record<string, unknown>) {
  const elements: Spec["elements"] = {};
  const dropped: Drop[] = [];
  for (const [id, el] of Object.entries(spec.elements)) {
    const props = { ...(el.props as Record<string, unknown>) };
    if (typeof props.ref === "string") {
      const data = resolved[props.ref];
      if (data === null || data === undefined) {
        dropped.push({ id, type: el.type, reason: `unresolved reference ${props.ref}` });
        continue;
      }
      props.data = data;
    }
    const def = COMPONENTS[el.type as ComponentType];
    if (!def?.props.safeParse(props).success) {
      dropped.push({ id, type: el.type, reason: def ? "invalid props" : "unknown component" });
      continue;
    }
    elements[id] = { ...el, props };
  }
  for (const el of Object.values(elements)) el.children = (el.children ?? []).filter((c) => c in elements);
  return { spec: { root: spec.root, elements }, dropped };
}

export function refsOf(spec: Spec): string[] {
  return Object.values(spec.elements)
    .map((el) => (el.props as { ref?: unknown }).ref)
    .filter((r): r is string => typeof r === "string");
}

export function textsOf(spec: Spec): string[] {
  return Object.values(spec.elements).flatMap((el) => {
    const p = el.props as { text?: unknown; label?: unknown };
    return [p.text, p.label].filter((x): x is string => typeof x === "string");
  });
}
