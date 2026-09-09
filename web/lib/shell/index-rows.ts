import type { Dimension, DimensionState } from "../dimensions";
import type { RegisterSubstrate } from "../substrate-types";
import type { ViewKey } from "./route";

// Pure builders for the index pane: identity plus one line of meaning per
// row (design/ui-map-1.json index surface). The Shell owns sort + filter
// state; this module turns them into rows.

export type SortMode = "alpha" | "kind" | "chapter" | "term" | "type" | "group";

export const SORT_CYCLES: Record<ViewKey, SortMode[]> = {
  lexicon: ["alpha", "kind", "chapter"],
  phrasebook: ["alpha", "term"],
  "concept-relations": ["type"],
  chapters: ["group"],
};

export function defaultSort(view: ViewKey): SortMode {
  return SORT_CYCLES[view][0];
}

export function cycleSort(view: ViewKey, current: SortMode): SortMode {
  const cycle = SORT_CYCLES[view];
  const i = cycle.indexOf(current);
  return cycle[(i + 1) % cycle.length];
}

export const SORT_LABELS: Record<SortMode, string> = {
  alpha: "a–z",
  kind: "by kind",
  chapter: "by chapter",
  term: "by term",
  type: "by type",
  group: "by group",
};

export interface SectionRow {
  rowType: "section";
  id: string;
  label: string;
  count: number;
}

export interface EntryIndexRow {
  rowType: "entry";
  id: string; // selection key (term/phrase slug, edge id, chapter local id)
  href: string;
  headword: string;
  line?: string; // definition | intent | gloss, first line
  aliases?: string[];
  kind?: string; // term.kind | chapter.kind, plain text after the headword
  number?: string; // chapters only
  states?: Partial<Record<Dimension, DimensionState>>; // chapters only
}

export type IndexRow = SectionRow | EntryIndexRow;

export interface IndexRows {
  rows: IndexRow[];
  entryIds: string[]; // navigable ids in visual order
  visible: number;
  total: number;
}

const LINE_MAX = 90;

function firstLine(text: string): string {
  const line = text.split("\n", 1)[0];
  return line.length > LINE_MAX ? `${line.slice(0, LINE_MAX - 1)}…` : line;
}

const TERM_KINDS = ["concept", "name", "identifier", "command", "file", "value"];

interface Candidate {
  row: EntryIndexRow;
  match: string; // lowercased headword + aliases + slug
  section: string; // section key under the active sort ("" = flat)
}

function sectionize(
  candidates: Candidate[],
  sections: { key: string; label: string }[],
): IndexRow[] {
  const bySection = new Map<string, EntryIndexRow[]>();
  for (const c of candidates) {
    const list = bySection.get(c.section);
    if (list) list.push(c.row);
    else bySection.set(c.section, [c.row]);
  }
  const rows: IndexRow[] = [];
  for (const s of sections) {
    const list = bySection.get(s.key);
    if (!list?.length) continue;
    rows.push({ rowType: "section", id: s.key, label: s.label, count: list.length });
    rows.push(...list);
  }
  return rows;
}

export function rowsFor(
  substrate: RegisterSubstrate,
  view: ViewKey,
  sort: SortMode,
  filter: string,
  staleOnly: boolean,
): IndexRows {
  const needle = filter.trim().toLowerCase();
  let candidates: Candidate[] = [];
  let sections: { key: string; label: string }[] = [];
  let flat = false;

  if (view === "lexicon") {
    candidates = substrate.termOrder.map((slug) => {
      const t = substrate.terms[slug];
      return {
        row: {
          rowType: "entry",
          id: slug,
          href: t.href,
          headword: t.term,
          line: firstLine(t.definition),
          aliases: t.aliases,
          kind: t.kind,
        },
        match: [t.term, ...t.aliases, slug].join(" ").toLowerCase(),
        section:
          sort === "kind" ? t.kind : sort === "chapter" ? t.definedIn : "",
      };
    });
    if (sort === "alpha") flat = true;
    else if (sort === "kind")
      sections = TERM_KINDS.map((k) => ({ key: k, label: k }));
    else {
      sections = substrate.chapterOrder.map((id) => ({
        key: id,
        label: substrate.chapters[id].title,
      }));
      sections.push({ key: "", label: "elsewhere" });
      // Terms whose defining chapter is unknown fall into "elsewhere".
      for (const c of candidates) {
        if (!substrate.chapters[c.section]) c.section = "";
      }
      // Course feel: within a chapter, terms in the order it defines them.
      const bySlug = new Map(candidates.map((c) => [c.row.id, c]));
      const ordered: Candidate[] = [];
      for (const id of substrate.chapterOrder) {
        for (const slug of substrate.chapters[id].defines) {
          const c = bySlug.get(slug);
          if (c && c.section === id) {
            ordered.push(c);
            bySlug.delete(slug);
          }
        }
      }
      ordered.push(...bySlug.values()); // leftovers, alphabetical already
      candidates = ordered;
    }
  } else if (view === "phrasebook") {
    candidates = substrate.phraseOrder.map((slug) => {
      const p = substrate.phrases[slug];
      const first = p.terms[0] ?? "";
      return {
        row: {
          rowType: "entry",
          id: slug,
          href: p.href,
          headword: p.phrase,
          line: firstLine(p.intent),
        },
        match: [p.phrase, slug].join(" ").toLowerCase(),
        section: sort === "term" ? first : "",
      };
    });
    if (sort === "alpha") flat = true;
    else {
      const firsts = [...new Set(candidates.map((c) => c.section))];
      sections = firsts
        .map((key) => ({
          key,
          label: key ? (substrate.terms[key]?.term ?? key) : "unlinked",
        }))
        .sort((a, b) => a.label.localeCompare(b.label));
    }
  } else if (view === "concept-relations") {
    candidates = substrate.edgeOrder.map((id) => {
      const e = substrate.edges[id];
      const from = substrate.terms[e.from]?.term ?? e.from;
      const to = substrate.terms[e.to]?.term ?? e.to;
      return {
        row: {
          rowType: "entry",
          id,
          href: e.href,
          headword: `${from} → ${to}`,
          line: firstLine(e.gloss),
        },
        match: [from, to, e.from, e.to, e.type].join(" ").toLowerCase(),
        section: e.type,
      };
    });
    const types = [...new Set(candidates.map((c) => c.section))];
    sections = types.map((t) => ({ key: t, label: t }));
  } else {
    candidates = substrate.chapterOrder.map((id) => {
      const c = substrate.chapters[id];
      return {
        row: {
          rowType: "entry",
          id,
          href: c.href,
          headword: c.title,
          kind: c.kind === "code" ? "code" : undefined,
          number: c.number,
          states: c.states,
        },
        match: [c.title, c.slug, id].join(" ").toLowerCase(),
        section: c.group,
      };
    });
    sections = substrate.register.groups.map((g) => ({
      key: g.id,
      label: g.label,
    }));
    if (staleOnly) {
      candidates = candidates.filter((c) =>
        Object.values(c.row.states ?? {}).includes("stale"),
      );
    }
  }

  const total = candidates.length;
  const kept = needle
    ? candidates.filter((c) => c.match.includes(needle))
    : candidates;

  const rows: IndexRow[] = flat
    ? kept.map((c) => c.row)
    : sectionize(kept, sections);

  return {
    rows,
    entryIds: kept.map((c) => c.row.id),
    visible: kept.length,
    total,
  };
}
