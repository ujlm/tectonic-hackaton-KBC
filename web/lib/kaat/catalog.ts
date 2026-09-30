/**
 * Kaat's component catalog: the contract between whoever writes a spec (templates today, Gemini later) and the app.
 *
 * Grounding rule: specs never carry numbers, amounts or dates. Data props are references (`ref`), and the server
 * fills `data` from engine state before the spec reaches the client. An element whose reference doesn't resolve,
 * or whose props don't validate, is dropped.
 */
import { defineCatalog } from "@json-render/core";
import { schema } from "@json-render/react/schema";
import { z } from "zod";

export const MOMENTS = ["move_house", "buy_car", "renovation", "start_investing", "cash_squeeze"] as const;
const moment = z.enum(MOMENTS);
/** Filled in by the server from engine state; never written by the spec author. */
const data = z.any().optional();

export const COMPONENTS = {
  Stack: { props: z.object({}), slots: ["default"], description: "One Kaat message: a vertical group of components." },
  KaatMessage: {
    props: z.object({ text: z.string().min(1).max(420) }),
    description: "A short message from Kaat. Only quote facts from the context pack.",
  },
  ForecastMini: {
    props: z.object({ ref: z.literal("forecast"), data }),
    description: "One line: the lowest point of the current account per month for the next 6 months; the tightest month is highlighted.",
  },
  CompareToPeers: {
    props: z.object({ moment, ref: z.string().regex(/^peers:/), data }),
    description: "You vs people like you, as natural frequencies (about 4 in 10).",
  },
  WhyPanel: {
    props: z.object({ moment, ref: z.string().regex(/^why:/), data }),
    description: "Expandable list of the assumptions behind a prediction, with their effect.",
  },
  AssumptionCard: {
    props: z.object({ feature: z.string(), ref: z.string().regex(/^assumption:/), data }),
    description: "One assumption the customer can confirm or correct.",
  },
  WhatIfSlider: {
    props: z.object({ plan: z.literal("buffer_monthly"), ref: z.literal("plan:buffer_monthly"), data }),
    description: "Bounded slider for a plan; the outlook updates when the customer lets go.",
  },
  ServiceActionCard: {
    props: z.object({ service: z.string(), action: z.string(), ref: z.string().regex(/^service:/), data }),
    description: "A prepared service action. Nothing happens until the customer taps confirm.",
  },
  ProductCard: {
    props: z.object({ product: z.string(), ref: z.string().regex(/^product:/), data }),
    description: "A KBC product, only from the deciding stage on and never in a security flow.",
  },
  QuickReplies: { props: z.object({}), slots: ["default"], description: "Two to four reply buttons." },
  QuickReply: {
    props: z.object({ label: z.string().min(1).max(60), primary: z.boolean().optional() }),
    description: "One reply button; its `on.press` binds an action.",
  },
};

export const ACTIONS = {
  prepare_service_action: { params: z.object({ service: z.string(), action: z.string() }), description: "Prepare a service action (does not execute)." },
  show_details: { params: z.object({ moment }), description: "Show the reasons behind a topic in detail." },
  not_now: { params: z.object({ moment }), description: "Pause this topic for 60 days." },
  open_profile: { params: z.object({}), description: "Open 'What Kaat thinks about you'." },
  talk_to_person: { params: z.object({}), description: "Book a call with an adviser (simulated)." },
};

export const catalog = defineCatalog(schema, { components: COMPONENTS, actions: ACTIONS });

export type ComponentType = keyof typeof COMPONENTS;
