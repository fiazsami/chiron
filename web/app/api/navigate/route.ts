import { NextRequest } from "next/server";
import { query } from "@anthropic-ai/claude-agent-sdk";
import { findCorpus, getManifest } from "@/lib/content";
import {
  CREDENTIAL_HINT,
  buildNavigatorOptions,
  loadNavigatorContext,
  parseNavigatorOutput,
  parseResultText,
  resolveDestinations,
  withCredentialHint,
} from "@/lib/navigator";
import type { NavigateRequest } from "@/lib/navigator-types";

export const dynamic = "force-dynamic";

// One model round-trip should answer in a few seconds; anything past this is
// a hang, not a slow answer.
const DEADLINE_MS = 30_000;

const SELECTION_MAX = 500;
const CONTEXT_MAX = 1_000;

function badRequest(message: string): Response {
  return Response.json({ error: message }, { status: 400 });
}

export async function POST(req: NextRequest): Promise<Response> {
  let body: NavigateRequest;
  try {
    body = (await req.json()) as NavigateRequest;
  } catch {
    return badRequest("request body must be JSON");
  }
  const { corpus: name, register } = body;
  if (
    typeof name !== "string" ||
    typeof register !== "string" ||
    typeof body.selection !== "string" ||
    !body.selection.trim()
  ) {
    return badRequest("corpus, register, and a non-empty selection are required");
  }
  if (body.context !== undefined && typeof body.context !== "string") {
    return badRequest("context must be a string");
  }
  if (body.pathname !== undefined && typeof body.pathname !== "string") {
    return badRequest("pathname must be a string");
  }
  const request: NavigateRequest = {
    corpus: name,
    register,
    selection: body.selection.trim().slice(0, SELECTION_MAX),
    context: body.context?.slice(0, CONTEXT_MAX),
    pathname: body.pathname,
  };

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

  const ctx = await loadNavigatorContext(manifest, corpus);
  const abortController = new AbortController();
  req.signal.addEventListener("abort", () => abortController.abort());
  const deadline = setTimeout(() => abortController.abort(), DEADLINE_MS);

  try {
    const options = buildNavigatorOptions(ctx, request, abortController);
    let structured: unknown = null;
    let failure: string | null = null;
    for await (const msg of query({
      prompt: "Find destinations for the selection.",
      options,
    })) {
      if (
        msg.type === "system" &&
        msg.subtype === "api_retry" &&
        (msg.error_status === 401 || msg.error_status === 403)
      ) {
        // Bad/missing credentials: the CLI would retry ~10 times with
        // exponential backoff. Fail fast instead of hanging the popup.
        abortController.abort();
        return Response.json(
          {
            error: `authentication failed (${msg.error_status}) — ${CREDENTIAL_HINT}`,
          },
          { status: 503 },
        );
      }
      if (msg.type === "result") {
        if (msg.subtype !== "success") {
          failure = `navigator stopped early (${msg.subtype}): ${msg.errors.join("; ") || "unknown error"}`;
        } else if (msg.is_error) {
          failure = msg.result;
        } else {
          structured = msg.structured_output ?? parseResultText(msg.result);
        }
      }
    }
    if (failure) {
      return Response.json(
        { error: withCredentialHint(failure) },
        { status: 500 },
      );
    }
    const raw = parseNavigatorOutput(structured);
    if (!raw) {
      return Response.json(
        { error: "navigator returned no parseable results" },
        { status: 500 },
      );
    }
    const results = resolveDestinations(ctx, raw, request.pathname);
    return Response.json(
      { results },
      { headers: { "Cache-Control": "no-store" } },
    );
  } catch (err) {
    if (abortController.signal.aborted) {
      return Response.json({ error: "navigator timed out" }, { status: 504 });
    }
    const message = err instanceof Error ? err.message : String(err);
    return Response.json(
      { error: withCredentialHint(message) },
      { status: 500 },
    );
  } finally {
    clearTimeout(deadline);
  }
}
