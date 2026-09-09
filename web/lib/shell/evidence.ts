import type { AnchorVM } from "../substrate-types";

// Anchors accumulate across chapters (a term mentioned in five chapters
// carries five chapters' anchors), so entries can hold near-identical
// quotes many times over. The Evidence section renders quote-groups: one
// quote block, every distinct provenance beneath it, first-seen order.

export interface AnchorGroup {
  quote: string;
  code: boolean;
  stale: boolean; // any ref drifted
  refs: AnchorVM[];
}

// Groups shown before the "N more" expander row.
export const EVIDENCE_VISIBLE = 6;

export function groupAnchors(anchors: AnchorVM[]): AnchorGroup[] {
  const groups = new Map<string, AnchorGroup>();
  for (const a of anchors) {
    const existing = groups.get(a.quote);
    if (existing) {
      // The same chapter can pin the same quote more than once (e.g. via
      // different paths); keep one provenance line per (chapter, path).
      if (
        !existing.refs.some((r) => r.chapter === a.chapter && r.path === a.path)
      ) {
        existing.refs.push(a);
      }
      existing.stale ||= a.stale;
      existing.code ||= a.code;
    } else {
      groups.set(a.quote, {
        quote: a.quote,
        code: a.code,
        stale: a.stale,
        refs: [a],
      });
    }
  }
  return [...groups.values()];
}
