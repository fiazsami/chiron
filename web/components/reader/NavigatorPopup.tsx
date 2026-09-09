"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { fetchNavigation } from "@/lib/navigate-client";
import type { Destination } from "@/lib/navigator-types";

const GLYPHS: Record<Destination["kind"], string> = {
  chapter: "¶",
  term: "◇",
  phrase: "❝",
  relations: "⇢",
};

export interface CapturedSelection {
  selection: string;
  context?: string;
}

// Read the learner's text selection, scoped to the article pane. Null when
// there is nothing usefully selected — the shell's look-up keys (p/w) then
// fall back to the cursor item instead.
export function captureSelection(
  container: HTMLElement | null,
): CapturedSelection | null {
  if (!container) return null;
  const sel = window.getSelection();
  if (!sel || sel.isCollapsed || sel.rangeCount === 0) return null;
  const text = sel.toString().trim();
  if (!text) return null;
  const anchor = sel.anchorNode;
  if (!anchor || !container.contains(anchor)) return null;

  const start = sel.getRangeAt(0).startContainer;
  const el = start instanceof Element ? start : start.parentElement;
  const block = el?.closest("p, li, pre, h1, h2, h3, h4, h5, h6, td, blockquote");
  const blockText = block?.textContent?.trim();
  const context =
    blockText && blockText !== text ? blockText.slice(0, 700) : undefined;
  return { selection: text.slice(0, 500), context };
}

type PopupState =
  | { status: "loading" }
  | { status: "done"; results: Destination[] }
  | { status: "error"; message: string };

// Centered modal listing LLM-suggested pages for the captured selection.
// While it is open the shell suppresses the global keymap; keys land on the
// focused dialog instead.
export default function NavigatorPopup({
  corpus,
  register,
  pathname,
  selection,
  context,
  onClose,
}: {
  corpus: string;
  register: string;
  pathname: string;
  selection: string;
  context?: string;
  onClose: () => void;
}) {
  const router = useRouter();
  const [state, setState] = useState<PopupState>({ status: "loading" });
  const [sel, setSel] = useState(0);
  const [attempt, setAttempt] = useState(0);
  const boxRef = useRef<HTMLDivElement>(null);
  const rowRefs = useRef<(HTMLElement | null)[]>([]);

  useEffect(() => {
    boxRef.current?.focus();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setState({ status: "loading" });
    setSel(0);
    fetchNavigation(
      { corpus, register, selection, context, pathname },
      controller.signal,
      attempt > 0,
    )
      .then((res) => setState({ status: "done", results: res.results }))
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setState({
          status: "error",
          message: err instanceof Error ? err.message : String(err),
        });
      });
    return () => controller.abort();
  }, [corpus, register, selection, context, pathname, attempt]);

  useEffect(() => {
    rowRefs.current[sel]?.scrollIntoView({ block: "nearest" });
  }, [sel]);

  const results = state.status === "done" ? state.results : [];

  function go(dest: Destination | undefined) {
    if (!dest) return;
    router.push(dest.href);
    onClose();
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    switch (e.key) {
      case "ArrowDown":
      case "k":
      case "d":
        e.preventDefault();
        setSel((s) => Math.min(Math.max(results.length - 1, 0), s + 1));
        break;
      case "ArrowUp":
      case "i":
      case "e":
        e.preventDefault();
        setSel((s) => Math.max(0, s - 1));
        break;
      case "Enter":
        e.preventDefault();
        go(results[sel]);
        break;
      case "Escape":
        e.preventDefault();
        onClose();
        break;
      default:
        // Swallow the reader keymap (j/l/a/f/p/w…) while the popup is open.
        if (/^[a-z]$/.test(e.key)) e.preventDefault();
    }
  }

  return (
    <div className="overlay-backdrop" onMouseDown={onClose}>
      <div
        className="navigator"
        role="dialog"
        aria-label="Related pages"
        tabIndex={-1}
        ref={boxRef}
        onMouseDown={(e) => e.stopPropagation()}
        onKeyDown={onKeyDown}
      >
        <p className="navigator-selection">
          “{selection.length > 120 ? `${selection.slice(0, 119)}…` : selection}”
        </p>
        {state.status === "loading" && (
          <p className="navigator-status">finding pages…</p>
        )}
        {state.status === "error" && (
          <div className="navigator-error">
            <span>{state.message}</span>
            <button
              className="navigator-retry"
              onClick={() => setAttempt((a) => a + 1)}
            >
              Retry
            </button>
          </div>
        )}
        {state.status === "done" &&
          (results.length === 0 ? (
            <p className="navigator-status">
              No related pages for this selection.
            </p>
          ) : (
            <div className="navigator-list">
              {results.map((dest, i) => (
                <div
                  key={dest.href}
                  ref={(el) => {
                    rowRefs.current[i] = el;
                  }}
                  className={`nav-row${i === sel ? " sel" : ""}`}
                  onMouseEnter={() => setSel(i)}
                  onClick={() => go(dest)}
                >
                  <span className="nav-glyph" aria-hidden>
                    {GLYPHS[dest.kind]}
                  </span>
                  <span className="nav-row-body">
                    <span className="nav-title">{dest.title}</span>
                    {dest.detail && (
                      <span className="nav-detail">{dest.detail}</span>
                    )}
                  </span>
                  <span className="nav-kind">{dest.kind}</span>
                </div>
              ))}
            </div>
          ))}
        <p className="navigator-hint">
          ↑↓ / i k / e d navigate · ↵ open · esc close
        </p>
      </div>
    </div>
  );
}
