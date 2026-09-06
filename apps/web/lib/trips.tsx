"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { useAuth } from "./auth";
import type {
  ChatDevelopmentResponse,
  Trip,
  TripListItem,
} from "./types";

type TripsContextValue = {
  trips: TripListItem[];
  loading: boolean;
  error: string | null;
  createTrip: (title?: string) => Promise<Trip>;
  getTrip: (tripId: string) => Promise<Trip>;
  renameTrip: (tripId: string, title: string) => Promise<Trip>;
  deleteTrip: (tripId: string) => Promise<void>;
  appendMessage: (
    tripId: string,
    content: string,
  ) => Promise<ChatDevelopmentResponse>;
};

const TripsContext = createContext<TripsContextValue | null>(null);

function newestFirst(left: TripListItem, right: TripListItem): number {
  return right.updated_at.localeCompare(left.updated_at) || right.id.localeCompare(left.id);
}

function asListItem(trip: Trip): TripListItem {
  const { preferences: _preferences, chat_messages: _chatMessages, ...item } = trip;
  return item;
}

export function TripsProvider({ children }: { children: ReactNode }) {
  const { user, loading: authLoading, request } = useAuth();
  const [trips, setTrips] = useState<TripListItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (authLoading) {
      return;
    }
    if (!user) {
      setTrips([]);
      setError(null);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);
    request<TripListItem[]>("/api/trips")
      .then((loadedTrips) => {
        if (!cancelled) {
          setTrips(loadedTrips);
        }
      })
      .catch((requestError: unknown) => {
        if (!cancelled) {
          setError(
            requestError instanceof Error
              ? requestError.message
              : "Unable to load trips",
          );
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [authLoading, request, user]);

  const storeTrip = useCallback((trip: Trip) => {
    const item = asListItem(trip);
    setTrips((current) =>
      [item, ...current.filter((currentItem) => currentItem.id !== trip.id)].sort(
        newestFirst,
      ),
    );
  }, []);

  const createTrip = useCallback(
    async (title?: string) => {
      const trip = await request<Trip>("/api/trips", {
        method: "POST",
        body: JSON.stringify(title ? { title } : {}),
      });
      storeTrip(trip);
      return trip;
    },
    [request, storeTrip],
  );

  const getTrip = useCallback(
    (tripId: string) => request<Trip>(`/api/trips/${tripId}`),
    [request],
  );

  const renameTrip = useCallback(
    async (tripId: string, title: string) => {
      const trip = await request<Trip>(`/api/trips/${tripId}`, {
        method: "PATCH",
        body: JSON.stringify({ title }),
      });
      storeTrip(trip);
      return trip;
    },
    [request, storeTrip],
  );

  const deleteTrip = useCallback(
    async (tripId: string) => {
      await request<void>(`/api/trips/${tripId}`, { method: "DELETE" });
      setTrips((current) => current.filter((trip) => trip.id !== tripId));
    },
    [request],
  );

  const appendMessage = useCallback(
    async (tripId: string, content: string) => {
      const response = await request<ChatDevelopmentResponse>(
        `/api/trips/${tripId}/chat`,
        {
          method: "POST",
          body: JSON.stringify({ content }),
        },
      );
      setTrips((current) =>
        current
          .map((trip) =>
            trip.id === tripId
              ? { ...trip, updated_at: response.trip_updated_at }
              : trip,
          )
          .sort(newestFirst),
      );
      return response;
    },
    [request],
  );

  const value = useMemo(
    () => ({
      trips,
      loading,
      error,
      createTrip,
      getTrip,
      renameTrip,
      deleteTrip,
      appendMessage,
    }),
    [
      appendMessage,
      createTrip,
      deleteTrip,
      error,
      getTrip,
      loading,
      renameTrip,
      trips,
    ],
  );

  return <TripsContext.Provider value={value}>{children}</TripsContext.Provider>;
}

export function useTrips(): TripsContextValue {
  const context = useContext(TripsContext);
  if (context === null) {
    throw new Error("useTrips must be used inside TripsProvider");
  }
  return context;
}
