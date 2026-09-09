import { notFound } from "next/navigation";
import {
  DIMENSIONS,
  findCorpus,
  getManifest,
  totalsLine,
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

// The register's "All Items" landing. The extracted linguistic structure is
// deliberately not browsable from here — terms, phrasings, and relations
// surface through smart lookup (p/w) and the ⌘K palette only.
export default async function RegisterPage({ params }: Params) {
  const { corpus: name, register } = await params;
  const manifest = await getManifest();
  const corpus = findCorpus(manifest, name, register);
  if (!corpus) notFound();

  const tracked = DIMENSIONS.filter((d) => d in corpus.data);
  const totals = totalsLine(corpus);

  return (
    <header className="index-header">
      <h1>
        {corpus.title} <span className="muted">· {corpus.register}</span>
      </h1>
      {corpus.label && <p className="description">{corpus.label}</p>}
      {totals && <p className="muted">{totals} — select a passage and press p to look things up.</p>}
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
  );
}
