"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { listTrips } from "./api";
import { useAuth } from "./auth";
import type { TripSummary } from "./types";

interface TripsState {
  trips: TripSummary[];
  loading: boolean;
  refresh: () => Promise<void>;
}

const TripsContext = createContext<TripsState | null>(null);

export function TripsProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  const [trips, setTrips] = useState<TripSummary[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    if (!user) {
      setTrips([]);
      setLoading(false);
      return;
    }
    try {
      setTrips(await listTrips());
    } catch {
      /* sidebar is best-effort; ignore transient errors */
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const value = useMemo(
    () => ({ trips, loading, refresh }),
    [trips, loading, refresh],
  );

  return <TripsContext.Provider value={value}>{children}</TripsContext.Provider>;
}

export function useTrips(): TripsState {
  const ctx = useContext(TripsContext);
  if (!ctx) throw new Error("useTrips must be used within a TripsProvider");
  return ctx;
}
