import Link from "next/link";
import { notFound } from "next/navigation";
import Anchors from "@/components/Anchors";
import {
  chapterByLocalId,
  chapterHref,
  findCorpus,
  getManifest,
} from "@/lib/content";
import { getLexicon, getPhrasebook, getRelations } from "@/lib/lingua";

export const dynamic = "force-dynamic";

interface Params {
  params: Promise<{ corpus: string; register: string; term: string }>;
}

export async function generateMetadata({ params }: Params) {
  const { corpus, register, term } = await params;
  const entry = findCorpus(await getManifest(), corpus, register);
  if (!entry) return { title: "chiron" };
  const lexicon = await getLexicon(entry);
  const t = lexicon[term];
  return { title: t ? `${t.term} · ${entry.title} · chiron` : "chiron" };
}

export default async function TermPage({ params }: Params) {
  const { corpus: name, register, term: slug } = await params;
  const manifest = await getManifest();
  const corpus = findCorpus(manifest, name, register);
  if (!corpus) notFound();
  const [lexicon, phrasebook, relations] = await Promise.all([
    getLexicon(corpus),
    getPhrasebook(corpus),
    getRelations(corpus),
  ]);
  const entry = lexicon[slug];
  if (!entry) notFound();

  const definedIn = chapterByLocalId(manifest, name, register, entry.defined_in);
  const phrasings = Object.entries(phrasebook).filter(([, p]) =>
    p.terms.includes(slug),
  );
  const outgoing = relations.filter((e) => e.from === slug);
  const incoming = relations.filter((e) => e.to === slug);
  const termHref = (s: string) => `/${name}/${register}/lexicon/${s}`;
  const termName = (s: string) => lexicon[s]?.term ?? s;

  return (
    <>
      <nav className="crumbs">
        <Link href={`/${name}/${register}/lexicon`}>&larr; Lexicon</Link>
      </nav>
      <article className="card term-detail">
        <h1>
          {entry.term} <span className="mini-badge">{entry.kind}</span>
        </h1>
        <p className="term-slug muted">
          <code>{slug}</code> · defined in{" "}
          {definedIn ? (
            <Link href={chapterHref(definedIn)}>{definedIn.title}</Link>
          ) : (
            entry.defined_in
          )}
        </p>
        <p className="term-full-definition">{entry.definition}</p>
        {entry.aliases && entry.aliases.length > 0 && (
          <p className="muted">Also known as: {entry.aliases.join(", ")}.</p>
        )}

        <h2>Anchors</h2>
        <Anchors
          anchors={entry.anchors}
          manifest={manifest}
          corpus={name}
          register={register}
        />

        {phrasings.length > 0 && (
          <>
            <h2>Phrasings using this term</h2>
            <ul className="term-phrasings">
              {phrasings.map(([pslug, p]) => (
                <li key={pslug}>
                  <Link href={`/${name}/${register}/phrasebook`}>
                    {p.phrase}
                  </Link>{" "}
                  <span className="muted">— {p.intent}</span>
                </li>
              ))}
            </ul>
          </>
        )}

        {(outgoing.length > 0 || incoming.length > 0) && (
          <>
            <h2>Relations</h2>
            <ul className="relation-neighborhood">
              {outgoing.map((e, i) => (
                <li key={`out-${i}`} className="relation-line">
                  <span className="relation-arrow">
                    —{e.type}&rarr;{" "}
                    <Link href={termHref(e.to)}>{termName(e.to)}</Link>
                  </span>
                  <span className="muted">{e.gloss}</span>
                </li>
              ))}
              {incoming.map((e, i) => (
                <li key={`in-${i}`} className="relation-line">
                  <span className="relation-arrow">
                    <Link href={termHref(e.from)}>{termName(e.from)}</Link>{" "}
                    —{e.type}&rarr;
                  </span>
                  <span className="muted">{e.gloss}</span>
                </li>
              ))}
            </ul>
          </>
        )}
      </article>
    </>
  );
}
