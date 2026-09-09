import { getSubstrate } from "@/lib/substrate";

export const dynamic = "force-dynamic";

type Params = { params: Promise<{ corpus: string; register: string }> };

export async function generateMetadata({ params }: Params) {
  const { corpus, register } = await params;
  const s = await getSubstrate(corpus, register);
  return {
    title: s ? `Concept relations · ${s.register.title} · chiron` : "chiron",
  };
}

export default function RelationsIndexPage() {
  return null;
}
