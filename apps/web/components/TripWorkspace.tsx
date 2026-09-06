"use client";

import {
  Compass,
  LoaderCircle,
  MapPinned,
  RefreshCw,
  Send,
} from "lucide-react";
import { useRouter } from "next/navigation";
import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";

import { useTrips } from "../lib/trips";
import type { Trip } from "../lib/types";

type TripWorkspaceProps = {
  tripId?: string;
};

export default function TripWorkspace({ tripId }: TripWorkspaceProps) {
  const router = useRouter();
  const { trips, createTrip, getTrip, appendMessage } = useTrips();
  const [trip, setTrip] = useState<Trip | null>(null);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(Boolean(tripId));
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const displayTitle =
    (tripId ? trips.find((item) => item.id === tripId)?.title : null) ??
    trip?.title ??
    "New trip";

  useEffect(() => {
    if (!tripId) {
      setTrip(null);
      setLoading(false);
      setError(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);
    getTrip(tripId)
      .then((loadedTrip) => {
        if (!cancelled) {
          setTrip(loadedTrip);
        }
      })
      .catch((requestError: unknown) => {
        if (!cancelled) {
          setTrip(null);
          setError(
            requestError instanceof Error
              ? requestError.message
              : "Unable to load trip",
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
  }, [getTrip, tripId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ block: "end" });
  }, [trip?.chat_messages.length]);

  async function sendMessage(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    const content = message.trim();
    if (!content || sending) {
      return;
    }

    setSending(true);
    setError(null);
    let currentTrip = trip;
    let createdTrip: Trip | null = null;

    try {
      if (!currentTrip) {
        createdTrip = await createTrip();
        currentTrip = createdTrip;
        setTrip(createdTrip);
      }

      const response = await appendMessage(currentTrip.id, content);
      setTrip({
        ...currentTrip,
        chat_messages: [...currentTrip.chat_messages, response.message],
        updated_at: response.trip_updated_at,
      });
      setMessage("");

      if (createdTrip) {
        router.replace(`/trips/${createdTrip.id}`);
      }
    } catch (requestError) {
      if (createdTrip) {
        router.replace(`/trips/${createdTrip.id}`);
      }
      setError(
        requestError instanceof Error ? requestError.message : "Unable to save message",
      );
    } finally {
      setSending(false);
    }
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  }

  return (
    <div className="grid h-full min-h-0 min-w-0 grid-cols-1 lg:grid-cols-2">
      <section
        aria-labelledby="chat-heading"
        className="flex h-full min-h-0 min-w-0 flex-col overflow-hidden border-r border-line bg-white"
      >
        <header className="border-b border-line px-5 py-4">
          <h1 id="chat-heading" className="truncate text-sm font-semibold text-ink">
            {displayTitle}
          </h1>
          <p className="mt-0.5 text-xs text-gray-500">
            Tell Puppycat what kind of journey you have in mind.
          </p>
        </header>

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
          {loading && (
            <div className="flex h-full items-center justify-center text-xs text-gray-400">
              <LoaderCircle aria-hidden="true" className="mr-2 animate-spin" size={14} />
              Loading trip…
            </div>
          )}

          {!loading && error && <div className="notice-error">{error}</div>}

          {!loading && !error && (trip?.chat_messages.length ?? 0) === 0 && (
            <div className="flex justify-start">
              <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl bg-gray-100 px-4 py-2.5 text-sm leading-6 text-gray-800">
                Hi! Share your destination, dates, and travel preferences. Your
                messages will be saved to this trip.
              </div>
            </div>
          )}

          {!loading &&
            trip?.chat_messages.map((chatMessage, index) => (
              <div
                key={`${chatMessage.ts}-${index}`}
                className={
                  chatMessage.role === "user" ? "flex justify-end" : "flex justify-start"
                }
              >
                <div
                  className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-sm leading-6 ${
                    chatMessage.role === "user"
                      ? "bg-brand text-brand-fg"
                      : "bg-gray-100 text-gray-800"
                  }`}
                >
                  {chatMessage.content}
                </div>
              </div>
            ))}

          <div ref={messagesEndRef} />
        </div>

        <div className="space-y-2 border-t border-line p-3">
          <p className="rounded-lg border border-brand/20 bg-brand/5 px-3 py-2 text-xs leading-5 text-gray-600">
            Gemini chat is not connected yet. Messages are saved now; Puppycat
            replies arrive in Phase 6.
          </p>
          <form className="flex items-end gap-2" onSubmit={sendMessage}>
            <textarea
              aria-label="Trip message"
              rows={1}
              placeholder="Tell Puppycat about your trip…"
              className="form-input max-h-32 flex-1 resize-none"
              value={message}
              disabled={loading || sending || Boolean(tripId && !trip)}
              onChange={(event) => setMessage(event.target.value)}
              onKeyDown={handleComposerKeyDown}
            />
            <button
              type="submit"
              disabled={loading || sending || !message.trim() || Boolean(tripId && !trip)}
              className="button-primary px-3"
            >
              {sending ? (
                <LoaderCircle aria-hidden="true" className="animate-spin" size={15} />
              ) : (
                <Send aria-hidden="true" size={15} />
              )}
              <span className="sr-only">Send message</span>
            </button>
          </form>
          <button type="button" disabled className="button-secondary w-full">
            <RefreshCw aria-hidden="true" size={15} />
            Create plan
          </button>
        </div>
      </section>

      <section
        aria-labelledby="guide-heading"
        className="h-full min-h-0 min-w-0 overflow-y-auto bg-page p-5"
      >
        <div className="mb-4 flex items-center justify-between gap-3">
          <div>
            <h2 id="guide-heading" className="text-xl font-semibold text-ink">
              Guide
            </h2>
            <p className="mt-0.5 text-sm text-gray-500">
              Your verified itinerary will appear here.
            </p>
          </div>
          <span className="rounded-full border border-brand/20 bg-brand/10 px-2.5 py-1 text-xs font-medium text-brand">
            Not created
          </span>
        </div>

        <div className="panel flex min-h-[calc(100%_-_4.5rem)] items-center justify-center border-dashed p-8 text-center">
          <div className="max-w-sm">
            <span className="mx-auto grid size-12 place-items-center rounded-xl bg-brand/10 text-brand">
              <MapPinned aria-hidden="true" size={22} />
            </span>
            <h3 className="mt-4 text-sm font-semibold text-ink">
              Your trip starts with a conversation
            </h3>
            <p className="mt-1.5 text-sm leading-6 text-gray-500">
              Share your destination, dates, and preferences in chat. Your daily
              itinerary, map, and travel notes will live in this Guide.
            </p>
            <div className="mt-4 inline-flex items-center gap-1.5 text-xs font-medium text-brand">
              <Compass aria-hidden="true" size={14} />
              Ready when you are
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
