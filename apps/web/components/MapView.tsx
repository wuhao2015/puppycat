"use client";

import { useEffect, useRef } from "react";
import mapboxgl from "mapbox-gl";
import type { Itinerary } from "@/lib/types";

interface Pin {
  name: string;
  lat: number;
  lng: number;
  day: number;
}

export default function MapView({ itinerary }: { itinerary: Itinerary }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<mapboxgl.Map | null>(null);

  const pins: Pin[] = itinerary.days.flatMap((day, dayIdx) =>
    day.items
      .filter((it) => it.location)
      .map((it) => ({
        name: it.name,
        lat: it.location!.lat,
        lng: it.location!.lng,
        day: dayIdx + 1,
      })),
  );

  useEffect(() => {
    const token = process.env.NEXT_PUBLIC_MAPBOX_TOKEN;
    if (!token || !containerRef.current || pins.length === 0) return;

    mapboxgl.accessToken = token;
    const map = new mapboxgl.Map({
      container: containerRef.current,
      style: "mapbox://styles/mapbox/streets-v12",
      center: [pins[0].lng, pins[0].lat],
      zoom: 12,
    });
    mapRef.current = map;

    const bounds = new mapboxgl.LngLatBounds();
    pins.forEach((pin) => {
      const popup = new mapboxgl.Popup({ offset: 18 }).setText(
        `Day ${pin.day}: ${pin.name}`,
      );
      new mapboxgl.Marker({ color: "#6d5efc" })
        .setLngLat([pin.lng, pin.lat])
        .setPopup(popup)
        .addTo(map);
      bounds.extend([pin.lng, pin.lat]);
    });

    if (pins.length > 1) {
      map.fitBounds(bounds, { padding: 60, maxZoom: 14 });
    }

    return () => map.remove();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [itinerary]);

  if (!process.env.NEXT_PUBLIC_MAPBOX_TOKEN) {
    return (
      <div className="flex h-64 items-center justify-center rounded-xl border border-dashed border-gray-300 text-sm text-gray-500">
        Set NEXT_PUBLIC_MAPBOX_TOKEN to see the trip map.
      </div>
    );
  }

  if (pins.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center rounded-xl border border-dashed border-gray-300 text-sm text-gray-500">
        No mapped venues for this itinerary yet.
      </div>
    );
  }

  return <div ref={containerRef} className="h-80 w-full rounded-xl" />;
}
