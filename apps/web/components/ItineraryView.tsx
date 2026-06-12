"use client";

import { useState } from "react";
import { Clock, Download, ExternalLink, MapPin, CloudRain } from "lucide-react";
import dynamic from "next/dynamic";
import { downloadPdf } from "@/lib/api";
import type { Itinerary, ItineraryItem } from "@/lib/types";
import WarningBadge from "./WarningBadge";

const MapView = dynamic(() => import("./MapView"), { ssr: false });

function ItemRow({ item }: { item: ItineraryItem }) {
  return (
    <div className="border-l-2 border-brand/30 pl-3">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        {item.start_time && (
          <span className="flex items-center gap-1 text-sm font-medium text-brand">
            <Clock size={13} />
            {item.start_time}
            {item.end_time ? `–${item.end_time}` : ""}
          </span>
        )}
        <span className="font-medium">{item.name}</span>
        {item.category && (
          <span className="text-xs text-gray-500">· {item.category}</span>
        )}
        {item.business_status === "CLOSED_TEMPORARILY" && (
          <span className="rounded bg-red-100 px-1.5 py-0.5 text-[10px] font-semibold text-red-700">
            TEMP CLOSED
          </span>
        )}
      </div>

      {item.description && (
        <p className="mt-0.5 text-sm text-gray-600">{item.description}</p>
      )}
      {item.address && (
        <p className="mt-0.5 flex items-center gap-1 text-xs text-gray-500">
          <MapPin size={12} /> {item.address}
        </p>
      )}

      {item.reservation_url && (
        <a
          href={item.reservation_url}
          target="_blank"
          rel="noreferrer"
          className="mt-1 inline-flex items-center gap-1 rounded-md border border-brand/40 px-2 py-1 text-xs font-medium text-brand hover:bg-brand/5"
        >
          <ExternalLink size={12} /> Reserve / official page
        </a>
      )}

      {item.warnings.length > 0 && (
        <div className="mt-2 space-y-1">
          {item.warnings.map((w, i) => (
            <WarningBadge key={i} warning={w} />
          ))}
        </div>
      )}
    </div>
  );
}

export default function ItineraryView({ itinerary }: { itinerary: Itinerary }) {
  const [downloading, setDownloading] = useState(false);

  async function handleDownload() {
    setDownloading(true);
    try {
      await downloadPdf(
        "itinerary",
        itinerary,
        `itinerary-${itinerary.destination.toLowerCase().replace(/\s+/g, "-")}.pdf`,
      );
    } catch (err) {
      alert((err as Error).message);
    } finally {
      setDownloading(false);
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold">{itinerary.destination}</h2>
          <p className="text-sm text-gray-600">
            {itinerary.start_date} – {itinerary.end_date}
          </p>
        </div>
        <button
          onClick={handleDownload}
          disabled={downloading}
          className="flex items-center gap-1 rounded-lg bg-brand px-3 py-2 text-sm font-medium text-brand-fg disabled:opacity-50"
        >
          <Download size={15} /> {downloading ? "Preparing…" : "Download PDF"}
        </button>
      </div>

      {itinerary.warnings.length > 0 && (
        <div className="space-y-1.5 rounded-xl border border-amber-200 bg-amber-50/50 p-3">
          <p className="text-sm font-medium text-amber-800">Trip notices</p>
          {itinerary.warnings.map((w, i) => (
            <WarningBadge key={i} warning={w} />
          ))}
        </div>
      )}

      <MapView itinerary={itinerary} />

      <div className="space-y-4">
        {itinerary.days.map((day, idx) => (
          <div key={idx} className="rounded-xl border border-gray-200 bg-white p-4">
            <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
              <h3 className="font-semibold">
                {day.title || `Day ${idx + 1}`}{" "}
                <span className="text-sm font-normal text-gray-500">{day.date}</span>
              </h3>
              {day.weather?.summary && (
                <span className="flex items-center gap-1 text-xs text-gray-500">
                  <CloudRain size={13} /> {day.weather.summary}
                  {day.weather.temp_min_c != null &&
                    ` ${Math.round(day.weather.temp_min_c)}–${Math.round(
                      day.weather.temp_max_c ?? day.weather.temp_min_c,
                    )}°C`}
                </span>
              )}
            </div>
            {day.summary && <p className="mb-3 text-sm text-gray-600">{day.summary}</p>}
            <div className="space-y-3">
              {day.items.map((item, i) => (
                <ItemRow key={i} item={item} />
              ))}
            </div>
          </div>
        ))}
      </div>

      <p className="text-xs text-gray-400">{itinerary.disclaimer}</p>
    </div>
  );
}
