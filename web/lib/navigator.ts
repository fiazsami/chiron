// Server-only: the smart navigator's LLM call. Builds Claude Agent SDK
// query() options that ask for 0–6 destinations picked from a closed
// candidate index, then resolves the model's ids against the manifest and
// data files so only pages that actually exist ever reach the client.
// Never import from client components.

import { execFile } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import type { Options } from "@anthropic-ai/claude-agent-sdk";
import {
  CORPORA_DIR,
  chapterByLocalId,
  chapterHref,
  type Manifest,
  type ManifestChapter,
  type ManifestCorpus,
} from "./content";
import {
  getLexicon,
  getPhrasebook,
  getRelations,
  type Lexicon,
  type Phrasebook,
  type RelationEdge,
} from "./lingua";
import {
  destinationKey,
  type BitAnchor,
  type BitDestination,
  type BitKind,
  type Destination,
  type NavigateRequest,
  type PhraseBit,
  type RelationsBit,
  type TermBit,
} from "./navigator-types";
import type { Anchor, LexiconEntry, Phrase } from "./lingua";

export const CREDENTIAL_HINT =
  "set ANTHROPIC_API_KEY in web/.env.local or run `claude /login`";

export function withCredentialHint(message: string): string {
  // Missing/invalid credentials surface as auth errors from the API or as
  // the CLI process dying at startup — attach the fix in both cases.
  if (/api.?key|log.?in|auth|credential|billing|credit|exited with/i.test(message)) {
    return `${message} — ${CREDENTIAL_HINT}`;
  }
  return message;
}

// Everything one navigate call needs, loaded once per request.
export interface NavigatorContext {
  manifest: Manifest;
  corpus: ManifestCorpus;
  chapters: ManifestChapter[];
  lexicon: Lexicon;
  phrasebook: Phrasebook;
  edges: RelationEdge[];
}

export async function loadNavigatorContext(
  manifest: Manifest,
  corpus: ManifestCorpus,
): Promise<NavigatorContext> {
  const [lexicon, phrasebook, edges] = await Promise.all([
    getLexicon(corpus),
    getPhrasebook(corpus),
    getRelations(corpus),
  ]);
  const chapters = manifest.chapters.filter(
    (c) => c.corpus === corpus.name && c.register === corpus.register,
  );
  return { manifest, corpus, chapters, lexicon, phrasebook, edges };
}

// ---------------------------------------------------------- chroma bridge

// Retrieval hit from the register's chroma store (tools/lingua/chroma.py).
export interface RetrievedBit {
  id: string;
  document: string;
  metadata: Record<string, string>;
  distance: number;
}

const REPO_ROOT = path.dirname(CORPORA_DIR);
const RETRIEVE_N = 12; // results cap at 6 after dedupe/membership drops
const BRIDGE_TIMEOUT_MS = 20_000;

// Query the register's persistent chroma store via a short-lived Python
// bridge (an embedded store has no wire protocol for Node). Resolves null
// on any failure — no store yet, bridge error, bad JSON — and the caller
// falls back to the full candidate index, so retrieval is never load-bearing.
export function queryChroma(
  corpus: ManifestCorpus,
  text: string,
  n = RETRIEVE_N,
): Promise<RetrievedBit[] | null> {
  const chromaDir = path.join(
    CORPORA_DIR,
    corpus.name,
    corpus.register,
    "chroma",
  );
  if (!existsSync(path.join(chromaDir, "chroma.sqlite3"))) {
    return Promise.resolve(null);
  }
  return new Promise((resolve) => {
    const child = execFile(
      "uv",
      ["run", "python", "-m", "tools.lingua.chroma", "query", chromaDir, String(n)],
      { cwd: REPO_ROOT, timeout: BRIDGE_TIMEOUT_MS, maxBuffer: 4 * 1024 * 1024 },
      (err, stdout) => {
        if (err) {
          console.warn(`navigator: chroma bridge failed (${err.message})`);
          resolve(null);
          return;
        }
        try {
          const parsed = JSON.parse(stdout) as unknown;
          resolve(Array.isArray(parsed) ? (parsed as RetrievedBit[]) : null);
        } catch {
          resolve(null);
        }
      },
    );
    child.stdin?.write(text);
    child.stdin?.end();
  });
}

