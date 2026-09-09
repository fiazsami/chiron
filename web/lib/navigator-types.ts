// Wire types for the smart navigator (select text, hit `a`, get pages to
// follow). Client-safe — shared by app/api/navigate/route.ts and the popup.

export type DestinationKind = "chapter" | "term" | "phrase" | "relations";

// Inline content for the popup's detail view, shipped with the response so
// expanding a result needs no second request. Display-only enums stay plain
// strings to keep this module import-free and client-safe.
export interface BitAnchor {
  chapter: string; // register-local "<group>/<NN>", fallback label
  chapterTitle?: string;
  quote: string; // verbatim, server-truncated
}

export interface TermBit {
  kind: "term";
  termKind: string;
  definition: string; // full, untruncated
  aliases?: string[];
  definedIn?: { title: string; href: string };
  anchors: BitAnchor[];
}

export interface PhraseBit {
  kind: "phrase";
  phrase: string; // untruncated (Destination.title is capped)
  intent: string;
  template?: string;
  terms: string[]; // resolved display names
}

export interface RelationsBit {
  kind: "relations";
  edges: { from: string; to: string; gloss: string }[];
  more: number; // edges beyond the cap
}

export type BitDetail = TermBit | PhraseBit | RelationsBit;

export interface Destination {
  href: string; // resolved server-side; always an existing viewer route
  title: string;
  kind: DestinationKind;
  detail: string; // the model's reason, trimmed server-side
  bit?: BitDetail; // present for non-chapter kinds
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
