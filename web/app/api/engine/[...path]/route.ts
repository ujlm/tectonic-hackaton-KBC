import { engineHeaders, engineUrl } from "@/lib/engine";

/** Browser -> engine proxy. Only these engine endpoints are reachable from the client. */
const ALLOW = new Set(["showcase", "users/random", "meta", "state", "op", "parse", "scale", "whatif"]);

async function forward(req: Request, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  const target = path.join("/");
  if (!ALLOW.has(target)) return Response.json({ error: "Not found" }, { status: 404 });
  const init: RequestInit = {
    method: req.method,
    cache: "no-store",
    headers: { "content-type": "application/json", ...engineHeaders() },
  };
  if (req.method === "POST") init.body = await req.text();
  try {
    const res = await fetch(engineUrl(`engine/${target}`), init);
    return new Response(await res.text(), { status: res.status, headers: { "content-type": "application/json" } });
  } catch {
    return Response.json({ error: "The engine is not reachable." }, { status: 502 });
  }
}

export const GET = forward;
export const POST = forward;
