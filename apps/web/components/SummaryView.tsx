"use client";

import { Bed, MapPin, TramFront } from "lucide-react";
import type { SummaryItinerary } from "@/lib/types";

export default function SummaryView({ summary }: { summary: SummaryItinerary }) {
  return (
    <div className="space-y-3">
      {summary.days.map((day, idx) => (
        <div key={idx} className="rounded-xl border border-gray-200 bg-white p-4">
          <div className="mb-2 flex items-baseline justify-between">
            <h3 className="font-semibold">Day {idx + 1}</h3>
            <span className="text-sm text-gray-500">{day.date}</span>
          </div>
          {day.destination && (
            <p className="flex items-center gap-1 text-sm text-gray-600">
              <MapPin size={13} /> {day.destination}
            </p>
          )}
          {day.transport.length > 0 && (
            <p className="mt-1 flex items-start gap-1 text-sm text-gray-700">
              <TramFront size={13} className="mt-0.5 shrink-0" />
              <span>{day.transport.join(" · ")}</span>
            </p>
          )}
          {day.activities.length > 0 && (
            <ul className="mt-2 list-disc space-y-0.5 pl-5 text-sm text-gray-700">
              {day.activities.map((a, i) => (
                <li key={i}>{a}</li>
              ))}
            </ul>
          )}
          {day.accommodation && (
            <p className="mt-2 flex items-center gap-1 text-sm text-gray-600">
              <Bed size={13} /> {day.accommodation}
            </p>
          )}
        </div>
      ))}
      <p className="text-xs text-gray-400">{summary.disclaimer}</p>
    </div>
  );
}
