"use client";

import { useRouter } from "next/navigation";
import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { fetchBit } from "@/lib/bit-client";
import { buildCardRefs, type CardRefIndex } from "@/lib/card-refs";
import { fetchNavigation } from "@/lib/navigate-client";
import {
  destinationKey,
  type BitDestination,
  type BitKind,
  type BitRef,
  type Destination,
  type DestinationKind,
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

const MAX_DIVE_DEPTH = 16;

export type NavigatorEntry =
  | { mode: "lookup"; selection: string; context?: string }
  | { mode: "bit"; kind: BitKind; id: string };

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

type LookupState =
  | { status: "loading" }
  | { status: "done"; results: Destination[] }
  | { status: "error"; message: string };

type CardState =
  | { status: "loading" }
  | { status: "done"; dest: BitDestination }
  | { status: "error"; message: string };

interface CardEntry {
  key: number; // monotonic — a popped entry can never be resurrected
  ref: BitRef;
  state: CardState;
  cursor: number; // inner ref cursor, preserved under pushes
}

interface RefCallbacks {
  cursor: number;
  onHover: (i: number) => void;
  onActivate: (i: number) => void;
  setRefEl: (i: number, el: HTMLElement | null) => void;
}

// A cross-reference: highlighted when the inner cursor is on it; null index
// renders as plain text (e.g. an anchor whose chapter no longer resolves).
function Ref({
  i,
  cb,
  className,
  children,
}: {
  i: number | null;
  cb: RefCallbacks;
  className?: string;
  children: React.ReactNode;
}) {
  if (i === null) {
    return <span className={className}>{children}</span>;
  }
  return (
    <span
      ref={(el) => cb.setRefEl(i, el)}
      className={`nav-ref${i === cb.cursor ? " sel" : ""}${className ? ` ${className}` : ""}`}
      onMouseEnter={() => cb.onHover(i)}
      onClick={(e) => {
        e.stopPropagation();
        cb.onActivate(i);
      }}
    >
      {children}
    </span>
  );
}

function AnchorSection({
  anchors,
  total,
  anchorRefs,
  cb,
}: {
  anchors: { chapter: string; chapterTitle?: string; quote: string }[];
  total: number;
  anchorRefs: (number | null)[];
  cb: RefCallbacks;
}) {
  if (anchors.length === 0) return null;
  return (
    <>
      <p className="nav-detail-sub">
        Anchors{total > anchors.length ? ` · ${anchors.length} of ${total}` : ""}
      </p>
      {anchors.map((a, i) => (
        <Fragment key={i}>
          <p className="muted nav-anchor-label">
            <Ref i={anchorRefs[i]} cb={cb}>
              {a.chapterTitle ?? a.chapter}
            </Ref>
          </p>
          <blockquote className="anchor-quote">{a.quote}</blockquote>
        </Fragment>
      ))}
    </>
  );
}

// The flashcard: header + body, with every cross-reference rendered through
// Ref so the inner cursor can reach it. Positions come from the CardRefIndex
// maps — the renderer never counts refs itself.
function DetailCard({
  dest,
  refIndex,
  cb,
}: {
  dest: BitDestination;
  refIndex: CardRefIndex;
  cb: RefCallbacks;
}) {
  const bit = dest.bit;
  return (
    <>
      <div className="nav-detail-head">
        <span className="nav-glyph" aria-hidden>
          {GLYPHS[dest.kind]}
        </span>
        <span className="nav-detail-title">
          {bit.kind === "phrase" ? bit.phrase : dest.title}
          {bit.kind === "term" && (
            <span className="mini-badge">{bit.termKind}</span>
          )}
        </span>
        {bit.kind === "term" && bit.definedIn && (
          <span className="nav-detail-source muted">
            defined in{" "}
            <Ref i={refIndex.definedIn} cb={cb} className="nav-detail-link">
              {bit.definedIn.title}
            </Ref>
          </span>
        )}
      </div>

      {bit.kind === "term" && (
        <>
          <p className="nav-detail-def">{bit.definition}</p>
          {bit.aliases && (
            <p className="muted">Also known as: {bit.aliases.join(", ")}.</p>
          )}
          <AnchorSection
            anchors={bit.anchors}
            total={bit.totalAnchors}
            anchorRefs={refIndex.anchors}
            cb={cb}
          />
          {bit.phrasings.length > 0 && (
            <>
              <p className="nav-detail-sub">Phrasings</p>
              {bit.phrasings.map((p, i) => (
                <div key={p.id} className="nav-phrasing-row">
                  <Ref i={refIndex.phrasings[i]} cb={cb} className="nav-ref-row">
                    <span className="nav-phrasing-text">{p.phrase}</span>{" "}
                    <span className="muted">— {p.intent}</span>
                  </Ref>
                </div>
              ))}
              {bit.morePhrasings > 0 && (
                <p className="muted nav-detail-more">
                  and {bit.morePhrasings} more phrasings.
                </p>
              )}
            </>
          )}
          {bit.relations.length > 0 && (
            <>
              <p className="nav-detail-sub">Relations</p>
              <ul className="relation-list">
                {bit.relations.map((r, i) => (
                  <li key={i} className="relation-line">
                    <span className="relation-arrow">
                      {r.dir === "in" && (
                        <>
                          <Ref i={refIndex.relations[i]} cb={cb} className="nav-edge-term">
                            {r.other.name}
                          </Ref>{" "}
                        </>
                      )}
                      <span className="nav-edge-type">—{r.type}&rarr;</span>
                      {r.dir === "out" && (
                        <>
                          {" "}
                          <Ref i={refIndex.relations[i]} cb={cb} className="nav-edge-term">
                            {r.other.name}
                          </Ref>
                        </>
                      )}
                    </span>
                    <span className="muted">{r.gloss}</span>
                  </li>
                ))}
              </ul>
              {bit.moreRelations > 0 && (
                <p className="muted nav-detail-more">
                  and {bit.moreRelations} more relations.
                </p>
              )}
            </>
          )}
        </>
      )}

      {bit.kind === "phrase" && (
        <>
          <p className="nav-detail-intent">{bit.intent}</p>
          {bit.template && (
            <>
              <p className="nav-detail-sub">Template</p>
              <pre className="phrase-template">
                <code>{bit.template}</code>
              </pre>
            </>
          )}
          {bit.terms.length > 0 && (
            <>
              <p className="nav-detail-sub">Terms</p>
              <p className="mini-badges">
                {bit.terms.map((t, i) => (
                  <Ref key={t.id} i={refIndex.terms[i]} cb={cb} className="mini-badge">
                    {t.name}
                  </Ref>
                ))}
              </p>
            </>
          )}
          <AnchorSection
            anchors={bit.anchors}
            total={bit.totalAnchors}
            anchorRefs={refIndex.anchors}
            cb={cb}
          />
        </>
      )}

      {bit.kind === "relations" && (
        <>
          <p className="nav-detail-intent">
            {dest.detail ||
              `${bit.edges.length + bit.more} typed links between lexicon terms.`}
          </p>
          <ul className="relation-list">
            {bit.edges.map((e, i) => (
              <li key={i} className="relation-line">
                <span className="relation-arrow">
                  <Ref i={refIndex.edges[i].from} cb={cb} className="nav-edge-term">
                    {e.from.name}
                  </Ref>{" "}
                  <span className="nav-edge-type">—{dest.id}&rarr;</span>{" "}
                  <Ref i={refIndex.edges[i].to} cb={cb} className="nav-edge-term">
                    {e.to.name}
                  </Ref>
                </span>
                <span className="muted">{e.gloss}</span>
              </li>
            ))}
          </ul>
          {bit.more > 0 && (
            <p className="muted nav-detail-more">and {bit.more} more.</p>
          )}
        </>
      )}
    </>
  );
}

// The bit modal: lookup entry shows a grouped result list; opening a
// non-chapter pushes its flashcard onto a dive stack, and every card's
// cross-references are divable in turn (dive-first keyboard: up/down move
// the inner cursor, l/Enter follows, j/esc pops). Chapters — the GitHub-
// styled reading surface — are the only navigation exits. While the modal
// is open the shell suppresses the global keymap.
export default function NavigatorPopup({
  corpus,
  register,
  pathname,
  entry,
  onClose,
}: {
  corpus: string;
  register: string;
  pathname: string;
  entry: NavigatorEntry;
  onClose: () => void;
}) {
  const router = useRouter();
  const [lookup, setLookup] = useState<LookupState>({ status: "loading" });
  const [sel, setSel] = useState(0);
  const [attempt, setAttempt] = useState(0);
  const [stack, setStack] = useState<CardEntry[]>([]);
  const nextKey = useRef(0);
  const diveControllers = useRef(new Map<number, AbortController>());
  const boxRef = useRef<HTMLDivElement>(null);
  const rowRefs = useRef<(HTMLElement | null)[]>([]);
  const refEls = useRef<(HTMLElement | null)[]>([]);

  useEffect(() => {
    boxRef.current?.focus();
  }, []);

  function settleCard(key: number, state: CardState) {
    // Popped entries no longer match by key — a late resolve is a no-op.
    setStack((s) => s.map((e) => (e.key === key ? { ...e, state } : e)));
  }

  function startFetch(key: number, ref: BitRef, bypassCache = false) {
    const controller = new AbortController();
    diveControllers.current.set(key, controller);
    fetchBit({ corpus, register, ...ref }, controller.signal, bypassCache)
      .then((dest) =>
        settleCard(key, { status: "done", dest: dest as BitDestination }),
      )
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        settleCard(key, {
          status: "error",
          message: err instanceof Error ? err.message : String(err),
        });
      })
      .finally(() => diveControllers.current.delete(key));
  }

  // Lookup entry: fetch grouped results; retry resets the dive trail too.
  useEffect(() => {
    if (entry.mode !== "lookup") return;
    const controller = new AbortController();
    setLookup({ status: "loading" });
    setSel(0);
    setStack([]);
    rowRefs.current = [];
    fetchNavigation(
      {
        corpus,
        register,
        selection: entry.selection,
        context: entry.context,
        pathname,
      },
      controller.signal,
      attempt > 0,
    )
      .then((res) => setLookup({ status: "done", results: res.results }))
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setLookup({
          status: "error",
          message: err instanceof Error ? err.message : String(err),
        });
      });
    return () => controller.abort();
  }, [corpus, register, entry, pathname, attempt]);

  // Direct bit entry: seed the stack with the requested flashcard.
  useEffect(() => {
    if (entry.mode !== "bit") return;
    const key = nextKey.current++;
    setStack([
      {
        key,
        ref: { kind: entry.kind, id: entry.id },
        state: { status: "loading" },
        cursor: 0,
      },
    ]);
    startFetch(key, { kind: entry.kind, id: entry.id });
    return () => diveControllers.current.get(key)?.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [corpus, register, entry]);

  const top = stack[stack.length - 1];
  const topDest = top?.state.status === "done" ? top.state.dest : null;
  const refIndex = useMemo(
    () => (topDest ? buildCardRefs(topDest) : null),
    [topDest],
  );
  const refs = refIndex?.refs ?? [];
  const cursor = top?.cursor ?? 0;

  // Stable partition into display order; `sel` indexes this array.
  const display = useMemo(
    () =>
      lookup.status === "done"
        ? GROUP_ORDER.flatMap((k) => lookup.results.filter((d) => d.kind === k))
        : [],
    [lookup],
  );

  useEffect(() => {
    if (!top) rowRefs.current[sel]?.scrollIntoView({ block: "nearest" });
  }, [sel, top, lookup.status]);

  useEffect(() => {
    if (top) refEls.current[cursor]?.scrollIntoView({ block: "nearest" });
  }, [top?.key, cursor, topDest]); // eslint-disable-line react-hooks/exhaustive-deps

  function go(href: string) {
    router.push(href);
    onClose();
  }

  function setCursor(i: number) {
    if (!top) return;
    const key = top.key;
    setStack((s) => s.map((e) => (e.key === key ? { ...e, cursor: i } : e)));
  }

  function moveCursor(dir: 1 | -1) {
    if (refs.length === 0) return;
    setCursor(Math.max(0, Math.min(refs.length - 1, cursor + dir)));
  }

  function pushCard(ref: BitRef) {
    if (stack.length >= MAX_DIVE_DEPTH) return;
    const key = nextKey.current++;
    setStack((s) => [
      ...s,
      { key, ref, state: { status: "loading" }, cursor: 0 },
    ]);
    startFetch(key, ref);
  }

  function activateRef(i: number) {
    const ref = refs[i];
    if (!ref) return;
    if (ref.refType === "chapter") {
      go(ref.href); // entering reading mode is a full exit
      return;
    }
    pushCard({ kind: ref.kind, id: ref.id });
  }

  function retryTop() {
    if (!top || top.state.status !== "error") return;
    const key = top.key;
    settleCard(key, { status: "loading" });
    startFetch(key, top.ref, true);
  }

  function pop() {
    if (!top) return;
    diveControllers.current.get(top.key)?.abort();
    if (stack.length === 1 && entry.mode === "bit") {
      onClose();
      return;
    }
    setStack((s) => s.slice(0, -1));
  }

  // List activation: chapters navigate; bits push their (already complete)
  // flashcard — no fetch.
  function activate(dest: Destination | undefined) {
    if (!dest) return;
    if (dest.kind === "chapter") {
      go(dest.href);
      return;
    }
    const key = nextKey.current++;
    setStack((s) => [
      ...s,
      {
        key,
        ref: { kind: dest.kind, id: dest.id },
        state: { status: "done", dest },
        cursor: 0,
      },
    ]);
  }

  // Dive-first keyboard: up/down = inner cursor over the card's refs;
  // right/Enter follows; left/esc pops (list at the bottom for lookup
  // entries, closed for direct entries).
  function onKeyDown(e: React.KeyboardEvent) {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    const down = e.key === "ArrowDown" || e.key === "k" || e.key === "d";
    const up = e.key === "ArrowUp" || e.key === "i" || e.key === "e";
    const left = e.key === "ArrowLeft" || e.key === "j" || e.key === "a";
    const right = e.key === "ArrowRight" || e.key === "l" || e.key === "f";

    if (top) {
      if (top.state.status === "loading") {
        // Rapid-repeat guard: only backing out works mid-fetch.
        e.preventDefault();
        if (left || e.key === "Escape") pop();
        return;
      }
      if (top.state.status === "error") {
        e.preventDefault();
        if (right || e.key === "Enter") retryTop();
        else if (left || e.key === "Escape") pop();
        return;
      }
      if (down || up) {
        e.preventDefault();
        moveCursor(down ? 1 : -1);
      } else if (right || e.key === "Enter") {
        e.preventDefault();
        activateRef(cursor);
      } else if (left || e.key === "Escape") {
        e.preventDefault();
        pop();
      } else if (/^[a-z]$/.test(e.key)) {
        e.preventDefault(); // swallow the reader keymap while open
      }
      return;
    }

    if (entry.mode === "bit") {
      // Stack still seeding — only escape hatches work.
      e.preventDefault();
      if (left || e.key === "Escape") onClose();
      return;
    }

    if (down || up) {
      e.preventDefault();
      setSel((s) =>
        down ? Math.min(Math.max(display.length - 1, 0), s + 1) : Math.max(0, s - 1),
      );
    } else if (right || e.key === "Enter") {
      e.preventDefault();
      activate(display[sel]);
    } else if (left || e.key === "Escape") {
      e.preventDefault();
      onClose();
    } else if (/^[a-z]$/.test(e.key)) {
      e.preventDefault(); // swallow the rest of the reader keymap (p/w…)
    }
  }

  const cb: RefCallbacks = {
    cursor,
    onHover: setCursor,
    onActivate: activateRef,
    setRefEl: (i, el) => {
      refEls.current[i] = el;
    },
  };

  const inCard = top !== undefined;
  const hint = !inCard
    ? "↑↓ / i k navigate · l / ↵ open · j / esc close"
    : top.state.status === "loading"
      ? "looking up… · j / esc back"
      : top.state.status === "error"
        ? "l / ↵ retry · j / esc back"
        : refs.length > 0
          ? "↑↓ refs · l / ↵ follow · j / esc back"
          : "j / esc back";

  return (
    <div
      className={`overlay-backdrop${inCard ? " deep" : ""}`}
      onMouseDown={onClose}
    >
      <div
        className={`navigator${inCard ? " expanded" : ""}`}
        role="dialog"
        aria-label="Look up"
        tabIndex={-1}
        ref={boxRef}
        onMouseDown={(e) => e.stopPropagation()}
        onKeyDown={onKeyDown}
      >
        {entry.mode === "lookup" && (
          <p className="navigator-selection">
            “
            {entry.selection.length > 120
              ? `${entry.selection.slice(0, 119)}…`
              : entry.selection}
            ”
          </p>
        )}

        {!inCard && entry.mode === "bit" && (
          <p className="navigator-status">looking up…</p>
        )}
        {!inCard && entry.mode === "lookup" && (
          <>
            {lookup.status === "loading" && (
              <p className="navigator-status">finding pages…</p>
            )}
            {lookup.status === "error" && (
              <div className="navigator-error">
                <span>{lookup.message}</span>
                <button
                  className="navigator-retry"
                  onClick={() => setAttempt((a) => a + 1)}
                >
                  Retry
                </button>
              </div>
            )}
            {lookup.status === "done" &&
              (display.length === 0 ? (
                <p className="navigator-status">
                  No related pages for this selection.
                </p>
              ) : (
                <div className="navigator-list">
                  {display.map((dest, i) => (
                    <Fragment key={destinationKey(dest)}>
                      {(i === 0 || display[i - 1].kind !== dest.kind) && (
                        <div className="nav-section">
                          {GROUP_LABELS[dest.kind]}
                        </div>
                      )}
                      <div
                        ref={(el) => {
                          rowRefs.current[i] = el;
                        }}
                        className={`nav-row${i === sel ? " sel" : ""}`}
                        onMouseEnter={() => setSel(i)}
                        onClick={() => {
                          setSel(i);
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
              ))}
          </>
        )}

        {inCard && (
          <div className="nav-detail-view">
            {top.state.status === "loading" && (
              <p className="navigator-status">looking up…</p>
            )}
            {top.state.status === "error" && (
              <div className="navigator-error">
                <span>{top.state.message}</span>
                <button className="navigator-retry" onClick={retryTop}>
                  Retry
                </button>
              </div>
            )}
            {top.state.status === "done" && refIndex && (
              <DetailCard dest={top.state.dest} refIndex={refIndex} cb={cb} />
            )}
          </div>
        )}

        <p className="navigator-hint">{hint}</p>
      </div>
    </div>
  );
}
