import { NextRequest } from "next/server";
import { findCorpus, getManifest } from "@/lib/content";
import { buildBitDestination, loadNavigatorContext } from "@/lib/navigator";
import type { BitRequest } from "@/lib/navigator-types";

export const dynamic = "force-dynamic";

const BIT_KINDS = new Set(["term", "phrase", "relations"]);

function badRequest(message: string): Response {
  return Response.json({ error: message }, { status: 400 });
}

// One bit's full flashcard — the modal's dive and direct-entry fetch. Pure
// YAML reads: no LLM, no chroma.
export async function POST(req: NextRequest): Promise<Response> {
  let body: BitRequest;
  try {
    body = (await req.json()) as BitRequest;
  } catch {
    return badRequest("request body must be JSON");
  }
  const { corpus: name, register, kind, id } = body;
  if (
    typeof name !== "string" ||
    typeof register !== "string" ||
    typeof id !== "string" ||
    !id.trim() ||
    !BIT_KINDS.has(kind)
  ) {
    return badRequest(
      "corpus, register, a bit kind (term|phrase|relations), and an id are required",
    );
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

  const ctx = await loadNavigatorContext(manifest, corpus);
  const destination = buildBitDestination(ctx, kind, id);
  if (!destination) {
    return Response.json(
      { error: `unknown ${kind} "${id}" in ${name}/${register}` },
      { status: 404 },
    );
  }
  return Response.json(
    { destination },
    { headers: { "Cache-Control": "no-store" } },
  );
}
