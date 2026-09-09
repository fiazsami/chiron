// Client-side fetch helper for the smart navigator. Stateless per request; a
// small in-memory cache makes repeating `a` on the same selection instant.

import type {
  Destination,
  NavigateRequest,
  NavigateResponse,
} from "./navigator-types";

const cache = new Map<string, Destination[]>();
const CACHE_MAX = 30;

function cacheKey(body: NavigateRequest): string {
  return `${body.corpus}/${body.register}|${body.pathname ?? ""}|${body.selection.trim().toLowerCase()}`;
}

export async function fetchNavigation(
  body: NavigateRequest,
  signal: AbortSignal,
  bypassCache = false,
): Promise<NavigateResponse> {
  const key = cacheKey(body);
  if (!bypassCache) {
    const hit = cache.get(key);
    if (hit) return { results: hit };
  }
  const res = await fetch("/api/navigate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok) {
    let message = `navigate failed (${res.status})`;
    try {
      const data = (await res.json()) as { error?: unknown };
      if (typeof data.error === "string") message = data.error;
    } catch {
      // non-JSON error body — keep the status message
    }
    throw new Error(message);
  }
  const data = (await res.json()) as NavigateResponse;
  const results = Array.isArray(data.results) ? data.results : [];
  cache.set(key, results);
  if (cache.size > CACHE_MAX) {
    const oldest = cache.keys().next().value;
    if (oldest !== undefined) cache.delete(oldest);
  }
  return { results };
}
