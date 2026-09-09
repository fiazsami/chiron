// The whole viewer keymap (design/ui-map-1.json keymap section), one table:
// the Shell dispatches from KEY_LOOKUP and the Help overlay renders KEYMAP,
// so the two can never drift. Multi-key (gg), shifted-modifier combos
// (shift+backspace) and ⌘K are dispatched specially by the Shell and appear
// here only for display (keys: []).

export type ShellAction =
  | "pane-prev"
  | "pane-next"
  | "cursor-down"
  | "cursor-up"
  | "cursor-top"
  | "cursor-bottom"
  | "activate"
  | "view-1"
  | "view-2"
  | "view-3"
  | "view-4"
  | "scope"
  | "hints"
  | "peek"
  | "ref-next"
  | "ref-prev"
  | "anchor-next"
  | "entry-next"
  | "entry-prev"
  | "open-source"
  | "copy"
  | "trail-back"
  | "trail-forward"
  | "trail-clear"
  | "filter"
  | "jump"
  | "drill"
  | "theme"
  | "help"
  | "sort"
  | "escape";

export type KeymapSection =
  | "Panes"
  | "Within a pane"
  | "Dimensions"
  | "Entry"
  | "Trail"
  | "Search"
  | "Modes";

export interface KeyBinding {
  keys: string[]; // KeyboardEvent.key values; [] = dispatched specially
  display: string; // help-overlay keycap text
  section: KeymapSection;
  description: string;
  action: ShellAction;
}

export const KEYMAP: KeyBinding[] = [
  { keys: ["h", "ArrowLeft"], display: "h / ←", section: "Panes", description: "focus previous pane", action: "pane-prev" },
  { keys: ["l", "ArrowRight"], display: "l / →", section: "Panes", description: "focus next pane", action: "pane-next" },

  { keys: ["j", "ArrowDown"], display: "j / ↓", section: "Within a pane", description: "next row or reference", action: "cursor-down" },
  { keys: ["k", "ArrowUp"], display: "k / ↑", section: "Within a pane", description: "previous", action: "cursor-up" },
  { keys: [], display: "g g", section: "Within a pane", description: "top", action: "cursor-top" },
  { keys: ["G"], display: "G", section: "Within a pane", description: "bottom", action: "cursor-bottom" },
  { keys: ["Enter"], display: "↵", section: "Within a pane", description: "open (index) / follow (reference)", action: "activate" },

  { keys: ["1"], display: "1", section: "Dimensions", description: "first dimension", action: "view-1" },
  { keys: ["2"], display: "2", section: "Dimensions", description: "second dimension", action: "view-2" },
  { keys: ["3"], display: "3", section: "Dimensions", description: "third dimension", action: "view-3" },
  { keys: ["4"], display: "4", section: "Dimensions", description: "chapters", action: "view-4" },
  { keys: ["0"], display: "0", section: "Dimensions", description: "scope (corpus / register)", action: "scope" },

  { keys: ["f"], display: "f", section: "Entry", description: "hint mode: type the letters to follow", action: "hints" },
  { keys: [" "], display: "space", section: "Entry", description: "peek the cursor reference", action: "peek" },
  { keys: ["n"], display: "n", section: "Entry", description: "next cross-reference", action: "ref-next" },
  { keys: ["p"], display: "p", section: "Entry", description: "previous cross-reference", action: "ref-prev" },
  { keys: ["e"], display: "e", section: "Entry", description: "next anchor (evidence)", action: "anchor-next" },
  { keys: ["]"], display: "]", section: "Entry", description: "next entry in the index", action: "entry-next" },
  { keys: ["["], display: "[", section: "Entry", description: "previous entry in the index", action: "entry-prev" },
  { keys: ["o"], display: "o", section: "Entry", description: "open the chapter source", action: "open-source" },
  { keys: ["y"], display: "y", section: "Entry", description: "copy template / term", action: "copy" },

  { keys: ["Backspace", "u"], display: "⌫ / u", section: "Trail", description: "back", action: "trail-back" },
  { keys: ["U"], display: "shift+u", section: "Trail", description: "forward", action: "trail-forward" },
  { keys: [], display: "shift+⌫", section: "Trail", description: "clear trail to the current entry", action: "trail-clear" },

  { keys: ["/"], display: "/", section: "Search", description: "filter the index", action: "filter" },
  { keys: [], display: "⌘K", section: "Search", description: "jump anywhere", action: "jump" },
  { keys: ["Escape"], display: "esc", section: "Search", description: "clear filter / close overlay", action: "escape" },

  { keys: ["s"], display: "s", section: "Modes", description: "cycle index sort / grouping", action: "sort" },
  { keys: ["d"], display: "d", section: "Modes", description: "drill the current index scope", action: "drill" },
  { keys: ["t"], display: "t", section: "Modes", description: "toggle theme", action: "theme" },
  { keys: ["?"], display: "?", section: "Modes", description: "this help", action: "help" },
];

export const KEY_LOOKUP: ReadonlyMap<string, ShellAction> = new Map(
  KEYMAP.flatMap((b) => b.keys.map((k) => [k, b.action] as const)),
);

export const KEYMAP_SECTIONS: KeymapSection[] = [
  "Panes",
  "Within a pane",
  "Dimensions",
  "Entry",
  "Trail",
  "Search",
  "Modes",
];
