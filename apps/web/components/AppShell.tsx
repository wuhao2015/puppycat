"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import type { ReactNode } from "react";

import { useAuth } from "../lib/auth";
import Sidebar from "./Sidebar";

type AppShellProps = {
  activePage: "workspace" | "settings";
  children: ReactNode;
};

export default function AppShell({ activePage, children }: AppShellProps) {
  const router = useRouter();
  const { user, loading } = useAuth();

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/login");
    }
  }, [loading, router, user]);

  if (loading || !user) {
    return (
      <div className="grid h-screen place-items-center bg-page">
        <div className="loading-dots" aria-label="Loading account">
          <span>●</span>
          <span>●</span>
          <span>●</span>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen overflow-hidden bg-page">
      <Sidebar activePage={activePage} />
      <main className="min-h-0 min-w-0 flex-1 overflow-hidden">{children}</main>
    </div>
  );
}
