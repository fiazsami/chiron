"use client";

import { usePathname } from "next/navigation";
import { DIMENSION_COUNT_KEYS, DIMENSION_LABELS } from "@/lib/dimensions";
import { activeRegister, type WorkspaceData } from "@/lib/workspace-types";

// Bottom status bar: active register facts on the left, panel toggles and
// overlay shortcuts on the right.
export default function StatusBar({
  data,
  explorerOpen,
  coachOpen,
  onToggleExplorer,
  onToggleCoach,
  onPalette,
  onHelp,
}: {
  data: WorkspaceData;
  explorerOpen: boolean;
  coachOpen: boolean;
  onToggleExplorer: () => void;
  onToggleCoach: () => void;
  onPalette: () => void;
  onHelp: () => void;
}) {
  const pathname = usePathname();
  const reg = activeRegister(data, pathname);
  const totals = reg
    ? reg.modes
        .map((d) => {
          const key = DIMENSION_COUNT_KEYS[d];
          return `${reg.totals[key] ?? 0} ${key}`;
        })
        .join(" · ")
    : null;

  return (
    <footer className="statusbar">
      <div className="sb-left">
        {reg ? (
          <>
            <span className="sb-item">
              {reg.key} <span className="sb-dim">@{reg.checkout}</span>
            </span>
            <span className="sb-dots" aria-hidden>
              {reg.modes.map((d) => (
                <span
                  key={d}
                  className={`status-dot ${reg.states[d] ?? "none"}`}
                  title={`${DIMENSION_LABELS[d]}: ${reg.states[d] ?? "none"}`}
                />
              ))}
            </span>
            {totals && <span className="sb-item sb-dim">{totals}</span>}
          </>
        ) : (
          <span className="sb-item sb-dim">
            {data.registers.length === 0
              ? "no corpora mounted"
              : `${data.registers.length} register${
                  data.registers.length === 1 ? "" : "s"
                } · ${data.chapters.length} chapters · ${data.terms.length} terms`}
          </span>
        )}
      </div>
      <div className="sb-right">
        <button
          className={`sb-btn${explorerOpen ? " on" : ""}`}
          onClick={onToggleExplorer}
          title="Toggle explorer (⌘B)"
        >
          explorer
        </button>
        <button
          className={`sb-btn${coachOpen ? " on" : ""}`}
          onClick={onToggleCoach}
          title="Toggle coach (⌘J)"
        >
          coach
        </button>
        <button className="sb-btn" onClick={onPalette} title="Go to anything (⌘K)">
          ⌘K
        </button>
        <button className="sb-btn" onClick={onHelp} title="Keyboard help (?)">
          ?
        </button>
      </div>
    </footer>
  );
}
