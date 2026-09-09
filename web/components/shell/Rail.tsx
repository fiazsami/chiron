"use client";

import Link from "next/link";
import type { RegisterSubstrate } from "@/lib/substrate-types";
import type { ViewKey } from "@/lib/shell/route";

// Identity and corpus navigation: wordmark, one row per mounted (corpus,
// register), the Chapters row, drift summary. The far-left pane navigates
// corpora entirely; dimension rows are never displayed — dimensions are
// reached through keys 1-3, ⌘K, and cross-references.

export interface RailRow {
  id: string;
  kind: "register" | "chapters" | "drift";
  href?: string; // register rows: the register root (lands on chapters)
}

// The focusable rows in render order — the Shell's rail cursor walks this
// same list, so keep it in sync with the JSX below.
export function railRows(substrate: RegisterSubstrate): RailRow[] {
  const rows: RailRow[] = substrate.registers.map((r) => ({
    id: `reg:${r.key}`,
    kind: "register",
    href: r.href,
  }));
  rows.push({ id: "chapters", kind: "chapters" });
  if (substrate.staleTotal > 0) rows.push({ id: "drift", kind: "drift" });
  return rows;
}

export default function Rail({
  substrate,
  view,
  cursor,
  focused,
  onActivate,
}: {
  substrate: RegisterSubstrate;
  view: ViewKey | null;
  cursor: number;
  focused: boolean;
  onActivate: (row: RailRow) => void;
}) {
  const active = substrate.register;
  const rows = railRows(substrate);
  const cursorId = focused ? rows[cursor]?.id : undefined;

  return (
    <aside className={`pane rail${focused ? " focused" : ""}`}>
      <Link href="/" className="wordmark">
        chiron
      </Link>
      <nav className="rail-rows" aria-label="Corpora">
        {substrate.registers.map((r) => {
          const isActive = r.key === active.key;
          const row: RailRow = { id: `reg:${r.key}`, kind: "register", href: r.href };
          return (
            <button
              key={r.key}
              type="button"
              title={r.label ?? undefined}
              className={`rail-row dimension-row${isActive ? " active" : ""}${cursorId === row.id ? " cursor" : ""}`}
              onClick={() => onActivate(row)}
              tabIndex={-1}
            >
              <span className="rail-text">{r.title}</span>
              <span className="count rail-text register-name">
                {r.register}
              </span>
            </button>
          );
        })}
      </nav>
      <nav className="rail-rows" aria-label="Chapters">
        <button
          type="button"
          data-dim="chapters"
          className={`rail-row dimension-row${view === "chapters" ? " active" : ""}${cursorId === "chapters" ? " cursor" : ""}`}
          onClick={() => onActivate({ id: "chapters", kind: "chapters" })}
          tabIndex={-1}
        >
          <span className="rail-text">Chapters</span>
          <span className="count rail-text">
            {substrate.chapterOrder.length}
          </span>
          <span className="keycap">4</span>
        </button>
      </nav>
      <div className="rail-footer">
        {substrate.staleTotal > 0 ? (
          <button
            type="button"
            className={`rail-row drift-summary${cursorId === "drift" ? " cursor" : ""}`}
            onClick={() => onActivate({ id: "drift", kind: "drift" })}
            tabIndex={-1}
          >
            <span className="rail-text">{substrate.staleTotal} stale</span>
          </button>
        ) : (
          <div className="rail-row drift-summary zero">
            <span className="rail-text">no drift</span>
          </div>
        )}
        <div className="rail-text" style={{ padding: "0 8px" }}>
          <span className="keycap">?</span>{" "}
          <span className="count-inline">keys</span>
        </div>
      </div>
    </aside>
  );
}
