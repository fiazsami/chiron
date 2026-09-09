// Server-only: builds Claude Agent SDK query() options for the embedded
// language-calibration coach. Never import from client components.
import path from "node:path";
import type { Options } from "@anthropic-ai/claude-agent-sdk";
import {
  CORPORA_DIR,
  DIMENSIONS,
  type Dimension,
  type ManifestCorpus,
} from "./content";
import { dataPath, getLexicon, getPhrasebook, getRelations } from "./lingua";

// Keep the grounding digest bounded so the system prompt stays lean.
const DIGEST_CAP = 10_000;

function firstSentence(text: string): string {
  const line = text.split("\n", 1)[0].trim();
  const m = line.match(/^.*?[.!?](?=\s|$)/);
  return m ? m[0] : line;
}

// Digest of the register's extracted data: full slug index, phrasebook
// intents, relation type inventory. Degrades gracefully to bare counts when
// the corpus outgrows the cap.
async function groundingDigest(corpus: ManifestCorpus): Promise<string> {
  const [lexicon, phrasebook, relations] = await Promise.all([
    getLexicon(corpus),
    getPhrasebook(corpus),
    getRelations(corpus),
  ]);
  const termSlugs = Object.keys(lexicon).sort();
  const phraseSlugs = Object.keys(phrasebook).sort();
  const typeCounts = new Map<string, number>();
  for (const e of relations) {
    typeCounts.set(e.type, (typeCounts.get(e.type) ?? 0) + 1);
  }
  const relationLine =
    relations.length === 0
      ? "Relations: none extracted yet."
      : `Relations (${relations.length} edges): ` +
        [...typeCounts.entries()].map(([t, n]) => `${t} ×${n}`).join(", ") +
        ".";

  const attempts: Array<() => string> = [
    // Full: definitions + intents.
    () =>
      [
        `Lexicon (${termSlugs.length} terms):`,
        ...termSlugs.map(
          (s) =>
            `- ${s}: ${lexicon[s].term} (${lexicon[s].kind}) — ${firstSentence(lexicon[s].definition)}`,
        ),
        `Phrasebook (${phraseSlugs.length} phrasings):`,
        ...phraseSlugs.map((s) => `- ${s}: ${phrasebook[s].intent}`),
        relationLine,
      ].join("\n"),
    // Trimmed: slugs only.
    () =>
      [
        `Lexicon (${termSlugs.length} terms): ` + termSlugs.join(", "),
        `Phrasebook (${phraseSlugs.length} phrasings): ` +
          phraseSlugs.join(", "),
        relationLine,
      ].join("\n"),
    // Counts only.
    () =>
      `Extracted so far: ${termSlugs.length} lexicon terms, ` +
      `${phraseSlugs.length} phrasings, ${relations.length} relation edges. ` +
      `Read the data files below for the details.`,
  ];
  for (const attempt of attempts) {
    const digest = attempt();
    if (digest.length <= DIGEST_CAP) return digest;
  }
  return attempts[attempts.length - 1]();
}

function liveFileIndex(corpus: ManifestCorpus): string {
  const lines = DIMENSIONS.map((d: Dimension) => {
    const p = dataPath(corpus, d);
    return `- ${d} data: ${p ?? "(mode not tracked by this register)"}`;
  });
  lines.push(
    `- rendered pages: ${path.join(CORPORA_DIR, corpus.name, corpus.register, "pages")}/`,
    `- corpus source: ${path.join(CORPORA_DIR, corpus.name, "source")}/`,
  );
  return lines.join("\n");
}

async function coachSystemPrompt(corpus: ManifestCorpus): Promise<string> {
  const digest = await groundingDigest(corpus);
  return `You are the language-calibration coach for the corpus "${corpus.title}" (${corpus.name}/${corpus.register}). The learner is training to articulate ideas and instruct AI agents in this corpus's own terms — your job is to tighten the fit between what they say and what the corpus actually calls things.

Hard rule: whenever the learner uses an alien or approximate term for something this corpus names, name the corpus's canonical term and cite an anchor (chapter id, and file path when you have one) showing where the corpus uses it.

What you do:
- Answer "what is X called here": map the learner's wording to the corpus's term, with its definition and grounding.
- Critique and rewrite learner-drafted instructions into canonical phrasing, explaining each substitution (what was replaced, with which term or phrasing, and why).
- Quiz the learner's articulation: pose small "say this in the corpus's terms" exercises and grade the answers against the lexicon and phrasebook, citing anchors.
- Explain relation chains: given two terms, walk the typed relation edges connecting them and gloss each hop.

Evidence discipline:
- Read or Grep the corpus files (data YAMLs, pages, source) before asserting what the corpus says; do not answer from memory alone.
- Cite chapter ids (like "${corpus.groups[0]?.id ?? "group"}/01") and file paths for every claim about the corpus.
- Never present a term as belonging to this corpus unless it appears in the lexicon; if the learner needs a word the lexicon lacks, say explicitly that it is absent from the extracted lexicon.

Keep replies compact and conversational — this is a chat panel, not a report.

## Grounding digest (from the register's extracted data files)
${digest}

## Live files (read these for full definitions, templates, anchors)
${liveFileIndex(corpus)}`;
}

export interface AgentQueryConfig {
  abortController: AbortController;
  resume?: string;
}

// Verified against the installed SDK's sdk.d.ts (v0.3.266): all option names
// below exist on Options. Read is path-scoped to CORPORA_DIR via a permission
// rule in allowedTools; permissionMode "dontAsk" denies anything not
// pre-approved, and the tools base set + disallowedTools keep the session
// read-only either way.
export async function buildAgentOptions(
  corpus: ManifestCorpus,
  { abortController, resume }: AgentQueryConfig,
): Promise<Options> {
  const systemPrompt = await coachSystemPrompt(corpus);
  return {
    cwd: CORPORA_DIR,
    systemPrompt,
    tools: ["Read", "Grep", "Glob"],
    allowedTools: [`Read(/${CORPORA_DIR}/**)`, "Grep", "Glob"],
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
    maxTurns: 16,
    includePartialMessages: true,
    abortController,
    ...(process.env.CHIRON_AGENT_MODEL
      ? { model: process.env.CHIRON_AGENT_MODEL }
      : {}),
    ...(resume ? { resume } : {}),
  };
}