// Keep the candidate index bounded so the prompt stays one fast call; detail
// degrades before membership ever does — the closed set holds at any size.
// Retained as the fallback when a register has no chroma store yet.
const INDEX_CAP = 24_000;

function firstSentence(text: string): string {
  const line = text.split("\n", 1)[0].trim();
  const m = line.match(/^.*?[.!?](?=\s|$)/);
  return m ? m[0] : line;
}

function truncate(text: string, max: number): string {
  return text.length <= max ? text : `${text.slice(0, max - 1)}…`;
}

function candidateIndex(ctx: NavigatorContext): string {
  const chapterLines = ctx.chapters.map(
    (c) => `- ${c.group}/${c.number}: ${c.title}`,
  );
  const termSlugs = Object.keys(ctx.lexicon).sort();
  const phraseSlugs = Object.keys(ctx.phrasebook).sort();
  const typeCounts = new Map<string, number>();
  for (const e of ctx.edges) {
    typeCounts.set(e.type, (typeCounts.get(e.type) ?? 0) + 1);
  }
  const relationLine =
    typeCounts.size === 0
      ? "(none extracted)"
      : [...typeCounts.entries()].map(([t, n]) => `${t} ×${n}`).join(", ");

  const assemble = (
    termLine: (s: string) => string,
    phraseLine: (s: string) => string,
  ) =>
    [
      `### Chapters (${ctx.chapters.length})`,
      ...chapterLines,
      `### Terms (${termSlugs.length})`,
      ...termSlugs.map(termLine),
      `### Phrases (${phraseSlugs.length})`,
      ...phraseSlugs.map(phraseLine),
      "### Relation types",
      relationLine,
    ].join("\n");

  const attempts: Array<() => string> = [
    () =>
      assemble(
        (s) =>
          `- ${s}: ${ctx.lexicon[s].term} (${ctx.lexicon[s].kind}) — ${firstSentence(ctx.lexicon[s].definition)}`,
        (s) => `- ${s}: ${ctx.phrasebook[s].phrase}`,
      ),
    () =>
      assemble(
        (s) => `- ${s}: ${ctx.lexicon[s].term} (${ctx.lexicon[s].kind})`,
        (s) => `- ${s}: ${truncate(ctx.phrasebook[s].phrase, 60)}`,
      ),
    () => assemble((s) => `- ${s}`, (s) => `- ${s}`),
  ];
  for (const attempt of attempts) {
    const index = attempt();
    if (index.length <= INDEX_CAP) return index;
  }
  return attempts[attempts.length - 1]();
}

function safeDecode(pathname: string): string {
  try {
    return decodeURIComponent(pathname);
  } catch {
    return pathname;
  }
}

function locationBlock(ctx: NavigatorContext, pathname?: string): string {
  if (!pathname) return "";
  const decoded = safeDecode(pathname);
  const chapter = ctx.chapters.find((c) => {
    const href = chapterHref(c);
    return href === decoded || href === pathname;
  });
  if (!chapter) return "";
  const parts = [`${chapter.group}/${chapter.number}: ${chapter.title}.`];
  if (chapter.terms_defined?.length) {
    parts.push(`Terms defined here: ${chapter.terms_defined.join(", ")}.`);
  }
  if (chapter.terms_mentioned?.length) {
    parts.push(`Terms mentioned: ${chapter.terms_mentioned.join(", ")}.`);
  }
  if (chapter.phrases?.length) {
    parts.push(`Phrasings grounded here: ${chapter.phrases.join(", ")}.`);
  }
  return `\n## Where they are reading\n${parts.join(" ")}\n`;
}

