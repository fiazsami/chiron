"use client";

import type { RegisterSubstrate, TermVM } from "@/lib/substrate-types";
import Evidence from "./Evidence";
import Reference from "./Reference";
import Section from "./Section";

// The full term entry: every required attribute, all anchors (1-8, no
// viewer cap), and every inverse relationship (phrasings, edges, mentions).

function EdgeLine({
  substrate,
  edgeId,
  endpoint,
}: {
  substrate: RegisterSubstrate;
  edgeId: string;
  endpoint: "from" | "to";
}) {
  const edge = substrate.edges[edgeId];
  const other = endpoint === "to" ? edge.from : edge.to;
  const term = substrate.terms[other];
  return (
    <li className="relation-line">
      <span className="edge-type">{edge.type}</span>
      <span>
        {term ? (
          <Reference href={term.href} headword={term.term} kind="term">
            {term.term}
          </Reference>
        ) : (
          other
        )}
        <span className="gloss">{edge.gloss}</span>
      </span>
    </li>
  );
}

export default function TermEntry({
  substrate,
  term,
}: {
  substrate: RegisterSubstrate;
  term: TermVM;
}) {
  const definedIn = substrate.chapters[term.definedIn];
  const mentioned = term.mentionedIn
    .map((id) => substrate.chapters[id])
    .filter(Boolean);

  return (
    <article className="entry-body">
      <header>
        <div className="entry-headline">
          <h1 className="entry-headword">{term.term}</h1>
          <span className="entry-kind">{term.kind}</span>
          <span className="entry-slug">{term.slug}</span>
        </div>
        <div className="entry-reading">{term.definition}</div>
        {term.aliases.length > 0 && (
          <p className="entry-aliases">Also written: {term.aliases.join(", ")}</p>
        )}
      </header>

      {definedIn && (
        <Section title="Defined in">
          <p className="entry-reading" style={{ marginTop: 0 }}>
            <Reference
              href={definedIn.href}
              headword={definedIn.title}
              kind="chapter"
            >
              {definedIn.title}
            </Reference>
          </p>
        </Section>
      )}

      <Section title="Evidence" count={term.anchors.length}>
        {term.anchors.map((a, i) => (
          <Evidence key={i} anchor={a} />
        ))}
      </Section>

      {term.phrasings.length > 0 && (
        <Section title="Phrasings" count={term.phrasings.length}>
          <ul>
            {term.phrasings.map((slug) => {
              const p = substrate.phrases[slug];
              if (!p) return null;
              return (
                <li key={slug} className="phrasing-row">
                  <Reference href={p.href} headword={p.phrase} kind="phrase">
                    {p.phrase}
                  </Reference>
                  <span className="intent">{p.intent}</span>
                </li>
              );
            })}
          </ul>
        </Section>
      )}

      {(term.edgesOut.length > 0 || term.edgesIn.length > 0) && (
        <Section
          title="Relations"
          count={term.edgesOut.length + term.edgesIn.length}
        >
          <div className="relation-columns">
            <div className="relation-column">
              <h3>this → others</h3>
              <ul>
                {term.edgesOut.map((id) => (
                  <EdgeLine
                    key={id}
                    substrate={substrate}
                    edgeId={id}
                    endpoint="from"
                  />
                ))}
              </ul>
            </div>
            <div className="relation-column">
              <h3>others → this</h3>
              <ul>
                {term.edgesIn.map((id) => (
                  <EdgeLine
                    key={id}
                    substrate={substrate}
                    edgeId={id}
                    endpoint="to"
                  />
                ))}
              </ul>
            </div>
          </div>
        </Section>
      )}

      {mentioned.length > 0 && (
        <Section title="Mentioned in" count={mentioned.length}>
          <ul>
            {mentioned.map((c) => (
              <li key={c.id} className="phrasing-row">
                <Reference href={c.href} headword={c.title} kind="chapter">
                  {c.title}
                </Reference>
              </li>
            ))}
          </ul>
        </Section>
      )}
    </article>
  );
}
