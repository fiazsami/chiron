"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";
import type { ListRow } from "@/lib/reader";

// Middle pane: the chapters of the current scope, Reeder-style — uppercase
// group label + right-aligned number on top, title beneath. Selection
// follows the URL; the active row is kept scrolled into view.
export default function ArticleList({
  rows,
  activeHref,
  header,
  sub,
}: {
  rows: ListRow[];
  activeHref: string | null;
  header: string;
  sub: string;
}) {
  const rowRefs = useRef(new Map<string, HTMLElement>());

  useEffect(() => {
    if (!activeHref) return;
    rowRefs.current.get(activeHref)?.scrollIntoView({ block: "nearest" });
  }, [activeHref]);

  return (
    <>
      <header className="list-header">
        <h2>{header || "chiron"}</h2>
        {sub && <p className="muted">{sub}</p>}
      </header>
      <div className="list-scroll">
        {rows.length === 0 && (
          <p className="list-empty">No chapters in this scope.</p>
        )}
        {rows.map((row) =>
          row.kind === "section" ? (
            <div key={`s:${row.group}`} className="list-section">
              <span>{row.label}</span>
              <span className="list-section-count">{row.count}</span>
            </div>
          ) : (
            <Link
              key={row.chapter.id}
              href={row.chapter.href}
              ref={(el) => {
                if (el) rowRefs.current.set(row.chapter.href, el);
                else rowRefs.current.delete(row.chapter.href);
              }}
              className={`list-row${row.chapter.href === activeHref ? " on" : ""}`}
            >
              <span className="list-row-top">
                <span className="list-row-source">{row.groupLabel}</span>
                <span className="list-row-num">{row.chapter.number}</span>
              </span>
              <span className="list-row-title">{row.chapter.title}</span>
              {(row.chapter.counts.terms > 0 ||
                row.chapter.counts.phrases > 0) && (
                <span className="list-row-meta">
                  {row.chapter.counts.terms > 0 && (
                    <span>{row.chapter.counts.terms} terms</span>
                  )}
                  {row.chapter.counts.phrases > 0 && (
                    <span>{row.chapter.counts.phrases} phrases</span>
                  )}
                </span>
              )}
            </Link>
          ),
        )}
      </div>
    </>
  );
}
