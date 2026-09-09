import type { NextConfig } from "next";

// Dev-only viewer over ../corpora — no static export; pages read the
// filesystem per request so regenerated notes show up on refresh.
const nextConfig: NextConfig = {};

export default nextConfig;
