import ScopeScreen from "@/components/shell/ScopeScreen";
import { getScopeData } from "@/lib/substrate";

export const dynamic = "force-dynamic";

// The scope surface: corpus/register identity, totals, provenance, and
// worst-of drift state. Key 0 returns here from anywhere in the shell.
export default async function ScopePage() {
  return <ScopeScreen data={await getScopeData()} />;
}
