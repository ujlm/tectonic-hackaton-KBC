/**
 * Gemini through the Vercel AI Gateway. Credentials come from the environment only (AI_GATEWAY_API_KEY, or the
 * Vercel OIDC token when no key is set); nothing here logs them.
 */
import { generateText, Output } from "ai";
import type { z } from "zod";

import { estimateCostUsd } from "./pricing";

export const TIMEOUT_MS = 8000;

export function modelId(): string {
  const m = (process.env.GEMINI_MODEL || "gemini-3.8-flash").trim();
  return m.includes("/") ? m : `google/${m}`;
}

/** Server kill switch: CHAT_ENABLED=false means templates and the offline parser only. */
export function chatEnabled(): boolean {
  return (process.env.CHAT_ENABLED ?? "true").toLowerCase() !== "false";
}

const providerOptions = {
  // Inference stays in the EU; if the gateway can't honour that, the call fails and we use the fallback.
  gateway: { inferenceRegion: { scope: "zone", geoRegion: "eu" } },
  google: { thinkingConfig: { thinkingLevel: "low" } },
  vertex: { thinkingConfig: { thinkingLevel: "low" } },
};

export type CallInfo = { model: string; ms: number; inputTokens: number; outputTokens: number; costUsd: number; costSource: string };

function info(started: number, usage: { inputTokens?: number; outputTokens?: number } | undefined, meta: unknown): CallInfo {
  const input = usage?.inputTokens ?? 0;
  const output = usage?.outputTokens ?? 0;
  const gatewayCost = Number((meta as { gateway?: { cost?: string } } | undefined)?.gateway?.cost);
  return {
    model: modelId(), ms: Date.now() - started, inputTokens: input, outputTokens: output,
    costUsd: Number.isFinite(gatewayCost) ? gatewayCost : estimateCostUsd(input, output),
    costSource: Number.isFinite(gatewayCost) ? "gateway" : "estimate",
  };
}

export async function generate(system: string, prompt: string, timeoutMs = TIMEOUT_MS): Promise<{ text: string; info: CallInfo }> {
  const started = Date.now();
  const r = await generateText({
    model: modelId(), system, prompt, timeout: timeoutMs, maxRetries: 0,
    providerOptions: providerOptions as never,
  });
  return { text: r.text, info: info(started, r.usage, r.providerMetadata) };
}

export async function generateObject<T>(system: string, prompt: string, schema: z.ZodType<T>, timeoutMs = TIMEOUT_MS): Promise<{ output: T; info: CallInfo }> {
  const started = Date.now();
  const r = await generateText({
    model: modelId(), system, prompt, timeout: timeoutMs, maxRetries: 0,
    output: Output.object({ schema }),
    providerOptions: providerOptions as never,
  });
  return { output: r.output as T, info: info(started, r.usage, r.providerMetadata) };
}
