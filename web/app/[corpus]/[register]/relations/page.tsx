import Link from "next/link";
import { notFound } from "next/navigation";
import { findCorpus, getManifest } from "@/lib/content";
import { RELATION_TYPES, getLexicon, getRelations } from "@/lib/lingua";

export const dynamic = "force-dynamic";

interface Params {
  params: Promise<{ corpus: string; register: string }>;
}

export async function generateMetadata({ params }: Params) {
  const { corpus, register } = await params;
  const entry = findCorpus(await getManifest(), corpus, register);
  return {
    title: entry ? `Concept relations · ${entry.title} · chiron` : "chiron",
  };
}

export default async function RelationsPage({ params }: Params) {
  const { corpus: name, register } = await params;
  const manifest = await getManifest();
  const corpus = findCorpus(manifest, name, register);
  if (!corpus || !("concept-relations" in corpus.data)) notFound();
  const [edges, lexicon] = await Promise.all([
    getRelations(corpus),
    getLexicon(corpus),
  ]);

  const termHref = (s: string) => `/${name}/${register}/lexicon/${s}`;
  const termName = (s: string) => lexicon[s]?.term ?? s;
  const types = RELATION_TYPES.filter((t) => edges.some((e) => e.type === t));

  return (
    <>
      <nav className="crumbs">
        <Link href={`/${name}/${register}`}>
          &larr; {corpus.title} · {register}
        </Link>
      </nav>
      <header className="index-header">
        <h1>Concept relations</h1>
        <p className="description">
          {edges.length} typed links between lexicon terms.
        </p>
      </header>
      {edges.length === 0 ? (
        <p className="muted">
          Nothing extracted yet. Author edges via <code>/translate</code>.
        </p>
      ) : (
        types.map((type) => (
          <section key={type} className="card relation-group">
            <h2>{type}</h2>
            <ul className="relation-list">
              {edges
                .filter((e) => e.type === type)
                .map((e, i) => (
                  <li key={i} className="relation-line">
                    <span className="relation-arrow">
                      <Link href={termHref(e.from)}>{termName(e.from)}</Link>{" "}
                      —{e.type}&rarr;{" "}
                      <Link href={termHref(e.to)}>{termName(e.to)}</Link>
                    </span>
                    <span className="muted">{e.gloss}</span>
                  </li>
                ))}
            </ul>
          </section>
        ))
      )}
    </>
  );
}
