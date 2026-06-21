"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { RefreshCw, Send } from "lucide-react";
import {
  createTrip,
  getTrip,
  getTripVisaNotice,
  sendTripMessage,
  updateTripPlan,
} from "@/lib/api";
import { useTrips } from "@/lib/trips";
import type { ChatMessage, Itinerary, VisaNotice } from "@/lib/types";
import { cn } from "@/lib/utils";
import ItineraryView from "./ItineraryView";

const GREETING: ChatMessage = {
  role: "assistant",
  content:
    "Hi! I'm Puppycat. Tell me where you'd like to go and when, plus anything about your " +
    "style of travel. When you're ready, hit \"Update plan\" and I'll build a verified " +
    "itinerary you can keep refining.",
};

export default function TripWorkspace({ initialTripId }: { initialTripId?: string }) {
  const { refresh } = useTrips();
  const [tripId, setTripId] = useState<string | undefined>(initialTripId);
  const [messages, setMessages] = useState<ChatMessage[]>([GREETING]);
  const [itinerary, setItinerary] = useState<Itinerary | null>(null);
  const [visaNotices, setVisaNotices] = useState<VisaNotice[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [planning, setPlanning] = useState(false);
  const [planError, setPlanError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = useCallback(() => {
    requestAnimationFrame(() => {
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
    });
  }, []);

  const loadVisa = useCallback(async (id: string) => {
    try {
      const resp = await getTripVisaNotice(id);
      setVisaNotices(resp.notices);
    } catch {
      /* visa reminders are best-effort */
    }
  }, []);

  useEffect(() => {
    let active = true;
    setTripId(initialTripId);
    if (!initialTripId) {
      setMessages([GREETING]);
      setItinerary(null);
      setVisaNotices([]);
      return;
    }
    (async () => {
      try {
        const trip = await getTrip(initialTripId);
        if (!active) return;
        setMessages(trip.messages.length ? trip.messages : [GREETING]);
        setItinerary(trip.itinerary ?? null);
        if (trip.itinerary) loadVisa(initialTripId);
      } catch {
        /* handled by redirect-on-401 elsewhere */
      }
    })();
    return () => {
      active = false;
    };
  }, [initialTripId, loadVisa]);

  async function send() {
    const text = input.trim();
    if (!text || streaming) return;

    let id = tripId;
    if (!id) {
      const detail = await createTrip();
      id = detail.trip_id;
      setTripId(id);
      window.history.replaceState(null, "", `/trips/${id}`);
      refresh();
    }

    setInput("");
    setStreaming(true);
    setMessages((prev) => [
      ...prev,
      { role: "user", content: text },
      { role: "assistant", content: "" },
    ]);
    scrollToBottom();

    try {
      await sendTripMessage(id, text, (chunk) => {
        setMessages((prev) => {
          const copy = [...prev];
          copy[copy.length - 1] = {
            role: "assistant",
            content: copy[copy.length - 1].content + chunk,
          };
          return copy;
        });
        scrollToBottom();
      });
      refresh();
    } catch (err) {
      setMessages((prev) => {
        const copy = [...prev];
        copy[copy.length - 1] = {
          role: "assistant",
          content: `Sorry, something went wrong: ${(err as Error).message}`,
        };
        return copy;
      });
    } finally {
      setStreaming(false);
    }
  }

  async function updatePlan() {
    if (!tripId || planning) return;
    setPlanning(true);
    setPlanError(null);
    try {
      const resp = await updateTripPlan(tripId);
      setItinerary(resp.itinerary);
      loadVisa(tripId);
      refresh();
    } catch (err) {
      setPlanError((err as Error).message);
    } finally {
      setPlanning(false);
    }
  }

  return (
    <div className="grid h-full grid-cols-1 lg:grid-cols-2">
      {/* Chat column */}
      <div className="flex h-full flex-col border-r border-gray-200 bg-white">
        <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto p-4">
          {messages.map((m, i) => (
            <div
              key={i}
              className={cn("flex", m.role === "user" ? "justify-end" : "justify-start")}
            >
              <div
                className={cn(
                  "max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-2 text-sm",
                  m.role === "user"
                    ? "bg-brand text-brand-fg"
                    : "bg-gray-100 text-gray-800",
                )}
              >
                {m.content || (streaming && i === messages.length - 1 ? "…" : "")}
              </div>
            </div>
          ))}
        </div>

        {planError && (
          <div className="mx-4 mb-2 rounded-lg border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800">
            {planError}
          </div>
        )}

        <div className="space-y-2 border-t border-gray-200 p-3">
          <div className="flex items-end gap-2">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
              rows={1}
              placeholder="Tell Puppycat about your trip…"
              className="max-h-32 flex-1 resize-none rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-brand"
            />
            <button
              type="button"
              onClick={send}
              disabled={streaming || !input.trim()}
              className="flex items-center gap-1 rounded-lg bg-brand px-3 py-2 text-sm font-medium text-brand-fg disabled:opacity-50"
            >
              <Send size={15} />
            </button>
          </div>
          <button
            type="button"
            onClick={updatePlan}
            disabled={planning || !tripId}
            className="flex w-full items-center justify-center gap-2 rounded-lg border border-brand/40 px-3 py-2 text-sm font-medium text-brand hover:bg-brand/5 disabled:opacity-50"
          >
            <RefreshCw size={15} className={planning ? "animate-spin" : ""} />
            {planning
              ? "Building your verified plan…"
              : itinerary
                ? "Update plan"
                : "Create plan"}
          </button>
        </div>
      </div>

      {/* Itinerary column */}
      <div className="h-full overflow-y-auto p-5">
        {itinerary && tripId ? (
          <ItineraryView itinerary={itinerary} tripId={tripId} visaNotices={visaNotices} />
        ) : (
          <div className="flex h-full min-h-64 items-center justify-center rounded-xl border border-dashed border-gray-300 p-8 text-center text-sm text-gray-500">
            {planning
              ? "Gathering venues, drafting, and running the real-time verification pass…"
              : "Chat about your trip, then press Create plan to see your verified itinerary here."}
          </div>
        )}
      </div>
    </div>
  );
}
