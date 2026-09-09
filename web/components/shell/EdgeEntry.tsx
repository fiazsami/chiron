"use client";

import { useMemo } from "react";
import { RELATION_TYPE_MEANINGS } from "@/lib/lingua-types";
import { groupAnchors } from "@/lib/shell/evidence";
import type { EdgeVM, RegisterSubstrate } from "@/lib/substrate-types";
import EvidenceList from "./EvidenceList";
import Reference from "./Reference";
import Section from "./Section";

export default function EdgeEntry({
  substrate,
  edge,
}: {
  substrate: RegisterSubstrate;
  edge: EdgeVM;
}) {
  const from = substrate.terms[edge.from];
  const to = substrate.terms[edge.to];
  const evidence = useMemo(() => groupAnchors(edge.anchors), [edge]);

  // Other edges sharing either endpoint, grouped by type. Rows never repeat
  // the shared endpoint — arrow + the other end; the gloss carries detail.
  const neighborhood = new Map<string, EdgeVM[]>();
  const seen = new Set([edge.id]);
  for (const t of [from, to]) {
    if (!t) continue;
    for (const id of [...t.edgesOut, ...t.edgesIn]) {
      if (seen.has(id)) continue;
      seen.add(id);
      const e = substrate.edges[id];
      const list = neighborhood.get(e.type);
      if (list) list.push(e);
      else neighborhood.set(e.type, [e]);
    }
  }

  const endpoint = (
    term: typeof from,
    slug: string,
    className?: string,
  ): React.ReactNode =>
    term ? (
      <Reference
        href={term.href}
        headword={term.term}
        kind="term"
        className={className}
      >
        {term.term}
      </Reference>
    ) : (
      slug
    );

  return (
    <article className="entry-body">
      <header>
        <div className="entry-headline">
          <h1 className="entry-headword-edge">
            {endpoint(from, edge.from)}
            <span className="edge-type">—{edge.type}→</span>
            {endpoint(to, edge.to)}
          </h1>
        </div>
        <div className="entry-reading">{edge.gloss}</div>
        <p className="entry-aliases">
          {edge.type}: {RELATION_TYPE_MEANINGS[edge.type]}
        </p>
      </header>

      <Section title="Evidence" count={evidence.length}>
        <EvidenceList key={edge.id} groups={evidence} />
      </Section>

      {neighborhood.size > 0 && (
        <Section title="Neighborhood" count={seen.size - 1}>
          {[...neighborhood.entries()].map(([type, list]) => (
            <div key={type} className="neighborhood-group">
              <h3 className="edge-type">{type}</h3>
              <ul>
                {list.map((e) => {
                  const outgoing =
                    e.from === edge.from || e.from === edge.to;
                  const otherSlug = outgoing ? e.to : e.from;
                  const other = substrate.terms[otherSlug];
                  return (
                    <li key={e.id} className="relation-line">
                      <span className="edge-arrow">
                        {outgoing ? "→" : "←"}
                      </span>{" "}
                      {other ? (
                        <Reference
                          href={e.href}
                          headword={other.term}
                          kind="edge"
                        >
                          {other.term}
                        </Reference>
                      ) : (
                        otherSlug
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </Section>
      )}
    </article>
  );
}
