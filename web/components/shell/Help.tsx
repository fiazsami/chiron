"use client";

import { KEYMAP, KEYMAP_SECTIONS } from "@/lib/shell/keymap";

// The keymap as a two-column table, rendered from the same table the Shell
// dispatches from — the help can never drift from the behavior.

export default function Help({ onClose }: { onClose: () => void }) {
  return (
    <div className="overlay-backdrop" onMouseDown={onClose}>
      <div
        className="overlay-box help"
        role="dialog"
        aria-modal="true"
        aria-label="Keyboard help"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="help-columns">
          {KEYMAP_SECTIONS.map((section) => (
            <div key={section}>
              <h3>{section}</h3>
              {KEYMAP.filter((b) => b.section === section).map((b) => (
                <div key={b.display} className="help-row">
                  <span className="keys">
                    <span className="keycap">{b.display}</span>
                  </span>
                  <span>{b.description}</span>
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
