// Wire types for the smart navigator (select text, hit `p`/`w`, get pages
// to follow) and the bit modal (the only surface for linguistic bits).
// Client-safe — shared by the API routes and the popup. Display-only enums
// stay plain strings to keep this module import-free.

export type BitKind = "term" | "phrase" | "relations";
export type DestinationKind = BitKind | "chapter";

export interface BitRef {
  kind: BitKind;
  id: string; // lexicon slug | phrasebook slug | relation type
}

// Inline flashcard content, shipped with responses so opening or diving
// needs no page. Cross-references carry ids so the modal can dive further.
export interface BitAnchor {
  chapter: string; // register-local "<group>/<NN>", fallback label
  chapterTitle?: string;
  chapterHref?: string; // present iff the chapter resolves — a chapter ref
  quote: string; // verbatim, server-truncated
}

export interface TermBit {
  kind: "term";
  termKind: string;
  definition: string; // full, untruncated
  aliases?: string[];
  definedIn?: { title: string; href: string };
  anchors: BitAnchor[]; // capped; totalAnchors carries the real count
  totalAnchors: number;
  phrasings: { id: string; phrase: string; intent: string }[]; // capped
  morePhrasings: number;
  relations: {
    dir: "out" | "in";
    type: string;
    other: { id: string; name: string };
    gloss: string;
  }[]; // capped
  moreRelations: number;
}

export interface PhraseBit {
  kind: "phrase";
  phrase: string; // untruncated (Destination.title is capped)
  intent: string;
  template?: string;
  terms: { id: string; name: string }[]; // divable
  anchors: BitAnchor[];
  totalAnchors: number;
}

export interface RelationsBit {
  kind: "relations";
  edges: {
    from: { id: string; name: string };
    to: { id: string; name: string };
    gloss: string;
  }[];
  more: number; // edges beyond the cap
}

export type BitDetail = TermBit | PhraseBit | RelationsBit;

// Chapters are the only navigable destinations (the GitHub-styled reading
// surface); bits open in the modal and carry their full flashcard.
export type Destination =
  | { kind: "chapter"; href: string; title: string; detail: string }
  | { kind: BitKind; id: string; title: string; detail: string; bit: BitDetail };

export type BitDestination = Extract<Destination, { kind: BitKind }>;

// Stable identity: dedupe key server-side, React key client-side.
export function destinationKey(d: Destination): string {
  return d.kind === "chapter" ? d.href : `bit:${d.kind}:${d.id}`;
}

export interface NavigateRequest {
  corpus: string;
  register: string;
  selection: string; // required non-empty; server truncates to 500 chars
  context?: string; // surrounding block text, client-truncated
  pathname?: string; // current route, used for a location hint + self-exclusion
}

export interface NavigateResponse {
  results: Destination[];
}

export interface BitRequest {
  corpus: string;
  register: string;
  kind: BitKind;
  id: string;
}

export interface BitResponse {
  destination: Destination; // always the bit arm
}
