import fs from "node:fs/promises";
import path from "node:path";
import { parse } from "yaml";
import { REFERENCE_DIR, type Dimension, type ManifestCorpus } from "./content";
import type { Lexicon, Phrasebook, RelationEdge } from "./lingua-types";

// Server-side readers for the per-register data YAMLs. A missing data file
// (or an untracked mode, which has no data key at all) reads as empty. The
// type mirrors live in lingua-types.ts (client-safe) and are re-exported
// here so server modules keep a single import site.

export * from "./lingua-types";

export function dataPath(
  corpus: ManifestCorpus,
  dimension: Dimension,
): string | null {
  const entry = corpus.data[dimension];
  return entry ? path.join(REFERENCE_DIR, entry.path) : null;
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
