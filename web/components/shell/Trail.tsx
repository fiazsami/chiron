"use client";

// The dive stack made visible: a breadcrumb of entries visited by following
// cross-references. Rendered above the entry so the reading measure is
// never interrupted. Collapses middle crumbs beyond 6.

export interface TrailEntry {
  href: string;
  headword: string;
}

export default function Trail({
  entries,
  pos,
  onJump,
}: {
  entries: TrailEntry[];
  pos: number;
  onJump: (index: number) => void;
}) {
  if (entries.length < 2) return null;

  // Beyond 6 crumbs: first 2 + … + last 4.
  let visible: (number | "gap")[] = entries.map((_, i) => i);
  if (entries.length > 6) {
    visible = [0, 1, "gap", ...visible.slice(-4).map((i) => i as number)];
  }

  return (
    <nav className="trail-bar" aria-label="Trail">
      {visible.map((v, i) =>
        v === "gap" ? (
          <span key="gap" className="trail-sep">
            …
          </span>
        ) : (
          <span key={entries[v].href + v} style={{ display: "contents" }}>
            {i > 0 && <span className="trail-sep">›</span>}
            <button
              type="button"
              className={`trail-crumb${v === pos ? " current" : ""}`}
              onClick={() => onJump(v)}
              tabIndex={-1}
            >
              {entries[v].headword}
            </button>
          </span>
        ),
      )}
    </nav>
  );
}
