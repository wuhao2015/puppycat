"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { useAuth } from "@/lib/auth";

const PUBLIC_ROUTES = new Set(["/login", "/register"]);

export default function AppShell({ children }: { children: React.ReactNode }) {
  const { user, loading, logout } = useAuth();
  const pathname = usePathname();
  const router = useRouter();

  const isPublic = PUBLIC_ROUTES.has(pathname);

  useEffect(() => {
    if (!loading && !user && !isPublic) {
      router.replace("/login");
    }
  }, [loading, user, isPublic, router]);

  return (
    <div className="min-h-screen">
      <header className="border-b border-gray-200 bg-white">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
          <Link href="/" className="flex items-center gap-2 font-semibold text-brand">
            <span className="text-xl">🐾</span> Puppycat Travel
          </Link>
          <nav className="flex items-center gap-4 text-sm text-gray-600">
            {user && (
              <>
                <Link href="/" className="hover:text-brand">
                  Planner
                </Link>
                <Link href="/trips" className="hover:text-brand">
                  My trips
                </Link>
                <Link href="/chat" className="hover:text-brand">
                  Chat
                </Link>
                <Link href="/visa" className="hover:text-brand">
                  Visa
                </Link>
                <span className="hidden text-gray-400 sm:inline">
                  {user.display_name || user.email}
                </span>
                <button
                  type="button"
                  onClick={() => {
                    logout();
                    router.replace("/login");
                  }}
                  className="rounded-md border border-gray-300 px-2 py-1 text-gray-700 hover:bg-gray-50"
                >
                  Sign out
                </button>
              </>
            )}
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-6">
        {loading && !isPublic ? (
          <div className="flex min-h-64 items-center justify-center text-sm text-gray-500">
            Loading…
          </div>
        ) : !user && !isPublic ? (
          <div className="flex min-h-64 items-center justify-center text-sm text-gray-500">
            Redirecting to sign in…
          </div>
        ) : (
          children
        )}
      </main>
    </div>
  );
}
