import type { NextConfig } from "next";

const internalApiUrl = (
  process.env.INTERNAL_API_URL || "http://localhost:8111"
).replace(/\/$/, "");

const nextConfig: NextConfig = {
  devIndicators: false,
  output: "standalone",
  experimental: {
    // Keep enough multipart overhead above the backend's 100 MB file limit.
    proxyClientMaxBodySize: "101mb",
  },
  async rewrites() {
    return [
      {
        source: "/backend-api/:path*",
        destination: `${internalApiUrl}/api/:path*`,
      },
    ];
  },
};
export default nextConfig;
