import type { NextConfig } from "next";
import path from "node:path";

const nextConfig: NextConfig = {
  output: "standalone",
  transpilePackages: ["@mymediavault/core"],
  turbopack: {
    root: path.join(__dirname, "../.."),
  },
};

export default nextConfig;
