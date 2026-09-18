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
  ChatMessage,
  ChatStreamResult,
  ItineraryResponse,
  Trip,
  TripListItem,
} from "./types";

type ChatStreamEvent =
  | { type: "chunk"; content: string }
  | { type: "done"; message: ChatMessage; trip_updated_at: string }
  | { type: "error"; detail: { code: string; message: string } };

type TripsContextValue = {
  trips: TripListItem[];
  loading: boolean;
  error: string | null;
  createTrip: (title?: string) => Promise<Trip>;
  getTrip: (tripId: string) => Promise<Trip>;
  renameTrip: (tripId: string, title: string) => Promise<Trip>;
  deleteTrip: (tripId: string) => Promise<void>;
  planTrip: (tripId: string) => Promise<ItineraryResponse>;
  streamMessage: (
    tripId: string,
    content: string,
    onChunk: (chunk: string) => void,
    signal: AbortSignal,
  ) => Promise<ChatStreamResult>;
};

const TripsContext = createContext<TripsContextValue | null>(null);

function newestFirst(left: TripListItem, right: TripListItem): number {
  return right.updated_at.localeCompare(left.updated_at) || right.id.localeCompare(left.id);
}

function asListItem(trip: Trip): TripListItem {
  const {
    preferences: _preferences,
    chat_messages: _chatMessages,
    latest_itinerary: _latestItinerary,
    ...item
  } = trip;
  return item;
}

export function TripsProvider({ children }: { children: ReactNode }) {
  const { user, loading: authLoading, request, requestResponse } = useAuth();
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

  const planTrip = useCallback(
    (tripId: string) =>
      request<ItineraryResponse>(`/api/trips/${tripId}/plan`, {
        method: "POST",
      }),
    [request],
  );

  const streamMessage = useCallback(
    async (
      tripId: string,
      content: string,
      onChunk: (chunk: string) => void,
      signal: AbortSignal,
    ): Promise<ChatStreamResult> => {
      const response = await requestResponse(`/api/trips/${tripId}/chat`, {
        method: "POST",
        body: JSON.stringify({ content }),
        signal,
      });
      if (!response.body) {
        throw new Error("Puppycat returned an empty response");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      const streamState: { completed: ChatStreamResult | null } = {
        completed: null,
      };

      function consumeLine(line: string) {
        if (!line.trim()) {
          return;
        }
        const event = JSON.parse(line) as ChatStreamEvent;
        if (event.type === "chunk") {
          onChunk(event.content);
          return;
        }
        if (event.type === "error") {
          throw new Error(event.detail.message);
        }
        if (event.type === "done") {
          streamState.completed = {
            message: event.message,
            trip_updated_at: event.trip_updated_at,
          };
        }
      }

      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) {
            break;
          }
          buffer += decoder.decode(value, { stream: true });
          let newlineIndex = buffer.indexOf("\n");
          while (newlineIndex >= 0) {
            consumeLine(buffer.slice(0, newlineIndex));
            buffer = buffer.slice(newlineIndex + 1);
            newlineIndex = buffer.indexOf("\n");
          }
        }
        buffer += decoder.decode();
        consumeLine(buffer);
      } finally {
        reader.releaseLock();
      }

      if (!streamState.completed) {
        throw new Error("Puppycat's response was interrupted. Please try again.");
      }
      const result = streamState.completed;

      setTrips((current) =>
        current
          .map((trip) =>
            trip.id === tripId
              ? { ...trip, updated_at: result.trip_updated_at }
              : trip,
          )
          .sort(newestFirst),
      );
      return result;
    },
    [requestResponse],
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
      planTrip,
      streamMessage,
    }),
    [
      createTrip,
      deleteTrip,
      error,
      getTrip,
      loading,
      planTrip,
      renameTrip,
      streamMessage,
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
