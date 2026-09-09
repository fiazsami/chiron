// Pure helpers for the Reeder-style shell: list scoping, row building, the
// cross-pane cursor, and the keymap. Client-safe — no node APIs (mirrors
// workspace-types.ts).

import { DIMENSION_LABELS, DIMENSION_SEGMENTS } from "./dimensions";
import {
  activeRegister,
  segmentsOf,
  type WorkspaceChapter,
  type WorkspaceData,
} from "./workspace-types";

// What the middle pane shows: every chapter of the register ("all", the hub)
// or one group's chapters. Selecting an article never changes the scope; the
// scope only moves when a sidebar folder / hub link is followed, or when a
// deep link lands on an article outside the remembered scope.
export type Scope =
  | { kind: "all"; key: string }
  | { kind: "group"; key: string; group: string };

export interface SectionRow {
  kind: "section";
  group: string;
  label: string;
  count: number;
}

export interface ChapterRow {
  kind: "chapter";
  chapter: WorkspaceChapter;
  groupLabel: string;
}

export type ListRow = SectionRow | ChapterRow;

const DIMENSION_SEGMENT_SET = new Set(Object.values(DIMENSION_SEGMENTS));

// Resolve the list scope for a pathname. `lastScope` is the shell's sticky
// memory for the register; a null result means no register is active.
export function scopeFor(
  data: WorkspaceData,
  pathname: string,
  lastScope: Scope | null,
): Scope | null {
  const reg = activeRegister(data, pathname);
  if (!reg) return null;
  const remembered = lastScope?.key === reg.key ? lastScope : null;
  const seg = segmentsOf(pathname);
  if (seg.length === 2) return { kind: "all", key: reg.key };
  const third = seg[2];
  if (DIMENSION_SEGMENT_SET.has(third)) {
    return remembered ?? { kind: "all", key: reg.key };
  }
  if (seg.length === 3) return { kind: "group", key: reg.key, group: third };
  // Article URL: keep the remembered scope when it contains this article,
  // otherwise snap to the article's own group.
  if (remembered && (remembered.kind === "all" || remembered.group === third)) {
    return remembered;
  }
  return { kind: "group", key: reg.key, group: third };
}

// Rows for the middle pane. In all-items scope each group gets a section
// header; group scope shows just that group's chapters.
export function listRowsFor(
  data: WorkspaceData,
  scope: Scope | null,
): ListRow[] {
  if (!scope) return [];
  const reg = data.registers.find((r) => r.key === scope.key);
  if (!reg) return [];
  const chapters = data.chapters.filter((c) => c.key === scope.key);
  const labelOf = (id: string) =>
    reg.groups.find((g) => g.id === id)?.label ?? id;

  if (scope.kind === "group") {
    return chapters
      .filter((c) => c.group === scope.group)
      .map((chapter) => ({
        kind: "chapter" as const,
        chapter,
        groupLabel: labelOf(scope.group),
      }));
  }

  const rows: ListRow[] = [];
  for (const group of reg.groups) {
    const groupChapters = chapters.filter((c) => c.group === group.id);
    if (groupChapters.length === 0) continue;
    rows.push({
      kind: "section",
      group: group.id,
      label: group.label,
      count: groupChapters.length,
    });
    for (const chapter of groupChapters) {
      rows.push({ kind: "chapter", chapter, groupLabel: group.label });
    }
  }
  return rows;
}

export function chapterAt(
  data: WorkspaceData,
  pathname: string,
): WorkspaceChapter | null {
  const seg = segmentsOf(pathname);
  if (seg.length !== 4) return null;
  const key = `${seg[0]}/${seg[1]}`;
  return (
    data.chapters.find(
      (c) => c.key === key && c.group === seg[2] && c.slug === seg[3],
    ) ?? null
  );
}

// ------------------------------------------------- cross-pane cursor model

export type Pane = "sidebar" | "list" | "article";

