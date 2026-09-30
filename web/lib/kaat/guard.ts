/**
 * Misuse protection for Kaat's LLM routes.
 *
 * - Same origin: only the app's own pages may call /api/kaat/* (blocks other sites from using the endpoint from a
 *   visitor's browser; a determined script can still fake headers, hence the limits below).
 * - Per IP: RATE_LIMIT_PER_MIN (default 8) and RATE_LIMIT_PER_DAY (default 60) LLM turns, keyed on the client IP
 *   that Vercel reports (x-real-ip), not on a header the caller controls.
 * - Global: LLM_DAILY_CALL_CAP (default 2,000) Gemini calls a day; after that everyone gets the offline parser.
 *
 * Counters live in memory, so they hold per server instance. For a hard, shared limit add a Vercel Firewall
 * rate-limit rule on /api/kaat/reply and cap spend on the AI Gateway account (prepaid credits, no auto top-up).
 */
const perIp = new Map<string, { minute: number[]; day: string; turns: number }>();
const global = { day: "", calls: 0 };

const num = (name: string, fallback: number) => {
  const v = Number(process.env[name]);
  return Number.isFinite(v) && v > 0 ? v : fallback;
};
const today = () => new Date().toISOString().slice(0, 10);

/** The client IP as Vercel reports it; the caller can't set x-real-ip on Vercel. */
export function clientIp(req: Request): string {
  const h = req.headers;
  return h.get("x-real-ip") ?? h.get("x-vercel-forwarded-for")?.split(",")[0]?.trim()
    ?? h.get("x-forwarded-for")?.split(",")[0]?.trim() ?? "local";
}

/** True when the request comes from a page on this same site. */
export function sameOrigin(req: Request): boolean {
  const site = req.headers.get("sec-fetch-site");
  if (site && site !== "same-origin") return false;
  const origin = req.headers.get("origin");
  if (!origin) return site === "same-origin";
  const host = req.headers.get("x-forwarded-host") ?? req.headers.get("host");
  try {
    return new URL(origin).host === host;
  } catch {
    return false;
  }
}

export type Admission = { ok: true } | { ok: false; reason: string };

/** Admit one LLM turn for this IP, or say which limit stops it. Records the turn when admitted. */
export function admitTurn(ip: string): Admission {
  const day = today();
  if (global.day !== day) {
    global.day = day;
    global.calls = 0;
    perIp.clear();
  }
  if (global.calls >= num("LLM_DAILY_CALL_CAP", 2000)) return { ok: false, reason: "daily LLM budget reached" };
  const now = Date.now();
  const b = perIp.get(ip) ?? { minute: [], day, turns: 0 };
  b.minute = b.minute.filter((t) => now - t < 60_000);
  if (b.turns >= num("RATE_LIMIT_PER_DAY", 60)) return { ok: false, reason: "per-day limit for this IP" };
  if (b.minute.length >= num("RATE_LIMIT_PER_MIN", 8)) return { ok: false, reason: "per-minute limit for this IP" };
  b.minute.push(now);
  b.turns += 1;
  perIp.set(ip, b);
  if (perIp.size > 20_000) perIp.clear();
  return { ok: true };
}

/** Count Gemini calls against the global daily ceiling. */
export function countCalls(n: number) {
  if (global.day !== today()) {
    global.day = today();
    global.calls = 0;
  }
  global.calls += n;
}

export const forbidden = () => Response.json({ error: "Forbidden" }, { status: 403 });
