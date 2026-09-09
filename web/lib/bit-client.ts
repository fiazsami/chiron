// Client-side fetch for a single bit's flashcard — the modal's dive and
// direct-entry path. Mirrors navigate-client: small in-memory cache, only
// successes cached (a stale-store dive can succeed once the data catches up).

import type { BitRequest, BitResponse, Destination } from "./navigator-types";

const cache = new Map<string, Destination>();
const CACHE_MAX = 50;

function cacheKey(req: BitRequest): string {
  return `${req.corpus}/${req.register}|${req.kind}:${req.id}`;
}

export async function fetchBit(
  req: BitRequest,
  signal: AbortSignal,
  bypassCache = false,
): Promise<Destination> {
  const key = cacheKey(req);
  if (!bypassCache) {
    const hit = cache.get(key);
    if (hit) return hit;
  }
  const res = await fetch("/api/bit", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
    signal,
  });
  if (!res.ok) {
    let message = `lookup failed (${res.status})`;
    try {
      const data = (await res.json()) as { error?: unknown };
      if (typeof data.error === "string") message = data.error;
    } catch {
      // non-JSON error body — keep the status message
    }
    throw new Error(message);
  }
  const data = (await res.json()) as BitResponse;
  cache.set(key, data.destination);
  if (cache.size > CACHE_MAX) {
    const oldest = cache.keys().next().value;
    if (oldest !== undefined) cache.delete(oldest);
  }
  return data.destination;
}
