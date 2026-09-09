import type { NextConfig } from "next";

// Dev-only viewer over ../corpora — no static export; pages read the
// filesystem per request so regenerated pages show up on refresh.
const nextConfig: NextConfig = {
  // Next blocks dev assets + the HMR websocket for origins other than the
  // one the server started on. Browsing via a LAN address needs that origin
  // allowed; it is machine-specific, so it lives in web/.env.local:
  //   CHIRON_DEV_ORIGINS=192.168.86.111
  ...(process.env.CHIRON_DEV_ORIGINS
    ? { allowedDevOrigins: process.env.CHIRON_DEV_ORIGINS.split(",") }
    : {}),
};

export default nextConfig;
