import Link from "next/link";
import { notFound } from "next/navigation";
import {
  DIMENSIONS,
  DIMENSION_COUNT_KEYS,
  DIMENSION_LABELS,
  DIMENSION_SEGMENTS,
  accentClass,
  chapterHref,
  findCorpus,
  getManifest,
} from "@/lib/content";

export const dynamic = "force-dynamic";

interface Params {
  params: Promise<{ corpus: string; register: string }>;
}

export async function generateMetadata({ params }: Params) {
  const { corpus, register } = await params;
  const entry = findCorpus(await getManifest(), corpus, register);
  return {
    title: entry ? `${entry.title} · ${entry.register} · chiron` : "chiron",
  };
}

export default async function RegisterPage({ params }: Params) {
  const { corpus: name, register } = await params;
  const manifest = await getManifest();
  const corpus = findCorpus(manifest, name, register);
  if (!corpus) notFound();

  const chapters = manifest.chapters.filter(
    (c) => c.corpus === name && c.register === register,
  );
  const tracked = DIMENSIONS.filter((d) => d in corpus.data);

  return (
    <>
      <nav className="crumbs">
        <Link href="/">&larr; All corpora</Link>
      </nav>
      <header className="index-header">
        <h1>
          {corpus.title} <span className="muted">· {corpus.register}</span>
        </h1>
        {corpus.label && <p className="description">{corpus.label}</p>}
        <p className="mini-badges hub-modes">
          {tracked.map((d) => (
            <span key={d} className="mini-badge">
              {d}
            </span>
          ))}
          {corpus.recorded_modes.map((m) => (
            <span key={m} className="mini-badge recorded">
              {m} (recorded)
            </span>
          ))}
        </p>
      </header>

      <div className="dimension-cards">
        {tracked.map((d) => {
          const state = corpus.data[d]!.state;
          const count = corpus.totals[DIMENSION_COUNT_KEYS[d]] ?? 0;
          return (
            <Link
              key={d}
              className="dimension-card"
              href={`/${name}/${register}/${DIMENSION_SEGMENTS[d]}`}
            >
              <span className="dimension-card-head">
                <span className={`status-dot ${state}`} title={state} />
                {DIMENSION_LABELS[d]}
              </span>
              <span className="dimension-card-count">
                {count} {DIMENSION_COUNT_KEYS[d]}
              </span>
              <span className="dimension-card-state muted">{state}</span>
            </Link>
          );
        })}
      </div>

      {corpus.groups.map((group) => {
        const groupChapters = chapters.filter((c) => c.group === group.id);
        if (groupChapters.length === 0) return null;
        const accent = accentClass(manifest, name, register, group.id);
        return (
          <section key={group.id} className={`group-section ${accent}`}>
            <h2>{group.label}</h2>
            <div className="chapter-list">
              {groupChapters.map((c) => (
                <Link key={c.id} className="chapter-row" href={chapterHref(c)}>
                  {tracked.map((d) => (
                    <span
                      key={d}
                      className={`status-dot ${c.states[d]}`}
                      title={`${DIMENSION_LABELS[d]}: ${c.states[d]}`}
                    />
                  ))}
                  <span className="chapter-num">{c.number}</span>
                  <span className="chapter-title">{c.title}</span>
                </Link>
              ))}
            </div>
          </section>
        );
      })}
    </>
  );
}
