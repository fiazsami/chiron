"use client";

import Link from "next/link";
import {
  DIMENSION_COUNT_KEYS,
  DIMENSION_LABELS,
  DIMENSION_SEGMENTS,
} from "@/lib/dimensions";
import type { Scope } from "@/lib/reader";
import type { WorkspaceData } from "@/lib/workspace-types";

// Left pane: wordmark, then one section per register — "All Items", the
// dimension surfaces (Reeder's special items), and group folders with
// disclosure chevrons and chapter counts. Rows are plain links; the chevron
// toggles the same collapse state the `i` key does.
export default function Sidebar({
  data,
  pathname,
  scope,
  collapsed,
  onToggleGroup,
}: {
  data: WorkspaceData;
  pathname: string;
  scope: Scope | null;
  collapsed: ReadonlySet<string>;
  onToggleGroup: (token: string) => void;
}) {
  return (
    <nav className="side-nav">
      <div className="side-brand">
        <Link href="/">chiron</Link>
      </div>
      {data.registers.length === 0 && (
        <p className="side-empty">
          No corpora mounted yet. Run <code>/mount</code> in Claude Code, then{" "}
          <code>uv run python -m tools.lingua</code>.
        </p>
      )}
      {data.registers.map((reg) => {
        const chapters = data.chapters.filter((c) => c.key === reg.key);
        // A dimension surface being open owns the highlight; otherwise the
        // current scope (all items vs a group folder) does.
        const activeDimension = reg.modes.find((d) =>
          pathname.startsWith(`/${reg.key}/${DIMENSION_SEGMENTS[d]}`),
        );
        const scopeHere = !activeDimension && scope?.key === reg.key;
        return (
          <section key={reg.key} className="side-section">
            <h2 className="side-heading" title={reg.key}>
              {reg.title} · {reg.register}
            </h2>
            <Link
              className={`side-row${scopeHere && scope.kind === "all" ? " on" : ""}`}
              href={`/${reg.key}`}
            >
              <span className="side-label">All Items</span>
              <span className="side-count">{chapters.length}</span>
            </Link>
            {reg.modes.map((d) => (
              <Link
                key={d}
                className={`side-row side-special${activeDimension === d ? " on" : ""}`}
                href={`/${reg.key}/${DIMENSION_SEGMENTS[d]}`}
              >
                <span className={`status-dot ${reg.states[d] ?? "none"}`} />
                <span className="side-label">{DIMENSION_LABELS[d]}</span>
                <span className="side-count">
                  {reg.totals[DIMENSION_COUNT_KEYS[d]] ?? 0}
                </span>
              </Link>
            ))}
            {reg.groups.map((group) => {
              const token = `${reg.key}/${group.id}`;
              const count = chapters.filter(
                (c) => c.group === group.id,
              ).length;
              if (count === 0) return null;
              const open = !collapsed.has(token);
              const on =
                scopeHere &&
                scope.kind === "group" &&
                scope.group === group.id;
              return (
                <div key={group.id} className={`side-row folder${on ? " on" : ""}`}>
                  <button
                    className={`side-chevron${open ? " open" : ""}`}
                    onClick={() => onToggleGroup(token)}
                    aria-label={`${open ? "Collapse" : "Expand"} ${group.label}`}
                    aria-expanded={open}
                  >
                    ▸
                  </button>
                  <Link className="side-row-link" href={`/${reg.key}/${group.id}`}>
                    {group.label}
                  </Link>
                  <span className="side-count">{count}</span>
                </div>
              );
            })}
          </section>
        );
      })}
    </nav>
  );
}
