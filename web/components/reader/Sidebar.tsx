"use client";

import Link from "next/link";
import type { Scope } from "@/lib/reader";
import type { WorkspaceData } from "@/lib/workspace-types";

// Left pane: wordmark, then one section per register — "All Items" and the
// group folders with chapter counts. Rows are plain links; keyboard
// traversal order must mirror this render order (see sidebarRowsFor in
// lib/reader.ts). The linguistic bits (terms, phrasings, relations) have no
// rows here on purpose: they are reachable only via smart lookup and ⌘K.
export default function Sidebar({
  data,
  scope,
}: {
  data: WorkspaceData;
  scope: Scope | null;
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
        const scopeHere = scope?.key === reg.key;
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
            {reg.groups.map((group) => {
              const count = chapters.filter(
                (c) => c.group === group.id,
              ).length;
              if (count === 0) return null;
              const on =
                scopeHere &&
                scope.kind === "group" &&
                scope.group === group.id;
              return (
                <Link
                  key={group.id}
                  className={`side-row${on ? " on" : ""}`}
                  href={`/${reg.key}/${group.id}`}
                >
                  <span className="side-label">{group.label}</span>
                  <span className="side-count">{count}</span>
                </Link>
              );
            })}
          </section>
        );
      })}
    </nav>
  );
}
