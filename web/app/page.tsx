import Link from "next/link";
import {
  DIMENSIONS,
  DIMENSION_LABELS,
  accentClass,
  chapterHref,
  getManifest,
  totalsLine,
  type ManifestCorpus,
} from "@/lib/content";

export const dynamic = "force-dynamic";

export default async function IndexPage() {
  const manifest = await getManifest();
  const chapters = manifest.chapters;

  if (manifest.corpora.length === 0) {
    return (
      <header className="index-header">
        <h1>chiron</h1>
        <p className="description">
          No corpora mounted yet. In Claude Code, run{" "}
          <code>/mount &lt;repo-url&gt;</code> to mount one, then build its
          pages with <code>uv run python -m tools.lingua</code> and refresh
          this page.
        </p>
      </header>
    );
  }

  // One manifest entry per (corpus, register); group them by corpus.
  const corpora = new Map<string, ManifestCorpus[]>();
  for (const c of manifest.corpora) {
    corpora.set(c.name, [...(corpora.get(c.name) ?? []), c]);
  }
  const multiCorpus = corpora.size > 1;

  return (
    <>
      <header className="index-header">
        <h1>chiron</h1>
        <p className="description">
          The linguistic structure — lexicon, phrasebook, concept relations —
          extracted from each mounted corpus.
        </p>
      </header>

      {[...corpora.entries()].map(([name, registers]) => (
        <div key={name}>
          {multiCorpus && (
            <h2 className="corpus-heading">{registers[0].title}</h2>
          )}
          {registers.map((corpus) => {
            const key = `${corpus.name}/${corpus.register}`;
            const totals = totalsLine(corpus);
            return (
              <div key={key}>
                <h3 className="register-heading">
                  <Link href={`/${key}`}>
                    {multiCorpus ? corpus.register : `${corpus.title} · ${corpus.register}`}
                  </Link>
                  {corpus.label ? (
                    <span className="register-label"> — {corpus.label}</span>
                  ) : null}
                  {totals ? <span className="register-totals">{totals}</span> : null}
                </h3>
                {corpus.groups.map((group) => {
                  const groupChapters = chapters.filter(
                    (c) =>
                      c.corpus === corpus.name &&
                      c.register === corpus.register &&
                      c.group === group.id,
                  );
                  if (groupChapters.length === 0) return null;
                  const accent = accentClass(
                    manifest,
                    corpus.name,
                    corpus.register,
                    group.id,
                  );
                  return (
                    <section
                      key={`${key}/${group.id}`}
                      className={`group-section ${accent}`}
                    >
                      <h2>{group.label}</h2>
                      <div className="chapter-list">
                        {groupChapters.map((c) => (
                          <Link
                            key={c.id}
                            className="chapter-row"
                            href={chapterHref(c)}
                          >
                            {DIMENSIONS.filter((d) => d in c.states).map(
                              (d) => (
                                <span
                                  key={d}
                                  className={`status-dot ${c.states[d]}`}
                                  title={`${DIMENSION_LABELS[d]}: ${c.states[d]}`}
                                />
                              ),
                            )}
                            <span className="chapter-num">{c.number}</span>
                            <span className="chapter-title">{c.title}</span>
                          </Link>
                        ))}
                      </div>
                    </section>
                  );
                })}
              </div>
            );
          })}
        </div>
      ))}
    </>
  );
}
