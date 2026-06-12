"use client";

import { useState } from "react";
import { Sparkles } from "lucide-react";
import type { TripPace, TripRequest } from "@/lib/types";

interface Props {
  onSubmit: (req: TripRequest) => void;
  loading: boolean;
}

const PACES: TripPace[] = ["relaxed", "balanced", "packed"];

export default function PlannerForm({ onSubmit, loading }: Props) {
  const [destination, setDestination] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [interests, setInterests] = useState("");
  const [pace, setPace] = useState<TripPace>("balanced");
  const [travelers, setTravelers] = useState(1);
  const [budget, setBudget] = useState("");
  const [notes, setNotes] = useState("");

  function submit(e: React.FormEvent) {
    e.preventDefault();
    onSubmit({
      destination,
      start_date: startDate,
      end_date: endDate,
      interests: interests
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
      pace,
      travelers,
      budget: budget || null,
      notes: notes || null,
    });
  }

  const field = "rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-brand";

  return (
    <form onSubmit={submit} className="space-y-3 rounded-xl border border-gray-200 bg-white p-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label className="flex flex-col gap-1 text-sm sm:col-span-2">
          <span className="text-gray-600">Destination</span>
          <input
            required
            value={destination}
            onChange={(e) => setDestination(e.target.value)}
            placeholder="Kyoto, Japan"
            className={field}
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-gray-600">Start date</span>
          <input
            required
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            className={field}
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-gray-600">End date</span>
          <input
            required
            type="date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            className={field}
          />
        </label>
        <label className="flex flex-col gap-1 text-sm sm:col-span-2">
          <span className="text-gray-600">Interests (comma separated)</span>
          <input
            value={interests}
            onChange={(e) => setInterests(e.target.value)}
            placeholder="temples, ramen, hiking, art"
            className={field}
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-gray-600">Pace</span>
          <select value={pace} onChange={(e) => setPace(e.target.value as TripPace)} className={field}>
            {PACES.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-gray-600">Travelers</span>
          <input
            type="number"
            min={1}
            value={travelers}
            onChange={(e) => setTravelers(Number(e.target.value))}
            className={field}
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-gray-600">Budget (optional)</span>
          <input
            value={budget}
            onChange={(e) => setBudget(e.target.value)}
            placeholder="mid-range"
            className={field}
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-gray-600">Notes (optional)</span>
          <input
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="traveling with a toddler"
            className={field}
          />
        </label>
      </div>

      <button
        type="submit"
        disabled={loading}
        className="flex w-full items-center justify-center gap-2 rounded-lg bg-brand px-4 py-2.5 text-sm font-medium text-brand-fg disabled:opacity-50"
      >
        <Sparkles size={16} />
        {loading ? "Planning & verifying…" : "Generate verified itinerary"}
      </button>
    </form>
  );
}
