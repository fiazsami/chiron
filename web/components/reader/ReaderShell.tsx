"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  KEYMAP,
  chapterAt,
  listRowsFor,
  scopeFor,
  type ChapterRow,
  type Scope,
} from "@/lib/reader";
import {
  activeRegister,
  segmentsOf,
  type WorkspaceData,
} from "@/lib/workspace-types";
import ArticleList from "./ArticleList";
import NavigatorPopup, {
  captureSelection,
  type CapturedSelection,
} from "./NavigatorPopup";
import Sidebar from "./Sidebar";

const STORE = {
  sidebarWidth: "chiron.sidebarWidth",
  listWidth: "chiron.listWidth",
  collapsed: "chiron.collapsedGroups",
  scope: "chiron.scope",
};

// Storage keys of the retired IDE shell, cleared once on load.
const LEGACY_KEYS = [
  "chiron.explorerOpen",
  "chiron.coachOpen",
  "chiron.explorerWidth",
  "chiron.coachWidth",
];
const LEGACY_SESSION_KEYS = ["chiron.tabs"];

const SIDEBAR_WIDTH = { def: 260, min: 200, max: 360 };
const LIST_WIDTH = { def: 360, min: 300, max: 480 };

function clamp(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, v));
}

function parseScope(key: string, stored: string | undefined): Scope | null {
  if (stored === "all") return { kind: "all", key };
  if (stored?.startsWith("group:")) {
    return { kind: "group", key, group: stored.slice("group:".length) };
  }
  return null;
}

function encodeScope(scope: Scope): string {
  return scope.kind === "all" ? "all" : `group:${scope.group}`;
}

interface NavigatorRequest extends CapturedSelection {
  corpus: string;
  register: string;
}

