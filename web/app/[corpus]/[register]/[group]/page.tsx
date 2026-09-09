import { notFound } from "next/navigation";
import {
  DIMENSIONS,
  DIMENSION_LABELS,
  accentClass,
  findCorpus,
  getManifest,
  type DimensionState,
} from "@/lib/content";

export const dynamic = "force-dynamic";

interface Params {
  params: Promise<{ corpus: string; register: string; group: string }>;
}

export async function generateMetadata({ params }: Params) {
  const { corpus, register, group } = await params;
  const entry = findCorpus(await getManifest(), corpus, register);
  const label = entry?.groups.find((g) => g.id === group)?.label;
  return { title: label ? `${label} · ${entry!.title} · chiron` : "chiron" };
}

// Group landing: the URL a sidebar folder click scopes the list to. The
// middle pane is the real navigation surface; this page just summarizes the
// folder.
export default async function GroupPage({ params }: Params) {
  const { corpus: name, register, group } = await params;
  const manifest = await getManifest();
  const corpus = findCorpus(manifest, name, register);
  const entry = corpus?.groups.find((g) => g.id === group);
  if (!corpus || !entry) notFound();

  const chapters = manifest.chapters.filter(
    (c) => c.corpus === name && c.register === register && c.group === group,
  );
  const tracked = DIMENSIONS.filter((d) => d in corpus.data);
  const states: DimensionState[] = ["ok", "stale", "none"];

  return (
    <header className={`index-header ${accentClass(manifest, name, register, group)}`}>
      <h1>{entry.label}</h1>
      <p className="description muted">
        {chapters.length} chapter{chapters.length === 1 ? "" : "s"} ·{" "}
        {corpus.title} · {register}
      </p>
      {tracked.map((d) => {
        const counts = states
          .map((s) => ({
            state: s,
            n: chapters.filter((c) => c.states[d] === s).length,
          }))
          .filter(({ n }) => n > 0);
        return (
          <p key={d} className="group-state-line">
            <span className="muted">{DIMENSION_LABELS[d]}:</span>{" "}
            {counts.map(({ state, n }) => (
              <span key={state} className="group-state">
                <span className={`status-dot ${state}`} /> {n} {state}
              </span>
            ))}
          </p>
        );
      })}
    </header>
  );
}