function navigatorSystemPrompt(
  ctx: NavigatorContext,
  req: NavigateRequest,
): string {
  const { corpus } = ctx;
  const chapterExample = ctx.chapters[0]
    ? `${ctx.chapters[0].group}/${ctx.chapters[0].number}`
    : "group/01";
  return `You are the smart navigator for the corpus "${corpus.title}" (${corpus.name}/${corpus.register}). The learner selected a passage while reading and wants the most relevant pages in this viewer to follow next.

Choose ONLY from the candidate index below. Return 0 to 6 destinations, best first. Every id must be copied verbatim — never invent one. If nothing is genuinely relevant, return an empty results list.

Kinds and id formats:
- "chapter": register-local chapter id, e.g. "${chapterExample}"
- "term": lexicon slug
- "phrase": phrasebook slug
- "relations": a relation type

Ranking guidance: the term a selected word names, then the chapter that defines or develops it, then phrasings that teach the selected wording, then a relation type only when the selection is about how concepts connect. Each reason: one clause, learner-facing, grounded in the selection.

## Learner's selection
"${req.selection}"
${req.context ? `\n## Surrounding paragraph\n${req.context}\n` : ""}${locationBlock(ctx, req.pathname)}
## Candidate index
${candidateIndex(ctx)}`;
}

// Structure only — no maxItems/maxLength/pattern/format, which the
// structured-outputs schema subset rejects (see tools/lingua, commit
// 4e0ba8d). Caps are enforced server-side in resolveDestinations.
const NAVIGATE_SCHEMA = {
  type: "object",
  additionalProperties: false,
  required: ["results"],
  properties: {
    results: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        required: ["kind", "id", "reason"],
        properties: {
          kind: {
            type: "string",
            enum: ["chapter", "term", "phrase", "relations"],
          },
          id: { type: "string" },
          reason: { type: "string" },
        },
      },
    },
  },
};

// No tools: one model round-trip over the candidate index is the latency
// budget. maxTurns 2 leaves one spare turn for a structured-output retry.
export function buildNavigatorOptions(
  ctx: NavigatorContext,
  req: NavigateRequest,
  abortController: AbortController,
): Options {
  const model =
    process.env.CHIRON_NAVIGATOR_MODEL ?? process.env.CHIRON_AGENT_MODEL;
  return {
    cwd: CORPORA_DIR,
    systemPrompt: navigatorSystemPrompt(ctx, req),
    tools: [],
    disallowedTools: [
      "Bash",
      "Write",
      "Edit",
      "NotebookEdit",
      "WebFetch",
      "WebSearch",
      "Task",
      "TodoWrite",
      "KillShell",
      "BashOutput",
      "ExitPlanMode",
    ],
    permissionMode: "dontAsk",
    settingSources: [],
    maxTurns: 2,
    abortController,
    outputFormat: { type: "json_schema", schema: NAVIGATE_SCHEMA },
    ...(model ? { model } : {}),
  };
}

interface RawResult {
  kind: string;
  id: string;
  reason: string;
}

// Defensive shape check over the SDK's `structured_output: unknown`.
export function parseNavigatorOutput(value: unknown): RawResult[] | null {
  if (!value || typeof value !== "object") return null;
  const results = (value as { results?: unknown }).results;
  if (!Array.isArray(results)) return null;
  const out: RawResult[] = [];
  for (const r of results) {
    if (!r || typeof r !== "object") continue;
    const { kind, id, reason } = r as Record<string, unknown>;
    if (typeof kind !== "string" || typeof id !== "string") continue;
    out.push({ kind, id, reason: typeof reason === "string" ? reason : "" });
  }
  return out;
}

// Fallback when structured output is absent: pull the outermost JSON object
// out of the result text.
export function parseResultText(text: string): unknown {
  const start = text.indexOf("{");
  const end = text.lastIndexOf("}");
  if (start < 0 || end <= start) return null;
  try {
    return JSON.parse(text.slice(start, end + 1));
  } catch {
    return null;
  }
}

const MAX_RESULTS = 6;
const DETAIL_MAX = 160;

// Bounds for the inline flashcard payloads the modal renders. Assimilation
// view, not a reference dump — totals carry the real counts.
const BIT_ANCHOR_CAP = 3;
const BIT_EDGE_CAP = 12;
const BIT_PHRASING_CAP = 8;
const BIT_RELATION_CAP = 10;
const BIT_QUOTE_MAX = 240;
const BIT_GLOSS_MAX = 160;

function anchorBits(ctx: NavigatorContext, anchors: Anchor[]): BitAnchor[] {
  const { name, register } = ctx.corpus;
  return anchors.slice(0, BIT_ANCHOR_CAP).map((a) => {
    const chapter = chapterByLocalId(ctx.manifest, name, register, a.chapter);
    return {
      chapter: a.chapter,
      ...(chapter
        ? { chapterTitle: chapter.title, chapterHref: chapterHref(chapter) }
        : {}),
      quote: truncate(a.quote, BIT_QUOTE_MAX),
    };
  });
}

function termBit(
  ctx: NavigatorContext,
  slug: string,
  entry: LexiconEntry,
): TermBit {
  const { name, register } = ctx.corpus;
  const termName = (s: string) => ctx.lexicon[s]?.term ?? s;
  const defined = chapterByLocalId(
    ctx.manifest, name, register, entry.defined_in,
  );
  const phrasings = Object.entries(ctx.phrasebook).filter(([, p]) =>
    p.terms.includes(slug),
  );
  const related = [
    ...ctx.edges
      .filter((e) => e.from === slug)
      .map((e) => ({
        dir: "out" as const,
        type: e.type as string,
        other: { id: e.to, name: termName(e.to) },
        gloss: truncate(e.gloss, BIT_GLOSS_MAX),
      })),
    ...ctx.edges
      .filter((e) => e.to === slug)
      .map((e) => ({
        dir: "in" as const,
        type: e.type as string,
        other: { id: e.from, name: termName(e.from) },
        gloss: truncate(e.gloss, BIT_GLOSS_MAX),
      })),
  ];
  return {
    kind: "term",
    termKind: entry.kind,
    definition: entry.definition,
    ...(entry.aliases?.length ? { aliases: entry.aliases } : {}),
    ...(defined
      ? {
          definedIn: {
            title: `${defined.number} ${defined.title}`,
            href: chapterHref(defined),
          },
        }
      : {}),
    anchors: anchorBits(ctx, entry.anchors),
    totalAnchors: entry.anchors.length,
    phrasings: phrasings
      .slice(0, BIT_PHRASING_CAP)
      .map(([id, p]) => ({
        id,
        phrase: p.phrase,
        intent: truncate(p.intent, BIT_GLOSS_MAX),
      })),
    morePhrasings: Math.max(0, phrasings.length - BIT_PHRASING_CAP),
    relations: related.slice(0, BIT_RELATION_CAP),
    moreRelations: Math.max(0, related.length - BIT_RELATION_CAP),
  };
}

function phraseBit(ctx: NavigatorContext, phrase: Phrase): PhraseBit {
  return {
    kind: "phrase",
    phrase: phrase.phrase,
    intent: phrase.intent,
    ...(phrase.template ? { template: phrase.template } : {}),
    terms: phrase.terms.map((s) => ({
      id: s,
      name: ctx.lexicon[s]?.term ?? s,
    })),
    anchors: anchorBits(ctx, phrase.anchors),
    totalAnchors: phrase.anchors.length,
  };
}

function relationsBit(ctx: NavigatorContext, type: string): RelationsBit {
  const termName = (s: string) => ctx.lexicon[s]?.term ?? s;
  const typed = ctx.edges.filter((e) => e.type === type);
  return {
    kind: "relations",
    edges: typed.slice(0, BIT_EDGE_CAP).map((e) => ({
      from: { id: e.from, name: termName(e.from) },
      to: { id: e.to, name: termName(e.to) },
      gloss: truncate(e.gloss, BIT_GLOSS_MAX),
    })),
    more: Math.max(0, typed.length - BIT_EDGE_CAP),
  };
}

// The one bit-to-flashcard entry point, shared by resolveDestinations and
// POST /api/bit. Null when the id doesn't resolve against the data files.
export function buildBitDestination(
  ctx: NavigatorContext,
  kind: BitKind,
  id: string,
  reason = "",
): BitDestination | null {
  if (kind === "term") {
    const entry = ctx.lexicon[id];
    if (!entry) return null;
    return {
      kind: "term",
      id,
      title: entry.term,
      detail: truncate(reason, DETAIL_MAX),
      bit: termBit(ctx, id, entry),
    };
  }
  if (kind === "phrase") {
    const phrase = ctx.phrasebook[id];
    if (!phrase) return null;
    return {
      kind: "phrase",
      id,
      title: truncate(phrase.phrase, 80),
      detail: truncate(reason, DETAIL_MAX),
      bit: phraseBit(ctx, phrase),
    };
  }
  const bit = relationsBit(ctx, id);
  if (bit.edges.length === 0) return null;
  return {
    kind: "relations",
    id,
    title: `relations: ${id}`,
    detail: truncate(reason, DETAIL_MAX),
    bit,
  };
}

// The retrieval-only fast path: chroma hits become the answer directly —
// no LLM round-trip. Detail lines come from the data files (definition,
// intent, gloss), and the top term's defining chapter is suggested right
// after it, mirroring what the model used to do. Output feeds
// resolveDestinations, so the membership firewall still applies (a store
// mid-rebuild can hold bits the YAML no longer has).
export function retrievedToRaw(
  ctx: NavigatorContext,
  bits: RetrievedBit[],
): { kind: string; id: string; reason: string }[] {
  const out: { kind: string; id: string; reason: string }[] = [];
  let chapterSuggested = false;
  for (const bit of bits) {
    const m = bit.metadata;
    if (m.kind === "term") {
      const entry = ctx.lexicon[m.slug];
      if (!entry) continue;
      out.push({
        kind: "term",
        id: m.slug,
        reason: firstSentence(entry.definition),
      });
      if (!chapterSuggested && entry.defined_in) {
        out.push({
          kind: "chapter",
          id: entry.defined_in,
          reason: `defines ${entry.term}`,
        });
        chapterSuggested = true;
      }
    } else if (m.kind === "phrase") {
      const phrase = ctx.phrasebook[m.slug];
      if (!phrase) continue;
      out.push({ kind: "phrase", id: m.slug, reason: phrase.intent });
    } else if (m.kind === "relation") {
      const edge = ctx.edges.find(
        (e) => e.from === m.from && e.to === m.to && e.type === m.type,
      );
      if (!edge) continue;
      out.push({ kind: "relations", id: m.type, reason: edge.gloss });
    }
  }
  return out;
}

// The hallucination firewall: every id must resolve against the manifest or
// data files or the result is silently dropped. Model order is the ranking.
export function resolveDestinations(
  ctx: NavigatorContext,
  raw: RawResult[],
  pathname?: string,
): Destination[] {
  const { name, register } = ctx.corpus;
  const decodedPath = pathname ? safeDecode(pathname) : null;
  const seen = new Set<string>();
  const out: Destination[] = [];
  for (const r of raw) {
    let dest: Destination | null = null;
    if (r.kind === "chapter") {
      const ch = chapterByLocalId(ctx.manifest, name, register, r.id);
      if (ch) {
        dest = {
          kind: "chapter",
          href: chapterHref(ch),
          title: `${ch.number} ${ch.title}`,
          detail: truncate(r.reason, DETAIL_MAX),
        };
      }
    } else if (
      r.kind === "term" ||
      r.kind === "phrase" ||
      r.kind === "relations"
    ) {
      dest = buildBitDestination(ctx, r.kind, r.id, r.reason);
    }
    if (!dest) continue;
    if (
      dest.kind === "chapter" &&
      decodedPath &&
      (dest.href === decodedPath || dest.href === pathname)
    ) {
      continue; // never suggest the page they're on
    }
    const key = destinationKey(dest);
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(dest);
    if (out.length === MAX_RESULTS) break;
  }
  return out;
}
