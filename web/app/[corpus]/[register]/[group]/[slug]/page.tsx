import Link from "next/link";
import { notFound } from "next/navigation";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import {
  accentClass,
  findCorpus,
  getChapter,
  getManifest,
} from "@/lib/content";
import { getLexicon, type Lexicon } from "@/lib/lingua";

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

function TermLinks({
  slugs,
  lexicon,
  corpus,
  register,
}: {
  slugs: string[];
  lexicon: Lexicon;
  corpus: string;
  register: string;
}) {
  return (
    <span className="mini-badges">
      {slugs.map((s) => (
        <Link
          key={s}
          className="mini-badge term-chip"
          href={`/${corpus}/${register}/lexicon/${s}`}
        >
          {lexicon[s]?.term ?? s}
        </Link>
      ))}
    </span>
  );
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
  const corpusEntry = findCorpus(manifest, corpus, register);
  const defined = entry.terms_defined ?? [];
  const mentioned = entry.terms_mentioned ?? [];
  const lexicon =
    corpusEntry && defined.length + mentioned.length > 0
      ? await getLexicon(corpusEntry)
      : {};

  // The Markdown body already carries the full page (title, meta line,
  // callout, sections); the app adds navigation, the group accent, and the
  // lexicon cross-links below the article.
  return (
    <>
      <nav className="crumbs">
        <Link href="/">&larr; All corpora</Link>
        <Link className="crumb-register" href={`/${corpus}/${register}`}>
          {corpus}/{register}
        </Link>
      </nav>
      <article
        className={`card chapter-body ${accentClass(manifest, corpus, register, group)}`}
      >
        <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]}>
          {chapter.body}
        </ReactMarkdown>
      </article>
      {defined.length + mentioned.length > 0 && (
        <aside className="card chapter-terms">
          <h2>Terms in this chapter</h2>
          {defined.length > 0 && (
            <p>
              Defined here:{" "}
              <TermLinks
                slugs={defined}
                lexicon={lexicon}
                corpus={corpus}
                register={register}
              />
            </p>
          )}
          {mentioned.length > 0 && (
            <p>
              Mentioned:{" "}
              <TermLinks
                slugs={mentioned}
                lexicon={lexicon}
                corpus={corpus}
                register={register}
              />
            </p>
          )}
        </aside>
      )}
    </>
  );
}
