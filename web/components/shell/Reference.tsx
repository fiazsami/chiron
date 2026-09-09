"use client";

import { useId, useLayoutEffect, useRef } from "react";
import type { RefKind } from "@/lib/substrate-types";
import { useShell } from "./shell-context";

// Every cross-reference in an entry renders through this: it registers
// itself with the Shell's ref registry (cursor, n/p, hint mode) and routes
// clicks through follow() so the trail records them.

export interface ReferenceProps {
  href: string;
  headword: string;
  kind: RefKind;
  className?: string;
  title?: string; // tooltip (e.g. the term kind on a pill)
  dataKind?: string; // term.kind — drives the pill's color coding
  children: React.ReactNode;
}

export default function Reference({
  href,
  headword,
  kind,
  className,
  title,
  dataKind,
  children,
}: ReferenceProps) {
  const api = useShell();
  const id = useId();
  const el = useRef<HTMLAnchorElement>(null);
  const { registry } = api;

  useLayoutEffect(() => {
    if (!el.current) return;
    registry.register({
      id,
      el: el.current,
      href,
      headword,
      kind,
      isAnchor: false,
    });
    return () => registry.unregister(id);
  }, [registry, id, href, headword, kind]);

  const cursor = api.refCursor === id;
  const label = api.hint?.labels.get(id);
  const dim =
    label !== undefined &&
    api.hint !== null &&
    !label.startsWith(api.hint.buffer);

  return (
    <a
      ref={el}
      href={href}
      className={`reference${cursor ? " cursor" : ""}${className ? ` ${className}` : ""}`}
      title={title}
      data-kind={dataKind}
      tabIndex={-1}
      onClick={(e) => {
        e.preventDefault();
        api.follow(href);
      }}
    >
      {label !== undefined && (
        <span className={`hint-label${dim ? " dim" : ""}`} aria-hidden>
          {label}
        </span>
      )}
      {children}
    </a>
  );
}
