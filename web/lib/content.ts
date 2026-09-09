import fs from "node:fs/promises";
import path from "node:path";
import matter from "gray-matter";

// Mounted corpora live beside web/ at the repo root; each corpus register
// keeps its generated pages under corpora/<name>/<vN>/notes/.
export const CORPORA_DIR = path.resolve(process.cwd(), "../corpora");

export interface ManifestGroup {
  id: string;
  label: string;
}

// One manifest corpus entry per (corpus, register) pair.
export interface ManifestCorpus {
  name: string;
  register: string; // "v1"
  label: string | null; // one-line description of this retelling
  title: string;
  checkout: string; // git short SHA of the shared source/ checkout
  urls: Record<string, string>;
  has_labs: boolean;
  modes: string[]; // translation mode slugs
  groups: ManifestGroup[];
}

export interface ManifestChapter {
  id: string;
  corpus: string;
  register: string;
  group: string;
  slug: string;
  title: string;
  lab: string | null;
  components: string[];
  content_hash: string;
  content: { schematic: string; facts: string };
  page: string;
  svgs: string[];
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
      return { version: 5, corpora: [], chapters: [] };
    }
    throw err;
  }
  const manifest = JSON.parse(raw) as Manifest;
  if (manifest.version !== 5) {
    throw new Error(
      `unsupported manifest version ${manifest.version ?? 1}; ` +
        "regenerate with `uv run python -m tools.notes`",
    );
  }
  return manifest;
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
  const s = manifest.corpora.find(
    (x) => x.name === corpus && x.register === register,
  );
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
