"use client";

import { useCallback, useEffect, useState } from "react";
import ItineraryView from "@/components/ItineraryView";
import { getItinerary, listTrips } from "@/lib/api";
import type { Itinerary, TripSummary } from "@/lib/types";

export default function TripsPage() {
  const [trips, setTrips] = useState<TripSummary[]>([]);
  const [selected, setSelected] = useState<Itinerary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listTrips()
      .then(setTrips)
      .catch((err) => setError((err as Error).message))
      .finally(() => setLoading(false));
  }, []);

  const openItinerary = useCallback(async (itineraryId: string) => {
    setError(null);
    try {
      const resp = await getItinerary(itineraryId);
      setSelected(resp.itinerary);
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[380px_1fr]">
      <div className="space-y-3">
        <h1 className="text-2xl font-semibold">My trips</h1>
        {loading && <p className="text-sm text-gray-500">Loading your trips…</p>}
        {!loading && trips.length === 0 && (
          <p className="text-sm text-gray-500">
            No trips yet. Plan one and it will be saved here.
          </p>
        )}
        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {error}
          </div>
        )}
        <ul className="space-y-2">
          {trips.map((trip) => (
            <li key={trip.trip_id}>
              <button
                type="button"
                disabled={!trip.itinerary_id}
                onClick={() => trip.itinerary_id && openItinerary(trip.itinerary_id)}
                className="w-full rounded-lg border border-gray-200 bg-white p-3 text-left hover:border-brand disabled:cursor-not-allowed disabled:opacity-60"
              >
                <div className="font-medium">{trip.destination}</div>
                <div className="text-sm text-gray-500">
                  {trip.start_date} → {trip.end_date}
                </div>
              </button>
            </li>
          ))}
        </ul>
      </div>

      <div>
        {selected ? (
          <ItineraryView itinerary={selected} />
        ) : (
          <div className="flex h-full min-h-64 items-center justify-center rounded-xl border border-dashed border-gray-300 p-8 text-center text-sm text-gray-500">
            Select a trip to view its saved itinerary.
          </div>
        )}
      </div>
    </div>
  );
}
