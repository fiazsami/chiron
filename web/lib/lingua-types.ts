// TS mirrors of the per-register data YAML shapes owned by
// tools/lingua/dimensions/{lexicon,phrasebook,relations}.py. Pure types (no
// node imports) so client components may import them; lib/lingua.ts owns the
// server-side readers and re-exports everything here.

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

// One-line meanings for the closed relationType enum, shown on the edge
// entry so the type is never bare jargon. Wording mirrors
// design/datamodel.json enums.relationType — keep in sync.
export const RELATION_TYPE_MEANINGS: Record<RelationType, string> = {
  "is-a": "kind/instance",
  "part-of": "containment",
  uses: "dependency without data flow",
  feeds: "output of one becomes input of the other",
  configures: "one thing sets the other's behavior",
  "contrasts-with": "the corpus explicitly distinguishes the two",
  implements: "a concrete thing realizes a contract/idea",
  precedes: "required ordering",
};

export interface RelationEdge {
  from: string;
  to: string;
  type: RelationType;
  gloss: string;
  anchors: Anchor[];
}
