import Link from "next/link";
import { notFound } from "next/navigation";
import Anchors from "@/components/Anchors";
import { findCorpus, getManifest } from "@/lib/content";
import { getLexicon, getPhrasebook } from "@/lib/lingua";

export const dynamic = "force-dynamic";

interface Params {
  params: Promise<{ corpus: string; register: string; phrase: string }>;
}

export async function generateMetadata({ params }: Params) {
  const { corpus, register, phrase } = await params;
  const entry = findCorpus(await getManifest(), corpus, register);
  if (!entry) return { title: "chiron" };
  const phrasebook = await getPhrasebook(entry);
  const p = phrasebook[phrase];
  return { title: p ? `${p.phrase} · ${entry.title} · chiron` : "chiron" };
}

// One phrasing — an individually-addressable bit, reached via smart lookup
// or ⌘K (there is no phrasebook index page).
export default async function PhrasePage({ params }: Params) {
  const { corpus: name, register, phrase: slug } = await params;
  const manifest = await getManifest();
  const corpus = findCorpus(manifest, name, register);
  if (!corpus || !("phrasebook" in corpus.data)) notFound();
  const [phrasebook, lexicon] = await Promise.all([
    getPhrasebook(corpus),
    getLexicon(corpus),
  ]);
  const phrase = phrasebook[slug];
  if (!phrase) notFound();

  return (
    <article className="card phrase-entry">
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
  );
}
