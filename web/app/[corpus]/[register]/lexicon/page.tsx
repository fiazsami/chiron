import { getSubstrate } from "@/lib/substrate";

export const dynamic = "force-dynamic";

type Params = { params: Promise<{ corpus: string; register: string }> };

export async function generateMetadata({ params }: Params) {
  const { corpus, register } = await params;
  const s = await getSubstrate(corpus, register);
  return { title: s ? `Lexicon · ${s.register.title} · chiron` : "chiron" };
}

// The Shell renders the index and the no-entry hint; this route only
// claims the URL.
export default function LexiconIndexPage() {
  return null;
}
