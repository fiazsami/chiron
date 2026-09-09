// Types and pure route helpers shared by the IDE shell (client) and the
// server-side workspace builder (lib/workspace.ts). Nothing here may touch
// node APIs — client components import this module directly.

import {
  DIMENSION_LABELS,
  DIMENSION_SEGMENTS,
  type Dimension,
  type DimensionState,
} from "./dimensions";

export interface WorkspaceGroup {
  id: string;
  label: string;
}

// One entry per (corpus, register) pair — the manifest corpus, flattened to
// what the shell chrome needs.
export interface WorkspaceRegister {
  key: string; // "<corpus>/<register>"
  corpus: string;
  register: string;
  title: string;
  label: string | null;
  checkout: string;
  modes: Dimension[]; // tracked dimensions, registry order
  recordedModes: string[];
  states: Partial<Record<Dimension, DimensionState>>;
  totals: { terms?: number; phrases?: number; relations?: number };
  groups: WorkspaceGroup[];
}

export interface WorkspaceChapter {
  id: string;
  key: string; // register key
  group: string;
  number: string;
  slug: string;
  title: string;
  href: string;
  states: Partial<Record<Dimension, DimensionState>>;
}

export interface WorkspaceTerm {
  key: string; // register key
  slug: string;
  term: string;
  kind: string;
  href: string;
}

export interface WorkspaceData {
  registers: WorkspaceRegister[];
  chapters: WorkspaceChapter[];
  terms: WorkspaceTerm[];
}

export const EMPTY_WORKSPACE: WorkspaceData = {
  registers: [],
  chapters: [],
  terms: [],
};

// Route segment → dimension, the reverse of DIMENSION_SEGMENTS.
const SEGMENT_DIMENSIONS = Object.fromEntries(
  Object.entries(DIMENSION_SEGMENTS).map(([d, s]) => [s, d]),
) as Record<string, Dimension>;

export function segmentsOf(pathname: string): string[] {
  return pathname
    .split("/")
    .filter(Boolean)
    .map((s) => decodeURIComponent(s));
}

export function activeRegister(
  data: WorkspaceData,
  pathname: string,
): WorkspaceRegister | null {
  const seg = segmentsOf(pathname);
  if (seg.length < 2) return null;
  const key = `${seg[0]}/${seg[1]}`;
  return data.registers.find((r) => r.key === key) ?? null;
}

export interface Crumb {
  label: string;
  href?: string;
}

// Breadcrumb trail for the editor's crumb bar; the last crumb is the
// current location and is rendered without a link.
export function breadcrumbsFor(data: WorkspaceData, pathname: string): Crumb[] {
  const seg = segmentsOf(pathname);
  if (seg.length === 0) return [{ label: "corpora" }];
  const reg = activeRegister(data, pathname);
  if (!reg) return [{ label: seg.join(" / ") }];

  const crumbs: Crumb[] = [
    { label: "corpora", href: "/" },
    { label: reg.key, href: `/${reg.key}` },
  ];
  if (seg.length === 2) return crumbs;

  const [, , third, fourth] = seg;
  const dim = SEGMENT_DIMENSIONS[third];
  if (dim) {
    crumbs.push({
      label: DIMENSION_LABELS[dim].toLowerCase(),
      href: `/${reg.key}/${third}`,
    });
    if (fourth && dim === "lexicon") {
      const term = data.terms.find(
        (t) => t.key === reg.key && t.slug === fourth,
      );
      crumbs.push({ label: term?.term ?? fourth });
    }
  } else {
    const group = reg.groups.find((g) => g.id === third);
    crumbs.push({ label: group?.label ?? third });
    if (fourth) {
      const chapter = data.chapters.find(
        (c) => c.key === reg.key && c.group === third && c.slug === fourth,
      );
      crumbs.push({ label: chapter ? `${chapter.number} ${chapter.title}` : fourth });
    }
  }
  return crumbs;
}

// Short tab label for a route — the last breadcrumb.
export function routeLabel(data: WorkspaceData, pathname: string): string {
  const crumbs = breadcrumbsFor(data, pathname);
  return crumbs[crumbs.length - 1]?.label ?? pathname;
}

// Reading order within a register for [ / ] paging: hub, tracked dimension
// surfaces, then chapters in manifest order.
export function readingOrder(data: WorkspaceData, key: string): string[] {
  const reg = data.registers.find((r) => r.key === key);
  if (!reg) return [];
  const order = [`/${key}`];
  for (const d of reg.modes) order.push(`/${key}/${DIMENSION_SEGMENTS[d]}`);
  for (const c of data.chapters) if (c.key === key) order.push(c.href);
  return order;
}
