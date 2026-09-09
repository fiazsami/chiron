"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  DIMENSION_COUNT_KEYS,
  DIMENSION_SEGMENTS,
  type DimensionState,
} from "@/lib/dimensions";
import type { WorkspaceData, WorkspaceRegister } from "@/lib/workspace-types";

// Imperative surface for the shell's global keybindings (j/k/h/l/o).
export interface ExplorerHandle {
  move(delta: number): void;
  open(): void;
  left(): void;
  right(): void;
}

interface FolderNode {
  kind: "folder";
  id: string;
  label: string;
  depth: number;
  meta?: string;
}

interface LeafNode {
  kind: "leaf";
  id: string; // === href, unique per page
  href: string;
  label: string;
  depth: number;
  meta?: string;
  num?: string;
  dots?: DimensionState[];
}

type TreeNode = FolderNode | LeafNode;

interface TreeSpec {
  node: TreeNode;
  children?: TreeSpec[];
}

function buildTree(data: WorkspaceData): TreeSpec[] {
  const byCorpus = new Map<string, WorkspaceRegister[]>();
  for (const r of data.registers) {
    byCorpus.set(r.corpus, [...(byCorpus.get(r.corpus) ?? []), r]);
  }
  return [...byCorpus.entries()].map(([corpus, regs]) => ({
    node: {
      kind: "folder" as const,
      id: `corpus:${corpus}`,
      label: regs[0].title,
      depth: 0,
    },
    children: regs.map((r) => ({
      node: {
        kind: "folder" as const,
        id: `reg:${r.key}`,
        label: r.register,
        meta: r.label ?? undefined,
        depth: 1,
      },
      children: [
        {
          node: {
            kind: "leaf" as const,
            id: `/${r.key}`,
            href: `/${r.key}`,
            label: "overview",
            depth: 2,
          },
        },
        ...r.modes.map((d) => {
          const href = `/${r.key}/${DIMENSION_SEGMENTS[d]}`;
          return {
            node: {
              kind: "leaf" as const,
              id: href,
              href,
              label: DIMENSION_SEGMENTS[d],
              depth: 2,
              meta: String(r.totals[DIMENSION_COUNT_KEYS[d]] ?? 0),
              dots: [r.states[d] ?? "none"],
            },
          };
        }),
        ...r.groups
          .map((g) => ({
            node: {
              kind: "folder" as const,
              id: `grp:${r.key}/${g.id}`,
              label: g.label,
              depth: 2,
            },
            children: data.chapters
              .filter((c) => c.key === r.key && c.group === g.id)
              .map((c) => ({
                node: {
                  kind: "leaf" as const,
                  id: c.href,
                  href: c.href,
                  label: c.title,
                  num: c.number,
                  depth: 3,
                  dots: r.modes.map((d) => c.states[d] ?? "none"),
                },
              })),
          }))
          .filter((spec) => spec.children.length > 0),
      ],
    })),
  }));
}

// Folder-id chain from the roots down to the leaf with this href.
function findPath(specs: TreeSpec[], href: string): string[] | null {
  for (const s of specs) {
    if (s.node.kind === "leaf" && s.node.href === href) return [];
    if (s.children) {
      const sub = findPath(s.children, href);
      if (sub) return [s.node.id, ...sub];
    }
  }
  return null;
}

function defaultExpanded(roots: TreeSpec[]): Set<string> {
  // Corpora and registers start open; chapter groups start closed (the
  // reveal effect opens the active route's group).
  const ids = new Set<string>();
  for (const c of roots) {
    ids.add(c.node.id);
    for (const r of c.children ?? []) ids.add(r.node.id);
  }
  return ids;
}

