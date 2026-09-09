"use client";

import { createContext, useContext } from "react";
import type { RefKind, RegisterSubstrate } from "@/lib/substrate-types";

// The one integration point between the Shell and everything rendered
// inside it: entries and their references read the substrate, the ref
// cursor, and hint state from here, and hand navigation back to the Shell
// so the trail stays coherent.

export interface RefTarget {
  id: string;
  el: HTMLElement;
  href: string;
  headword: string;
  kind: RefKind;
  isAnchor: boolean; // evidence blocks; `e` walks these, n/p skip them
}

// Registered by Reference/Evidence on mount; ordered on demand by document
// position, never by registration order (re-renders would scramble it).
export class RefRegistry {
  private map = new Map<string, RefTarget>();

  register(target: RefTarget) {
    this.map.set(target.id, target);
  }

  unregister(id: string) {
    this.map.delete(id);
  }

  get(id: string): RefTarget | undefined {
    return this.map.get(id);
  }

  ordered(): RefTarget[] {
    return [...this.map.values()].sort((a, b) =>
      a.el.compareDocumentPosition(b.el) & Node.DOCUMENT_POSITION_FOLLOWING
        ? -1
        : 1,
    );
  }
}

export interface HintState {
  labels: Map<string, string>; // target id → label
  buffer: string;
}

export interface ShellApi {
  substrate: RegisterSubstrate;
  registry: RefRegistry;
  refCursor: string | null;
  hint: HintState | null;
  copied: boolean; // y-copy flash
  follow: (href: string) => void; // push onto the trail
}

export const ShellContext = createContext<ShellApi | null>(null);

export function useShell(): ShellApi {
  const api = useContext(ShellContext);
  if (!api) throw new Error("useShell outside <Shell>");
  return api;
}
