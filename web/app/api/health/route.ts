import { engineGet } from "@/lib/engine";

export async function GET() {
  const started = Date.now();
  try {
    const [health, meta] = await Promise.all([
      engineGet<{ ok: boolean }>("engine/health"),
      engineGet<Record<string, unknown>>("engine/meta"),
    ]);
    return Response.json({ web: "ok", engine: health, meta, ms: Date.now() - started });
  } catch (err) {
    return Response.json({ web: "ok", engine: { ok: false, error: String(err) } }, { status: 502 });
  }
}
