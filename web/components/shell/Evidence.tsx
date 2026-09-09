"use client";

import { useId, useLayoutEffect, useRef } from "react";
import type { AnchorVM } from "@/lib/substrate-types";
import { useShell } from "./shell-context";

// One anchor quote: the only verbatim block in the viewer. Evidence is ink,
// not color — a neutral rule and a provenance line; the rule turns amber
// only when the anchor drifted. Registers as an anchor target so `e` cycles
// evidence and Enter follows to the anchored chapter.

export default function Evidence({ anchor }: { anchor: AnchorVM }) {
  const api = useShell();
  const id = useId();
  const el = useRef<HTMLElement>(null);
  const { registry } = api;
  const href = anchor.chapterHref;

  useLayoutEffect(() => {
    if (!el.current || !href) return;
    registry.register({
      id,
      el: el.current,
      href,
      headword: anchor.chapterTitle,
      kind: "chapter",
      isAnchor: true,
    });
    return () => registry.unregister(id);
  }, [registry, id, href, anchor.chapterTitle]);

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
      className={`evidence${anchor.stale ? " stale" : ""}`}
    >
      <blockquote
        className={`evidence-quote${cursor ? " cursor" : ""}`}
        style={{ position: "relative" }}
      >
        {label !== undefined && (
          <span className={`hint-label${dim ? " dim" : ""}`} aria-hidden>
            {label}
          </span>
        )}
        “{anchor.quote}”
      </blockquote>
      <figcaption className="evidence-provenance">
        {href ? (
          <a
            href={href}
            className="reference"
            tabIndex={-1}
            onClick={(e) => {
              e.preventDefault();
              api.follow(href);
            }}
          >
            {anchor.chapterTitle}
          </a>
        ) : (
          anchor.chapterTitle
        )}
        {anchor.path && <span className="path"> · {anchor.path}</span>}
      </figcaption>
      {anchor.stale && (
        <p className="evidence-drift">
          pinned to {anchor.curatedAgainst.slice(0, 8)}…, chapter now{" "}
          {anchor.chapterHash ? `${anchor.chapterHash.slice(0, 8)}…` : "unknown"}
        </p>
      )}
    </figure>
  );
}
