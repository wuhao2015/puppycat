"use client";

import {
  Check,
  LoaderCircle,
  LogOut,
  Pencil,
  Plus,
  Settings,
  Trash2,
  UserRound,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { useAuth } from "../lib/auth";
import { useTrips } from "../lib/trips";

type SidebarProps = {
  activePage: "workspace" | "settings";
};

export default function Sidebar({ activePage }: SidebarProps) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, signOut } = useAuth();
  const { trips, loading, error, renameTrip, deleteTrip } = useTrips();
  const [editingTripId, setEditingTripId] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [busyTripId, setBusyTripId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const currentTripId = pathname.startsWith("/trips/")
    ? pathname.split("/")[2]
    : null;

  function startRenaming(tripId: string, currentTitle: string | null) {
    setEditingTripId(tripId);
    setTitle(currentTitle ?? "New trip");
    setActionError(null);
  }

  async function submitRename(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextTitle = title.trim();
    if (!editingTripId || !nextTitle) {
      return;
    }

    setBusyTripId(editingTripId);
    setActionError(null);
    try {
      await renameTrip(editingTripId, nextTitle);
      setEditingTripId(null);
    } catch (requestError) {
      setActionError(
        requestError instanceof Error ? requestError.message : "Unable to rename trip",
      );
    } finally {
      setBusyTripId(null);
    }
  }

  async function removeTrip(tripId: string, tripTitle: string | null) {
    const confirmed = window.confirm(
      `Delete “${tripTitle ?? "New trip"}”? This cannot be undone.`,
    );
    if (!confirmed) {
      return;
    }

    setBusyTripId(tripId);
    setActionError(null);
    try {
      await deleteTrip(tripId);
      if (tripId === currentTripId) {
        router.replace("/");
      }
    } catch (requestError) {
      setActionError(
        requestError instanceof Error ? requestError.message : "Unable to delete trip",
      );
    } finally {
      setBusyTripId(null);
    }
  }

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

      <nav aria-label="Trips" className="mt-5 min-h-0 flex-1 overflow-y-auto px-3">
        <p className="px-2 text-[11px] font-semibold uppercase tracking-wide text-gray-400">
          Trips
        </p>

        {loading && (
          <div className="mt-3 flex items-center gap-2 px-2 text-xs text-gray-400">
            <LoaderCircle aria-hidden="true" className="animate-spin" size={13} />
            Loading trips…
          </div>
        )}

        {!loading && error && <div className="notice-error mt-2 text-xs">{error}</div>}

        {!loading && !error && trips.length === 0 && (
          <div
            className={`mt-2 rounded-lg px-3 py-3 text-xs leading-5 ${
              activePage === "workspace"
                ? "bg-brand/10 text-brand"
                : "text-gray-400"
            }`}
          >
            No trips yet. Start a new chat to plan one.
          </div>
        )}

        {trips.length > 0 && (
          <div className="mt-2 space-y-1">
            {trips.map((trip) => {
              const isCurrent = trip.id === currentTripId;
              const isBusy = trip.id === busyTripId;

              if (editingTripId === trip.id) {
                return (
                  <form
                    key={trip.id}
                    onSubmit={submitRename}
                    className="flex items-center gap-1 rounded-lg bg-brand/10 p-1"
                  >
                    <input
                      aria-label="Trip title"
                      autoFocus
                      maxLength={100}
                      value={title}
                      onChange={(event) => setTitle(event.target.value)}
                      className="min-w-0 flex-1 rounded-md border border-brand/30 bg-white px-2 py-1.5 text-xs text-ink outline-none focus:border-brand"
                    />
                    <button
                      type="submit"
                      disabled={isBusy || !title.trim()}
                      aria-label="Save trip title"
                      className="rounded-md p-1.5 text-brand hover:bg-white disabled:opacity-40"
                    >
                      <Check aria-hidden="true" size={13} />
                    </button>
                    <button
                      type="button"
                      disabled={isBusy}
                      onClick={() => setEditingTripId(null)}
                      aria-label="Cancel renaming"
                      className="rounded-md p-1.5 text-gray-400 hover:bg-white"
                    >
                      <X aria-hidden="true" size={13} />
                    </button>
                  </form>
                );
              }

              return (
                <div
                  key={trip.id}
                  className={`group flex items-center rounded-lg transition-colors ${
                    isCurrent
                      ? "bg-brand/10 text-brand"
                      : "text-gray-600 hover:bg-gray-100"
                  }`}
                >
                  <Link
                    href={`/trips/${trip.id}`}
                    className="min-w-0 flex-1 truncate px-3 py-2 text-xs font-medium"
                    title={trip.title ?? "New trip"}
                  >
                    {trip.title ?? "New trip"}
                  </Link>
                  {isBusy ? (
                    <LoaderCircle
                      aria-label="Updating trip"
                      className="mr-2 shrink-0 animate-spin text-gray-400"
                      size={13}
                    />
                  ) : (
                    <span className="mr-1 flex shrink-0 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
                      <button
                        type="button"
                        onClick={() => startRenaming(trip.id, trip.title)}
                        aria-label={`Rename ${trip.title ?? "New trip"}`}
                        className="rounded-md p-1.5 text-gray-400 hover:bg-white hover:text-brand"
                      >
                        <Pencil aria-hidden="true" size={12} />
                      </button>
                      <button
                        type="button"
                        onClick={() => removeTrip(trip.id, trip.title)}
                        aria-label={`Delete ${trip.title ?? "New trip"}`}
                        className="rounded-md p-1.5 text-gray-400 hover:bg-white hover:text-red-600"
                      >
                        <Trash2 aria-hidden="true" size={12} />
                      </button>
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {actionError && <div className="notice-error mt-2 text-xs">{actionError}</div>}
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