// The sidebar's keyboard traversal order. Must mirror Sidebar.tsx's render
// order exactly (hub, then non-empty groups) or the cursor would visit rows
// that aren't on screen. The linguistic bits (terms, phrasings, relations)
// deliberately have no sidebar rows — they are lookup-only surfaces.
export interface SidebarRow {
  href: string;
  key: string; // register key
  kind: "hub" | "group";
  group?: string;
}

export function sidebarRowsFor(data: WorkspaceData): SidebarRow[] {
  const rows: SidebarRow[] = [];
  for (const reg of data.registers) {
    rows.push({ href: `/${reg.key}`, key: reg.key, kind: "hub" });
    for (const group of reg.groups) {
      if (!data.chapters.some((c) => c.key === reg.key && c.group === group.id))
        continue;
      rows.push({
        href: `/${reg.key}/${group.id}`,
        key: reg.key,
        kind: "group",
        group: group.id,
      });
    }
  }
  return rows;
}

// Which sidebar row the current URL implies the cursor is on. -1 means
// unresolvable (no register active); the shell then enters at the top on
// the next "down".
export function sidebarIndexFor(
  data: WorkspaceData,
  rows: SidebarRow[],
  pathname: string,
  scope: Scope | null,
): number {
  const reg = activeRegister(data, pathname);
  if (!reg) return -1;
  const seg = segmentsOf(pathname);
  const hubIndex = rows.findIndex(
    (r) => r.key === reg.key && r.kind === "hub",
  );

  const scopedIndex = () => {
    if (scope?.key === reg.key && scope.kind === "group") {
      const i = rows.findIndex(
        (r) => r.key === reg.key && r.kind === "group" && r.group === scope.group,
      );
      if (i >= 0) return i;
    }
    return hubIndex;
  };

  // Article URLs win over segment interpretation (routing does the same);
  // articles and the lookup-only bit pages (terms, phrasings, relations)
  // keep the cursor on the row that scoped the list.
  if (chapterAt(data, pathname)) return scopedIndex();
  if (DIMENSION_SEGMENT_SET.has(seg[2])) return scopedIndex();
  if (seg.length === 3) {
    const i = rows.findIndex(
      (r) => r.key === reg.key && r.kind === "group" && r.group === seg[2],
    );
    return i >= 0 ? i : hubIndex;
  }
  if (seg.length === 2) return hubIndex;
  return -1;
}

// Lookup text for `p`/`w` when nothing is text-selected: the thing the
// cursor is on, derived from the URL.
export function lookupTextFor(
  data: WorkspaceData,
  pathname: string,
): string | null {
  const reg = activeRegister(data, pathname);
  if (!reg) return null;
  const chapter = chapterAt(data, pathname);
  if (chapter) return chapter.title;
  const seg = segmentsOf(pathname);
  if (seg.length === 4) {
    if (seg[2] === "lexicon") {
      return (
        data.terms.find((t) => t.key === reg.key && t.slug === seg[3])?.term ??
        seg[3]
      );
    }
    if (seg[2] === "phrasebook") {
      return (
        data.phrases.find((p) => p.key === reg.key && p.slug === seg[3])
          ?.phrase ?? seg[3]
      );
    }
    if (seg[2] === "relations") return seg[3];
  }
  if (seg.length === 3) {
    const dim = reg.modes.find((d) => DIMENSION_SEGMENTS[d] === seg[2]);
    if (dim) return DIMENSION_LABELS[dim];
    return reg.groups.find((g) => g.id === seg[2])?.label ?? seg[2];
  }
  return reg.title;
}

export type KeyAction = "up" | "down" | "left" | "right" | "lookup";

// The whole reader keymap: two mirrored hand clusters (right-hand IJKL,
// left-hand EDAF) move the cursor; p/w look up the selected thing. Bare
// keys only; the shell suppresses them inside form fields and while the
// popup is open.
export const KEYMAP: Record<string, KeyAction> = {
  i: "up",
  e: "up",
  k: "down",
  d: "down",
  j: "left",
  a: "left",
  l: "right",
  f: "right",
  p: "lookup",
  w: "lookup",
};
