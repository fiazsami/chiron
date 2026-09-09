import { notFound, redirect } from "next/navigation";
import { DIMENSION_SEGMENTS } from "@/lib/dimensions";
import { getSubstrate } from "@/lib/substrate";

export const dynamic = "force-dynamic";

// One canonical URL per view: the register root immediately enters the
// first tracked dimension (registry order), or chapters when none are.
export default async function RegisterPage({
  params,
}: {
  params: Promise<{ corpus: string; register: string }>;
}) {
  const { corpus, register } = await params;
  const substrate = await getSubstrate(corpus, register);
  if (!substrate) notFound();
  const first = substrate.register.modes[0];
  redirect(
    `/${corpus}/${register}/${first ? DIMENSION_SEGMENTS[first] : "chapters"}`,
  );
}
