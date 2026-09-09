// Server-only: the smart navigator's LLM call. Builds Claude Agent SDK
// query() options that ask for 0–6 destinations picked from a closed
// candidate index, then resolves the model's ids against the manifest and
// data files so only pages that actually exist ever reach the client.
// Never import from client components.

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
import type { Destination, NavigateRequest } from "./navigator-types";

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

// Keep the candidate index bounded so the prompt stays one fast call; detail
// degrades before membership ever does — the closed set holds at any size.
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
  return `You are the smart navigator for the corpus "${corpus.title}" (${corpus.name}/${corpus.register}). The learner selected a passage while reading and wants the most relevant pages in this viewer to follow next.

Choose ONLY from the candidate index below. Return 0 to 6 destinations, best first. Every id must be copied verbatim from the index — never invent one. If nothing is genuinely relevant, return an empty results list.

Kinds and id formats:
- "chapter": register-local chapter id, e.g. "${ctx.chapters[0] ? `${ctx.chapters[0].group}/${ctx.chapters[0].number}` : "group/01"}"
- "term": lexicon slug
- "phrase": phrasebook slug
- "relations": a relation type from the inventory

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
          href: chapterHref(ch),
          title: `${ch.number} ${ch.title}`,
          kind: "chapter",
          detail: truncate(r.reason, DETAIL_MAX),
        };
      }
    } else if (r.kind === "term") {
      const entry = ctx.lexicon[r.id];
      if (entry) {
        dest = {
          href: `/${name}/${register}/lexicon/${r.id}`,
          title: entry.term,
          kind: "term",
          detail: truncate(r.reason, DETAIL_MAX),
        };
      }
    } else if (r.kind === "phrase") {
      const phrase = ctx.phrasebook[r.id];
      if (phrase) {
        dest = {
          href: `/${name}/${register}/phrasebook#${r.id}`,
          title: truncate(phrase.phrase, 80),
          kind: "phrase",
          detail: truncate(r.reason, DETAIL_MAX),
        };
      }
    } else if (r.kind === "relations") {
      if (ctx.edges.some((e) => e.type === r.id)) {
        dest = {
          href: `/${name}/${register}/relations#${r.id}`,
          title: `relations: ${r.id}`,
          kind: "relations",
          detail: truncate(r.reason, DETAIL_MAX),
        };
      }
    }
    if (!dest) continue;
    if (decodedPath && (dest.href === decodedPath || dest.href === pathname)) {
      continue; // never suggest the page they're on
    }
    if (seen.has(dest.href)) continue;
    seen.add(dest.href);
    out.push(dest);
    if (out.length === MAX_RESULTS) break;
  }
  return out;
}
