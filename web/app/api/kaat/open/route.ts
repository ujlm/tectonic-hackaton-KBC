/**
 * A Kaat message as a json-render spec: context pack -> spec (template; Gemini later) -> resolve references from
 * engine state -> validate every element against the catalog -> send. Nothing unresolved or invalid reaches the client.
 */
import type { Spec } from "@json-render/core";

import { enginePost } from "@/lib/engine";
import { resolveAndValidate } from "@/lib/kaat/pipeline";
import { buildSpec, type ContextPack } from "@/lib/kaat/templates";

type Body = { user_id: number; session: unknown; lang: string; depth?: "simple" | "detailed"; moment?: string };

export async function POST(req: Request) {
  const body = (await req.json()) as Body;
  const started = Date.now();
  try {
    const c = await enginePost<{ context: ContextPack; session: unknown }>("engine/context", {
      user_id: body.user_id, session: body.session, lang: body.lang, depth: body.depth ?? "simple",
      purpose: body.moment ? "reply" : "opener", moment: body.moment ?? null,
    });
    const spec = buildSpec(c.context);
    const refs = Object.values(spec.elements)
      .map((el) => (el.props as { ref?: unknown }).ref)
      .filter((r): r is string => typeof r === "string");
    const r = refs.length
      ? await enginePost<{ resolved: Record<string, unknown>; session: unknown }>("engine/resolve", {
          user_id: body.user_id, session: c.session, lang: body.lang, refs, allowed: c.context.allowed,
        })
      : { resolved: {}, session: c.session };
    const { spec: out, dropped } = resolveAndValidate(spec, r.resolved);
    return Response.json({
      spec: out,
      session: r.session,
      trace: { author: "template", components: Object.keys(out.elements).length, refs, dropped, ms: Date.now() - started },
    });
  } catch (err) {
    return Response.json({ error: String(err) }, { status: 502 });
  }
}
