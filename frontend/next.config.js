/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  // API calls go through nginx → /api/* → FastAPI on :8000
  // In dev (next dev), rewrite to localhost:8000 directly.
  async rewrites() {
    if (process.env.NODE_ENV === 'development') {
      return [
        {
          source: '/api/:path*',
          destination: 'http://localhost:8000/api/:path*',
        },
        {
          source: '/auth/:path*',
          destination: 'http://localhost:9999/:path*',
        },
      ];
    }
    return [];
  },
};

module.exports = nextConfig;
