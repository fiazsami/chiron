import { notFound } from "next/navigation";
import { getSubstrate } from "@/lib/substrate";

export const dynamic = "force-dynamic";

type Params = {
  params: Promise<{
    corpus: string;
    register: string;
    group: string;
    number: string;
  }>;
};

async function chapterFor({ params }: Params) {
  const { corpus, register, group, number } = await params;
  const s = await getSubstrate(corpus, register);
  const id = `${decodeURIComponent(group)}/${decodeURIComponent(number)}`;
  return { s, chapter: s?.chapters[id] };
}

export async function generateMetadata(props: Params) {
  const { s, chapter } = await chapterFor(props);
  return {
    title:
      chapter && s
        ? `${chapter.title} · ${s.register.title} · chiron`
        : "chiron",
  };
}

export default async function ChapterEntryPage(props: Params) {
  const { chapter } = await chapterFor(props);
  if (!chapter) notFound();
  return null;
}
