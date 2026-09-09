"use client";

import { usePathname, useRouter } from "next/navigation";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  cycleSort,
  defaultSort,
  rowsFor,
  SORT_CYCLES,
  type SortMode,
} from "@/lib/shell/index-rows";
import { hintLabels } from "@/lib/shell/hints";
import { KEY_LOOKUP, type ShellAction } from "@/lib/shell/keymap";
import {
  entryAt,
  parseViewerPath,
  selectionKey,
  viewHref,
  viewOf,
  type EntryModel,
  type ViewKey,
} from "@/lib/shell/route";
import type { RegisterSubstrate } from "@/lib/substrate-types";
import Drill, { buildDrillItems, type DrillItem } from "./Drill";
import EntryPane from "./EntryPane";
import Help from "./Help";
import IndexPane from "./IndexPane";
import Jump from "./Jump";
import Peek from "./Peek";
import PeekExpanded from "./PeekExpanded";
import Rail, { railRows, type RailRow } from "./Rail";
import {
  RefRegistry,
  ShellContext,
  type HintState,
  type RefTarget,
  type ShellApi,
} from "./shell-context";
import Trail, { type TrailEntry } from "./Trail";

// The shell: rail | index | entry with a trail bar, one keyboard, and the
// overlays. All state lives here; entries and references reach back through
// ShellContext. The single window listener + handlerRef pattern is carried
// over from the previous shell.

const PANES = ["rail", "index", "entry"] as const;
type Pane = (typeof PANES)[number];

const TRAIL_CAP = 16;
const GG_WINDOW_MS = 600;

type Overlay =
  | {
      kind: "peek";
      targetId: string;
      rect: DOMRect;
      measureRect: DOMRect | null;
      expanded: boolean; // enter expands in place — a peek never navigates
    }
  | { kind: "jump" }
  | { kind: "drill"; items: DrillItem[] }
  | { kind: "help" };

// Keys from retired shells, cleared once on load.
const LEGACY_KEYS = [
  "chiron.explorerOpen",
  "chiron.coachOpen",
  "chiron.explorerWidth",
  "chiron.coachWidth",
  "chiron.collapsedGroups",
  "chiron.sidebarWidth",
  "chiron.listWidth",
  "chiron.scope",
];

const clampWidth = (w: number) => Math.max(140, Math.min(520, w));

