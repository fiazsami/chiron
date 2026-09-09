"use client";

import { useId, useLayoutEffect, useRef } from "react";
import type { AnchorGroup } from "@/lib/shell/evidence";
import { useShell } from "./shell-context";

// One quote-group of evidence: the only verbatim block in the viewer.
// Evidence is ink, not color — a neutral rule and quiet provenance lines
// (one per distinct chapter/path that pinned this quote); the rule turns
// amber only when a pin drifted. Prose quotes are serif with typographic
// quotes; quotes from code chapters are mono, unquoted. Registers as an
// anchor target so `e` cycles evidence and Enter follows the chapter.

export default function Evidence({ group }: { group: AnchorGroup }) {
  const api = useShell();
  const id = useId();
  const el = useRef<HTMLElement>(null);
  const { registry } = api;
  const primary = group.refs.find((r) => r.chapterHref) ?? group.refs[0];
  const href = primary?.chapterHref ?? null;

  useLayoutEffect(() => {
    if (!el.current || !href) return;
    registry.register({
      id,
      el: el.current,
      href,
      headword: primary.chapterTitle,
      kind: "chapter",
      isAnchor: true,
    });
    return () => registry.unregister(id);
  }, [registry, id, href, primary?.chapterTitle]);

  const cursor = api.refCursor === id;
  const label = api.hint?.labels.get(id);
  const dim =
    label !== undefined &&
    api.hint !== null &&
    !label.startsWith(api.hint.buffer);

  return (
    <figure
      ref={el}
      tabIndex={-1}
      className={`evidence${group.stale ? " stale" : ""}`}
    >
      <blockquote
        className={`evidence-quote${group.code ? " code" : ""}${cursor ? " cursor" : ""}`}
        style={{ position: "relative" }}
      >
        {label !== undefined && (
          <span className={`hint-label${dim ? " dim" : ""}`} aria-hidden>
            {label}
          </span>
        )}
        {group.code ? group.quote : `“${group.quote}”`}
      </blockquote>
      {group.refs.map((ref, i) => (
        <div key={`${ref.chapter}:${ref.path ?? ""}`}>
          <div className="evidence-provenance">
            {ref.chapterHref ? (
              <a
                href={ref.chapterHref}
                className="reference quiet"
                tabIndex={-1}
                onClick={(e) => {
                  e.preventDefault();
                  api.follow(ref.chapterHref!);
                }}
              >
                {ref.chapterTitle}
              </a>
            ) : (
              ref.chapterTitle
            )}
            {ref.path && <span className="path"> · {ref.path}</span>}
          </div>
          {ref.stale && (
            <p className="evidence-drift">
              pinned to {ref.curatedAgainst.slice(0, 8)}…, chapter now{" "}
              {ref.chapterHash ? `${ref.chapterHash.slice(0, 8)}…` : "unknown"}
            </p>
          )}
        </div>
      ))}
    </figure>
  );
}
