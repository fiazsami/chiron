// Server-side builder for the reader shell's workspace data: the sidebar
// sections, article-list rows, and the term/phrase index behind the command
// palette and smart lookup, all derived from the manifest plus each
// register's data YAMLs.

import {
  DIMENSIONS,
  chapterHref,
  getManifest,
  type Dimension,
  type DimensionState,
} from "./content";
import { getLexicon, getPhrasebook, getRelations } from "./lingua";
import type {
  WorkspaceChapter,
  WorkspaceData,
  WorkspacePhrase,
  WorkspaceRegister,
  WorkspaceTerm,
} from "./workspace-types";

export async function getWorkspace(): Promise<WorkspaceData> {
  const manifest = await getManifest();

  const registers: WorkspaceRegister[] = [];
  const terms: WorkspaceTerm[] = [];
  const phrases: WorkspacePhrase[] = [];

  for (const c of manifest.corpora) {
    const key = `${c.name}/${c.register}`;
    // Each loader reads as empty when the mode is untracked.
    const [lexicon, phrasebook, relations] = await Promise.all([
      getLexicon(c),
      getPhrasebook(c),
      getRelations(c),
    ]);

    registers.push({
      key,
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
      relationTypes: [...new Set(relations.map((e) => e.type))],
    });

    for (const [slug, entry] of Object.entries(lexicon)) {
      terms.push({
        key,
        slug,
        term: entry.term,
        kind: entry.kind,
        href: `/${key}/lexicon/${slug}`,
      });
    }
    for (const [slug, entry] of Object.entries(phrasebook)) {
      phrases.push({
        key,
        slug,
        phrase: entry.phrase,
        href: `/${key}/phrasebook/${slug}`,
      });
    }
  }
  terms.sort((a, b) => a.term.localeCompare(b.term));
  phrases.sort((a, b) => a.phrase.localeCompare(b.phrase));

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

  return { registers, chapters, terms, phrases };
}
