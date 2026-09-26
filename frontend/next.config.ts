import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Force-visible for local demo when DB/Docker is unavailable.
  // Prefer frontend/.env.local in normal workflows; this guarantees mock fixtures load.
  env: {
    NEXT_PUBLIC_USE_MOCK_API: process.env.NEXT_PUBLIC_USE_MOCK_API ?? "true",
  },
};

export default nextConfig;
