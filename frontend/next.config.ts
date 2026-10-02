import type { NextConfig } from "next";
const nextConfig: NextConfig = {
  poweredByHeader: false,
  trailingSlash: true,
  outputFileTracingRoot: process.cwd(),
  webpack(config) {
    config.resolve.symlinks = false;
    return config;
  },
  async rewrites() {
    return [{source: "/api/:path*/", destination: (process.env.BACKEND_URL || "http://127.0.0.1:8000") + "/api/:path*/"}];
  },
  async headers() {
    return [{source: "/:path*", headers: [
      {key: "X-Content-Type-Options", value: "nosniff"},
      {key: "Referrer-Policy", value: "no-referrer"},
      {key: "X-Frame-Options", value: "DENY"},
    ]}];
  },
};
export default nextConfig;
