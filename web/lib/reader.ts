// Pure helpers for the Reeder-style shell: list scoping, row building, and
// the keymap. Client-safe — no node APIs (mirrors workspace-types.ts).

import { DIMENSION_SEGMENTS } from "./dimensions";
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
  collapsed: boolean;
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
// header; a collapsed group keeps its header but folds its chapter rows away
// (so p/l skip them). Group scope always shows its chapters.
export function listRowsFor(
  data: WorkspaceData,
  scope: Scope | null,
  collapsed: ReadonlySet<string>,
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
    const isCollapsed = collapsed.has(`${scope.key}/${group.id}`);
    rows.push({
      kind: "section",
      group: group.id,
      label: group.label,
      count: groupChapters.length,
      collapsed: isCollapsed,
    });
    if (!isCollapsed) {
      for (const chapter of groupChapters) {
        rows.push({ kind: "chapter", chapter, groupLabel: group.label });
      }
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

export type KeyAction =
  | "prevArticle"
  | "nextArticle"
  | "scrollDown"
  | "scrollUp"
  | "toggleGroup"
  | "navigator";

// The whole reader keymap. Bare keys only; the shell suppresses them inside
// form fields and while an overlay is open.
export const KEYMAP: Record<string, KeyAction> = {
  p: "prevArticle",
  l: "nextArticle",
  j: "scrollDown",
  k: "scrollUp",
  i: "toggleGroup",
  a: "navigator",
};
