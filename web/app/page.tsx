import Link from "next/link";
import {
  getManifest,
  totalsLine,
  type ManifestCorpus,
} from "@/lib/content";

export const dynamic = "force-dynamic";

export default async function IndexPage() {
  const manifest = await getManifest();

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

  // One manifest entry per (corpus, register); group them by corpus. The
  // middle pane owns chapter browsing — this page is just the landing with
  // one card per register.
  const corpora = new Map<string, ManifestCorpus[]>();
  for (const c of manifest.corpora) {
    corpora.set(c.name, [...(corpora.get(c.name) ?? []), c]);
  }

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
        <div key={name} className="dimension-cards">
          {registers.map((corpus) => {
            const key = `${corpus.name}/${corpus.register}`;
            const totals = totalsLine(corpus);
            return (
              <Link key={key} className="dimension-card" href={`/${key}`}>
                <span className="dimension-card-head">
                  {corpus.title}
                  <span className="muted">· {corpus.register}</span>
                </span>
                {corpus.label && <span className="muted">{corpus.label}</span>}
                {totals && (
                  <span className="dimension-card-state muted">{totals}</span>
                )}
              </Link>
            );
          })}
        </div>
      ))}
    </>
  );
}
