"use client";

import { useEffect, useRef, useState } from "react";
import type { ViewKey } from "@/lib/shell/route";
import type { AnchorVM, RegisterSubstrate } from "@/lib/substrate-types";

// The drill: one prompt at a time from the current index scope; reveal
// shows the answer with its first anchor as evidence. Stateless per session
// by design — progress state is unmodeled in the data model.

export interface DrillItem {
  prompt: string;
  answer: string;
  gloss?: string; // relations: shown with the revealed type
  anchor?: AnchorVM;
}

export function buildDrillItems(
  substrate: RegisterSubstrate,
  view: ViewKey,
  entryIds: string[],
): DrillItem[] {
  if (view === "lexicon") {
    return entryIds.flatMap((slug) => {
      const t = substrate.terms[slug];
      return t
        ? [{ prompt: t.definition, answer: t.term, anchor: t.anchors[0] }]
        : [];
    });
  }
  if (view === "phrasebook") {
    return entryIds.flatMap((slug) => {
      const p = substrate.phrases[slug];
      return p
        ? [{ prompt: p.intent, answer: p.phrase, anchor: p.anchors[0] }]
        : [];
    });
  }
  if (view === "concept-relations") {
    return entryIds.flatMap((id) => {
      const e = substrate.edges[id];
      if (!e) return [];
      const from = substrate.terms[e.from]?.term ?? e.from;
      const to = substrate.terms[e.to]?.term ?? e.to;
      return [
        {
          prompt: `${from} — ? → ${to}`,
          answer: e.type,
          gloss: e.gloss,
          anchor: e.anchors[0],
        },
      ];
    });
  }
  return []; // chapters: nothing to recall
}

function shuffle<T>(items: T[]): T[] {
  const out = [...items];
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

export default function Drill({
  items,
  onClose,
}: {
  items: DrillItem[];
  onClose: () => void;
}) {
  const [queue, setQueue] = useState(() => shuffle(items));
  const [index, setIndex] = useState(0);
  const [revealed, setRevealed] = useState(false);
  const [got, setGot] = useState(0);
  const box = useRef<HTMLDivElement>(null);
  const restore = useRef<Element | null>(null);

  useEffect(() => {
    restore.current = document.activeElement;
    box.current?.focus();
    return () => {
      (restore.current as HTMLElement | null)?.focus?.();
    };
  }, []);

  // Drill owns its verdict keys; the Shell only backstops Escape.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === " ") {
        e.preventDefault();
        setRevealed(true);
      } else if (revealed && (e.key === "j" || e.key === "k")) {
        e.preventDefault();
        if (e.key === "j") setGot((g) => g + 1);
        else setQueue((q) => [...q, q[index]]); // again: requeue at the end
        setIndex((i) => i + 1);
        setRevealed(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [revealed, index]);

  const item = queue[index];

  return (
    <div className="overlay-backdrop" onMouseDown={onClose}>
      <div
        ref={box}
        tabIndex={-1}
        className="overlay-box drill"
        role="dialog"
        aria-modal="true"
        aria-label="Drill"
        onMouseDown={(e) => e.stopPropagation()}
      >
        {item ? (
          <>
            <div className="drill-progress">
              {index + 1} of {queue.length} · {got} got
            </div>
            <div className="drill-prompt">{item.prompt}</div>
            {revealed ? (
              <>
                <div className="drill-answer">{item.answer}</div>
                {item.gloss && <div className="drill-prompt">{item.gloss}</div>}
                {item.anchor && (
                  <figure className="evidence">
                    <blockquote className="evidence-quote">
                      “{item.anchor.quote}”
                    </blockquote>
                    <figcaption className="evidence-provenance">
                      {item.anchor.chapterTitle}
                    </figcaption>
                  </figure>
                )}
                <div className="drill-verdict">
                  <span>
                    <span className="keycap">j</span> got it
                  </span>
                  <span>
                    <span className="keycap">k</span> again
                  </span>
                </div>
              </>
            ) : (
              <div className="drill-verdict">
                <span>
                  <span className="keycap">space</span> reveal
                </span>
              </div>
            )}
          </>
        ) : (
          <>
            <div className="drill-answer">Done.</div>
            <div className="drill-progress">
              {got} of {queue.length} on the first try
            </div>
            <div className="drill-verdict">
              <span>
                <span className="keycap">esc</span> closes
              </span>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
