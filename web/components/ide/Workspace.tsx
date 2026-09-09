"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  activeRegister,
  breadcrumbsFor,
  readingOrder,
  routeLabel,
  type WorkspaceData,
} from "@/lib/workspace-types";
import CoachPane, { type CoachHandle } from "./CoachPane";
import CommandPalette from "./CommandPalette";
import Explorer, { type ExplorerHandle } from "./Explorer";
import HelpOverlay from "./HelpOverlay";
import StatusBar from "./StatusBar";

interface Tab {
  href: string;
  label: string;
}

const STORE = {
  explorerOpen: "chiron.explorerOpen",
  coachOpen: "chiron.coachOpen",
  explorerWidth: "chiron.explorerWidth",
  coachWidth: "chiron.coachWidth",
  tabs: "chiron.tabs",
};

const EXPLORER_WIDTH = { def: 264, min: 200, max: 480 };
const COACH_WIDTH = { def: 372, min: 280, max: 600 };

function clamp(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, v));
}

// The IDE shell: explorer tree | editor (tabs + breadcrumbs + routed page)
// | coach pane, over a status bar, with a command palette and TUI-style
// keybindings. Mounted once in the root layout; panes stay mounted while
// hidden so their state (tree selection, chats) survives toggling.
export default function Workspace({
  data,
  children,
}: {
  data: WorkspaceData;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();

  const [explorerOpen, setExplorerOpen] = useState(true);
  const [coachOpen, setCoachOpen] = useState(false);
  const [explorerWidth, setExplorerWidth] = useState(EXPLORER_WIDTH.def);
  const [coachWidth, setCoachWidth] = useState(COACH_WIDTH.def);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [tabs, setTabs] = useState<Tab[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [dragging, setDragging] = useState<"explorer" | "coach" | null>(null);

  const explorerRef = useRef<ExplorerHandle>(null);
  const coachRef = useRef<CoachHandle>(null);
  const editorRef = useRef<HTMLDivElement>(null);

  const reg = activeRegister(data, pathname);
  const crumbs = useMemo(() => breadcrumbsFor(data, pathname), [data, pathname]);

  // Restore persisted layout once on mount; persistence effects below wait
  // for `loaded` so they never clobber storage with the defaults.
  useEffect(() => {
    try {
      const eo = localStorage.getItem(STORE.explorerOpen);
      if (eo !== null) setExplorerOpen(eo === "1");
      const co = localStorage.getItem(STORE.coachOpen);
      if (co !== null) setCoachOpen(co === "1");
      const ew = Number(localStorage.getItem(STORE.explorerWidth));
      if (ew) setExplorerWidth(clamp(ew, EXPLORER_WIDTH.min, EXPLORER_WIDTH.max));
      const cw = Number(localStorage.getItem(STORE.coachWidth));
      if (cw) setCoachWidth(clamp(cw, COACH_WIDTH.min, COACH_WIDTH.max));
      const stored = sessionStorage.getItem(STORE.tabs);
      if (stored) setTabs(JSON.parse(stored) as Tab[]);
    } catch {
      // Storage unavailable (private mode) — defaults are fine.
    }
    setLoaded(true);
  }, []);

  useEffect(() => {
    if (!loaded) return;
    try {
      localStorage.setItem(STORE.explorerOpen, explorerOpen ? "1" : "0");
      localStorage.setItem(STORE.coachOpen, coachOpen ? "1" : "0");
      localStorage.setItem(STORE.explorerWidth, String(explorerWidth));
      localStorage.setItem(STORE.coachWidth, String(coachWidth));
      sessionStorage.setItem(STORE.tabs, JSON.stringify(tabs));
    } catch {
      // Storage unavailable — layout just won't persist.
    }
  }, [loaded, explorerOpen, coachOpen, explorerWidth, coachWidth, tabs]);

  // Open a tab for the current route and reset the editor scroll.
  useEffect(() => {
    if (!loaded) return;
    setTabs((ts) =>
      ts.some((t) => t.href === pathname)
        ? ts
        : [...ts, { href: pathname, label: routeLabel(data, pathname) }],
    );
    editorRef.current?.scrollTo({ top: 0 });
  }, [loaded, pathname, data]);

  function closeTab(href: string) {
    const i = tabs.findIndex((t) => t.href === href);
    if (i < 0) return;
    const next = tabs.filter((t) => t.href !== href);
    setTabs(next);
    if (href === pathname) {
      router.push(next[Math.min(i, next.length - 1)]?.href ?? "/");
    }
  }

  function cycleTab(delta: number) {
    if (tabs.length < 2) return;
    const i = tabs.findIndex((t) => t.href === pathname);
    const j = (Math.max(i, 0) + delta + tabs.length) % tabs.length;
    router.push(tabs[j].href);
  }

  function pageBy(delta: number) {
    if (!reg) return;
    const order = readingOrder(data, reg.key);
    const i = order.indexOf(pathname);
    if (i < 0) return;
    const next = order[i + delta];
    if (next) router.push(next);
  }

  function openCoach() {
    setCoachOpen(true);
    setTimeout(() => coachRef.current?.focus(), 0);
  }

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.defaultPrevented) return;
      const target = e.target as HTMLElement | null;
      const inField = Boolean(
        target?.closest("input, textarea, select, [contenteditable]"),
      );
      const mod = e.metaKey || e.ctrlKey;

      // Chorded shortcuts work everywhere, including inside fields.
      if (mod && !e.altKey && !e.shiftKey) {
        if (e.key === "k" || e.key === "p") {
          e.preventDefault();
          setPaletteOpen((o) => !o);
          return;
        }
        if (e.key === "b") {
          e.preventDefault();
          setExplorerOpen((o) => !o);
          return;
        }
        if (e.key === "j") {
          e.preventDefault();
          if (coachOpen) setCoachOpen(false);
          else openCoach();
          return;
        }
      }
      if (inField || mod || e.altKey) return;

      if (paletteOpen || helpOpen) {
        if (e.key === "Escape") {
          setPaletteOpen(false);
          setHelpOpen(false);
        }
        return;
      }

      switch (e.key) {
        case "/":
          e.preventDefault();
          setPaletteOpen(true);
          break;
        case "?":
          setHelpOpen(true);
          break;
        case "b":
          setExplorerOpen((o) => !o);
          break;
        case "c":
          if (coachOpen) setCoachOpen(false);
          else openCoach();
          break;
        case "j":
          if (explorerOpen) explorerRef.current?.move(1);
          break;
        case "k":
          if (explorerOpen) explorerRef.current?.move(-1);
          break;
        case "h":
          if (explorerOpen) explorerRef.current?.left();
          break;
        case "l":
          if (explorerOpen) explorerRef.current?.right();
          break;
        case "o":
          if (explorerOpen) explorerRef.current?.open();
          break;
        case "Enter":
          // Only treat Enter as tree-open when it wouldn't activate a
          // focused link or button natively.
          if (explorerOpen && !target?.closest("a, button")) {
            e.preventDefault();
            explorerRef.current?.open();
          }
          break;
        case "[":
          pageBy(-1);
          break;
        case "]":
          pageBy(1);
          break;
        case "{":
          cycleTab(-1);
          break;
        case "}":
          cycleTab(1);
          break;
        case "x":
          closeTab(pathname);
          break;
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  function startDrag(side: "explorer" | "coach") {
    return (e: React.PointerEvent) => {
      e.preventDefault();
      setDragging(side);
      const startX = e.clientX;
      const startW = side === "explorer" ? explorerWidth : coachWidth;
      function onMove(ev: PointerEvent) {
        const dx = ev.clientX - startX;
        if (side === "explorer") {
          setExplorerWidth(
            clamp(startW + dx, EXPLORER_WIDTH.min, EXPLORER_WIDTH.max),
          );
        } else {
          setCoachWidth(clamp(startW - dx, COACH_WIDTH.min, COACH_WIDTH.max));
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

  return (
    <div className="ide">
      <div className="ide-main">
        <aside
          className={`pane explorer${explorerOpen ? "" : " hidden"}`}
          style={{ width: explorerWidth }}
        >
          <header className="pane-head">
            <Link href="/" className="wordmark">
              chiron
            </Link>
            <button
              className="pane-x"
              onClick={() => setExplorerOpen(false)}
              title="Close panel (⌘B)"
            >
              ×
            </button>
          </header>
          <Explorer data={data} ref={explorerRef} />
        </aside>
        {explorerOpen && (
          <div
            className={`pane-handle${dragging === "explorer" ? " dragging" : ""}`}
            onPointerDown={startDrag("explorer")}
            onDoubleClick={() => setExplorerWidth(EXPLORER_WIDTH.def)}
          />
        )}

        <section className="editor">
          <div className="tabstrip" role="tablist">
            {tabs.map((t) => (
              <span
                key={t.href}
                className={`tab${t.href === pathname ? " on" : ""}`}
              >
                <Link className="tab-link" href={t.href} title={t.href}>
                  {t.label}
                </Link>
                <button
                  className="tab-x"
                  onClick={() => closeTab(t.href)}
                  aria-label={`Close ${t.label}`}
                >
                  ×
                </button>
              </span>
            ))}
          </div>
          <div className="crumbbar">
            {crumbs.map((c, i) => (
              <span key={i} className="crumb">
                {i > 0 && (
                  <span className="crumb-sep" aria-hidden>
                    ›
                  </span>
                )}
                {c.href && c.href !== pathname ? (
                  <Link href={c.href}>{c.label}</Link>
                ) : (
                  <span className="crumb-cur">{c.label}</span>
                )}
              </span>
            ))}
          </div>
          <div className="editor-scroll" ref={editorRef}>
            <div className="editor-content">{children}</div>
          </div>
        </section>

        {coachOpen && (
          <div
            className={`pane-handle${dragging === "coach" ? " dragging" : ""}`}
            onPointerDown={startDrag("coach")}
            onDoubleClick={() => setCoachWidth(COACH_WIDTH.def)}
          />
        )}
        <aside
          className={`pane coach-pane${coachOpen ? "" : " hidden"}`}
          style={{ width: coachWidth }}
        >
          <CoachPane
            reg={reg}
            onClose={() => setCoachOpen(false)}
            ref={coachRef}
          />
        </aside>
      </div>

      <StatusBar
        data={data}
        explorerOpen={explorerOpen}
        coachOpen={coachOpen}
        onToggleExplorer={() => setExplorerOpen((o) => !o)}
        onToggleCoach={() => (coachOpen ? setCoachOpen(false) : openCoach())}
        onPalette={() => setPaletteOpen(true)}
        onHelp={() => setHelpOpen(true)}
      />

      {paletteOpen && (
        <CommandPalette data={data} onClose={() => setPaletteOpen(false)} />
      )}
      {helpOpen && <HelpOverlay onClose={() => setHelpOpen(false)} />}
    </div>
  );
}
