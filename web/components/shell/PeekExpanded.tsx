"use client";

import { useEffect, useMemo, useRef } from "react";
import type { EntryModel } from "@/lib/shell/route";
import EntryPane from "./EntryPane";
import {
  RefRegistry,
  ShellContext,
  useShell,
  type ShellApi,
} from "./shell-context";

// The expanded peek: the full entry, rendered exactly as its route would,
// inside a centered scrollable overlay. Enter on a compact peek lands here
// instead of navigating — a follow would replace the entry pane and switch
// the index dimension, invalidating the two panes behind it. The URL never
// changes; references inside are real links, so an explicit click travels
// (and closes the overlay via follow()).

export default function PeekExpanded({
  entry,
  onClose,
}: {
  entry: EntryModel;
  onClose: () => void;
}) {
  const parent = useShell();
  // Fresh registry: the card's references must not pollute the underlying
  // entry's cursor, hint labels, or `e` cycling.
  const registry = useRef(new RefRegistry()).current;
  const scroller = useRef<HTMLDivElement>(null);
  const box = useRef<HTMLDivElement>(null);
  const restore = useRef<Element | null>(null);

  const api: ShellApi = useMemo(
    () => ({
      substrate: parent.substrate,
      registry,
      refCursor: null,
      hint: null,
      copied: false,
      follow: parent.follow,
    }),
    [parent.substrate, parent.follow, registry],
  );

  useEffect(() => {
    restore.current = document.activeElement;
    box.current?.focus();
    return () => {
      (restore.current as HTMLElement | null)?.focus?.();
    };
  }, []);

  // j/k page the card; the Shell backstops enter/space/esc.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "j" || e.key === "ArrowDown") {
        e.preventDefault();
        scroller.current?.scrollBy({ top: 160, behavior: "smooth" });
      } else if (e.key === "k" || e.key === "ArrowUp") {
        e.preventDefault();
        scroller.current?.scrollBy({ top: -160, behavior: "smooth" });
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="overlay-backdrop" onMouseDown={onClose}>
      <div
        ref={box}
        tabIndex={-1}
        className="overlay-box peek-expanded"
        role="dialog"
        aria-modal="true"
        aria-label="Entry preview"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div
          className="peek-expanded-scroll"
          ref={scroller}
          data-dim={
            entry.kind === "term"
              ? "lexicon"
              : entry.kind === "phrase"
                ? "phrasebook"
                : entry.kind === "edge"
                  ? "concept-relations"
                  : "chapters"
          }
        >
          <ShellContext.Provider value={api}>
            <EntryPane substrate={parent.substrate} entry={entry} view={null} />
          </ShellContext.Provider>
        </div>
        <div className="peek-footer">
          esc closes · j/k scroll · click a reference to travel
        </div>
      </div>
    </div>
  );
}
