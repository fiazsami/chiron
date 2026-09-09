import Link from "next/link";
import { notFound } from "next/navigation";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import { accentClass, getChapter, getManifest } from "@/lib/content";

export const dynamic = "force-dynamic";

interface Params {
  params: Promise<{
    corpus: string;
    register: string;
    group: string;
    slug: string;
  }>;
}

async function findChapter(
  corpus: string,
  register: string,
  group: string,
  slug: string,
) {
  const manifest = await getManifest();
  const chapter = manifest.chapters.find(
    (c) =>
      c.corpus === corpus &&
      c.register === register &&
      c.group === group &&
      c.slug === slug,
  );
  return { manifest, chapter };
}

export async function generateMetadata({ params }: Params) {
  const { corpus, register, group, slug } = await params;
  const { chapter } = await findChapter(corpus, register, group, slug);
  return {
    title: chapter ? `${chapter.title} · chiron` : "chiron",
  };
}

export default async function ChapterPage({ params }: Params) {
  const { corpus, register, group, slug } = await params;
  const { manifest, chapter: entry } = await findChapter(
    corpus,
    register,
    group,
    slug,
  );
  if (!entry) notFound();
  const chapter = await getChapter(entry);

  // The Markdown body already carries the full page (title, meta line,
  // callout, sections); the app only adds navigation and the group accent.
  return (
    <>
      <nav className="crumbs">
        <Link href="/">&larr; All notes</Link>
        <span className="crumb-register">{register}</span>
      </nav>
      <article
        className={`card chapter-body ${accentClass(manifest, corpus, register, group)}`}
      >
        <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]}>
          {chapter.body}
        </ReactMarkdown>
      </article>
    </>
  );
}
