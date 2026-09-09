"use client";

import { useRouter } from "next/navigation";
import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { fetchNavigation } from "@/lib/navigate-client";
import type {
  BitDetail,
  Destination,
  DestinationKind,
} from "@/lib/navigator-types";

const GLYPHS: Record<DestinationKind, string> = {
  chapter: "¶",
  term: "◇",
  phrase: "❝",
  relations: "⇢",
};

// Display order: bits grouped by kind, chapters always at the bottom —
// chapters navigate away (reading mode), everything else opens in place
// (lookup mode).
const GROUP_ORDER: DestinationKind[] = [
  "term",
  "phrase",
  "relations",
  "chapter",
];
const GROUP_LABELS: Record<DestinationKind, string> = {
  term: "Terms",
  phrase: "Phrasings",
  relations: "Relations",
  chapter: "Chapters",
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

function DetailBody({ dest }: { dest: Destination }) {
  const bit = dest.bit as BitDetail;
  if (bit.kind === "term") {
    return (
      <>
        <p className="nav-detail-def">{bit.definition}</p>
        {bit.aliases && (
          <p className="muted">Also known as: {bit.aliases.join(", ")}.</p>
        )}
        {bit.anchors.map((a, i) => (
          <Fragment key={i}>
            <p className="muted nav-anchor-label">
              {a.chapterTitle ?? a.chapter}
            </p>
            <blockquote className="anchor-quote">{a.quote}</blockquote>
          </Fragment>
        ))}
      </>
    );
  }
  if (bit.kind === "phrase") {
    return (
      <>
        <p className="muted">{bit.intent}</p>
        {bit.template && (
          <pre className="phrase-template">
            <code>{bit.template}</code>
          </pre>
        )}
        <p className="mini-badges">
          {bit.terms.map((t) => (
            <span key={t} className="mini-badge">
              {t}
            </span>
          ))}
        </p>
      </>
    );
  }
  // All edges in a relations bit share one type; it's the href's last segment.
  const type = dest.href.split("/").pop();
  return (
    <>
      {dest.detail && <p className="muted">{dest.detail}</p>}
      <ul className="relation-list">
        {bit.edges.map((e, i) => (
          <li key={i} className="relation-line">
            <span className="relation-arrow">
              {e.from} —{type}&rarr; {e.to}
            </span>
            <span className="muted">{e.gloss}</span>
          </li>
        ))}
      </ul>
      {bit.more > 0 && <p className="muted">and {bit.more} more.</p>}
    </>
  );
}

// Two-level lookup modal. List mode: results grouped by kind, chapters at
// the bottom. Detail mode (non-chapter Enter/click): the popup expands, the
// backdrop dims deeper, and up/down browse the bits in place — a different
// cognitive mode than reading, so focus stays inside the popup. While it is
// open the shell suppresses the global keymap; keys land on the focused
// dialog instead.
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
  const [mode, setMode] = useState<"list" | "detail">("list");
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
    setMode("list");
    rowRefs.current = [];
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

  // Stable partition into display order; `sel` indexes this array in both
  // modes, which is what makes Escape-preserves-selection free.
  const display = useMemo(
    () =>
      state.status === "done"
        ? GROUP_ORDER.flatMap((k) =>
            state.results.filter((d) => d.kind === k),
          )
        : [],
    [state],
  );

  useEffect(() => {
    if (mode === "list") {
      rowRefs.current[sel]?.scrollIntoView({ block: "nearest" });
    }
  }, [sel, mode, state.status]);

  function go(dest: Destination | undefined) {
    if (!dest) return;
    router.push(dest.href);
    onClose();
  }

  function activate(dest: Destination | undefined) {
    if (!dest) return;
    // !bit: a pre-upgrade cached entry — degrade to plain navigation.
    if (dest.kind === "chapter" || !dest.bit) {
      go(dest);
      return;
    }
    setMode("detail");
  }

  // Browse non-chapter bits in place; chapters are skipped, ends clamp.
  function moveDetail(dir: 1 | -1) {
    setSel((s) => {
      let i = s + dir;
      while (i >= 0 && i < display.length && display[i].kind === "chapter") {
        i += dir;
      }
      return i >= 0 && i < display.length ? i : s;
    });
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    const down = e.key === "ArrowDown" || e.key === "k" || e.key === "d";
    const up = e.key === "ArrowUp" || e.key === "i" || e.key === "e";
    if (mode === "detail") {
      if (down || up) {
        e.preventDefault();
        moveDetail(down ? 1 : -1);
      } else if (e.key === "Enter") {
        e.preventDefault();
        go(display[sel]);
      } else if (e.key === "Escape") {
        e.preventDefault();
        setMode("list");
      } else if (/^[a-z]$/.test(e.key)) {
        e.preventDefault(); // swallow the reader keymap while open
      }
      return;
    }
    if (down || up) {
      e.preventDefault();
      setSel((s) =>
        down ? Math.min(Math.max(display.length - 1, 0), s + 1) : Math.max(0, s - 1),
      );
    } else if (e.key === "Enter") {
      e.preventDefault();
      activate(display[sel]);
    } else if (e.key === "Escape") {
      e.preventDefault();
      onClose();
    } else if (/^[a-z]$/.test(e.key)) {
      e.preventDefault(); // swallow the reader keymap (j/l/a/f/p/w…)
    }
  }

  const current = display[sel];
  const inDetail = mode === "detail" && current?.bit !== undefined;
  const definedIn =
    current?.bit?.kind === "term" ? current.bit.definedIn : undefined;

  return (
    <div
      className={`overlay-backdrop${inDetail ? " deep" : ""}`}
      onMouseDown={onClose}
    >
      <div
        className={`navigator${inDetail ? " expanded" : ""}`}
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
        {state.status === "done" && !inDetail && (
          display.length === 0 ? (
            <p className="navigator-status">
              No related pages for this selection.
            </p>
          ) : (
            <div className="navigator-list">
              {display.map((dest, i) => (
                <Fragment key={dest.href}>
                  {(i === 0 || display[i - 1].kind !== dest.kind) && (
                    <div className="nav-section">{GROUP_LABELS[dest.kind]}</div>
                  )}
                  <div
                    ref={(el) => {
                      rowRefs.current[i] = el;
                    }}
                    className={`nav-row${i === sel ? " sel" : ""}`}
                    onMouseEnter={() => setSel(i)}
                    onClick={() => {
                      setSel(i); // detail renders display[sel]
                      activate(dest);
                    }}
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
                  </div>
                </Fragment>
              ))}
            </div>
          )
        )}
        {inDetail && current && (
          <div className="nav-detail-view">
            <div className="nav-detail-head">
              <button
                className="nav-detail-back"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => setMode("list")}
              >
                ‹ back
              </button>
              <span className="nav-glyph" aria-hidden>
                {GLYPHS[current.kind]}
              </span>
              <span className="nav-detail-title">
                {current.bit?.kind === "phrase"
                  ? current.bit.phrase
                  : current.title}
                {current.bit?.kind === "term" && (
                  <span className="mini-badge">{current.bit.termKind}</span>
                )}
              </span>
              {definedIn && (
                <span className="nav-detail-source muted">
                  defined in{" "}
                  <span
                    className="nav-detail-link"
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => {
                      router.push(definedIn.href);
                      onClose();
                    }}
                  >
                    {definedIn.title}
                  </span>
                </span>
              )}
            </div>
            <DetailBody dest={current} />
          </div>
        )}
        <p className="navigator-hint">
          {inDetail
            ? "↑↓ browse · ↵ open page · esc back"
            : "↑↓ / i k / e d navigate · ↵ open · esc close"}
        </p>
      </div>
    </div>
  );
}
