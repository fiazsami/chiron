import fs from "node:fs/promises";
import path from "node:path";
import { cache } from "react";
import matter from "gray-matter";
import { CORPORA_DIR, findCorpus, getManifest } from "./content";
import {
  DIMENSIONS,
  DIMENSION_COUNT_KEYS,
  type Dimension,
  type DimensionState,
} from "./dimensions";
import { getLexicon, getPhrasebook, getRelations } from "./lingua";
import { RELATION_TYPES, type Anchor } from "./lingua-types";
import type {
  AnchorVM,
  ChapterVM,
  EdgeVM,
  PhraseVM,
  RegisterSubstrate,
  RegisterVM,
  ScopeData,
  ScopeRegisterVM,
  SearchDoc,
  TermVM,
} from "./substrate-types";

// Builds the full register substrate the client Shell consumes (see
// substrate-types.ts). One pass per request: manifest → data YAMLs → page
// frontmatter (description / source_url — the two chapter attributes that
// reach no other output) → precomputed hrefs, per-anchor drift, and every
// inverse relationship. React cache() dedupes across layout, pages, and
// generateMetadata within a request.

interface ChapterMeta {
  description: string | null;
  sourceUrl: string | null;
}

async function readChapterMeta(page: string): Promise<ChapterMeta> {
  try {
    const raw = await fs.readFile(path.join(CORPORA_DIR, page), "utf8");
    const data = matter(raw).data as Record<string, unknown>;
    return {
      description:
        typeof data.description === "string" ? data.description : null,
      sourceUrl: typeof data.source_url === "string" ? data.source_url : null,
    };
  } catch {
    // A missing or unparsable page only costs the standfirst/source link.
    return { description: null, sourceUrl: null };
  }
}

