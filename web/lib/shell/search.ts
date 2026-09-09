import type { SearchDoc } from "../substrate-types";

// Jump-overlay matching. Tiers keep ranking legible: a headword prefix
// always beats a substring, which beats an alias hit (shown as the match
// reason), which beats a bare slug hit. Aliases as search keys close the
// alias gap called out by design/ui-map-1.json.

export const JUMP_MAX = 40;

export interface JumpMatch {
  doc: SearchDoc;
  alias?: string; // set when the match reason was an alias
}

export function matchJump(docs: SearchDoc[], query: string): JumpMatch[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return docs.slice(0, JUMP_MAX).map((doc) => ({ doc }));

  const scored: { m: JumpMatch; tier: number }[] = [];
  for (const doc of docs) {
    const headword = doc.headword.toLowerCase();
    if (headword.startsWith(needle)) {
      scored.push({ m: { doc }, tier: 0 });
      continue;
    }
    if (headword.includes(needle)) {
      scored.push({ m: { doc }, tier: 1 });
      continue;
    }
    const alias = doc.aliases.find((a) => a.toLowerCase().includes(needle));
    if (alias) {
      scored.push({ m: { doc, alias }, tier: 2 });
      continue;
    }
    if (doc.key.toLowerCase().includes(needle)) {
      scored.push({ m: { doc }, tier: 3 });
    }
  }
  scored.sort(
    (a, b) =>
      a.tier - b.tier || a.m.doc.headword.localeCompare(b.m.doc.headword),
  );
  return scored.slice(0, JUMP_MAX).map((s) => s.m);
}
