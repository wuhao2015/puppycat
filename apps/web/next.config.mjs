/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  experimental: {
    useTypeScriptCli: false,
  },
  async rewrites() {
    const apiBaseUrl =
      process.env.API_INTERNAL_BASE_URL ?? "http://localhost:8001";

    return [
      {
        source: "/api/:path*",
        destination: `${apiBaseUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