async function buildSubstrate(
  name: string,
  register: string,
): Promise<RegisterSubstrate | null> {
  const manifest = await getManifest();
  const corpus = findCorpus(manifest, name, register);
  if (!corpus) return null;

  const manifestChapters = manifest.chapters.filter(
    (c) => c.corpus === name && c.register === register,
  );
  const [lexicon, phrasebook, relations, metas] = await Promise.all([
    getLexicon(corpus),
    getPhrasebook(corpus),
    getRelations(corpus),
    Promise.all(manifestChapters.map((c) => readChapterMeta(c.page))),
  ]);

  const base = `/${name}/${register}`;
  const groupLabels = new Map(corpus.groups.map((g) => [g.id, g.label]));

  const chapters: Record<string, ChapterVM> = {};
  const chapterOrder: string[] = [];
  manifestChapters.forEach((c, i) => {
    const id = `${c.group}/${c.number}`;
    chapters[id] = {
      id,
      href: `${base}/chapters/${c.group}/${c.number}`,
      group: c.group,
      groupLabel: groupLabels.get(c.group) ?? c.group,
      number: c.number,
      slug: c.slug,
      title: c.title,
      kind: c.kind,
      contentHash: c.content_hash,
      description: metas[i].description,
      sourceUrl: metas[i].sourceUrl,
      sourcePaths: c.source_paths,
      states: c.states,
      defines: c.terms_defined ?? [],
      mentions: c.terms_mentioned ?? [],
      phrases: c.phrases ?? [],
      edges: [],
      staleAnchors: {},
    };
    chapterOrder.push(id);
  });

  const toAnchorVM = (a: Anchor): AnchorVM => {
    const ch = chapters[a.chapter];
    return {
      chapter: a.chapter,
      chapterTitle: ch?.title ?? a.chapter,
      chapterHref: ch?.href ?? null,
      ...(a.path ? { path: a.path } : {}),
      quote: a.quote,
      curatedAgainst: a.curated_against,
      chapterHash: ch?.contentHash ?? "",
      stale: ch ? a.curated_against !== ch.contentHash : false,
    };
  };
  const bumpStale = (anchors: AnchorVM[], dimension: Dimension) => {
    for (const a of anchors) {
      if (!a.stale) continue;
      const ch = chapters[a.chapter];
      if (!ch) continue;
      ch.staleAnchors[dimension] = (ch.staleAnchors[dimension] ?? 0) + 1;
    }
  };

  const terms: Record<string, TermVM> = {};
  for (const [slug, e] of Object.entries(lexicon)) {
    terms[slug] = {
      slug,
      href: `${base}/lexicon/${slug}`,
      term: e.term,
      kind: e.kind,
      definition: e.definition,
      aliases: e.aliases ?? [],
      definedIn: e.defined_in,
      anchors: e.anchors.map(toAnchorVM),
      phrasings: [],
      edgesOut: [],
      edgesIn: [],
      mentionedIn: [],
    };
    bumpStale(terms[slug].anchors, "lexicon");
  }
  const termOrder = Object.keys(terms).sort(
    (a, b) =>
      terms[a].term.localeCompare(terms[b].term, undefined, {
        sensitivity: "base",
      }) || a.localeCompare(b),
  );
  // mentionedIn in chapter order (chapters are already in register order).
  for (const id of chapterOrder) {
    for (const slug of chapters[id].mentions) terms[slug]?.mentionedIn.push(id);
  }

  const phrases: Record<string, PhraseVM> = {};
  for (const [slug, p] of Object.entries(phrasebook)) {
    phrases[slug] = {
      slug,
      href: `${base}/phrasebook/${slug}`,
      phrase: p.phrase,
      intent: p.intent,
      ...(p.template ? { template: p.template } : {}),
      terms: p.terms,
      anchors: p.anchors.map(toAnchorVM),
    };
    bumpStale(phrases[slug].anchors, "phrasebook");
  }
  const phraseOrder = Object.keys(phrases).sort(
    (a, b) =>
      phrases[a].phrase.localeCompare(phrases[b].phrase, undefined, {
        sensitivity: "base",
      }) || a.localeCompare(b),
  );
  // Term → phrasings in phraseOrder, so entry sections read alphabetically.
  for (const slug of phraseOrder) {
    for (const t of phrases[slug].terms) terms[t]?.phrasings.push(slug);
  }

  const edges: Record<string, EdgeVM> = {};
  for (const e of relations) {
    const id = `${e.from}/${e.type}/${e.to}`;
    if (edges[id]) {
      // (from, type, to) is the edge's identity; the pipeline should never
      // emit twins, but the route must stay canonical if it does.
      console.error(`substrate: duplicate edge ${id} — keeping the first`);
      continue;
    }
    edges[id] = {
      id,
      href: `${base}/relations/${e.from}/${e.type}/${e.to}`,
      from: e.from,
      to: e.to,
      type: e.type,
      gloss: e.gloss,
      anchors: e.anchors.map(toAnchorVM),
    };
    bumpStale(edges[id].anchors, "concept-relations");
  }
  const typeRank = new Map(RELATION_TYPES.map((t, i) => [t, i]));
  const edgeOrder = Object.keys(edges).sort((a, b) => {
    const ea = edges[a];
    const eb = edges[b];
    return (
      (typeRank.get(ea.type) ?? RELATION_TYPES.length) -
        (typeRank.get(eb.type) ?? RELATION_TYPES.length) ||
      ea.from.localeCompare(eb.from) ||
      ea.to.localeCompare(eb.to)
    );
  });
  for (const id of edgeOrder) {
    const e = edges[id];
    terms[e.from]?.edgesOut.push(id);
    terms[e.to]?.edgesIn.push(id);
    for (const ch of new Set(e.anchors.map((a) => a.chapter))) {
      chapters[ch]?.edges.push(id);
    }
  }

  let staleTotal = 0;
  for (const c of manifestChapters) {
    for (const s of Object.values(c.states)) if (s === "stale") staleTotal++;
  }

  const detail = (label: string) => `${label} · ${register}`;
  const doc = (
    kind: SearchDoc["kind"],
    key: string,
    href: string,
    headword: string,
    label: string,
    aliases: string[] = [],
    extraKeys: string[] = [],
  ): SearchDoc => ({
    kind,
    key,
    href,
    headword,
    aliases,
    detail: detail(label),
    haystack: [headword, ...aliases, key, ...extraKeys]
      .join(" ")
      .toLowerCase(),
  });
  const search: SearchDoc[] = [
    ...termOrder.map((s) =>
      doc("term", s, terms[s].href, terms[s].term, "Lexicon", terms[s].aliases),
    ),
    ...phraseOrder.map((s) =>
      doc("phrase", s, phrases[s].href, phrases[s].phrase, "Phrasebook"),
    ),
    ...edgeOrder.map((id) => {
      const e = edges[id];
      const from = terms[e.from]?.term ?? e.from;
      const to = terms[e.to]?.term ?? e.to;
      return doc(
        "edge",
        id,
        e.href,
        `${from} —${e.type}→ ${to}`,
        "Relations",
      );
    }),
    ...chapterOrder.map((id) =>
      doc("chapter", id, chapters[id].href, chapters[id].title, "Chapters", [], [
        chapters[id].slug,
      ]),
    ),
  ];

  const dimensionStates: Partial<Record<Dimension, DimensionState>> = {};
  for (const d of DIMENSIONS) {
    const entry = corpus.data[d];
    if (entry) dimensionStates[d] = entry.state;
  }
  const registerVM: RegisterVM = {
    key: `${name}/${register}`,
    corpus: name,
    register,
    title: corpus.title,
    label: corpus.label,
    checkout: corpus.checkout,
    urls: corpus.urls,
    sourceKind: corpus.source_kind,
    modes: corpus.modes,
    recordedModes: corpus.recorded_modes,
    dimensionStates,
    totals: corpus.totals,
    groups: corpus.groups,
  };

  return {
    register: registerVM,
    terms,
    termOrder,
    phrases,
    phraseOrder,
    edges,
    edgeOrder,
    chapters,
    chapterOrder,
    staleTotal,
    search,
  };
}

export const getSubstrate = cache(buildSubstrate);

export const getScopeData = cache(async (): Promise<ScopeData> => {
  const manifest = await getManifest();
  const registers: ScopeRegisterVM[] = manifest.corpora.map((corpus) => {
    const chapters = manifest.chapters.filter(
      (c) => c.corpus === corpus.name && c.register === corpus.register,
    );
    let staleCount = 0;
    for (const c of chapters) {
      for (const s of Object.values(c.states)) if (s === "stale") staleCount++;
    }
    const states = DIMENSIONS.flatMap((d) => {
      const entry = corpus.data[d];
      return entry ? [entry.state] : [];
    });
    const worst: DimensionState = states.includes("stale")
      ? "stale"
      : states.includes("none")
        ? "none"
        : "ok";
    return {
      key: `${corpus.name}/${corpus.register}`,
      corpus: corpus.name,
      register: corpus.register,
      title: corpus.title,
      label: corpus.label,
      sourceKind: corpus.source_kind,
      checkout: corpus.checkout,
      urls: corpus.urls,
      href: `/${corpus.name}/${corpus.register}`,
      totals: DIMENSIONS.filter((d) => d in corpus.data).map((d) => ({
        dimension: d,
        count: corpus.totals[DIMENSION_COUNT_KEYS[d]] ?? 0,
        noun: DIMENSION_COUNT_KEYS[d],
      })),
      chapterCount: chapters.length,
      staleCount,
      worst,
    };
  });
  return { registers };
});
