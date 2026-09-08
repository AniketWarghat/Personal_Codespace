import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // IMPORTANT: cpus:1 prevents multiple parallel worker threads from writing
  // to .next/ simultaneously. On OneDrive-synced paths (like this project),
  // parallel workers cause Windows file-lock deadlocks and the build hangs forever.
  // This is the ROOT CAUSE fix for "npm run build stuck" on this machine.
  experimental: {
    workerThreads: false,
    cpus: 1,
  },
};

export default nextConfig;
