"use client";

import { LogOut, Plus, Settings, UserRound } from "lucide-react";
import Link from "next/link";

import { useAuth } from "../lib/auth";

type SidebarProps = {
  activePage: "workspace" | "settings";
};

export default function Sidebar({ activePage }: SidebarProps) {
  const { user, signOut } = useAuth();

  return (
    <aside className="hidden h-screen w-72 shrink-0 flex-col border-r border-line bg-white md:flex">
      <div className="px-4 py-4">
        <Link
          href="/"
          className="flex items-center gap-2 font-semibold text-brand"
        >
          <span aria-hidden="true" className="text-xl">
            🐾
          </span>
          Puppycat Travel
        </Link>
      </div>

      <div className="px-3">
        <Link href="/" className="button-primary w-full">
          <Plus aria-hidden="true" size={16} />
          New trip
        </Link>
      </div>

      <nav aria-label="Trips" className="mt-5 flex-1 overflow-y-auto px-3">
        <p className="px-2 text-[11px] font-semibold uppercase tracking-wide text-gray-400">
          Trips
        </p>
        <div
          className={`mt-2 rounded-lg px-3 py-3 text-xs leading-5 ${
            activePage === "workspace"
              ? "bg-brand/10 text-brand"
              : "text-gray-400"
          }`}
        >
          No trips yet. Start a new chat to plan one.
        </div>
      </nav>

      <div className="border-t border-line p-3 text-sm">
        <Link
          href="/settings"
          className={`mb-2 flex items-center gap-2 rounded-lg px-2 py-2 transition-colors ${
            activePage === "settings"
              ? "bg-brand/10 text-brand"
              : "text-gray-700 hover:bg-gray-100"
          }`}
        >
          <Settings aria-hidden="true" size={15} />
          Profile &amp; passports
        </Link>

        <div className="flex items-center gap-2 px-2 py-1.5">
          <span className="grid size-8 shrink-0 place-items-center rounded-full bg-gray-100 text-gray-500">
            <UserRound aria-hidden="true" size={15} />
          </span>
          <span className="min-w-0">
            <span className="block truncate text-xs font-medium text-gray-700">
              {user?.display_name || user?.email || "Traveller"}
            </span>
            <span className="block truncate text-[11px] text-gray-400">
              {user?.email}
            </span>
          </span>
          <button
            type="button"
            onClick={signOut}
            title="Sign out"
            aria-label="Sign out"
            className="ml-auto rounded-lg p-2 text-gray-400 transition-colors hover:bg-gray-100 hover:text-brand"
          >
            <LogOut aria-hidden="true" size={15} />
          </button>
        </div>
      </div>
    </aside>
  );
}
