import { notFound } from "next/navigation";
import { getSubstrate } from "@/lib/substrate";

export const dynamic = "force-dynamic";

type Params = {
  params: Promise<{ corpus: string; register: string; slug: string }>;
};

export async function generateMetadata({ params }: Params) {
  const { corpus, register, slug } = await params;
  const s = await getSubstrate(corpus, register);
  const term = s?.terms[decodeURIComponent(slug)];
  return {
    title: term && s ? `${term.term} · ${s.register.title} · chiron` : "chiron",
  };
}

export default async function TermEntryPage({ params }: Params) {
  const { corpus, register, slug } = await params;
  const s = await getSubstrate(corpus, register);
  if (!s?.terms[decodeURIComponent(slug)]) notFound();
  return null; // the Shell renders the entry from the URL
}
