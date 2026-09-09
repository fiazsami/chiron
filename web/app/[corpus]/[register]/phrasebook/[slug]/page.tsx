import { notFound } from "next/navigation";
import { getSubstrate } from "@/lib/substrate";

export const dynamic = "force-dynamic";

type Params = {
  params: Promise<{ corpus: string; register: string; slug: string }>;
};

export async function generateMetadata({ params }: Params) {
  const { corpus, register, slug } = await params;
  const s = await getSubstrate(corpus, register);
  const phrase = s?.phrases[decodeURIComponent(slug)];
  return {
    title:
      phrase && s ? `${phrase.phrase} · ${s.register.title} · chiron` : "chiron",
  };
}

export default async function PhraseEntryPage({ params }: Params) {
  const { corpus, register, slug } = await params;
  const s = await getSubstrate(corpus, register);
  if (!s?.phrases[decodeURIComponent(slug)]) notFound();
  return null;
}
