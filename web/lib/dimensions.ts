// The three shipped linguistic dimensions and their display/routing
// constants. This module is import-safe from client components (no node
// imports) — lib/content.ts re-exports it for server code, so the manifest
// v6 contract surface is unchanged.

// "concept-relations" is the manifest/data/pages/states KEY; its data file
// is relations.yaml and its viewer route segment is /relations.
export type Dimension = "lexicon" | "phrasebook" | "concept-relations";
export type DimensionState = "ok" | "stale" | "none";

export const DIMENSIONS: Dimension[] = [
  "lexicon",
  "phrasebook",
  "concept-relations",
];

export const DIMENSION_LABELS: Record<Dimension, string> = {
  lexicon: "Lexicon",
  phrasebook: "Phrasebook",
  "concept-relations": "Concept relations",
};

// URL segment under /[corpus]/[register]/ for each dimension's surface.
export const DIMENSION_SEGMENTS: Record<Dimension, string> = {
  lexicon: "lexicon",
  phrasebook: "phrasebook",
  "concept-relations": "relations",
};

// totals key per dimension, in the same order the pipeline reports them.
export const DIMENSION_COUNT_KEYS: Record<
  Dimension,
  "terms" | "phrases" | "relations"
> = {
  lexicon: "terms",
  phrasebook: "phrases",
  "concept-relations": "relations",
};