export default function Shell({
  substrate,
  children,
}: {
  substrate: RegisterSubstrate;
  children: React.ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const base = `/${substrate.register.corpus}/${substrate.register.register}`;

  const location = useMemo(() => parseViewerPath(pathname), [pathname]);
  // Chapters is the primary view — the register root lands there.
  const view: ViewKey = viewOf(location) ?? "chapters";
  const selection = selectionKey(location);
  const entry = useMemo(
    () => entryAt(substrate, location),
    [substrate, location],
  );

  const [focusedPane, setFocusedPane] = useState<Pane>("index");
  const [railCursor, setRailCursor] = useState(0);
  const [cursorId, setCursorId] = useState<string | null>(null);
  const [refCursor, setRefCursor] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const [staleOnly, setStaleOnly] = useState(false);
  const [sort, setSort] = useState<Record<ViewKey, SortMode>>(() => ({
    lexicon: defaultSort("lexicon"),
    phrasebook: defaultSort("phrasebook"),
    "concept-relations": defaultSort("concept-relations"),
    chapters: defaultSort("chapters"),
  }));
  const [overlay, setOverlay] = useState<Overlay | null>(null);
  const [hint, setHint] = useState<HintState | null>(null);
  const [copied, setCopied] = useState(false);
  const [trail, setTrail] = useState<{ entries: TrailEntry[]; pos: number }>({
    entries: [],
    pos: 0,
  });
  const [railWidth, setRailWidth] = useState(232);
  const [indexWidth, setIndexWidth] = useState(336);
  const [mobileNav, setMobileNav] = useState(false);
  const [loaded, setLoaded] = useState(false);

  const registry = useRef(new RefRegistry()).current;
  const navIntent = useRef<"follow" | "trail" | "reset" | null>(null);
  const pendingG = useRef(0);
  const staleIntent = useRef(false);
  const prevView = useRef(view);
  const filterInput = useRef<HTMLInputElement | null>(null);
  const entryPaneRef = useRef<HTMLDivElement | null>(null);
  const copyTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const dragState = useRef<{
    pane: "rail" | "index";
    startX: number;
    startW: number;
  } | null>(null);

  const rows = useMemo(
    () => rowsFor(substrate, view, sort[view], filter, staleOnly),
    [substrate, view, sort, filter, staleOnly],
  );
  const rowHrefs = useMemo(() => {
    const map = new Map<string, string>();
    for (const r of rows.rows) if (r.rowType === "entry") map.set(r.id, r.href);
    return map;
  }, [rows]);
  const rails = useMemo(() => railRows(substrate), [substrate]);

  const headwordOf = useCallback(
    (m: EntryModel): string => {
      switch (m.kind) {
        case "term":
          return m.term.term;
        case "phrase":
          return m.phrase.phrase;
        case "edge":
          return `${substrate.terms[m.edge.from]?.term ?? m.edge.from} → ${substrate.terms[m.edge.to]?.term ?? m.edge.to}`;
        case "chapter":
          return m.chapter.title;
      }
    },
    [substrate],
  );

  // ---- boot: persisted widths / sort, legacy-key cleanup ----
  useEffect(() => {
    try {
      const rw = parseInt(localStorage.getItem("chiron.railWidth") ?? "", 10);
      if (Number.isFinite(rw)) setRailWidth(clampWidth(rw));
      const iw = parseInt(localStorage.getItem("chiron.indexWidth") ?? "", 10);
      if (Number.isFinite(iw)) setIndexWidth(clampWidth(iw));
      const raw = localStorage.getItem("chiron.sort");
      if (raw) {
        const stored = JSON.parse(raw) as Partial<Record<ViewKey, SortMode>>;
        setSort((s) => {
          const next = { ...s };
          for (const v of Object.keys(SORT_CYCLES) as ViewKey[]) {
            const mode = stored[v];
            if (mode && SORT_CYCLES[v].includes(mode)) next[v] = mode;
          }
          return next;
        });
      }
      for (const k of LEGACY_KEYS) localStorage.removeItem(k);
      sessionStorage.removeItem("chiron.tabs");
    } catch {
      // localStorage unavailable — defaults are fine
    }
    setLoaded(true);
  }, []);
  useEffect(() => {
    if (!loaded) return;
    try {
      localStorage.setItem("chiron.railWidth", String(railWidth));
      localStorage.setItem("chiron.indexWidth", String(indexWidth));
    } catch {}
  }, [railWidth, indexWidth, loaded]);

  // ---- pane resize ----
  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      const d = dragState.current;
      if (!d) return;
      const w = clampWidth(d.startW + e.clientX - d.startX);
      if (d.pane === "rail") setRailWidth(w);
      else setIndexWidth(w);
    };
    const onUp = () => {
      dragState.current = null;
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, []);

  // ---- view change: reset filter; staleOnly survives only a drift jump ----
  useEffect(() => {
    if (prevView.current === view) return;
    prevView.current = view;
    setFilter("");
    if (staleIntent.current) staleIntent.current = false;
    else setStaleOnly(false);
  }, [view]);

  // ---- cursor follows selection; stays visible under filters ----
  useEffect(() => {
    setCursorId(selection ?? null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selection]);
  useEffect(() => {
    if (cursorId && rows.entryIds.includes(cursorId)) return;
    const fallback =
      selection && rows.entryIds.includes(selection)
        ? selection
        : (rows.entryIds[0] ?? null);
    if (fallback !== cursorId) setCursorId(fallback);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows]);

  // ---- entry change: reset ref cursor, hints, peek; scroll to top ----
  useEffect(() => {
    setRefCursor(null);
    setHint(null);
    setOverlay((o) => (o?.kind === "peek" ? null : o));
    entryPaneRef.current?.scrollTo({ top: 0 });
  }, [pathname]);

  // ---- trail reconciliation (browser back/forward, resets) ----
  useEffect(() => {
    const intent = navIntent.current;
    navIntent.current = null;
    if (intent === "follow" || intent === "trail") return; // already applied
    const model = entryAt(substrate, parseViewerPath(pathname));
    if (intent === "reset") {
      setTrail(
        model
          ? { entries: [{ href: pathname, headword: headwordOf(model) }], pos: 0 }
          : { entries: [], pos: 0 },
      );
      return;
    }
    setTrail((t) => {
      if (!model) return t; // index/root: bar is hidden, keep the stack
      if (t.entries[t.pos]?.href === pathname) return t;
      if (t.entries[t.pos - 1]?.href === pathname) return { ...t, pos: t.pos - 1 };
      if (t.entries[t.pos + 1]?.href === pathname) return { ...t, pos: t.pos + 1 };
      return { entries: [{ href: pathname, headword: headwordOf(model) }], pos: 0 };
    });
  }, [pathname, substrate, headwordOf]);

  // ---- compact peek closes on scroll/resize (the expanded card is modal) ----
  useEffect(() => {
    if (overlay?.kind !== "peek" || overlay.expanded) return;
    const close = () => setOverlay(null);
    const pane = entryPaneRef.current;
    pane?.addEventListener("scroll", close);
    window.addEventListener("resize", close);
    return () => {
      pane?.removeEventListener("scroll", close);
      window.removeEventListener("resize", close);
    };
  }, [overlay]);

  // ---- navigation ----
  const follow = useCallback(
    (href: string) => {
      setHint(null);
      setOverlay(null);
      if (href === pathname) return;
      const model = entryAt(substrate, parseViewerPath(href));
      if (!model) {
        navIntent.current = "reset";
        router.push(href);
        return;
      }
      setTrail((t) => {
        const entries = t.entries.slice(0, t.pos + 1);
        entries.push({ href, headword: headwordOf(model) });
        while (entries.length > TRAIL_CAP) entries.shift();
        return { entries, pos: entries.length - 1 };
      });
      navIntent.current = "follow";
      router.push(href);
    },
    [pathname, substrate, router, headwordOf],
  );

  const navigateReset = (href: string) => {
    setHint(null);
    setOverlay(null);
    if (href === pathname) {
      const model = entryAt(substrate, parseViewerPath(href));
      setTrail(
        model
          ? { entries: [{ href, headword: headwordOf(model) }], pos: 0 }
          : { entries: [], pos: 0 },
      );
      return;
    }
    navIntent.current = "reset";
    router.push(href);
  };

  const trailGo = (target: number) => {
    if (target < 0 || target >= trail.entries.length || target === trail.pos)
      return;
    setTrail({ ...trail, pos: target });
    navIntent.current = "trail";
    router.push(trail.entries[target].href);
  };

  const trailClear = () => {
    setTrail((t) =>
      t.entries[t.pos]
        ? { entries: [t.entries[t.pos]], pos: 0 }
        : { entries: [], pos: 0 },
    );
  };

  // ---- movement ----
  const moveIndexCursor = (delta: number) => {
    const ids = rows.entryIds;
    if (!ids.length) return;
    const i = cursorId ? ids.indexOf(cursorId) : -1;
    const next =
      i === -1
        ? delta > 0
          ? 0
          : ids.length - 1
        : Math.max(0, Math.min(ids.length - 1, i + delta));
    setCursorId(ids[next]);
  };

  const moveRef = (delta: number, filterFn?: (t: RefTarget) => boolean) => {
    const all = registry.ordered();
    const list = filterFn ? all.filter(filterFn) : all;
    if (!list.length) {
      // Nothing to land on — page the reading surface instead.
      const pane = entryPaneRef.current;
      pane?.scrollBy({ top: delta * pane.clientHeight * 0.8, behavior: "smooth" });
      return;
    }
    const cur = refCursor ? list.findIndex((t) => t.id === refCursor) : -1;
    const next =
      cur === -1
        ? delta > 0
          ? 0
          : list.length - 1
        : (cur + delta + list.length) % list.length;
    const target = list[next];
    setRefCursor(target.id);
    target.el.scrollIntoView({ block: "nearest" });
    target.el.focus?.({ preventScroll: true });
  };

  const doTop = (bottom = false) => {
    if (focusedPane === "rail") {
      setRailCursor(bottom ? rails.length - 1 : 0);
    } else if (focusedPane === "index") {
      const ids = rows.entryIds;
      if (ids.length) setCursorId(bottom ? ids[ids.length - 1] : ids[0]);
    } else {
      const pane = entryPaneRef.current;
      pane?.scrollTo({ top: bottom ? pane.scrollHeight : 0 });
      const all = registry.ordered();
      if (all.length) setRefCursor(bottom ? all[all.length - 1].id : all[0].id);
    }
  };

  // ---- actions ----
  const activateRail = (row: RailRow) => {
    if (row.kind === "register") {
      if (row.href) navigateReset(row.href);
    } else if (row.kind === "chapters") {
      navigateReset(viewHref(base, "chapters"));
    } else {
      setStaleOnly(true);
      if (view !== "chapters") staleIntent.current = true;
      navigateReset(viewHref(base, "chapters"));
    }
  };

  const stepEntry = (delta: number) => {
    const ids = rows.entryIds;
    if (!ids.length) return;
    let i = selection ? ids.indexOf(selection) : -1;
    if (i === -1 && cursorId) i = ids.indexOf(cursorId);
    const next =
      i === -1
        ? delta > 0
          ? 0
          : ids.length - 1
        : Math.max(0, Math.min(ids.length - 1, i + delta));
    const href = rowHrefs.get(ids[next]);
    if (href && ids[next] !== selection) navigateReset(href);
  };

  const startHints = () => {
    const targets = registry.ordered();
    if (!targets.length) return;
    const labels = hintLabels(targets.length);
    setHint({
      labels: new Map(targets.map((t, i) => [t.id, labels[i]])),
      buffer: "",
    });
  };

  const openPeek = () => {
    if (!refCursor) return;
    const t = registry.get(refCursor);
    if (!t) return;
    if (!entryAt(substrate, parseViewerPath(t.href))) return;
    const measure = entryPaneRef.current
      ?.querySelector(".entry-body")
      ?.getBoundingClientRect();
    setOverlay({
      kind: "peek",
      targetId: refCursor,
      rect: t.el.getBoundingClientRect(),
      measureRect: measure ?? null,
      expanded: false,
    });
  };

  const openDrill = () => {
    if (view === "chapters") return;
    const items = buildDrillItems(substrate, view, rows.entryIds);
    if (items.length) setOverlay({ kind: "drill", items });
  };

  const doCopy = () => {
    if (!entry) return;
    const text =
      entry.kind === "term"
        ? entry.term.term
        : entry.kind === "phrase"
          ? (entry.phrase.template ?? entry.phrase.phrase)
          : null;
    if (!text) return;
    navigator.clipboard
      ?.writeText(text)
      .then(() => {
        setCopied(true);
        if (copyTimer.current) clearTimeout(copyTimer.current);
        copyTimer.current = setTimeout(() => setCopied(false), 1200);
      })
      .catch(() => {});
  };

  const toggleTheme = () => {
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
  };

  const run = (action: ShellAction) => {
    switch (action) {
      case "pane-prev":
        setFocusedPane((p) => PANES[Math.max(0, PANES.indexOf(p) - 1)]);
        break;
      case "pane-next":
        setFocusedPane((p) =>
          PANES[Math.min(PANES.length - 1, PANES.indexOf(p) + 1)],
        );
        break;
      case "cursor-down":
      case "cursor-up": {
        const delta = action === "cursor-down" ? 1 : -1;
        if (focusedPane === "rail")
          setRailCursor((c) =>
            Math.max(0, Math.min(rails.length - 1, c + delta)),
          );
        else if (focusedPane === "index") moveIndexCursor(delta);
        else moveRef(delta);
        break;
      }
      case "cursor-top":
        doTop(false);
        break;
      case "cursor-bottom":
        doTop(true);
        break;
      case "activate":
        if (focusedPane === "rail") {
          const row = rails[railCursor];
          if (row) activateRail(row);
        } else if (focusedPane === "index") {
          const href = cursorId ? rowHrefs.get(cursorId) : undefined;
          if (href) navigateReset(href);
        } else if (refCursor) {
          const t = registry.get(refCursor);
          if (t) follow(t.href);
        }
        break;
      case "view-1":
      case "view-2":
      case "view-3": {
        const n = Number(action.slice(-1)) - 1;
        const mode = substrate.register.modes[n];
        if (mode) navigateReset(viewHref(base, mode));
        break;
      }
      case "view-4":
        navigateReset(viewHref(base, "chapters"));
        break;
      case "scope":
        router.push("/");
        break;
      case "hints":
        startHints();
        break;
      case "peek":
        openPeek();
        break;
      case "ref-next":
        moveRef(1, (t) => !t.isAnchor);
        break;
      case "ref-prev":
        moveRef(-1, (t) => !t.isAnchor);
        break;
      case "anchor-next":
        moveRef(1, (t) => t.isAnchor);
        break;
      case "entry-next":
        stepEntry(1);
        break;
      case "entry-prev":
        stepEntry(-1);
        break;
      case "open-source":
        if (entry?.kind === "chapter" && entry.chapter.sourceUrl)
          window.open(entry.chapter.sourceUrl, "_blank", "noopener");
        break;
      case "copy":
        doCopy();
        break;
      case "trail-back":
        trailGo(trail.pos - 1);
        break;
      case "trail-forward":
        trailGo(trail.pos + 1);
        break;
      case "trail-clear":
        trailClear();
        break;
      case "filter":
        setFocusedPane("index");
        filterInput.current?.focus();
        break;
      case "jump":
        setOverlay({ kind: "jump" });
        break;
      case "drill":
        openDrill();
        break;
      case "theme":
        toggleTheme();
        break;
      case "help":
        setOverlay({ kind: "help" });
        break;
      case "sort":
        setSort((s) => {
          const next = { ...s, [view]: cycleSort(view, s[view]) };
          try {
            localStorage.setItem("chiron.sort", JSON.stringify(next));
          } catch {}
          return next;
        });
        break;
      case "escape":
        if (filter) setFilter("");
        else if (staleOnly) setStaleOnly(false);
        break;
    }
  };

  // ---- the one keyboard ----
  const handleKey = (e: KeyboardEvent) => {
    if (e.defaultPrevented) return;
    if (
      (e.metaKey || e.ctrlKey) &&
      !e.altKey &&
      !e.shiftKey &&
      e.key.toLowerCase() === "k"
    ) {
      e.preventDefault();
      setHint(null);
      setOverlay((o) => (o?.kind === "jump" ? null : { kind: "jump" }));
      return;
    }
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    const target = e.target as HTMLElement | null;
    if (target?.closest("input, textarea, select, [contenteditable]")) return;

    if (overlay) {
      if (overlay.kind === "peek") {
        if (e.key === " " || e.key === "Escape") {
          e.preventDefault();
          setOverlay(null);
        } else if (e.key === "Enter") {
          // Never a navigation: enter expands the peek into the full entry
          // in place; on the expanded card it closes.
          e.preventDefault();
          setOverlay(overlay.expanded ? null : { ...overlay, expanded: true });
        } else if (overlay.expanded) {
          // j/k scroll the card (its own listener); other keys pass.
        } else {
          setOverlay(null); // any other key just dismisses the compact peek
        }
      } else if (overlay.kind === "help") {
        if (e.key === "Escape" || e.key === "?") {
          e.preventDefault();
          setOverlay(null);
        }
      } else if (e.key === "Escape") {
        // jump: input owns its keys; drill: its own listener handles the rest
        e.preventDefault();
        setOverlay(null);
      }
      return;
    }

    if (hint) {
      if (/^[a-z]$/.test(e.key)) {
        e.preventDefault();
        const buffer = hint.buffer + e.key;
        const entries = [...hint.labels.entries()];
        const exact = entries.find(([, label]) => label === buffer);
        if (exact) {
          setHint(null);
          const t = registry.get(exact[0]);
          if (t) follow(t.href);
        } else if (entries.some(([, label]) => label.startsWith(buffer))) {
          setHint({ ...hint, buffer });
        } else {
          setHint(null);
        }
      } else {
        e.preventDefault();
        setHint(null);
      }
      return;
    }

    if (pendingG.current && Date.now() - pendingG.current < GG_WINDOW_MS) {
      pendingG.current = 0;
      if (e.key === "g") {
        e.preventDefault();
        doTop(false);
        return;
      }
      // an interrupted g falls through to normal handling
    } else {
      pendingG.current = 0;
    }
    if (e.key === "g") {
      e.preventDefault();
      pendingG.current = Date.now();
      return;
    }
    if (e.key === "Backspace" && e.shiftKey) {
      e.preventDefault();
      trailClear();
      return;
    }

    const action = KEY_LOOKUP.get(e.key);
    if (!action) return;
    e.preventDefault();
    run(action);
  };

  const handlerRef = useRef<(e: KeyboardEvent) => void>(() => {});
  handlerRef.current = handleKey;
  useEffect(() => {
    const listener = (e: KeyboardEvent) => handlerRef.current(e);
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  }, []);

  const api: ShellApi = useMemo(
    () => ({ substrate, registry, refCursor, hint, copied, follow }),
    [substrate, registry, refCursor, hint, copied, follow],
  );

  const peekModel =
    overlay?.kind === "peek"
      ? (() => {
          const t = registry.get(overlay.targetId);
          return t ? entryAt(substrate, parseViewerPath(t.href)) : null;
        })()
      : null;

  const focusPaneFromEvent = (e: React.MouseEvent) => {
    const el = e.target as HTMLElement;
    if (el.closest(".rail")) setFocusedPane("rail");
    else if (el.closest(".index-pane")) setFocusedPane("index");
    else if (el.closest(".entry-column")) setFocusedPane("entry");
  };

  return (
    <ShellContext.Provider value={api}>
      <div
        className={`shell${mobileNav ? " mobile-nav" : ""}`}
        data-dim={view}
        style={
          {
            "--rail-w": `${railWidth}px`,
            "--index-w": `${indexWidth}px`,
          } as React.CSSProperties
        }
        onMouseDownCapture={focusPaneFromEvent}
      >
        <Rail
          substrate={substrate}
          view={viewOf(location)}
          cursor={railCursor}
          focused={focusedPane === "rail"}
          onActivate={activateRail}
        />
        <div
          className="pane-handle rail-handle"
          onMouseDown={(e) => {
            e.preventDefault();
            dragState.current = {
              pane: "rail",
              startX: e.clientX,
              startW: railWidth,
            };
          }}
        />
        <IndexPane
          view={view}
          rows={rows}
          cursorId={cursorId}
          selectedId={selection}
          focused={focusedPane === "index"}
          filter={filter}
          staleOnly={staleOnly}
          sort={sort[view]}
          filterRef={filterInput}
          onFilterChange={setFilter}
          onFilterCommit={() => {
            setFocusedPane("index");
            if (!cursorId && rows.entryIds.length) setCursorId(rows.entryIds[0]);
          }}
          onOpen={(id) => {
            const href = rowHrefs.get(id);
            if (href) navigateReset(href);
          }}
        />
        <div
          className="pane-handle index-handle"
          onMouseDown={(e) => {
            e.preventDefault();
            dragState.current = {
              pane: "index",
              startX: e.clientX,
              startW: indexWidth,
            };
          }}
        />
        <div
          className={`pane entry-column${focusedPane === "entry" ? " focused" : ""}`}
        >
          <Trail entries={trail.entries} pos={trail.pos} onJump={trailGo} />
          <div className="entry-pane" ref={entryPaneRef}>
            <EntryPane
              substrate={substrate}
              entry={entry}
              view={viewOf(location)}
            />
            {children}
          </div>
        </div>

        {overlay?.kind === "help" && <Help onClose={() => setOverlay(null)} />}
        {overlay?.kind === "jump" && (
          <Jump
            docs={substrate.search}
            onOpen={(href) => navigateReset(href)}
            onClose={() => setOverlay(null)}
          />
        )}
        {overlay?.kind === "drill" && (
          <Drill items={overlay.items} onClose={() => setOverlay(null)} />
        )}
        {overlay?.kind === "peek" && peekModel && !overlay.expanded && (
          <Peek
            entry={peekModel}
            targetRect={overlay.rect}
            measureRect={overlay.measureRect}
          />
        )}
        {overlay?.kind === "peek" && peekModel && overlay.expanded && (
          <PeekExpanded entry={peekModel} onClose={() => setOverlay(null)} />
        )}

        <button
          type="button"
          className="mobile-toggle"
          aria-label="Toggle navigation"
          onClick={() => setMobileNav((v) => !v)}
        >
          ☰
        </button>
      </div>
    </ShellContext.Provider>
  );
}
