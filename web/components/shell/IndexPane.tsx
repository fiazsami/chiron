"use client";

import { useEffect, useRef } from "react";
import type { RefObject } from "react";
import { DIMENSION_LABELS, type Dimension } from "@/lib/dimensions";
import type { IndexRows, SortMode } from "@/lib/shell/index-rows";
import { SORT_CYCLES, SORT_LABELS } from "@/lib/shell/index-rows";
import type { ViewKey } from "@/lib/shell/route";

// The index pane: identity plus one line of meaning per row — enough to
// choose without opening. The Shell owns cursor, selection, filter, sort.

export default function IndexPane({
  view,
  rows,
  cursorId,
  selectedId,
  focused,
  filter,
  staleOnly,
  sort,
  filterRef,
  onFilterChange,
  onFilterCommit,
  onOpen,
}: {
  view: ViewKey;
  rows: IndexRows;
  cursorId: string | null;
  selectedId: string | null;
  focused: boolean;
  filter: string;
  staleOnly: boolean;
  sort: SortMode;
  filterRef: RefObject<HTMLInputElement | null>;
  onFilterChange: (value: string) => void;
  onFilterCommit: () => void; // Enter/↓ from the field: move into the rows
  onOpen: (id: string) => void;
}) {
  const rowEls = useRef(new Map<string, HTMLElement>());

  useEffect(() => {
    if (!cursorId) return;
    rowEls.current.get(cursorId)?.scrollIntoView({ block: "nearest" });
  }, [cursorId]);

  const label = view === "chapters" ? "Chapters" : DIMENSION_LABELS[view];

  return (
    <section className={`pane index-pane${focused ? " focused" : ""}`}>
      <header className="index-header">
        <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
          <span className="index-section" style={{ padding: 0, position: "static" }}>
            {label}
            {staleOnly && <span className="count"> · stale only</span>}
          </span>
          {SORT_CYCLES[view].length > 1 && (
            <span className="count-inline" style={{ marginLeft: "auto" }}>
              {SORT_LABELS[sort]} · <span className="keycap">s</span>
            </span>
          )}
        </div>
        <div className="index-filter">
          <input
            ref={filterRef}
            value={filter}
            placeholder="Filter…"
            spellCheck={false}
            onChange={(e) => onFilterChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Escape") {
                e.preventDefault();
                onFilterChange("");
                e.currentTarget.blur();
              } else if (e.key === "Enter" || e.key === "ArrowDown") {
                e.preventDefault();
                e.currentTarget.blur();
                onFilterCommit();
              }
            }}
          />
          <span className="live-count">
            {filter || staleOnly
              ? `${rows.visible} of ${rows.total}`
              : rows.total}
          </span>
        </div>
      </header>
      <div className="index-scroll">
        {rows.rows.map((row) =>
          row.rowType === "section" ? (
            <div key={`s:${row.id}`} className="index-section">
              {row.label}
              <span className="count">{row.count}</span>
            </div>
          ) : (
            <a
              key={row.id}
              href={row.href}
              ref={(el) => {
                if (el) rowEls.current.set(row.id, el);
                else rowEls.current.delete(row.id);
              }}
              className={`index-row${cursorId === row.id && focused ? " cursor" : ""}`}
              aria-current={selectedId === row.id ? "page" : undefined}
              tabIndex={-1}
              onClick={(e) => {
                e.preventDefault();
                onOpen(row.id);
              }}
            >
              <span className="index-row-top">
                {row.number !== undefined && (
                  <span className="index-row-number">{row.number}</span>
                )}
                <span className="index-row-headword">{row.headword}</span>
                {row.kind && <span className="index-row-kind">{row.kind}</span>}
                {row.states && (
                  <span className="state-dots">
                    {Object.entries(row.states).map(([d, s]) => (
                      <i
                        key={d}
                        className={s}
                        title={`${DIMENSION_LABELS[d as Dimension] ?? d}: ${s}`}
                      />
                    ))}
                  </span>
                )}
              </span>
              {row.line && <span className="index-row-line">{row.line}</span>}
              {row.aliases && row.aliases.length > 0 && (
                <span className="index-row-aliases">
                  also {row.aliases.join(", ")}
                </span>
              )}
            </a>
          ),
        )}
        {rows.visible === 0 && (
          <p className="empty-state" style={{ padding: "16px" }}>
            {rows.total === 0
              ? `Nothing extracted yet — author via /translate.`
              : "No matches. esc clears the filter."}
          </p>
        )}
      </div>
    </section>
  );
}
