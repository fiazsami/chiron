import Link from "next/link";
import {
  accentClass,
  getManifest,
  type ManifestChapter,
  type ManifestCorpus,
} from "@/lib/content";

export const dynamic = "force-dynamic";

function summary(counts: Map<string, number>, order: string[]): string {
  return order
    .filter((s) => counts.get(s))
    .map((s) => `${counts.get(s)} ${s === "fallback" ? "auto" : s}`)
    .join(", ");
}

function tally(chapters: ManifestChapter[], pick: (c: ManifestChapter) => string) {
  const counts = new Map<string, number>();
  for (const c of chapters) {
    const key = pick(c);
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return counts;
}

const MAX_MINI_BADGES = 5;

export default async function IndexPage() {
  const manifest = await getManifest();
  const chapters = manifest.chapters;
  const labs = chapters.filter((c) => c.lab !== null).length;
  const facts = summary(
    tally(chapters, (c) => c.content.facts),
    ["ok", "stale", "none"],
  );
  const schematics = summary(
    tally(chapters, (c) => c.content.schematic),
    ["ok", "stale", "fallback", "none"],
  );

  const freq = new Map<string, number>();
  for (const c of chapters)
    for (const comp of c.components) freq.set(comp, (freq.get(comp) ?? 0) + 1);
  const componentFreq = [...freq.entries()].sort((a, b) => b[1] - a[1]);
  const maxCount = componentFreq[0]?.[1] ?? 1;

  // One manifest entry per (corpus, register); group them by corpus.
  const corpora = new Map<string, ManifestCorpus[]>();
  for (const s of manifest.corpora) {
    corpora.set(s.name, [...(corpora.get(s.name) ?? []), s]);
  }
  const multiCorpus = corpora.size > 1;

  if (manifest.corpora.length === 0) {
    return (
      <header className="index-header">
        <h1>chiron</h1>
        <p className="description">
          No corpora mounted yet. In Claude Code, run{" "}
          <code>/mount &lt;repo-url&gt;</code> to mount one, then build its
          notes with <code>uv run python -m tools.notes</code> and refresh this
          page.
        </p>
      </header>
    );
  }

  return (
    <>
      <header className="index-header">
        <h1>chiron</h1>
        <p className="description">
          Curated notes — key facts and flow schematics — retold from each
          mounted corpus. {chapters.length} chapters · {labs} labs · key
          facts: {facts} · schematics: {schematics}.
        </p>
      </header>

      {[...corpora.entries()].map(([name, registers]) => (
        <div key={name}>
          {multiCorpus && (
            <h2 className="corpus-heading">{registers[0].title}</h2>
          )}
          {registers.map((corpus: ManifestCorpus) => (
            <div key={`${corpus.name}/${corpus.register}`}>
              {(registers.length > 1 || corpus.label) && (
                <h3 className="register-heading">
                  {corpus.register}
                  {corpus.label ? ` — ${corpus.label}` : ""}{" "}
                  <span className="mini-badges">
                    {corpus.modes.map((m) => (
                      <span key={m} className="mini-badge">
                        {m}
                      </span>
                    ))}
                  </span>
                </h3>
              )}
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
                    key={`${corpus.name}/${corpus.register}/${group.id}`}
                    className={`group-section ${accent}`}
                  >
                    <h2>{group.label}</h2>
                    <div className="chapter-list">
                      {groupChapters.map((c) => {
                        const badges = c.components.slice(0, MAX_MINI_BADGES);
                        const extra = c.components.length - MAX_MINI_BADGES;
                        return (
                          <Link
                            key={c.id}
                            className="chapter-row"
                            href={`/${c.corpus}/${c.register}/${c.group}/${c.slug}`}
                          >
                            <span
                              className={`status-dot ${c.content.facts}`}
                              title={`key facts: ${c.content.facts}`}
                            />
                            <span
                              className={`status-dot ${c.content.schematic}`}
                              title={`schematic: ${c.content.schematic}`}
                            />
                            <span className="chapter-num">
                              {c.slug.split("-")[0]}
                            </span>
                            <span className="chapter-title">{c.title}</span>
                            <span className="mini-badges">
                              {badges.map((comp) => (
                                <span key={comp} className="mini-badge">
                                  {comp}
                                </span>
                              ))}
                              {extra > 0 && (
                                <span className="mini-badge">+{extra}</span>
                              )}
                              {c.lab === null && corpus.has_labs && (
                                <span className="mini-badge concept">
                                  concept
                                </span>
                              )}
                            </span>
                          </Link>
                        );
                      })}
                    </div>
                  </section>
                );
              })}
            </div>
          ))}
        </div>
      ))}

      {componentFreq.length > 0 && (
        <section className="card">
          <h2>Component frequency</h2>
          <div className="freq">
            {componentFreq.map(([comp, count]) => (
              <div key={comp} className="freq-row">
                <span className="freq-label">{comp}</span>
                <span className="freq-bar">
                  <span
                    className="freq-fill"
                    style={{ width: `${Math.round((100 * count) / maxCount)}%` }}
                  />
                </span>
                <span className="freq-count">{count}</span>
              </div>
            ))}
          </div>
        </section>
      )}
    </>
  );
}
