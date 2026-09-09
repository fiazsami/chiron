"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { matchJump } from "@/lib/shell/search";
import type { RefKind, SearchDoc } from "@/lib/substrate-types";

// ⌘K: jump anywhere. Matches headword, aliases, slug, chapter title;
// aliases are shown as the reason for the match.

const GLYPHS: Record<RefKind, string> = {
  term: "◇",
  phrase: "❝",
  edge: "⇢",
  chapter: "¶",
};

const GLYPH_DIM: Record<RefKind, string> = {
  term: "lexicon",
  phrase: "phrasebook",
  edge: "concept-relations",
  chapter: "chapters",
};

export default function Jump({
  docs,
  onOpen,
  onClose,
}: {
  docs: SearchDoc[];
  onOpen: (href: string) => void;
  onClose: () => void;
}) {
  const [query, setQuery] = useState("");
  const [sel, setSel] = useState(0);
  const [zone, setZone] = useState<"input" | "results">("input");
  const inputRef = useRef<HTMLInputElement>(null);
  const rowEls = useRef(new Map<number, HTMLElement>());

  const matches = useMemo(() => matchJump(docs, query), [docs, query]);
  const clamped = Math.min(sel, Math.max(0, matches.length - 1));

  useEffect(() => {
    inputRef.current?.focus();
  }, []);
  useEffect(() => {
    rowEls.current.get(clamped)?.scrollIntoView({ block: "nearest" });
  }, [clamped]);

  const move = (delta: number) => {
    setZone("results");
    setSel((s) =>
      Math.max(0, Math.min(matches.length - 1, Math.min(s, matches.length - 1) + delta)),
    );
  };

  return (
    <div className="overlay-backdrop" onMouseDown={onClose}>
      <div
        className="overlay-box jump"
        role="dialog"
        aria-modal="true"
        aria-label="Jump anywhere"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <input
          ref={inputRef}
          className="jump-input"
          placeholder="Term, phrasing, relation or chapter…"
          value={query}
          spellCheck={false}
          onChange={(e) => {
            setQuery(e.target.value);
            setSel(0);
            setZone("input");
          }}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") {
              e.preventDefault();
              move(1);
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              move(-1);
            } else if (
              zone === "results" &&
              (e.key === "j" || e.key === "k") &&
              !e.metaKey &&
              !e.ctrlKey &&
              !e.altKey
            ) {
              e.preventDefault();
              move(e.key === "j" ? 1 : -1);
            } else if (e.key === "Enter") {
              e.preventDefault();
              const m = matches[clamped];
              if (m) onOpen(m.doc.href);
            } else if (e.key === "Escape") {
              e.preventDefault();
              onClose();
            }
          }}
        />
        <div className="jump-rows">
          {matches.map((m, i) => (
            <button
              key={`${m.doc.kind}:${m.doc.key}`}
              type="button"
              ref={(el) => {
                if (el) rowEls.current.set(i, el);
                else rowEls.current.delete(i);
              }}
              className={`jump-row${i === clamped ? " cursor" : ""}`}
              data-dim={GLYPH_DIM[m.doc.kind]}
              onMouseEnter={() => {
                setSel(i);
                setZone("results");
              }}
              onClick={() => onOpen(m.doc.href)}
            >
              <span className="glyph">{GLYPHS[m.doc.kind]}</span>
              <span className="jump-headword">{m.doc.headword}</span>
              {m.alias && <span className="jump-alias">also: {m.alias}</span>}
              <span className="detail">{m.doc.detail}</span>
            </button>
          ))}
          {matches.length === 0 && (
            <p className="empty-state" style={{ padding: "12px 10px" }}>
              No matches.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
