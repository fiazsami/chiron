"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import type { ScopeData } from "@/lib/substrate-types";

// The scope surface (/): every mounted (corpus, register) pair with totals
// per dimension, worst-of drift state, and provenance. Outside the shell —
// it has no register substrate. j/k rows, enter opens; t still toggles.

export default function ScopeScreen({ data }: { data: ScopeData }) {
  const router = useRouter();
  const [cursor, setCursor] = useState(0);
  const rowEls = useRef(new Map<number, HTMLElement>());
  const registers = data.registers;

  useEffect(() => {
    rowEls.current.get(cursor)?.scrollIntoView({ block: "nearest" });
  }, [cursor]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.altKey) return;
      const target = e.target as HTMLElement | null;
      if (target?.closest("input, textarea, select, [contenteditable]")) return;
      if (e.key === "j" || e.key === "ArrowDown") {
        e.preventDefault();
        setCursor((c) => Math.min(registers.length - 1, c + 1));
      } else if (e.key === "k" || e.key === "ArrowUp") {
        e.preventDefault();
        setCursor((c) => Math.max(0, c - 1));
      } else if (e.key === "Enter") {
        e.preventDefault();
        const row = registers[cursor];
        if (row) router.push(row.href);
      } else if (e.key === "t") {
        e.preventDefault();
        const root = document.documentElement;
        const explicit = root.getAttribute("data-theme");
        const effective =
          explicit ??
          (window.matchMedia("(prefers-color-scheme: dark)").matches
            ? "dark"
            : "light");
        const next = effective === "dark" ? "light" : "dark";
        root.setAttribute("data-theme", next);
        try {
          localStorage.setItem("chiron.theme", next);
        } catch {}
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [registers, cursor, router]);

  return (
    <main className="scope-page">
      <header>
        <h1 className="wordmark" style={{ fontSize: "var(--text-xxl)" }}>
          chiron
        </h1>
      </header>
      <div className="scope-main">
        {registers.map((reg, i) => (
          <div
            key={reg.key}
            role="link"
            tabIndex={-1}
            ref={(el) => {
              if (el) rowEls.current.set(i, el);
              else rowEls.current.delete(i);
            }}
            className={`scope-register${i === cursor ? " cursor" : ""}`}
            onClick={(e) => {
              // Provenance links inside the card navigate on their own.
              if ((e.target as HTMLElement).closest("a")) return;
              router.push(reg.href);
            }}
            onMouseEnter={() => setCursor(i)}
          >
            <span className="scope-title-line">
              <span className="scope-title">{reg.title}</span>
              <span className="entry-slug">
                {reg.corpus} · {reg.register} · {reg.sourceKind}
              </span>
              <span
                className="state-dots"
                title={`worst state: ${reg.worst}`}
                style={{ marginLeft: "auto" }}
              >
                <i className={reg.worst} />
              </span>
            </span>
            {reg.label && <p className="scope-register-label">{reg.label}</p>}
            <span className="scope-totals">
              {reg.totals.map((t) => (
                <span key={t.dimension} className="big-numeral">
                  {t.count}
                  <span className="noun">{t.noun}</span>
                </span>
              ))}
              <span className="big-numeral">
                {reg.chapterCount}
                <span className="noun">chapters</span>
              </span>
            </span>
            <p className="scope-provenance">
              checkout {reg.checkout}
              {reg.staleCount > 0 && ` · ${reg.staleCount} stale`}
              {Object.entries(reg.urls).map(([name, url]) => (
                <span key={name}>
                  {" · "}
                  <a href={url} target="_blank" rel="noopener noreferrer">
                    {name}
                  </a>
                </span>
              ))}
            </p>
          </div>
        ))}
        {registers.length === 0 && (
          <p className="empty-state">
            No corpora mounted yet. In Claude Code, run{" "}
            <code>/mount &lt;repo-url&gt;</code> to mount one, then build its
            pages with <code>uv run python -m tools.lingua</code> and refresh
            this page.
          </p>
        )}
      </div>
    </main>
  );
}
