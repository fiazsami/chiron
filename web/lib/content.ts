import fs from "node:fs/promises";
import path from "node:path";
import matter from "gray-matter";

// Mounted corpora live beside web/ at the repo root; each corpus register
// keeps its generated pages under corpora/<name>/<vN>/pages/ and its
// extracted linguistic structure under corpora/<name>/<vN>/data/.
export const CORPORA_DIR = path.resolve(process.cwd(), "../corpora");

// The three shipped linguistic dimensions. "concept-relations" is the
// manifest/data/pages/states KEY; its data file is relations.yaml and its
// viewer route segment is /relations.
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
  keyof ManifestCorpus["totals"]
> = {
  lexicon: "terms",
  phrasebook: "phrases",
  "concept-relations": "relations",
};

export interface ManifestGroup {
  id: string;
  label: string;
}

// One manifest corpus entry per (corpus, register) pair. data/pages/totals
// only carry keys for the register's tracked modes.
export interface ManifestCorpus {
  name: string;
  register: string; // "v1"
  label: string | null; // one-line description of this retelling
  title: string;
  checkout: string; // git short SHA of source/ (or a content digest)
  urls: Record<string, string>;
  source_kind: "markdown" | "code" | "custom";
  modes: Dimension[]; // tracked dimension slugs, registry order
  recorded_modes: string[]; // modes without shipped machinery
  groups: ManifestGroup[];
  data: Partial<Record<Dimension, { state: DimensionState; path: string }>>;
  pages: { index: string } & Partial<Record<Dimension, string>>;
  totals: { terms?: number; phrases?: number; relations?: number };
}

export interface ManifestChapter {
  id: string; // "<corpus>/<vN>/<group>/<NN>"
  corpus: string;
  register: string;
  group: string;
  number: string;
  slug: string;
  title: string;
  kind: "doc" | "code";
  content_hash: string;
  page: string; // corpora-relative Markdown page path
  source_paths: string[]; // corpus-source-relative unit files
  states: Partial<Record<Dimension, DimensionState>>;
  // Present only when the matching mode is tracked by the register.
  terms_defined?: string[];
  terms_mentioned?: string[];
  phrases?: string[];
  edges?: number;
}

export interface Manifest {
  version: number;
  corpora: ManifestCorpus[];
  chapters: ManifestChapter[];
}

export async function getManifest(): Promise<Manifest> {
  let raw: string;
  try {
    raw = await fs.readFile(path.join(CORPORA_DIR, ".manifest.json"), "utf8");
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") {
      // No corpora mounted (or never built) — the empty state, not an error.
      return { version: 6, corpora: [], chapters: [] };
    }
    throw err;
  }
  const manifest = JSON.parse(raw) as Manifest;
  if (manifest.version !== 6) {
    throw new Error(
      `unsupported manifest version ${manifest.version ?? 1}; ` +
        "regenerate with `uv run python -m tools.lingua`",
    );
  }
  return manifest;
}

export function findCorpus(
  manifest: Manifest,
  name: string,
  register: string,
): ManifestCorpus | undefined {
  return manifest.corpora.find(
    (c) => c.name === name && c.register === register,
  );
}

// "41 terms · 12 phrases · 19 relations" — only tracked dimensions appear.
export function totalsLine(corpus: ManifestCorpus): string {
  return DIMENSIONS.filter((d) => d in corpus.data)
    .map((d) => {
      const key = DIMENSION_COUNT_KEYS[d];
      return `${corpus.totals[key] ?? 0} ${key}`;
    })
    .join(" · ");
}

// Resolve a register-local chapter id ("<group>/<NN>") — the key used by
// anchors and defined_in — back to its manifest entry.
export function chapterByLocalId(
  manifest: Manifest,
  corpus: string,
  register: string,
  localId: string,
): ManifestChapter | undefined {
  return manifest.chapters.find(
    (c) =>
      c.corpus === corpus &&
      c.register === register &&
      `${c.group}/${c.number}` === localId,
  );
}

export function chapterHref(chapter: ManifestChapter): string {
  return `/${chapter.corpus}/${chapter.register}/${chapter.group}/${chapter.slug}`;
}

// Accent colors cycle by the group's position within its corpus, so any
// number of corpora/groups gets a stable color without per-name CSS.
export const ACCENT_COUNT = 5;

export function accentClass(
  manifest: Manifest,
  corpus: string,
  register: string,
  group: string,
): string {
  const s = findCorpus(manifest, corpus, register);
  const i = s?.groups.findIndex((g) => g.id === group) ?? -1;
  return `accent-${i >= 0 ? i % ACCENT_COUNT : 0}`;
}

export interface Chapter {
  frontmatter: Record<string, unknown>;
  body: string;
}

export async function getChapter(entry: ManifestChapter): Promise<Chapter> {
  const raw = await fs.readFile(path.join(CORPORA_DIR, entry.page), "utf8");
  const { data, content } = matter(raw);
  return { frontmatter: data, body: content };
}
