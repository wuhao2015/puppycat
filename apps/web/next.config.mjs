/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  experimental: {
    // Itinerary generation performs several external calls and regularly exceeds
    // Next's 30-second default for proxied rewrites.
    proxyTimeout: 300_000,
  },
  async rewrites() {
    const apiBaseUrl = process.env.API_INTERNAL_BASE_URL ?? "http://localhost:8001";
    return [
      {
        source: "/api/:path*",
        destination: `${apiBaseUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
