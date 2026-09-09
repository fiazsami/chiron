import { NextRequest } from "next/server";
import { query } from "@anthropic-ai/claude-agent-sdk";
import { buildAgentOptions } from "@/lib/agent";
import { findCorpus, getManifest } from "@/lib/content";

export const dynamic = "force-dynamic";

const CREDENTIAL_HINT =
  "set ANTHROPIC_API_KEY in web/.env.local or run `claude /login`";

interface AgentRequest {
  corpus: string;
  register: string;
  message: string;
  sessionId?: string;
  pathname?: string;
}

function badRequest(message: string): Response {
  return Response.json({ error: message }, { status: 400 });
}

function withCredentialHint(message: string): string {
  // Missing/invalid credentials surface as auth errors from the API or as
  // the CLI process dying at startup — attach the fix in both cases.
  if (/api.?key|log.?in|auth|credential|billing|credit|exited with/i.test(message)) {
    return `${message} — ${CREDENTIAL_HINT}`;
  }
  return message;
}

export async function POST(req: NextRequest): Promise<Response> {
  let body: AgentRequest;
  try {
    body = (await req.json()) as AgentRequest;
  } catch {
    return badRequest("request body must be JSON");
  }
  const { corpus: name, register, message, sessionId, pathname } = body;
  if (
    typeof name !== "string" ||
    typeof register !== "string" ||
    typeof message !== "string" ||
    !message.trim()
  ) {
    return badRequest("corpus, register, and a non-empty message are required");
  }
  if (sessionId !== undefined && typeof sessionId !== "string") {
    return badRequest("sessionId must be a string");
  }

  const manifest = await getManifest();
  if (manifest.corpora.length === 0) {
    return Response.json(
      {
        error:
          "no manifest — mount a corpus and run `uv run python -m tools.lingua`",
      },
      { status: 503 },
    );
  }
  const corpus = findCorpus(manifest, name, register);
  if (!corpus) {
    return Response.json(
      { error: `unknown corpus register ${name}/${register}` },
      { status: 404 },
    );
  }

  const abortController = new AbortController();
  req.signal.addEventListener("abort", () => abortController.abort());
  const options = await buildAgentOptions(corpus, {
    abortController,
    resume: sessionId,
  });

  // Page context rides the user message, never the system prompt.
  const prompt = pathname
    ? `${message}\n\n[context: the learner is currently viewing ${pathname} in the viewer]`
    : message;

  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      const send = (line: Record<string, unknown>) => {
        try {
          controller.enqueue(encoder.encode(JSON.stringify(line) + "\n"));
        } catch {
          // Stream already closed (client went away) — drop the line.
        }
      };
      try {
        for await (const msg of query({ prompt, options })) {
          if (msg.type === "system" && msg.subtype === "init") {
            send({ kind: "init", sessionId: msg.session_id });
          } else if (
            msg.type === "system" &&
            msg.subtype === "api_retry" &&
            (msg.error_status === 401 || msg.error_status === 403)
          ) {
            // Bad/missing credentials: the CLI would retry ~10 times with
            // exponential backoff. Fail fast instead of hanging the panel.
            send({
              kind: "error",
              message: `authentication failed (${msg.error_status}) — ${CREDENTIAL_HINT}`,
            });
            abortController.abort();
            break;
          } else if (msg.type === "stream_event") {
            if (msg.parent_tool_use_id) continue; // subagent noise
            const event = msg.event;
            if (
              event.type === "content_block_delta" &&
              event.delta.type === "text_delta"
            ) {
              send({ kind: "delta", text: event.delta.text });
            } else if (
              event.type === "content_block_start" &&
              event.content_block.type === "tool_use"
            ) {
              send({ kind: "tool", name: event.content_block.name });
            }
          } else if (msg.type === "result") {
            if (msg.subtype !== "success") {
              send({
                kind: "error",
                message: withCredentialHint(
                  `agent stopped early (${msg.subtype}): ${msg.errors.join("; ") || "unknown error"}`,
                ),
              });
            } else if (msg.is_error) {
              send({
                kind: "error",
                message: withCredentialHint(msg.result),
              });
            }
            send({ kind: "done", sessionId: msg.session_id });
          }
        }
      } catch (err) {
        if (!abortController.signal.aborted) {
          const message = err instanceof Error ? err.message : String(err);
          send({ kind: "error", message: withCredentialHint(message) });
        }
      } finally {
        try {
          controller.close();
        } catch {
          // already closed
        }
      }
    },
    cancel() {
      abortController.abort();
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "application/x-ndjson; charset=utf-8",
      "Cache-Control": "no-store",
    },
  });
}
