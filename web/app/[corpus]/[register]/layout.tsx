import { notFound } from "next/navigation";
import Shell from "@/components/shell/Shell";
import { getSubstrate } from "@/lib/substrate";

// The register shell: loads the full substrate once per request and hands
// it to the client Shell. Route pages below validate their key, set
// metadata, and render null — the Shell derives the open entry from the URL.

export default async function RegisterLayout({
  params,
  children,
}: {
  params: Promise<{ corpus: string; register: string }>;
  children: React.ReactNode;
}) {
  const { corpus, register } = await params;
  const substrate = await getSubstrate(corpus, register);
  if (!substrate) notFound();
  return <Shell substrate={substrate}>{children}</Shell>;
}
