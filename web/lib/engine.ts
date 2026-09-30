/** Server-side client for the private engine service (bound as ENGINE_URL on Vercel). */
const LOCAL_ENGINE = "http://127.0.0.1:8000/";

export function engineUrl(path: string): URL {
  const base = process.env.ENGINE_URL ?? LOCAL_ENGINE;
  return new URL(path.replace(/^\//, ""), base.endsWith("/") ? base : `${base}/`);
}

export async function engineGet<T>(path: string): Promise<T> {
  const res = await fetch(engineUrl(path), { cache: "no-store", headers: engineHeaders() });
  if (!res.ok) throw new Error(`engine ${path}: ${res.status}`);
  return (await res.json()) as T;
}

export async function enginePost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(engineUrl(path), {
    method: "POST",
    cache: "no-store",
    headers: { "content-type": "application/json", ...engineHeaders() },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`engine ${path}: ${res.status} ${await res.text()}`);
  return (await res.json()) as T;
}

export function engineHeaders(): Record<string, string> {
  const token = process.env.ENGINE_TOKEN;
  return token ? { "x-engine-token": token } : {};
}
