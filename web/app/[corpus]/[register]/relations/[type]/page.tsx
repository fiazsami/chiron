import Link from "next/link";
import { notFound } from "next/navigation";
import { findCorpus, getManifest } from "@/lib/content";
import { getLexicon, getRelations } from "@/lib/lingua";

export const dynamic = "force-dynamic";

interface Params {
  params: Promise<{ corpus: string; register: string; type: string }>;
}

export async function generateMetadata({ params }: Params) {
  const { corpus, register, type } = await params;
  const entry = findCorpus(await getManifest(), corpus, register);
  return {
    title: entry ? `${type} relations · ${entry.title} · chiron` : "chiron",
  };
}

// One relation type's edges — an individually-addressable bit, reached via
// smart lookup or ⌘K (there is no relations index page).
export default async function RelationTypePage({ params }: Params) {
  const { corpus: name, register, type } = await params;
  const manifest = await getManifest();
  const corpus = findCorpus(manifest, name, register);
  if (!corpus || !("concept-relations" in corpus.data)) notFound();
  const [edges, lexicon] = await Promise.all([
    getRelations(corpus),
    getLexicon(corpus),
  ]);
  const typed = edges.filter((e) => e.type === type);
  if (typed.length === 0) notFound();

  const termHref = (s: string) => `/${name}/${register}/lexicon/${s}`;
  const termName = (s: string) => lexicon[s]?.term ?? s;

  return (
    <section className="card relation-group">
      <h1>{type}</h1>
      <p className="description muted">
        {typed.length} typed link{typed.length === 1 ? "" : "s"} between
        lexicon terms.
      </p>
      <ul className="relation-list">
        {typed.map((e, i) => (
          <li key={i} className="relation-line">
            <span className="relation-arrow">
              <Link href={termHref(e.from)}>{termName(e.from)}</Link> —{e.type}
              &rarr; <Link href={termHref(e.to)}>{termName(e.to)}</Link>
            </span>
            <span className="muted">{e.gloss}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
