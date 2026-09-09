"use client";

import { DIMENSION_LABELS, type Dimension } from "@/lib/dimensions";
import type { ChapterVM, RegisterSubstrate } from "@/lib/substrate-types";
import Reference from "./Reference";
import Section from "./Section";

// The chapter entry replaces the generated-markdown article: the same
// information, typed per contentKind instead of flattened into bullets.

export default function ChapterEntry({
  substrate,
  chapter,
}: {
  substrate: RegisterSubstrate;
  chapter: ChapterVM;
}) {
  const modes = substrate.register.modes;
  const stale = modes.filter((d) => chapter.states[d] === "stale");
  const registerKey = substrate.register.key;

  const termRow = (slug: string, note?: string) => {
    const t = substrate.terms[slug];
    if (!t) return null;
    return (
      <li key={slug} className="phrasing-row">
        <Reference href={t.href} headword={t.term} kind="term">
          {t.term}
        </Reference>
        <span className="intent">
          {note ?? t.definition.split("\n", 1)[0]}
        </span>
      </li>
    );
  };

  return (
    <article className="entry-body">
      <header>
        <div className="entry-headline">
          <h1 className="entry-headword">{chapter.title}</h1>
          <span className="entry-meta">
            {chapter.groupLabel} · {chapter.number}
          </span>
          {chapter.kind === "code" && <span className="entry-kind">code</span>}
        </div>
        {chapter.description && (
          <div className="entry-reading">{chapter.description}</div>
        )}
      </header>

      <Section title="Provenance">
        <div className="provenance-block">
          {chapter.sourcePaths.map((p, i) => (
            <div key={p}>
              source/{p}
              {i === 0 && chapter.sourcePaths.length > 1 ? "  (primary)" : ""}
            </div>
          ))}
          {chapter.sourceUrl && (
            <div>
              <a href={chapter.sourceUrl} target="_blank" rel="noopener noreferrer">
                {chapter.sourceUrl.replace(/^https?:\/\//, "")}
              </a>{" "}
              <span className="keycap">o</span>
            </div>
          )}
          <div>
            content <span className="hash">{chapter.contentHash}</span>
          </div>
        </div>
      </Section>

      <Section title="State">
        {modes.every((d) => chapter.states[d] === "ok") ? (
          // Healthy state stays quiet: one compact line, detail on drift only.
          <p className="phrasing-row">
            <span className="state-dots">
              {modes.map((d) => (
                <i
                  key={d}
                  className="ok"
                  title={`${DIMENSION_LABELS[d as Dimension]}: ok`}
                />
              ))}
            </span>{" "}
            <span className="intent">all ok</span>
          </p>
        ) : (
          <>
            <ul>
              {modes.map((d) => {
                const state = chapter.states[d] ?? "none";
                const staleCount = chapter.staleAnchors[d] ?? 0;
                return (
                  <li key={d} className="phrasing-row">
                    <span className="state-dots">
                      <i
                        className={state}
                        title={`${DIMENSION_LABELS[d as Dimension]}: ${state}`}
                      />
                    </span>{" "}
                    <span className="intent">
                      {DIMENSION_LABELS[d as Dimension]} — {state}
                      {staleCount > 0 &&
                        `, ${staleCount} stale anchor${staleCount === 1 ? "" : "s"}`}
                    </span>
                  </li>
                );
              })}
            </ul>
            {stale.length > 0 && (
              <div style={{ marginTop: 12 }}>
                {stale.map((d) => (
                  <p key={d} className="repair-line">
                    {DIMENSION_LABELS[d as Dimension]} drifted — re-author via{" "}
                    <code>
                      /translate {registerKey}/{chapter.id}
                    </code>{" "}
                    or review and run{" "}
                    <code>
                      uv run python -m tools.lingua accept-drift {registerKey}/
                      {chapter.id} --mode {d}
                    </code>
                  </p>
                ))}
              </div>
            )}
          </>
        )}
      </Section>

      {chapter.defines.length > 0 && (
        <Section title="Defines" count={chapter.defines.length}>
          <ul>{chapter.defines.map((slug) => termRow(slug))}</ul>
        </Section>
      )}

      {chapter.mentions.length > 0 && (
        <Section title="Mentions" count={chapter.mentions.length}>
          <ul>
            {chapter.mentions.map((slug) => {
              const t = substrate.terms[slug];
              const definedIn = t
                ? substrate.chapters[t.definedIn]
                : undefined;
              return termRow(
                slug,
                definedIn ? `defined in ${definedIn.title}` : undefined,
              );
            })}
          </ul>
        </Section>
      )}

      {chapter.phrases.length > 0 && (
        <Section title="Phrasings" count={chapter.phrases.length}>
          <ul>
            {chapter.phrases.map((slug) => {
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

      {chapter.edges.length > 0 && (
        <Section title="Relations" count={chapter.edges.length}>
          <ul>
            {chapter.edges.map((id) => {
              const e = substrate.edges[id];
              const from = substrate.terms[e.from]?.term ?? e.from;
              const to = substrate.terms[e.to]?.term ?? e.to;
              return (
                <li key={id} className="relation-line">
                  <div>
                    <span className="edge-type">{e.type}</span>{" "}
                    <Reference
                      href={e.href}
                      headword={`${from} → ${to}`}
                      kind="edge"
                    >
                      {from} → {to}
                    </Reference>
                  </div>
                  <div className="gloss">{e.gloss}</div>
                </li>
              );
            })}
          </ul>
        </Section>
      )}
    </article>
  );
}
