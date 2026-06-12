import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";
import "mapbox-gl/dist/mapbox-gl.css";

export const metadata: Metadata = {
  title: "Puppycat Travel",
  description: "Verified AI travel itineraries with real-time freshness checks.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <div className="min-h-screen">
          <header className="border-b border-gray-200 bg-white">
            <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
              <Link href="/" className="flex items-center gap-2 font-semibold text-brand">
                <span className="text-xl">🐾</span> Puppycat Travel
              </Link>
              <nav className="flex gap-4 text-sm text-gray-600">
                <Link href="/" className="hover:text-brand">
                  Planner
                </Link>
                <Link href="/chat" className="hover:text-brand">
                  Chat
                </Link>
                <Link href="/visa" className="hover:text-brand">
                  Visa
                </Link>
              </nav>
            </div>
          </header>
          <main className="mx-auto max-w-5xl px-4 py-6">{children}</main>
        </div>
      </body>
    </html>
  );
}
