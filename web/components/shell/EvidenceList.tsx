"use client";

import { useState } from "react";
import { EVIDENCE_VISIBLE, type AnchorGroup } from "@/lib/shell/evidence";
import Evidence from "./Evidence";

// The Evidence section body: first 6 quote-groups, the rest behind an
// expander. Mount keyed by the entry (parents pass key={slug}) so the
// expansion never leaks across entries.

export default function EvidenceList({ groups }: { groups: AnchorGroup[] }) {
  const [expanded, setExpanded] = useState(false);
  const visible = expanded ? groups : groups.slice(0, EVIDENCE_VISIBLE);
  const hidden = groups.length - visible.length;

  return (
    <>
      {visible.map((g, i) => (
        <Evidence key={i} group={g} />
      ))}
      {hidden > 0 && (
        <button
          type="button"
          className="evidence-more"
          onClick={() => setExpanded(true)}
        >
          {hidden} more quote{hidden === 1 ? "" : "s"}
        </button>
      )}
    </>
  );
}
