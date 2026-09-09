"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { DIMENSION_SEGMENTS } from "@/lib/dimensions";
import type { WorkspaceData } from "@/lib/workspace-types";

interface PaletteItem {
  href: string;
  label: string;
  detail: string;
  kind: "page" | "chapter" | "term";
}

const GLYPHS: Record<PaletteItem["kind"], string> = {
  page: "▸",
  chapter: "¶",
  term: "◇",
};

const MAX_RESULTS = 40;

// ⌘K quick-open over every route the workspace knows: register hubs,
// dimension surfaces, chapters, and lexicon terms.
export default function CommandPalette({
  data,
  onClose,
}: {
  data: WorkspaceData;
  onClose: () => void;
}) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [sel, setSel] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const rowRefs = useRef<(HTMLElement | null)[]>([]);

  const items = useMemo(() => {
    const out: PaletteItem[] = [
      { href: "/", label: "corpora", detail: "index", kind: "page" },
    ];
    for (const r of data.registers) {
      out.push({ href: `/${r.key}`, label: r.key, detail: r.title, kind: "page" });
      for (const d of r.modes) {
        const seg = DIMENSION_SEGMENTS[d];
        out.push({
          href: `/${r.key}/${seg}`,
          label: seg,
          detail: r.key,
          kind: "page",
        });
      }
    }
    for (const c of data.chapters) {
      out.push({
        href: c.href,
        label: `${c.number} ${c.title}`,
        detail: c.key,
        kind: "chapter",
      });
    }
    for (const t of data.terms) {
      out.push({
        href: t.href,
        label: t.term,
        detail: `${t.kind} · ${t.key}`,
        kind: "term",
      });
    }
    return out;
  }, [data]);

  const matches = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return items.slice(0, MAX_RESULTS);
    const tokens = needle.split(/\s+/);
    const scored: { item: PaletteItem; score: number }[] = [];
    for (const item of items) {
      const label = item.label.toLowerCase();
      const hay = `${label} ${item.detail.toLowerCase()}`;
      if (!tokens.every((t) => hay.includes(t))) continue;
      const score = label.startsWith(tokens[0])
        ? 0
        : label.includes(tokens[0])
          ? 1
          : 2;
      scored.push({ item, score });
    }
    scored.sort((a, b) => a.score - b.score);
    return scored.slice(0, MAX_RESULTS).map((s) => s.item);
  }, [items, query]);

  useEffect(() => setSel(0), [query]);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    rowRefs.current[sel]?.scrollIntoView({ block: "nearest" });
  }, [sel]);

  function go(item: PaletteItem | undefined) {
    if (!item) return;
    router.push(item.href);
    onClose();
  }

  return (
    <div className="overlay-backdrop" onMouseDown={onClose}>
      <div
        className="palette"
        role="dialog"
        aria-label="Go to anything"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <input
          ref={inputRef}
          className="palette-input"
          type="text"
          placeholder="Go to chapter, surface, or term…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setSel((s) => Math.min(matches.length - 1, s + 1));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setSel((s) => Math.max(0, s - 1));
            } else if (e.key === "Enter") {
              e.preventDefault();
              go(matches[sel]);
            } else if (e.key === "Escape") {
              e.preventDefault();
              onClose();
            }
          }}
        />
        <div className="palette-list">
          {matches.length === 0 && (
            <p className="palette-empty">Nothing matches “{query.trim()}”.</p>
          )}
          {matches.map((item, i) => (
            <div
              key={`${item.kind}:${item.href}`}
              ref={(el) => {
                rowRefs.current[i] = el;
              }}
              className={`palette-row${i === sel ? " sel" : ""}`}
              onMouseEnter={() => setSel(i)}
              onClick={() => go(item)}
            >
              <span className="palette-glyph" aria-hidden>
                {GLYPHS[item.kind]}
              </span>
              <span className="palette-label">{item.label}</span>
              <span className="palette-detail">{item.detail}</span>
            </div>
          ))}
        </div>
        <p className="palette-hint">↑↓ navigate · ↵ open · esc close</p>
      </div>
    </div>
  );
}
