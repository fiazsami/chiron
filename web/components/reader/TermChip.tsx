"use client";

// A term chip that opens the bit modal instead of navigating — the client
// island used inside server-rendered pages (chapter aside). Falls back to
// an inert span when no shell context is present.

import { useLookup } from "./lookup-context";

export default function TermChip({
  corpus,
  register,
  slug,
  name,
}: {
  corpus: string;
  register: string;
  slug: string;
  name: string;
}) {
  const lookup = useLookup();
  if (!lookup) {
    return <span className="mini-badge term-chip">{name}</span>;
  }
  return (
    <button
      className="mini-badge term-chip"
      onClick={() => lookup.openBit({ corpus, register, kind: "term", id: slug })}
    >
      {name}
    </button>
  );
}
