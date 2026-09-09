// Client-safe extraction of a flashcard's cross-references in visual order.
// The renderer never counts refs itself — it looks positions up through the
// index maps, so extraction order and markup order cannot drift apart.

import type { BitDestination, BitKind } from "./navigator-types";

export type CardRef =
  | { refType: "bit"; kind: BitKind; id: string; label: string }
  | { refType: "chapter"; href: string; label: string };

export interface CardRefIndex {
  refs: CardRef[]; // visual order
  definedIn: number | null; // term header
  anchors: (number | null)[]; // per rendered anchor; null = unresolvable
  phrasings: number[]; // term card
  relations: number[]; // term card
  terms: number[]; // phrase card
  edges: { from: number; to: number }[]; // relations card
}

// Visual order per kind: term = definedIn → anchor chapter labels →
// phrasings → relations; phrase = term chips → anchor labels; relations =
// per edge, from then to.
export function buildCardRefs(dest: BitDestination): CardRefIndex {
  const refs: CardRef[] = [];
  const index: CardRefIndex = {
    refs,
    definedIn: null,
    anchors: [],
    phrasings: [],
    relations: [],
    terms: [],
    edges: [],
  };
  const push = (ref: CardRef): number => refs.push(ref) - 1;
  const bit = dest.bit;

  if (bit.kind === "term") {
    if (bit.definedIn) {
      index.definedIn = push({
        refType: "chapter",
        href: bit.definedIn.href,
        label: bit.definedIn.title,
      });
    }
    for (const a of bit.anchors) {
      index.anchors.push(
        a.chapterHref
          ? push({
              refType: "chapter",
              href: a.chapterHref,
              label: a.chapterTitle ?? a.chapter,
            })
          : null,
      );
    }
    for (const p of bit.phrasings) {
      index.phrasings.push(
        push({ refType: "bit", kind: "phrase", id: p.id, label: p.phrase }),
      );
    }
    for (const r of bit.relations) {
      index.relations.push(
        push({ refType: "bit", kind: "term", id: r.other.id, label: r.other.name }),
      );
    }
  } else if (bit.kind === "phrase") {
    for (const t of bit.terms) {
      index.terms.push(
        push({ refType: "bit", kind: "term", id: t.id, label: t.name }),
      );
    }
    for (const a of bit.anchors) {
      index.anchors.push(
        a.chapterHref
          ? push({
              refType: "chapter",
              href: a.chapterHref,
              label: a.chapterTitle ?? a.chapter,
            })
          : null,
      );
    }
  } else {
    for (const e of bit.edges) {
      index.edges.push({
        from: push({ refType: "bit", kind: "term", id: e.from.id, label: e.from.name }),
        to: push({ refType: "bit", kind: "term", id: e.to.id, label: e.to.name }),
      });
    }
  }
  return index;
}
