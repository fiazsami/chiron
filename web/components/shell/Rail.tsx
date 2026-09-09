"use client";

import Link from "next/link";
import { DIMENSION_COUNT_KEYS, DIMENSION_LABELS } from "@/lib/dimensions";
import type { RegisterSubstrate } from "@/lib/substrate-types";
import type { ViewKey } from "@/lib/shell/route";

// Identity and wayfinding only: wordmark, scope line, dimension switcher,
// chapters row, drift summary. Groups live in the chapters index now.

export interface RailRow {
  id: string;
  kind: "view" | "drift";
  view?: ViewKey;
}

// The focusable rows in render order — the Shell's rail cursor walks this
// same list, so keep it in sync with the JSX below.
export function railRows(substrate: RegisterSubstrate): RailRow[] {
  const rows: RailRow[] = substrate.register.modes.map((m) => ({
    id: m,
    kind: "view",
    view: m,
  }));
  rows.push({ id: "chapters", kind: "view", view: "chapters" });
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
  const reg = substrate.register;
  const rows = railRows(substrate);
  const cursorId = focused ? rows[cursor]?.id : undefined;

  const viewRow = (row: RailRow, i: number) => {
    const v = row.view!;
    const label = v === "chapters" ? "Chapters" : DIMENSION_LABELS[v];
    const count =
      v === "chapters"
        ? substrate.chapterOrder.length
        : (reg.totals[DIMENSION_COUNT_KEYS[v]] ?? 0);
    const key = v === "chapters" ? 4 : reg.modes.indexOf(v) + 1;
    return (
      <button
        key={row.id}
        type="button"
        data-dim={v}
        className={`rail-row dimension-row${view === v ? " active" : ""}${cursorId === row.id ? " cursor" : ""}`}
        onClick={() => onActivate(row)}
        tabIndex={-1}
      >
        <span className="rail-text">{label}</span>
        <span className="count rail-text">{count}</span>
        <span className="keycap">{key}</span>
      </button>
    );
  };

  return (
    <aside className={`pane rail${focused ? " focused" : ""}`}>
      <Link href="/" className="wordmark">
        chiron
      </Link>
      <div className="scope-line rail-text" title={reg.label ?? undefined}>
        {reg.title} › <span className="register-name">{reg.register}</span>
      </div>
      <nav className="rail-rows" aria-label="Dimensions">
        {rows.filter((r) => r.kind === "view").map(viewRow)}
        {reg.recordedModes.map((m) => (
          <div key={m} className="rail-row dimension-row recorded">
            <span className="rail-text">{m}</span>
          </div>
        ))}
      </nav>
      <div className="rail-footer">
        {substrate.staleTotal > 0 ? (
          <button
            type="button"
            className={`rail-row drift-summary${cursorId === "drift" ? " cursor" : ""}`}
            onClick={() => onActivate({ id: "drift", kind: "drift" })}
            tabIndex={-1}
          >
            <span className="rail-text">
              {substrate.staleTotal} stale
            </span>
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
