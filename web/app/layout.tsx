import type { Metadata } from "next";
import ReaderShell from "@/components/reader/ReaderShell";
import { getWorkspace } from "@/lib/workspace";
import { EMPTY_WORKSPACE } from "@/lib/workspace-types";
// github-markdown-css first so globals.css wins equal-specificity ties.
import "github-markdown-css/github-markdown.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "chiron",
  description:
    "The lexicon, phrasebook, and concept relations of each mounted corpus.",
};

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // The reader shell (sidebar, article list) is workspace-wide, so it
  // mounts here; pages render into its article pane.
  const data = await getWorkspace().catch(() => EMPTY_WORKSPACE);
  return (
    <html lang="en">
      <body>
        <ReaderShell data={data}>{children}</ReaderShell>
      </body>
    </html>
  );
}
