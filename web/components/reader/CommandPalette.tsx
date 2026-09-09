"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import type { WorkspaceData } from "@/lib/workspace-types";
import type { OpenBitRef } from "./lookup-context";

// Pages/chapters navigate; bits open the modal (they have no pages).
type PaletteItem = { label: string; detail: string } & (
  | { kind: "page" | "chapter"; href: string }
  | { kind: "term" | "phrase" | "relations"; bit: OpenBitRef }
);

function itemKey(item: PaletteItem): string {
  return "href" in item
    ? `${item.kind}:${item.href}`
    : `bit:${item.bit.kind}:${item.bit.corpus}/${item.bit.register}/${item.bit.id}`;
}

function splitKey(key: string): { corpus: string; register: string } {
  const [corpus, register] = key.split("/");
  return { corpus, register };
}

const GLYPHS: Record<PaletteItem["kind"], string> = {
  page: "▸",
  chapter: "¶",
  term: "◇",
  phrase: "❝",
  relations: "⇢",
};

const MAX_RESULTS = 40;

// ⌘K quick-open over everything the workspace knows: pages (corpora index,
// register hubs, group landings, chapters) navigate; bits (terms, phrasings,
// relation types) open the lookup modal.
export default function CommandPalette({
  data,
  openBit,
  onClose,
}: {
  data: WorkspaceData;
  openBit: (ref: OpenBitRef) => void;
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
      for (const g of r.groups) {
        out.push({
          href: `/${r.key}/${g.id}`,
          label: g.label,
          detail: r.key,
          kind: "page",
        });
      }
      for (const type of r.relationTypes) {
        out.push({
          bit: { ...splitKey(r.key), kind: "relations", id: type },
          label: type,
          detail: `relations · ${r.key}`,
          kind: "relations",
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
        bit: { ...splitKey(t.key), kind: "term", id: t.slug },
        label: t.term,
        detail: `${t.kind} · ${t.key}`,
        kind: "term",
      });
    }
    for (const p of data.phrases) {
      out.push({
        bit: { ...splitKey(p.key), kind: "phrase", id: p.slug },
        label: p.phrase,
        detail: `phrasing · ${p.key}`,
        kind: "phrase",
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
    if ("href" in item) {
      router.push(item.href);
      onClose();
    } else {
      openBit(item.bit); // closes the palette via the shell
    }
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
          placeholder="Go to chapter, term, phrasing…"
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
              key={itemKey(item)}
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
