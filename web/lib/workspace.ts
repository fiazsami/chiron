// Server-side builder for the reader shell's workspace data: the sidebar
// sections, article-list rows, and term index, all derived from the
// manifest plus each register's lexicon (for term display names).

import {
  DIMENSIONS,
  chapterHref,
  getManifest,
  type Dimension,
  type DimensionState,
} from "./content";
import { getLexicon } from "./lingua";
import type {
  WorkspaceChapter,
  WorkspaceData,
  WorkspaceRegister,
  WorkspaceTerm,
} from "./workspace-types";

export async function getWorkspace(): Promise<WorkspaceData> {
  const manifest = await getManifest();

  const registers: WorkspaceRegister[] = manifest.corpora.map((c) => ({
    key: `${c.name}/${c.register}`,
    corpus: c.name,
    register: c.register,
    title: c.title,
    label: c.label,
    checkout: c.checkout,
    modes: DIMENSIONS.filter((d) => d in c.data),
    recordedModes: c.recorded_modes,
    states: Object.fromEntries(
      DIMENSIONS.filter((d) => d in c.data).map((d) => [d, c.data[d]!.state]),
    ) as Partial<Record<Dimension, DimensionState>>,
    totals: c.totals,
    groups: c.groups,
  }));

  const chapters: WorkspaceChapter[] = manifest.chapters.map((c) => ({
    id: c.id,
    key: `${c.corpus}/${c.register}`,
    group: c.group,
    number: c.number,
    slug: c.slug,
    title: c.title,
    href: chapterHref(c),
    states: c.states,
    counts: {
      terms: c.terms_defined?.length ?? 0,
      phrases: c.phrases?.length ?? 0,
    },
  }));

  const terms: WorkspaceTerm[] = [];
  for (const c of manifest.corpora) {
    if (!("lexicon" in c.data)) continue;
    const key = `${c.name}/${c.register}`;
    const lexicon = await getLexicon(c);
    for (const [slug, entry] of Object.entries(lexicon)) {
      terms.push({
        key,
        slug,
        term: entry.term,
        kind: entry.kind,
        href: `/${key}/lexicon/${slug}`,
      });
    }
  }
  terms.sort((a, b) => a.term.localeCompare(b.term));

  return { registers, chapters, terms };
}
