"use client";

import { use } from "react";
import TripWorkspace from "@/components/TripWorkspace";

export default function TripPage({
  params,
}: {
  params: Promise<{ tripId: string }>;
}) {
  const { tripId } = use(params);
  return <TripWorkspace key={tripId} initialTripId={tripId} />;
}
