"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Plus, Settings, Trash2 } from "lucide-react";
import { deleteTrip } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useTrips } from "@/lib/trips";

export default function Sidebar() {
  const { user, logout } = useAuth();
  const { trips, loading, refresh } = useTrips();
  const pathname = usePathname();
  const router = useRouter();

  async function handleDelete(tripId: string, e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (!confirm("Delete this trip and its itinerary?")) return;
    await deleteTrip(tripId);
    await refresh();
    if (pathname === `/trips/${tripId}`) router.push("/");
  }

  return (
    <aside className="flex h-screen w-72 flex-col border-r border-gray-200 bg-white">
      <div className="flex items-center justify-between px-4 py-4">
        <Link href="/" className="flex items-center gap-2 font-semibold text-brand">
          <span className="text-xl">🐾</span> Puppycat Travel
        </Link>
      </div>

      <div className="px-3">
        <Link
          href="/"
          className="flex items-center justify-center gap-2 rounded-lg bg-brand px-3 py-2 text-sm font-medium text-brand-fg hover:opacity-90"
        >
          <Plus size={16} /> New trip
        </Link>
      </div>

      <nav className="mt-3 flex-1 space-y-1 overflow-y-auto px-2">
        {loading && <p className="px-2 text-xs text-gray-400">Loading trips…</p>}
        {!loading && trips.length === 0 && (
          <p className="px-2 text-xs text-gray-400">
            No trips yet. Start a new chat to plan one.
          </p>
        )}
        {trips.map((trip) => {
          const active = pathname === `/trips/${trip.trip_id}`;
          return (
            <Link
              key={trip.trip_id}
              href={`/trips/${trip.trip_id}`}
              className={`group flex items-center justify-between gap-2 rounded-lg px-3 py-2 text-sm ${
                active ? "bg-brand/10 text-brand" : "text-gray-700 hover:bg-gray-100"
              }`}
            >
              <span className="truncate">
                {trip.title || trip.destination || "New trip"}
              </span>
              <button
                type="button"
                onClick={(e) => handleDelete(trip.trip_id, e)}
                className="invisible shrink-0 text-gray-400 hover:text-red-600 group-hover:visible"
                aria-label="Delete trip"
              >
                <Trash2 size={14} />
              </button>
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-gray-200 p-3 text-sm">
        <Link
          href="/settings"
          className="mb-2 flex items-center gap-2 rounded-lg px-2 py-1.5 text-gray-700 hover:bg-gray-100"
        >
          <Settings size={15} /> Profile &amp; passports
        </Link>
        <div className="flex items-center justify-between px-2">
          <span className="truncate text-gray-500">
            {user?.display_name || user?.email}
          </span>
          <button
            type="button"
            onClick={() => {
              logout();
              router.replace("/login");
            }}
            className="rounded-md border border-gray-300 px-2 py-1 text-xs text-gray-700 hover:bg-gray-50"
          >
            Sign out
          </button>
        </div>
      </div>
    </aside>
  );
}
