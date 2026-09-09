// Client-side helper: POST to /api/agent and yield parsed NDJSON events.

export type AgentEvent =
  | { kind: "init"; sessionId: string }
  | { kind: "delta"; text: string }
  | { kind: "tool"; name: string }
  | { kind: "done"; sessionId: string }
  | { kind: "error"; message: string };

export interface AgentRequestBody {
  corpus: string;
  register: string;
  message: string;
  sessionId?: string;
  pathname?: string;
}

export async function* streamAgent(
  body: AgentRequestBody,
  signal: AbortSignal,
): AsyncGenerator<AgentEvent> {
  const res = await fetch("/api/agent", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) {
    let message = `request failed (${res.status})`;
    try {
      const data = (await res.json()) as { error?: string };
      if (data.error) message = data.error;
    } catch {
      // non-JSON error body — keep the status message
    }
    yield { kind: "error", message };
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        if (line.trim()) yield JSON.parse(line) as AgentEvent;
      }
    }
    if (buffer.trim()) yield JSON.parse(buffer) as AgentEvent;
  } finally {
    reader.releaseLock();
  }
}
