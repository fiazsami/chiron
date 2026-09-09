"use client";

import { useLayoutEffect, useRef, useState } from "react";
import type { EntryModel } from "@/lib/shell/route";
import type { AnchorVM } from "@/lib/substrate-types";

// Compact preview of the cursor reference, anchored beside it — never over
// the reading measure. Space opens/closes; enter promotes to a real follow.

function contentOf(entry: EntryModel): {
  headword: string;
  kind: string;
  reading: string;
  anchor?: AnchorVM;
} {
  switch (entry.kind) {
    case "term":
      return {
        headword: entry.term.term,
        kind: entry.term.kind,
        reading: entry.term.definition,
        anchor: entry.term.anchors[0],
      };
    case "phrase":
      return {
        headword: entry.phrase.phrase,
        kind: "phrasing",
        reading: entry.phrase.intent,
        anchor: entry.phrase.anchors[0],
      };
    case "edge":
      return {
        headword: `${entry.edge.from} —${entry.edge.type}→ ${entry.edge.to}`,
        kind: "relation",
        reading: entry.edge.gloss,
        anchor: entry.edge.anchors[0],
      };
    case "chapter":
      return {
        headword: entry.chapter.title,
        kind:
          entry.chapter.kind === "code" ? "chapter · code" : "chapter",
        reading: entry.chapter.description ?? "",
        anchor: undefined,
      };
  }
}

export default function Peek({
  entry,
  targetRect,
  measureRect,
}: {
  entry: EntryModel;
  targetRect: DOMRect;
  measureRect: DOMRect | null; // the entry body box the peek must not cover
}) {
  const el = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null);

  useLayoutEffect(() => {
    const card = el.current;
    if (!card) return;
    const w = card.offsetWidth;
    const h = card.offsetHeight;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const clamp = (v: number, lo: number, hi: number) =>
      Math.max(lo, Math.min(hi, v));
    let left: number;
    let top: number;
    if (measureRect && vw - measureRect.right >= w + 32) {
      // Right margin beside the measure.
      left = measureRect.right + 24;
      top = clamp(targetRect.top, 16, vh - h - 16);
    } else if (vh - targetRect.bottom >= h + 16) {
      left = clamp(targetRect.left, 16, vw - w - 16);
      top = targetRect.bottom + 8;
    } else {
      left = clamp(targetRect.left, 16, vw - w - 16);
      top = Math.max(16, targetRect.top - h - 8);
    }
    setPos({ left, top });
  }, [entry, targetRect, measureRect]);

  const c = contentOf(entry);

  return (
    <div
      ref={el}
      className="peek"
      role="dialog"
      aria-label={c.headword}
      style={{
        left: pos?.left ?? -9999,
        top: pos?.top ?? 0,
        visibility: pos ? "visible" : "hidden",
      }}
    >
      <div className="peek-headword">
        {c.headword} <span className="peek-kind">{c.kind}</span>
      </div>
      {c.reading && <div className="peek-reading">{c.reading}</div>}
      {c.anchor && (
        <blockquote className="evidence-quote">“{c.anchor.quote}”</blockquote>
      )}
      <div className="peek-footer">↵ opens · space closes</div>
    </div>
  );
}
