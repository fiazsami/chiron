import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";

// Source Serif 4 variable (opsz 8–60, wght 200–900), committed under
// web/fonts/ so builds never touch the network; globals.css falls back to
// Iowan Old Style / Georgia when --font-serif is absent.
const serif = localFont({
  src: [
    { path: "../fonts/SourceSerif4Variable-Roman.woff2", style: "normal" },
    { path: "../fonts/SourceSerif4Variable-Italic.woff2", style: "italic" },
  ],
  weight: "200 900",
  display: "swap",
  variable: "--font-serif",
});

export const metadata: Metadata = {
  title: "chiron",
  description:
    "The lexicon, phrasebook, and concept relations of each mounted corpus.",
};

// Apply the persisted theme before first paint; without an explicit choice
// the stylesheet follows prefers-color-scheme on its own.
const THEME_BOOTSTRAP = `(function () {
  try {
    var t = localStorage.getItem("chiron.theme");
    if (t === "light" || t === "dark")
      document.documentElement.setAttribute("data-theme", t);
  } catch (e) {}
})();`;

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={serif.variable} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOTSTRAP }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
