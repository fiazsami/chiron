"use client";

import type { PhraseVM, RegisterSubstrate } from "@/lib/substrate-types";
import Evidence from "./Evidence";
import Reference from "./Reference";
import Section from "./Section";
import TemplateBlock from "./TemplateBlock";

export default function PhraseEntry({
  substrate,
  phrase,
}: {
  substrate: RegisterSubstrate;
  phrase: PhraseVM;
}) {
  return (
    <article className="entry-body">
      <header>
        <div className="entry-headline">
          <h1 className="entry-headword">{phrase.phrase}</h1>
          <span className="entry-slug">{phrase.slug}</span>
        </div>
        <div className="entry-reading">{phrase.intent}</div>
      </header>

      {phrase.template && (
        <Section title="Template">
          <TemplateBlock template={phrase.template} />
        </Section>
      )}

      <Section title="Terms used" count={phrase.terms.length}>
        <p className="entry-reading" style={{ marginTop: 0 }}>
          {phrase.terms.map((slug, i) => {
            const t = substrate.terms[slug];
            return (
              <span key={slug}>
                {i > 0 && ", "}
                {t ? (
                  <Reference
                    href={t.href}
                    headword={t.term}
                    kind="term"
                    className="term-chip"
                  >
                    {t.term}
                    <span className="kind">{t.kind}</span>
                  </Reference>
                ) : (
                  slug
                )}
              </span>
            );
          })}
        </p>
      </Section>

      <Section title="Evidence" count={phrase.anchors.length}>
        {phrase.anchors.map((a, i) => (
          <Evidence key={i} anchor={a} />
        ))}
      </Section>
    </article>
  );
}
