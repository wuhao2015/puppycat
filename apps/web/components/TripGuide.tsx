"use client";

import {
  CalendarDays,
  CloudSun,
  ExternalLink as ExternalLinkIcon,
  MapPin,
  TriangleAlert,
} from "lucide-react";
import dynamic from "next/dynamic";
import { useMemo } from "react";

import type {
  DailyWeather,
  Itinerary,
  ItineraryWarning,
} from "../lib/types";
import type { MapMarker } from "./ItineraryMap";

const ItineraryMap = dynamic(() => import("./ItineraryMap"), {
  ssr: false,
  loading: () => <div className="h-72 animate-pulse rounded-xl bg-gray-100" />,
});

const SOURCE_LABELS: Record<string, string> = {
  google_places: "Google Places",
  open_meteo: "Open-Meteo",
  tavily: "Tavily",
};

export default function TripGuide({ itinerary }: { itinerary: Itinerary }) {
  const weatherByDate = new Map(
    itinerary.weather.map((weather) => [weather.date, weather]),
  );
  const markers = useMemo(() => itineraryMarkers(itinerary), [itinerary]);

  return (
    <div className="space-y-5">
      <section
        aria-label="Trip overview"
        className="panel flex flex-wrap items-end justify-between gap-3 p-4"
      >
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-brand">
            Destination
          </p>
          <h3 className="mt-1 text-lg font-semibold text-ink">
            {itinerary.destination}
          </h3>
        </div>
        <p className="inline-flex items-center gap-1.5 text-sm text-gray-500">
          <CalendarDays aria-hidden="true" size={14} />
          {itinerary.start_date}–{itinerary.end_date}
        </p>
      </section>

      <section aria-labelledby="verification-heading" className="panel p-4">
        <h3 id="verification-heading" className="text-sm font-semibold text-ink">
          Verification sources
        </h3>
        <div className="mt-3 grid gap-3 text-xs sm:grid-cols-2">
          <SourceList
            label="Verified"
            sources={itinerary.verified_sources}
            empty="No source completed verification."
            tone="text-emerald-700"
          />
          <SourceList
            label="Unavailable"
            sources={itinerary.unavailable_sources}
            empty="All configured sources responded."
            tone="text-amber-700"
          />
        </div>
      </section>

      <section aria-labelledby="map-heading">
        <h3 id="map-heading" className="mb-2 text-sm font-semibold text-ink">
          Map
        </h3>
        <ItineraryMap markers={markers} />
      </section>

      <section aria-labelledby="notices-heading">
        <h3 id="notices-heading" className="mb-2 text-sm font-semibold text-ink">
          Trip notices
        </h3>
        {itinerary.warnings.length > 0 ? (
          <div className="space-y-2">
            {itinerary.warnings.map((warning, index) => (
              <WarningNotice
                key={`${warning.code}-${warning.item_id}-${index}`}
                warning={warning}
              />
            ))}
          </div>
        ) : (
          <p className="panel p-3 text-sm text-gray-500">
            No current notices were returned by the available sources.
          </p>
        )}
      </section>

      <section aria-labelledby="weather-heading">
        <h3 id="weather-heading" className="mb-2 text-sm font-semibold text-ink">
          Weather
        </h3>
        {itinerary.weather.length > 0 ? (
          <div className="grid gap-2 sm:grid-cols-2">
            {itinerary.weather.map((weather) => (
              <WeatherCard key={weather.date} weather={weather} />
            ))}
          </div>
        ) : (
          <p className="panel p-3 text-sm text-gray-500">
            Forecast data is unavailable for these travel dates.
          </p>
        )}
      </section>

      <section aria-labelledby="days-heading" className="space-y-4">
        <h3 id="days-heading" className="text-sm font-semibold text-ink">
          Daily itinerary
        </h3>
        {itinerary.days.map((day, dayIndex) => {
          const weather = weatherByDate.get(day.date);
          return (
            <article key={day.date} className="panel p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-medium uppercase tracking-wide text-brand">
                    Day {dayIndex + 1} · {day.date}
                  </p>
                  <h4 className="mt-1 text-base font-semibold text-ink">
                    {day.title}
                  </h4>
                </div>
                {weather && (
                  <span className="inline-flex items-center gap-1 text-xs text-gray-500">
                    <CloudSun aria-hidden="true" size={14} />
                    {weather.summary}
                  </span>
                )}
              </div>
              {day.accommodation && (
                <p className="mt-2 text-xs text-gray-500">
                  Accommodation: {day.accommodation}
                </p>
              )}
              <div className="mt-4 space-y-5 border-l border-brand/20 pl-4">
                {day.items.map((item) => (
                  <div key={item.id}>
                    <p className="text-xs font-medium text-brand">
                      {item.start_time.slice(0, 5)}–{item.end_time.slice(0, 5)}
                    </p>
                    <h5 className="mt-0.5 text-sm font-semibold text-ink">
                      {item.title}
                    </h5>
                    {item.place?.address && (
                      <p className="mt-1 inline-flex items-start gap-1 text-xs text-gray-500">
                        <MapPin
                          aria-hidden="true"
                          className="mt-0.5 shrink-0"
                          size={12}
                        />
                        {item.place.address}
                      </p>
                    )}
                    {item.description && (
                      <p className="mt-1 text-sm leading-6 text-gray-600">
                        {item.description}
                      </p>
                    )}
                    {item.place?.opening_hours?.weekday_descriptions.length ? (
                      <details className="mt-2 text-xs text-gray-500">
                        <summary className="cursor-pointer">Listed opening hours</summary>
                        <ul className="mt-1 space-y-0.5 pl-3">
                          {item.place.opening_hours.weekday_descriptions.map(
                            (description) => (
                              <li key={description}>{description}</li>
                            ),
                          )}
                        </ul>
                      </details>
                    ) : null}
                    {(item.place?.google_maps_uri || item.place?.website_uri) && (
                      <div className="mt-2 flex flex-wrap gap-3 text-xs font-medium text-brand">
                        {item.place.google_maps_uri && (
                          <OutboundLink
                            href={item.place.google_maps_uri}
                            label="Google Maps"
                          />
                        )}
                        {item.place.website_uri && (
                          <OutboundLink
                            href={item.place.website_uri}
                            label="Website"
                          />
                        )}
                      </div>
                    )}
                    {item.warnings.length > 0 && (
                      <div className="mt-2 space-y-1">
                        {item.warnings.map((warning, index) => (
                          <p
                            key={`${warning.code}-${index}`}
                            className="inline-flex items-start gap-1 text-xs text-amber-700"
                          >
                            <TriangleAlert
                              aria-hidden="true"
                              className="mt-0.5 shrink-0"
                              size={12}
                            />
                            {warning.message}
                          </p>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </article>
          );
        })}
      </section>
    </div>
  );
}

function SourceList({
  label,
  sources,
  empty,
  tone,
}: {
  label: string;
  sources: string[];
  empty: string;
  tone: string;
}) {
  return (
    <div>
      <p className={`font-semibold ${tone}`}>{label}</p>
      <p className="mt-1 text-gray-500">
        {sources.length > 0
          ? sources.map((source) => SOURCE_LABELS[source] ?? source).join(", ")
          : empty}
      </p>
    </div>
  );
}

function WarningNotice({ warning }: { warning: ItineraryWarning }) {
  const content = (
    <>
      <TriangleAlert aria-hidden="true" className="mt-0.5 shrink-0" size={14} />
      <span>{warning.message}</span>
    </>
  );
  const className =
    "flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800";
  return warning.source_url ? (
    <a href={warning.source_url} target="_blank" rel="noreferrer" className={className}>
      {content}
    </a>
  ) : (
    <div className={className}>{content}</div>
  );
}

function WeatherCard({ weather }: { weather: DailyWeather }) {
  return (
    <div className="panel p-3">
      <p className="text-xs font-medium text-brand">{weather.date}</p>
      <p className="mt-1 text-sm font-semibold text-ink">{weather.summary}</p>
      <p className="mt-1 text-xs text-gray-500">
        {temperatureRange(weather)}
        {weather.precipitation_probability_max !== null
          ? ` · Rain ${weather.precipitation_probability_max}%`
          : ""}
        {weather.wind_speed_max_kmh !== null
          ? ` · Wind ${weather.wind_speed_max_kmh} km/h`
          : ""}
      </p>
    </div>
  );
}

function temperatureRange(weather: DailyWeather): string {
  if (weather.temperature_min_c === null || weather.temperature_max_c === null) {
    return "Temperature unavailable";
  }
  return `${weather.temperature_min_c}–${weather.temperature_max_c}°C`;
}

function OutboundLink({ href, label }: { href: string; label: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="inline-flex items-center gap-1 hover:underline"
    >
      {label}
      <ExternalLinkIcon aria-hidden="true" size={11} />
    </a>
  );
}

function itineraryMarkers(itinerary: Itinerary): MapMarker[] {
  const markers = new Map<string, MapMarker>();
  for (const day of itinerary.days) {
    for (const item of day.items) {
      const location = item.place?.location;
      if (!location || !item.place) {
        continue;
      }
      markers.set(item.place.place_id, {
        id: item.place.place_id,
        label: item.place.name,
        latitude: location.latitude,
        longitude: location.longitude,
      });
    }
  }
  if (markers.size === 0 && itinerary.destination_location) {
    markers.set("destination", {
      id: "destination",
      label: itinerary.destination,
      latitude: itinerary.destination_location.latitude,
      longitude: itinerary.destination_location.longitude,
    });
  }
  return [...markers.values()];
}
