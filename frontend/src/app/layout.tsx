import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Analytics Platform',
  description: 'Unified product analytics — Segment A events & Segment B orders',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
