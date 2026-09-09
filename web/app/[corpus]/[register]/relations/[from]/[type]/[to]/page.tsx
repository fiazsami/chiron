import { notFound } from "next/navigation";
import { getSubstrate } from "@/lib/substrate";

export const dynamic = "force-dynamic";

type Params = {
  params: Promise<{
    corpus: string;
    register: string;
    from: string;
    type: string;
    to: string;
  }>;
};

async function edgeFor({ params }: Params) {
  const { corpus, register, from, type, to } = await params;
  const s = await getSubstrate(corpus, register);
  const id = [from, type, to].map(decodeURIComponent).join("/");
  return { s, edge: s?.edges[id] };
}

export async function generateMetadata(props: Params) {
  const { s, edge } = await edgeFor(props);
  return {
    title:
      edge && s
        ? `${edge.from} ${edge.type} ${edge.to} · ${s.register.title} · chiron`
        : "chiron",
  };
}

export default async function EdgeEntryPage(props: Params) {
  const { edge } = await edgeFor(props);
  if (!edge) notFound();
  return null;
}
