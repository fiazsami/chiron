import AgentPanel from "@/components/agent/AgentPanel";
import { findCorpus, getManifest } from "@/lib/content";

export const dynamic = "force-dynamic";

// Register-scoped layout: the coach panel lives here (not in pages) so its
// chat state survives navigation between the hub, dimension surfaces, and
// chapter pages of one register.
export default async function RegisterLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ corpus: string; register: string }>;
}) {
  const { corpus: name, register } = await params;
  const entry = findCorpus(await getManifest(), name, register);
  return (
    <>
      {children}
      {entry && (
        <AgentPanel corpus={name} register={register} title={entry.title} />
      )}
    </>
  );
}
