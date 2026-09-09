"use client";

// Lets client islands anywhere in the page tree (e.g. the chapter aside's
// term chips) open the bit modal without prop-drilling through server
// components. Provided by ReaderShell.

import { createContext, useContext } from "react";
import type { BitKind } from "@/lib/navigator-types";

export interface OpenBitRef {
  corpus: string;
  register: string;
  kind: BitKind;
  id: string;
}

export interface LookupApi {
  openBit: (ref: OpenBitRef) => void;
}

export const LookupContext = createContext<LookupApi | null>(null);

export function useLookup(): LookupApi | null {
  return useContext(LookupContext);
}
