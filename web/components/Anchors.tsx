import Link from "next/link";
import {
  chapterByLocalId,
  chapterHref,
  type Manifest,
} from "@/lib/content";
import type { Anchor } from "@/lib/lingua";

// Grounded anchors: chapter link, optional source path, verbatim quote.
// Server component — used by the term detail, phrasebook, and relations pages.
export default function Anchors({
  anchors,
  manifest,
  corpus,
  register,
}: {
  anchors: Anchor[];
  manifest: Manifest;
  corpus: string;
  register: string;
}) {
  return (
    <ul className="anchor-list">
      {anchors.map((a, i) => {
        const chapter = chapterByLocalId(manifest, corpus, register, a.chapter);
        return (
          <li key={i} className="anchor">
            <span className="anchor-meta">
              {chapter ? (
                <Link href={chapterHref(chapter)}>{chapter.title}</Link>
              ) : (
                <span className="muted">{a.chapter} (removed?)</span>
              )}
              {a.path && <code>{a.path}</code>}
            </span>
            <blockquote className="anchor-quote">{a.quote}</blockquote>
          </li>
        );
      })}
    </ul>
  );
}
