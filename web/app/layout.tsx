import type { Metadata } from "next";
import Workspace from "@/components/ide/Workspace";
import { getWorkspace } from "@/lib/workspace";
import { EMPTY_WORKSPACE } from "@/lib/workspace-types";
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
  // The shell (explorer tree, palette, status bar) is workspace-wide, so it
  // mounts here; pages render into its editor pane.
  const data = await getWorkspace().catch(() => EMPTY_WORKSPACE);
  return (
    <html lang="en">
      <body>
        <Workspace data={data}>{children}</Workspace>
      </body>
    </html>
  );
}
