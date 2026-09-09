"use client";

import { DIMENSION_COUNT_KEYS, DIMENSION_LABELS } from "@/lib/dimensions";
import type { EntryModel, ViewKey } from "@/lib/shell/route";
import type { RegisterSubstrate } from "@/lib/substrate-types";
import ChapterEntry from "./ChapterEntry";
import EdgeEntry from "./EdgeEntry";
import PhraseEntry from "./PhraseEntry";
import TermEntry from "./TermEntry";

// Dispatches the entry pane on the parsed location; when nothing is open,
// a one-sentence hint of what to do next (empty-state textRole).

function IndexHint({
  substrate,
  view,
}: {
  substrate: RegisterSubstrate;
  view: ViewKey | null;
}) {
  const reg = substrate.register;
  let message: React.ReactNode;
  if (!view) {
    message = <>Pick a dimension — keys 1–4.</>;
  } else if (view === "chapters") {
    message = <>No chapter open. j/k to move in the index, ↵ to open.</>;
  } else if (!reg.modes.includes(view)) {
    message = reg.recordedModes.includes(view) ? (
      <>
        {DIMENSION_LABELS[view]} is recorded for this register — methodology
        written, nothing extracted yet.
      </>
    ) : (
      <>{DIMENSION_LABELS[view]} is not tracked by this register.</>
    );
  } else if ((reg.totals[DIMENSION_COUNT_KEYS[view]] ?? 0) === 0) {
    message = (
      <>
        0 {DIMENSION_COUNT_KEYS[view]} — author via <code>/translate</code>.
      </>
    );
  } else {
    message = (
      <>
        No entry open. j/k to move in the index, ↵ to open, / filters,{" "}
        <code>⌘K</code> jumps anywhere.
      </>
    );
  }
  return (
    <div className="entry-body">
      <p className="empty-state">{message}</p>
    </div>
  );
}

export default function EntryPane({
  substrate,
  entry,
  view,
}: {
  substrate: RegisterSubstrate;
  entry: EntryModel | null;
  view: ViewKey | null;
}) {
  if (!entry) return <IndexHint substrate={substrate} view={view} />;
  switch (entry.kind) {
    case "term":
      return <TermEntry substrate={substrate} term={entry.term} />;
    case "phrase":
      return <PhraseEntry substrate={substrate} phrase={entry.phrase} />;
    case "edge":
      return <EdgeEntry substrate={substrate} edge={entry.edge} />;
    case "chapter":
      return <ChapterEntry substrate={substrate} chapter={entry.chapter} />;
  }
}