export default function Explorer({
  data,
  ref,
}: {
  data: WorkspaceData;
  ref?: React.Ref<ExplorerHandle>;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const roots = useMemo(() => buildTree(data), [data]);
  const [expanded, setExpanded] = useState<Set<string>>(() =>
    defaultExpanded(roots),
  );
  const [selId, setSelId] = useState<string | null>(null);
  const rowRefs = useRef(new Map<string, HTMLElement>());

  const visible = useMemo(() => {
    const out: TreeNode[] = [];
    const parents = new Map<string, string | null>();
    const walk = (specs: TreeSpec[], parent: string | null) => {
      for (const s of specs) {
        parents.set(s.node.id, parent);
        out.push(s.node);
        if (s.children && expanded.has(s.node.id)) walk(s.children, s.node.id);
      }
    };
    walk(roots, null);
    return { nodes: out, parents };
  }, [roots, expanded]);

  const selIdx = visible.nodes.findIndex((n) => n.id === selId);

  // Reveal + select the tree row for the current route.
  useEffect(() => {
    const decoded = pathname
      .split("/")
      .map((s) => decodeURIComponent(s))
      .join("/");
    const path = findPath(roots, decoded);
    if (!path) return;
    setExpanded((prev) => {
      if (path.every((id) => prev.has(id))) return prev;
      const next = new Set(prev);
      for (const id of path) next.add(id);
      return next;
    });
    setSelId(decoded);
  }, [pathname, roots]);

  useEffect(() => {
    if (selId) rowRefs.current.get(selId)?.scrollIntoView({ block: "nearest" });
  }, [selId]);

  function toggle(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  useImperativeHandle(ref, () => ({
    move(delta: number) {
      const { nodes } = visible;
      if (nodes.length === 0) return;
      const from = selIdx < 0 ? (delta > 0 ? -1 : nodes.length) : selIdx;
      const i = Math.max(0, Math.min(nodes.length - 1, from + delta));
      setSelId(nodes[i].id);
    },
    open() {
      const n = visible.nodes[selIdx];
      if (!n) return;
      if (n.kind === "folder") toggle(n.id);
      else router.push(n.href);
    },
    left() {
      const n = visible.nodes[selIdx];
      if (!n) return;
      if (n.kind === "folder" && expanded.has(n.id)) toggle(n.id);
      else {
        const parent = visible.parents.get(n.id);
        if (parent) setSelId(parent);
      }
    },
    right() {
      const n = visible.nodes[selIdx];
      if (!n || n.kind !== "folder") return;
      if (!expanded.has(n.id)) toggle(n.id);
      else {
        const next = visible.nodes[selIdx + 1];
        if (next && visible.parents.get(next.id) === n.id) setSelId(next.id);
      }
    },
  }));

  if (data.registers.length === 0) {
    return (
      <div className="tree-empty">
        No corpora mounted. In Claude Code, run <code>/mount &lt;repo&gt;</code>,
        then build with <code>uv run python -m tools.lingua</code>.
      </div>
    );
  }

  const rowRef = (id: string) => (el: HTMLElement | null) => {
    if (el) rowRefs.current.set(id, el);
    else rowRefs.current.delete(id);
  };

  return (
    <nav className="tree" role="tree" aria-label="Corpora">
      {visible.nodes.map((n) => {
        const sel = n.id === selId;
        const depthStyle = { "--depth": n.depth } as React.CSSProperties;
        if (n.kind === "folder") {
          const isOpen = expanded.has(n.id);
          return (
            <button
              key={n.id}
              ref={rowRef(n.id)}
              role="treeitem"
              aria-expanded={isOpen}
              className={`tree-row folder${sel ? " sel" : ""}`}
              style={depthStyle}
              tabIndex={sel ? 0 : -1}
              onClick={() => {
                setSelId(n.id);
                toggle(n.id);
              }}
            >
              <span className={`caret${isOpen ? " open" : ""}`} aria-hidden>
                ▸
              </span>
              <span className="tree-label">{n.label}</span>
              {n.meta && <span className="tree-meta">{n.meta}</span>}
            </button>
          );
        }
        const active = n.href === pathname;
        return (
          <Link
            key={n.id}
            ref={rowRef(n.id)}
            role="treeitem"
            aria-current={active ? "page" : undefined}
            className={`tree-row leaf${sel ? " sel" : ""}${active ? " on" : ""}`}
            style={depthStyle}
            tabIndex={sel ? 0 : -1}
            href={n.href}
            onClick={() => setSelId(n.id)}
          >
            {n.dots && (
              <span className="tree-dots" aria-hidden>
                {n.dots.map((s, j) => (
                  <span key={j} className={`status-dot ${s}`} />
                ))}
              </span>
            )}
            {n.num && <span className="tree-num">{n.num}</span>}
            <span className="tree-label">{n.label}</span>
            {n.meta && <span className="tree-meta">{n.meta}</span>}
          </Link>
        );
      })}
    </nav>
  );
}
