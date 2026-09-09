// Types and pure route helpers shared by the reader shell (client) and the
// server-side workspace builder (lib/workspace.ts). Nothing here may touch
// node APIs — client components import this module directly.

import type { Dimension, DimensionState } from "./dimensions";

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
  counts: { terms: number; phrases: number };
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
