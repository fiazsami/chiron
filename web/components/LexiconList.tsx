"use client";

import Link from "next/link";
import { useState } from "react";

export interface LexiconRow {
  slug: string;
  term: string;
  kind: string;
  definition: string; // first line/sentence, pre-trimmed by the server
  aliases: string[];
  anchorCount: number;
  href: string;
}

// Terms grouped by kind with a small client-side text filter — the filter
// matches term, slug, and aliases.
export default function LexiconList({
  rows,
  kindOrder,
}: {
  rows: LexiconRow[];
  kindOrder: string[];
}) {
  const [filter, setFilter] = useState("");
  const needle = filter.trim().toLowerCase();
  const visible = needle
    ? rows.filter((r) =>
        [r.term, r.slug, ...r.aliases].some((s) =>
          s.toLowerCase().includes(needle),
        ),
      )
    : rows;

  const kinds = kindOrder.filter((k) => visible.some((r) => r.kind === k));

  return (
    <>
      <input
        className="term-filter"
        type="search"
        placeholder="Filter terms…"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        aria-label="Filter terms"
      />
      {visible.length === 0 && (
        <p className="muted">No terms match “{filter.trim()}”.</p>
      )}
      {kinds.map((kind) => (
        <section key={kind} className="kind-section">
          <h2>{kind}</h2>
          <div className="term-list">
            {visible
              .filter((r) => r.kind === kind)
              .map((r) => (
                <Link key={r.slug} className="term-row" href={r.href}>
                  <span className="term-name">{r.term}</span>
                  <span className="mini-badge">{r.kind}</span>
                  <span className="term-definition">{r.definition}</span>
                  <span className="term-anchors muted">
                    {r.anchorCount} anchor{r.anchorCount === 1 ? "" : "s"}
                  </span>
                </Link>
              ))}
          </div>
        </section>
      ))}
    </>
  );
}
