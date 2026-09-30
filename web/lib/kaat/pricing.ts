/**
 * Price per 1M tokens for the default model, pinned to EU inference (Vertex, +10% over global).
 * Sources (checked 30 Sep 2026):
 * - https://vercel.com/ai-gateway/models/gemini-3.8-flash (gateway passes through list prices, no markup)
 * - https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing (introductory until 31 Dec 2026)
 * The gateway also reports the measured cost per call (providerMetadata.gateway.cost); prefer that when present.
 */
export const PRICE_PER_MTOK = {
  until_2026_12_31: { input: 0.825, output: 4.125 },
  from_2027_01_01: { input: 1.65, output: 8.25 },
} as const;

export function estimateCostUsd(inputTokens: number, outputTokens: number, when = new Date("2026-10-01")): number {
  const p = when < new Date("2027-01-01") ? PRICE_PER_MTOK.until_2026_12_31 : PRICE_PER_MTOK.from_2027_01_01;
  return (inputTokens * p.input + outputTokens * p.output) / 1_000_000;
}
