"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { useAuth } from "@/lib/auth";
import { TripsProvider } from "@/lib/trips";
import Sidebar from "./Sidebar";

const PUBLIC_ROUTES = new Set(["/login", "/register"]);

export default function AppShell({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const pathname = usePathname();
  const router = useRouter();

  const isPublic = PUBLIC_ROUTES.has(pathname);

  useEffect(() => {
    if (!loading && !user && !isPublic) {
      router.replace("/login");
    }
  }, [loading, user, isPublic, router]);

  // Auth pages render bare, without the sidebar workspace.
  if (isPublic) {
    return <div className="min-h-screen bg-gray-50">{children}</div>;
  }

  if (loading || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50 text-sm text-gray-500">
        {loading ? "Loading…" : "Redirecting to sign in…"}
      </div>
    );
  }

  return (
    <TripsProvider>
      <div className="flex h-screen overflow-hidden bg-gray-50">
        <Sidebar />
        <main className="flex-1 overflow-hidden">{children}</main>
      </div>
    </TripsProvider>
  );
}
