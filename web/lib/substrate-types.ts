import type { Dimension, DimensionState } from "./dimensions";
import type { RelationType, TermKind } from "./lingua-types";

// The register substrate handed from the server layout to the client Shell —
// every entry with all anchors and precomputed inverse relationships, so the
// index, entries, peek, jump, and drill never need a server round trip.
// Built once per request by lib/substrate.ts (design/ui-map-1.json is the
// binding surface map). Client-safe: no node imports.

export interface AnchorVM {
  chapter: string; // register-local "<group>/<NN>"
  chapterTitle: string; // resolved; falls back to the local id
  chapterHref: string | null; // null when the chapter no longer exists
  path?: string; // source-relative file (code chapters)
  quote: string;
  code: boolean; // anchored chapter is kind=code — the quote is source code
  curatedAgainst: string; // 12-hex drift pin
  chapterHash: string; // chapter content_hash at build time ("" if unresolvable)
  stale: boolean; // curatedAgainst !== chapterHash (false when unresolvable)
}

export interface TermVM {
  slug: string;
  href: string;
  term: string;
  kind: TermKind;
  definition: string;
  aliases: string[]; // [] when absent
  definedIn: string; // local chapter id
  anchors: AnchorVM[];
  phrasings: string[]; // phrase slugs whose terms include this slug
  edgesOut: string[]; // edge ids where from === slug
  edgesIn: string[]; // edge ids where to === slug
  mentionedIn: string[]; // local chapter ids (anchored here, defined elsewhere)
}

export interface PhraseVM {
  slug: string;
  href: string;
  phrase: string;
  intent: string;
  template?: string;
  terms: string[]; // term slugs; unresolvable ones render as plain text
  anchors: AnchorVM[];
}

export interface EdgeVM {
  id: string; // "<from>/<type>/<to>" — doubles as the route param triple
  href: string;
  from: string; // term slug
  to: string; // term slug
  type: RelationType;
  gloss: string;
  anchors: AnchorVM[];
}

export interface ChapterVM {
  id: string; // local "<group>/<NN>" (the anchor / defined_in key)
  href: string;
  group: string;
  groupLabel: string;
  number: string;
  slug: string;
  title: string;
  kind: "doc" | "code";
  contentHash: string;
  description: string | null; // page frontmatter standfirst
  sourceUrl: string | null; // page frontmatter; target of key `o`
  sourcePaths: string[]; // manifest source_paths; [0] is the primary path
  states: Partial<Record<Dimension, DimensionState>>;
  defines: string[]; // term slugs
  mentions: string[]; // term slugs
  phrases: string[]; // phrase slugs grounded here
  edges: string[]; // edge ids with >=1 anchor in this chapter
  staleAnchors: Partial<Record<Dimension, number>>; // stale anchors here, per dimension
}

export interface RegisterVM {
  key: string; // "<corpus>/<register>"
  corpus: string;
  register: string; // "v1"
  title: string;
  label: string | null;
  checkout: string;
  urls: Record<string, string>;
  sourceKind: "markdown" | "code" | "custom";
  modes: Dimension[]; // tracked, registry order
  recordedModes: string[];
  dimensionStates: Partial<Record<Dimension, DimensionState>>;
  totals: { terms?: number; phrases?: number; relations?: number };
  groups: { id: string; label: string }[]; // register order
}

export type RefKind = "term" | "phrase" | "edge" | "chapter";

// One row of the jump/filter search corpus. Aliases are match keys — the
// alias gap called out by design/ui-map-1.json.
export interface SearchDoc {
  kind: RefKind;
  key: string; // slug | slug | edge id | chapter local id
  href: string;
  headword: string;
  aliases: string[]; // terms only
  detail: string; // "Lexicon · v1"
  haystack: string; // lowercased headword + aliases + key
}

export interface RegisterSubstrate {
  register: RegisterVM;
  registers: ScopeRegisterVM[]; // every mounted (corpus, register) — the rail navigates corpora directly
  terms: Record<string, TermVM>;
  termOrder: string[]; // alphabetical by term
  phrases: Record<string, PhraseVM>;
  phraseOrder: string[]; // alphabetical by phrase
  edges: Record<string, EdgeVM>;
  edgeOrder: string[]; // RELATION_TYPES order, then from, then to
  chapters: Record<string, ChapterVM>;
  chapterOrder: string[]; // manifest emission order (group, then number)
  staleTotal: number; // stale (chapter, dimension) pairs — rail drift summary
  search: SearchDoc[];
}

// ---- scope surface (/) ----

export interface ScopeRegisterVM {
  key: string;
  corpus: string;
  register: string;
  title: string;
  label: string | null;
  sourceKind: "markdown" | "code" | "custom";
  checkout: string;
  urls: Record<string, string>;
  recordedModes: string[];
  href: string; // "/<corpus>/<register>" (redirects into chapters)
  totals: {
    dimension: Dimension;
    count: number;
    noun: "terms" | "phrases" | "relations";
  }[];
  chapterCount: number;
  staleCount: number; // stale (chapter, dimension) pairs
  worst: DimensionState; // stale > none > ok, across tracked dimensions
}

export interface ScopeData {
  registers: ScopeRegisterVM[];
}
