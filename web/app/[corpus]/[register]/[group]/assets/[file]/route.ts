import fs from "node:fs/promises";
import path from "node:path";
import { NextResponse } from "next/server";
import { CORPORA_DIR, getManifest } from "@/lib/content";

// Serves corpora/<corpus>/<vN>/notes/<group>/assets/<file> so the Markdown's
// relative image links (assets/<slug>-flow-<n>.svg) resolve from chapter
// pages. Only files listed in the manifest's svgs are servable — the manifest
// is the authority on what the build produced, so no path is reconstructed by
// hand.
export async function GET(
  _req: Request,
  {
    params,
  }: {
    params: Promise<{
      corpus: string;
      register: string;
      group: string;
      file: string;
    }>;
  },
) {
  const { corpus, register, group, file } = await params;
  const rel = `${corpus}/${register}/notes/${group}/assets/${file}`;
  const manifest = await getManifest().catch(() => null);
  const known = manifest?.chapters.some((c) => c.svgs.includes(rel)) ?? false;
  if (!known) {
    return new NextResponse("Not found", { status: 404 });
  }
  try {
    const svg = await fs.readFile(path.join(CORPORA_DIR, rel));
    return new NextResponse(svg, {
      headers: { "Content-Type": "image/svg+xml" },
    });
  } catch {
    return new NextResponse("Not found", { status: 404 });
  }
}
