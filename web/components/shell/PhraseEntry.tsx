"use client";

import { useMemo } from "react";
import { groupAnchors } from "@/lib/shell/evidence";
import type { PhraseVM, RegisterSubstrate } from "@/lib/substrate-types";
import EvidenceList from "./EvidenceList";
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
  const evidence = useMemo(() => groupAnchors(phrase.anchors), [phrase]);
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
        <p className="ref-list">
          {phrase.terms.map((slug) => {
            const t = substrate.terms[slug];
            return t ? (
              <Reference
                key={slug}
                href={t.href}
                headword={t.term}
                kind="term"
                className="term-chip"
                dataKind={t.kind}
                title={t.kind}
              >
                {t.term}
              </Reference>
            ) : (
              <span key={slug}>{slug}</span>
            );
          })}
        </p>
      </Section>

      <Section title="Evidence" count={evidence.length}>
        <EvidenceList key={phrase.slug} groups={evidence} />
      </Section>
    </article>
  );
}
