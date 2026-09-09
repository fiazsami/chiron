"use client";

import { RELATION_TYPE_MEANINGS } from "@/lib/lingua-types";
import type { EdgeVM, RegisterSubstrate } from "@/lib/substrate-types";
import Evidence from "./Evidence";
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

  // Other edges sharing either endpoint, grouped by type.
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

      <Section title="Evidence" count={edge.anchors.length}>
        {edge.anchors.map((a, i) => (
          <Evidence key={i} anchor={a} />
        ))}
      </Section>

      {neighborhood.size > 0 && (
        <Section title="Neighborhood" count={seen.size - 1}>
          {[...neighborhood.entries()].map(([type, list]) => (
            <ul key={type} style={{ marginBottom: 8 }}>
              {list.map((e) => (
                <li key={e.id} className="relation-line">
                  <span className="edge-type">{type}</span>
                  <span>
                    <Reference
                      href={e.href}
                      headword={`${substrate.terms[e.from]?.term ?? e.from} → ${substrate.terms[e.to]?.term ?? e.to}`}
                      kind="edge"
                    >
                      {substrate.terms[e.from]?.term ?? e.from} →{" "}
                      {substrate.terms[e.to]?.term ?? e.to}
                    </Reference>
                    <span className="gloss">{e.gloss}</span>
                  </span>
                </li>
              ))}
            </ul>
          ))}
        </Section>
      )}
    </article>
  );
}
