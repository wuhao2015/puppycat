"use client";

import { useState } from "react";
import PlannerForm from "@/components/PlannerForm";
import ItineraryView from "@/components/ItineraryView";
import { createItinerary } from "@/lib/api";
import type { Itinerary, TripRequest } from "@/lib/types";

export default function HomePage() {
  const [itinerary, setItinerary] = useState<Itinerary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(req: TripRequest) {
    setLoading(true);
    setError(null);
    try {
      const resp = await createItinerary(req);
      setItinerary(resp.itinerary);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[380px_1fr]">
      <div className="space-y-3">
        <div>
          <h1 className="text-2xl font-semibold">Plan a trip</h1>
          <p className="text-sm text-gray-600">
            Every itinerary is checked against live hours, closures, and weather before you
            see it.
          </p>
        </div>
        <PlannerForm onSubmit={handleSubmit} loading={loading} />
        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {error}
          </div>
        )}
      </div>

      <div>
        {itinerary ? (
          <ItineraryView itinerary={itinerary} />
        ) : (
          <div className="flex h-full min-h-64 items-center justify-center rounded-xl border border-dashed border-gray-300 p-8 text-center text-sm text-gray-500">
            {loading
              ? "Gathering venues, drafting, and running the real-time verification pass…"
              : "Your verified itinerary will appear here."}
          </div>
        )}
      </div>
    </div>
  );
}
