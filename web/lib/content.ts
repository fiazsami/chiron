import fs from "node:fs/promises";
import path from "node:path";
import { type Dimension, type DimensionState } from "./dimensions";

// Dimension types/constants live in lib/dimensions.ts (client-safe); this
// module re-exports them so server code keeps a single import site.
export * from "./dimensions";

// The reference room of the development environment, beside web/ at the repo
// root; each corpus register keeps its generated pages under
// devenv/reference/<name>/<vN>/pages/ and its extracted linguistic structure
// under devenv/reference/<name>/<vN>/data/. This path and chiron.yaml's
// devenv.reference change in lockstep — see the contracts list in AGENTS.md.
// CHIRON_REFERENCE_DIR (web/.env.local) overrides it, e.g. for a moved root.
export const REFERENCE_DIR = path.resolve(
  process.cwd(),
  process.env.CHIRON_REFERENCE_DIR ?? "../devenv/reference",
);

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
  page: string; // reference-room-relative Markdown page path
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
    raw = await fs.readFile(path.join(REFERENCE_DIR, ".manifest.json"), "utf8");
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
