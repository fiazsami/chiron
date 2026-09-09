import fs from "node:fs/promises";
import path from "node:path";
import { parse } from "yaml";
import { CORPORA_DIR, type Dimension, type ManifestCorpus } from "./content";

// TS mirrors of the per-register data YAML shapes owned by
// tools/lingua/dimensions/{lexicon,phrasebook,relations}.py. A missing data
// file (or an untracked mode, which has no data key at all) reads as empty.

export interface Anchor {
  chapter: string; // register-local "<group>/<NN>"
  path?: string; // source-relative file; required for code chapters
  quote: string; // verbatim (whitespace-normalized) quote from the source
  curated_against: string; // 12-hex content hash the quote was pinned to
}

export type TermKind =
  | "concept"
  | "name"
  | "identifier"
  | "command"
  | "file"
  | "value";

export interface LexiconEntry {
  term: string;
  kind: TermKind;
  definition: string;
  aliases?: string[];
  defined_in: string; // register-local chapter id
  anchors: Anchor[];
}

export type Lexicon = Record<string, LexiconEntry>;

export interface Phrase {
  phrase: string;
  intent: string;
  template?: string;
  terms: string[]; // lexicon slugs this phrasing leans on
  anchors: Anchor[];
}

export type Phrasebook = Record<string, Phrase>;

export type RelationType =
  | "is-a"
  | "part-of"
  | "uses"
  | "feeds"
  | "configures"
  | "contrasts-with"
  | "implements"
  | "precedes";

export const RELATION_TYPES: RelationType[] = [
  "is-a",
  "part-of",
  "uses",
  "feeds",
  "configures",
  "contrasts-with",
  "implements",
  "precedes",
];

export interface RelationEdge {
  from: string;
  to: string;
  type: RelationType;
  gloss: string;
  anchors: Anchor[];
}

export function dataPath(
  corpus: ManifestCorpus,
  dimension: Dimension,
): string | null {
  const entry = corpus.data[dimension];
  return entry ? path.join(CORPORA_DIR, entry.path) : null;
}

async function readData(
  corpus: ManifestCorpus,
  dimension: Dimension,
): Promise<unknown> {
  const file = dataPath(corpus, dimension);
  if (!file) return null; // mode not tracked by this register
  let raw: string;
  try {
    raw = await fs.readFile(file, "utf8");
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") return null;
    throw err;
  }
  return parse(raw);
}

export async function getLexicon(corpus: ManifestCorpus): Promise<Lexicon> {
  return ((await readData(corpus, "lexicon")) as Lexicon | null) ?? {};
}

export async function getPhrasebook(
  corpus: ManifestCorpus,
): Promise<Phrasebook> {
  return ((await readData(corpus, "phrasebook")) as Phrasebook | null) ?? {};
}

export async function getRelations(
  corpus: ManifestCorpus,
): Promise<RelationEdge[]> {
  const data = (await readData(corpus, "concept-relations")) as {
    edges?: RelationEdge[];
  } | null;
  return data?.edges ?? [];
}
