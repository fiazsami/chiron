import type { NextConfig } from "next";

// Dev-only viewer over ../corpora — no static export; pages read the
// filesystem per request so regenerated pages show up on refresh.
const nextConfig: NextConfig = {
  // The Agent SDK spawns a bundled CLI executable; keep it out of the
  // server bundle so native require() resolves its files on disk.
  serverExternalPackages: ["@anthropic-ai/claude-agent-sdk"],
};

export default nextConfig;
