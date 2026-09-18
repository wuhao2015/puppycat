"use client";

import "mapbox-gl/dist/mapbox-gl.css";

import { MapPinned } from "lucide-react";
import { useEffect, useRef, useState } from "react";

export type MapMarker = {
  id: string;
  label: string;
  latitude: number;
  longitude: number;
};

type ItineraryMapProps = {
  markers: MapMarker[];
};

const MAPBOX_TOKEN = process.env.NEXT_PUBLIC_MAPBOX_TOKEN?.trim() ?? "";

export default function ItineraryMap({ markers }: ItineraryMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [mapError, setMapError] = useState<string | null>(null);

  useEffect(() => {
    if (!MAPBOX_TOKEN || markers.length === 0 || !containerRef.current) {
      return;
    }

    setMapError(null);
    let disposed = false;
    let map: import("mapbox-gl").Map | null = null;

    async function initializeMap() {
      try {
        const mapboxgl = (await import("mapbox-gl")).default;
        if (disposed || !containerRef.current) {
          return;
        }
        mapboxgl.accessToken = MAPBOX_TOKEN;
        const bounds = new mapboxgl.LngLatBounds();
        for (const marker of markers) {
          bounds.extend([marker.longitude, marker.latitude]);
        }
        map = new mapboxgl.Map({
          container: containerRef.current,
          style: "mapbox://styles/mapbox/streets-v12",
          center: [markers[0].longitude, markers[0].latitude],
          zoom: markers.length === 1 ? 12 : 9,
          attributionControl: true,
        });
        map.addControl(new mapboxgl.NavigationControl(), "top-right");
        for (const marker of markers) {
          new mapboxgl.Marker({ color: "#6d5efc" })
            .setLngLat([marker.longitude, marker.latitude])
            .setPopup(new mapboxgl.Popup({ offset: 20 }).setText(marker.label))
            .addTo(map);
        }
        if (markers.length > 1) {
          map.fitBounds(bounds, { padding: 48, maxZoom: 13, duration: 0 });
        }
      } catch {
        if (!disposed) {
          setMapError("The map could not be loaded.");
        }
      }
    }

    void initializeMap();
    return () => {
      disposed = true;
      map?.remove();
    };
  }, [markers]);

  if (!MAPBOX_TOKEN) {
    return (
      <MapEmptyState message="Mapbox is not configured for this deployment." />
    );
  }
  if (markers.length === 0) {
    return (
      <MapEmptyState message="No verified place coordinates are available." />
    );
  }
  if (mapError) {
    return <MapEmptyState message={mapError} />;
  }
  return (
    <div
      ref={containerRef}
      aria-label="Itinerary map"
      className="h-72 overflow-hidden rounded-xl border border-line bg-gray-100"
    />
  );
}

function MapEmptyState({ message }: { message: string }) {
  return (
    <div className="panel flex h-44 items-center justify-center border-dashed p-5 text-center">
      <div>
        <MapPinned
          aria-hidden="true"
          className="mx-auto text-gray-400"
          size={22}
        />
        <p className="mt-2 text-sm text-gray-500">{message}</p>
      </div>
    </div>
  );
}
