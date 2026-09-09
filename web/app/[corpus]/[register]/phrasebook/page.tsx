import Link from "next/link";
import { notFound } from "next/navigation";
import Anchors from "@/components/Anchors";
import { findCorpus, getManifest } from "@/lib/content";
import { getLexicon, getPhrasebook } from "@/lib/lingua";

export const dynamic = "force-dynamic";

interface Params {
  params: Promise<{ corpus: string; register: string }>;
}

export async function generateMetadata({ params }: Params) {
  const { corpus, register } = await params;
  const entry = findCorpus(await getManifest(), corpus, register);
  return { title: entry ? `Phrasebook · ${entry.title} · chiron` : "chiron" };
}

export default async function PhrasebookPage({ params }: Params) {
  const { corpus: name, register } = await params;
  const manifest = await getManifest();
  const corpus = findCorpus(manifest, name, register);
  if (!corpus || !("phrasebook" in corpus.data)) notFound();
  const [phrasebook, lexicon] = await Promise.all([
    getPhrasebook(corpus),
    getLexicon(corpus),
  ]);
  const entries = Object.entries(phrasebook).sort(([a], [b]) =>
    a.localeCompare(b),
  );

  return (
    <>
      <nav className="crumbs">
        <Link href={`/${name}/${register}`}>
          &larr; {corpus.title} · {register}
        </Link>
      </nav>
      <header className="index-header">
        <h1>Phrasebook</h1>
        <p className="description">
          {entries.length} phrasings — how to say it when instructing an agent
          about this corpus.
        </p>
      </header>
      {entries.length === 0 ? (
        <p className="muted">
          Nothing extracted yet. Author entries via <code>/translate</code>.
        </p>
      ) : (
        entries.map(([slug, phrase]) => (
          <article key={slug} className="card phrase-entry">
            <h2 className="phrase-text">{phrase.phrase}</h2>
            <p className="phrase-intent muted">{phrase.intent}</p>
            {phrase.template && (
              <pre className="phrase-template">
                <code>{phrase.template}</code>
              </pre>
            )}
            <p className="mini-badges">
              {phrase.terms.map((t) => (
                <Link
                  key={t}
                  className="mini-badge term-chip"
                  href={`/${name}/${register}/lexicon/${t}`}
                >
                  {lexicon[t]?.term ?? t}
                </Link>
              ))}
            </p>
            <Anchors
              anchors={phrase.anchors}
              manifest={manifest}
              corpus={name}
              register={register}
            />
          </article>
        ))
      )}
    </>
  );
}