// The Reeder-style shell: sidebar | article list | article pane. Mounted
// once in the root layout; the URL is the single source of truth for what
// is selected, and the keymap (lib/reader.ts) drives navigation.
export default function ReaderShell({
  data,
  children,
}: {
  data: WorkspaceData;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();

  const [sidebarWidth, setSidebarWidth] = useState(SIDEBAR_WIDTH.def);
  const [listWidth, setListWidth] = useState(LIST_WIDTH.def);
  const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(new Set());
  const [scopes, setScopes] = useState<Record<string, string>>({});
  const [nav, setNav] = useState<NavigatorRequest | null>(null);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [dragging, setDragging] = useState<"sidebar" | "list" | null>(null);

  const articleRef = useRef<HTMLElement>(null);
  const lastIndexRef = useRef(0);

  // usePathname is percent-encoded; workspace hrefs are not.
  const decodedPath = useMemo(() => {
    const seg = segmentsOf(pathname);
    return seg.length ? `/${seg.join("/")}` : "/";
  }, [pathname]);

  const reg = activeRegister(data, pathname);
  const scope = useMemo<Scope | null>(() => {
    const resolved = reg
      ? scopeFor(data, pathname, parseScope(reg.key, scopes[reg.key]))
      : null;
    if (resolved) return resolved;
    // No register in the URL (the corpora index): show the first register's
    // remembered scope so the list pane is never pointlessly empty.
    const fallback = data.registers[0]?.key;
    if (!fallback) return null;
    return parseScope(fallback, scopes[fallback]) ?? { kind: "all", key: fallback };
  }, [data, pathname, reg, scopes]);

  const rows = useMemo(
    () => listRowsFor(data, scope, collapsed),
    [data, scope, collapsed],
  );
  const chapterRows = useMemo(
    () => rows.filter((r): r is ChapterRow => r.kind === "chapter"),
    [rows],
  );

  // Restore persisted layout once on mount; the persistence effect below
  // waits for `loaded` so defaults never clobber storage.
  useEffect(() => {
    try {
      const sw = Number(localStorage.getItem(STORE.sidebarWidth));
      if (sw) setSidebarWidth(clamp(sw, SIDEBAR_WIDTH.min, SIDEBAR_WIDTH.max));
      const lw = Number(localStorage.getItem(STORE.listWidth));
      if (lw) setListWidth(clamp(lw, LIST_WIDTH.min, LIST_WIDTH.max));
      const storedCollapsed = localStorage.getItem(STORE.collapsed);
      if (storedCollapsed) {
        const parsed = JSON.parse(storedCollapsed) as unknown;
        if (Array.isArray(parsed)) {
          setCollapsed(new Set(parsed.filter((t) => typeof t === "string")));
        }
      }
      const storedScopes = localStorage.getItem(STORE.scope);
      if (storedScopes) {
        const parsed = JSON.parse(storedScopes) as unknown;
        if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
          setScopes(
            Object.fromEntries(
              Object.entries(parsed as Record<string, unknown>).filter(
                ([, v]) => typeof v === "string",
              ),
            ) as Record<string, string>,
          );
        }
      }
      for (const key of LEGACY_KEYS) localStorage.removeItem(key);
      for (const key of LEGACY_SESSION_KEYS) sessionStorage.removeItem(key);
    } catch {
      // Storage unavailable (private mode) — defaults are fine.
    }
    setLoaded(true);
  }, []);

  useEffect(() => {
    if (!loaded) return;
    try {
      localStorage.setItem(STORE.sidebarWidth, String(sidebarWidth));
      localStorage.setItem(STORE.listWidth, String(listWidth));
      localStorage.setItem(STORE.collapsed, JSON.stringify([...collapsed]));
      localStorage.setItem(STORE.scope, JSON.stringify(scopes));
    } catch {
      // Storage unavailable — layout just won't persist.
    }
  }, [loaded, sidebarWidth, listWidth, collapsed, scopes]);

  // Sticky scope memory: remember the resolved scope per register so
  // article/dimension URLs keep the folder the learner was browsing in.
  useEffect(() => {
    if (!loaded || !reg || !scope || scope.key !== reg.key) return;
    const encoded = encodeScope(scope);
    if (scopes[reg.key] !== encoded) {
      setScopes((prev) => ({ ...prev, [reg.key]: encoded }));
    }
  }, [loaded, reg, scope, scopes]);

  // New page: reset the article scroll (unless a fragment owns it) and
  // remember where the current article sits in the visible list.
  useEffect(() => {
    if (!window.location.hash) {
      articleRef.current?.scrollTo({ top: 0 });
    }
    setMobileNavOpen(false);
  }, [pathname]);

  useEffect(() => {
    const i = chapterRows.findIndex((r) => r.chapter.href === decodedPath);
    if (i >= 0) lastIndexRef.current = i;
  }, [chapterRows, decodedPath]);

  function moveSelection(delta: number) {
    if (chapterRows.length === 0) return;
    const current = chapterRows.findIndex(
      (r) => r.chapter.href === decodedPath,
    );
    // Off-list (dimension surface open, or the article's group was folded):
    // re-enter the list at the remembered spot instead of jumping past it.
    const target =
      current >= 0
        ? current + delta
        : clamp(lastIndexRef.current, 0, chapterRows.length - 1);
    if (target < 0 || target >= chapterRows.length) return;
    router.push(chapterRows[target].chapter.href);
  }

  function scrollArticle(direction: 1 | -1) {
    const el = articleRef.current;
    if (!el) return;
    el.scrollBy({ top: direction * el.clientHeight * 0.8, behavior: "smooth" });
  }

  function toggleGroup(token: string) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(token)) next.delete(token);
      else next.add(token);
      return next;
    });
  }

  function toggleCurrentGroup() {
    const chapter = chapterAt(data, pathname);
    if (chapter) {
      toggleGroup(`${chapter.key}/${chapter.group}`);
      return;
    }
    // On a group landing page, `i` toggles that group.
    const seg = segmentsOf(pathname);
    if (reg && seg.length === 3 && reg.groups.some((g) => g.id === seg[2])) {
      toggleGroup(`${reg.key}/${seg[2]}`);
    }
  }

  function openNavigator(): boolean {
    if (!reg) return false;
    const captured = captureSelection(articleRef.current);
    if (!captured) return false;
    setNav({ corpus: reg.corpus, register: reg.register, ...captured });
    return true;
  }

  // Single window listener, attached once; the ref closes over fresh state
  // every render.
  const handlerRef = useRef<(e: KeyboardEvent) => void>(() => {});
  handlerRef.current = (e: KeyboardEvent) => {
    if (e.defaultPrevented) return;
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    const target = e.target as HTMLElement | null;
    if (target?.closest("input, textarea, select, [contenteditable]")) return;
    if (nav) {
      // The popup owns the keyboard; Escape here is a fallback in case
      // focus escaped the dialog.
      if (e.key === "Escape") setNav(null);
      return;
    }
    const action = KEYMAP[e.key];
    if (!action) return;
    switch (action) {
      case "prevArticle":
        e.preventDefault();
        moveSelection(-1);
        break;
      case "nextArticle":
        e.preventDefault();
        moveSelection(1);
        break;
      case "scrollDown":
        e.preventDefault();
        scrollArticle(1);
        break;
      case "scrollUp":
        e.preventDefault();
        scrollArticle(-1);
        break;
      case "toggleGroup":
        e.preventDefault();
        toggleCurrentGroup();
        break;
      case "navigator":
        if (openNavigator()) e.preventDefault();
        break;
    }
  };
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => handlerRef.current(e);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  function startDrag(side: "sidebar" | "list") {
    return (e: React.PointerEvent) => {
      e.preventDefault();
      setDragging(side);
      const startX = e.clientX;
      const startW = side === "sidebar" ? sidebarWidth : listWidth;
      function onMove(ev: PointerEvent) {
        const dx = ev.clientX - startX;
        if (side === "sidebar") {
          setSidebarWidth(clamp(startW + dx, SIDEBAR_WIDTH.min, SIDEBAR_WIDTH.max));
        } else {
          setListWidth(clamp(startW + dx, LIST_WIDTH.min, LIST_WIDTH.max));
        }
      }
      function onUp() {
        setDragging(null);
        window.removeEventListener("pointermove", onMove);
      }
      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp, { once: true });
    };
  }

  const listReg = scope
    ? data.registers.find((r) => r.key === scope.key)
    : null;
  const header =
    scope?.kind === "group"
      ? (listReg?.groups.find((g) => g.id === scope.group)?.label ??
        scope.group)
      : (listReg?.title ?? "");
  const scopeCount = scope
    ? data.chapters.filter(
        (c) =>
          c.key === scope.key &&
          (scope.kind === "all" || c.group === scope.group),
      ).length
    : 0;
  const sub = scope
    ? `${scopeCount} chapter${scopeCount === 1 ? "" : "s"}`
    : "";

  return (
    <div className={`reader${mobileNavOpen ? " mobile-nav" : ""}`}>
      <button
        className="mobile-toggle"
        onClick={() => setMobileNavOpen((o) => !o)}
        aria-label="Toggle navigation"
      >
        ☰
      </button>
      <aside className="sidebar" style={{ width: sidebarWidth }}>
        <Sidebar
          data={data}
          pathname={decodedPath}
          scope={scope}
          collapsed={collapsed}
          onToggleGroup={toggleGroup}
        />
      </aside>
      <div
        className={`pane-handle${dragging === "sidebar" ? " dragging" : ""}`}
        onPointerDown={startDrag("sidebar")}
        onDoubleClick={() => setSidebarWidth(SIDEBAR_WIDTH.def)}
      />
      <section className="list-pane" style={{ width: listWidth }}>
        <ArticleList
          rows={rows}
          activeHref={decodedPath}
          header={header}
          sub={sub}
        />
      </section>
      <div
        className={`pane-handle${dragging === "list" ? " dragging" : ""}`}
        onPointerDown={startDrag("list")}
        onDoubleClick={() => setListWidth(LIST_WIDTH.def)}
      />
      <main className="article-pane" ref={articleRef}>
        <div className="article-content">{children}</div>
      </main>
      {nav && (
        <NavigatorPopup
          corpus={nav.corpus}
          register={nav.register}
          pathname={pathname}
          selection={nav.selection}
          context={nav.context}
          onClose={() => setNav(null)}
        />
      )}
    </div>
  );
}
