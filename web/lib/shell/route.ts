import { DIMENSION_SEGMENTS, type Dimension } from "../dimensions";
import type {
  ChapterVM,
  EdgeVM,
  PhraseVM,
  RegisterSubstrate,
  TermVM,
} from "../substrate-types";

// Pure pathname <-> viewer-location mapping. The URL is the selection: the
// Shell parses the pathname to know which dimension is active and which
// entry is open; route pages only validate and set metadata.

// What the index pane can show: a dimension, or the chapter list.
export type ViewKey = Dimension | "chapters";

export const VIEW_KEYS: ViewKey[] = [
  "lexicon",
  "phrasebook",
  "concept-relations",
  "chapters",
];

// URL segment under /[corpus]/[register]/ for each view.
export const VIEW_SEGMENTS: Record<ViewKey, string> = {
  ...DIMENSION_SEGMENTS,
  chapters: "chapters",
};

export type ViewerLocation =
  | { kind: "root" }
  | { kind: "index"; view: ViewKey }
  | { kind: "term"; slug: string }
  | { kind: "phrase"; slug: string }
  | { kind: "edge"; from: string; type: string; to: string }
  | { kind: "chapter"; group: string; number: string };

export type EntryModel =
  | { kind: "term"; term: TermVM }
  | { kind: "phrase"; phrase: PhraseVM }
  | { kind: "edge"; edge: EdgeVM }
  | { kind: "chapter"; chapter: ChapterVM };

function segmentsOf(pathname: string): string[] {
  return pathname
    .split("/")
    .filter(Boolean)
    .map((s) => decodeURIComponent(s));
}

// Parse a pathname already known to live under /[corpus]/[register].
export function parseViewerPath(pathname: string): ViewerLocation {
  const rest = segmentsOf(pathname).slice(2);
  switch (rest[0]) {
    case "lexicon":
      return rest.length >= 2
        ? { kind: "term", slug: rest[1] }
        : { kind: "index", view: "lexicon" };
    case "phrasebook":
      return rest.length >= 2
        ? { kind: "phrase", slug: rest[1] }
        : { kind: "index", view: "phrasebook" };
    case "relations":
      return rest.length >= 4
        ? { kind: "edge", from: rest[1], type: rest[2], to: rest[3] }
        : { kind: "index", view: "concept-relations" };
    case "chapters":
      return rest.length >= 3
        ? { kind: "chapter", group: rest[1], number: rest[2] }
        : { kind: "index", view: "chapters" };
    default:
      return { kind: "root" };
  }
}

// Which index view a location belongs to (null only for the register root).
export function viewOf(loc: ViewerLocation): ViewKey | null {
  switch (loc.kind) {
    case "root":
      return null;
    case "index":
      return loc.view;
    case "term":
      return "lexicon";
    case "phrase":
      return "phrasebook";
    case "edge":
      return "concept-relations";
    case "chapter":
      return "chapters";
  }
}

export function viewHref(base: string, view: ViewKey): string {
  return `${base}/${VIEW_SEGMENTS[view]}`;
}

// Resolve a location to its entry, or null for root/index/missing keys.
export function entryAt(
  substrate: RegisterSubstrate,
  loc: ViewerLocation,
): EntryModel | null {
  switch (loc.kind) {
    case "term": {
      const term = substrate.terms[loc.slug];
      return term ? { kind: "term", term } : null;
    }
    case "phrase": {
      const phrase = substrate.phrases[loc.slug];
      return phrase ? { kind: "phrase", phrase } : null;
    }
    case "edge": {
      const edge = substrate.edges[`${loc.from}/${loc.type}/${loc.to}`];
      return edge ? { kind: "edge", edge } : null;
    }
    case "chapter": {
      const chapter = substrate.chapters[`${loc.group}/${loc.number}`];
      return chapter ? { kind: "chapter", chapter } : null;
    }
    default:
      return null;
  }
}

// The entry's identity in index terms: the row id that should read as
// selected, keyed by view. Null when nothing is open.
export function selectionKey(loc: ViewerLocation): string | null {
  switch (loc.kind) {
    case "term":
    case "phrase":
      return loc.slug;
    case "edge":
      return `${loc.from}/${loc.type}/${loc.to}`;
    case "chapter":
      return `${loc.group}/${loc.number}`;
    default:
      return null;
  }
}
