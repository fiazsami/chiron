import { notFound } from "next/navigation";
import LexiconList, { type LexiconRow } from "@/components/LexiconList";
import { findCorpus, getManifest } from "@/lib/content";
import { getLexicon } from "@/lib/lingua";

export const dynamic = "force-dynamic";

// Display order for term kinds (matches tools/lingua/dimensions/lexicon.py).
const KIND_ORDER = ["concept", "name", "identifier", "command", "file", "value"];

interface Params {
  params: Promise<{ corpus: string; register: string }>;
}

// The one-line definition shown in list rows: the first sentence, falling
// back to the first line of a multi-line definition.
function firstSentence(definition: string): string {
  const line = definition.split("\n", 1)[0].trim();
  const m = line.match(/^.*?[.!?](?=\s|$)/);
  return m ? m[0] : line;
}

export async function generateMetadata({ params }: Params) {
  const { corpus, register } = await params;
  const entry = findCorpus(await getManifest(), corpus, register);
  return { title: entry ? `Lexicon · ${entry.title} · chiron` : "chiron" };
}

export default async function LexiconPage({ params }: Params) {
  const { corpus: name, register } = await params;
  const manifest = await getManifest();
  const corpus = findCorpus(manifest, name, register);
  if (!corpus || !("lexicon" in corpus.data)) notFound();
  const lexicon = await getLexicon(corpus);

  const rows: LexiconRow[] = Object.entries(lexicon).map(([slug, entry]) => ({
    slug,
    term: entry.term,
    kind: entry.kind,
    definition: firstSentence(entry.definition),
    aliases: entry.aliases ?? [],
    anchorCount: entry.anchors.length,
    href: `/${name}/${register}/lexicon/${slug}`,
  }));
  rows.sort((a, b) => a.slug.localeCompare(b.slug));

  return (
    <>
      <header className="index-header">
        <h1>Lexicon</h1>
        <p className="description">
          {rows.length} terms — what things are called in this corpus.
        </p>
      </header>
      {rows.length === 0 ? (
        <p className="muted">
          Nothing extracted yet. Author entries via <code>/translate</code>.
        </p>
      ) : (
        <LexiconList rows={rows} kindOrder={KIND_ORDER} />
      )}
    </>
  );
}
