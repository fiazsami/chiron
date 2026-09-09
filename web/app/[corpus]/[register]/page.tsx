import { notFound, redirect } from "next/navigation";
import { getSubstrate } from "@/lib/substrate";

export const dynamic = "force-dynamic";

// Chapters is the primary view: entering a register (from the scope page or
// a rail register row) lands on the chapter index. Dimensions are reached
// by keys 1-3, ⌘K, and cross-references.
export default async function RegisterPage({
  params,
}: {
  params: Promise<{ corpus: string; register: string }>;
}) {
  const { corpus, register } = await params;
  const substrate = await getSubstrate(corpus, register);
  if (!substrate) notFound();
  redirect(`/${corpus}/${register}/chapters`);
}
