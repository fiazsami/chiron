// Wire types for the smart navigator (select text, hit `a`, get pages to
// follow). Client-safe — shared by app/api/navigate/route.ts and the popup.

export type DestinationKind = "chapter" | "term" | "phrase" | "relations";

export interface Destination {
  href: string; // resolved server-side; always an existing viewer route
  title: string;
  kind: DestinationKind;
  detail: string; // the model's reason, trimmed server-side
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
