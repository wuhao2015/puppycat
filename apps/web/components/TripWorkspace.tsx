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
import type { ChatMessage, Trip } from "../lib/types";
import TripGuide from "./TripGuide";

type TripWorkspaceProps = {
  tripId?: string;
};

export default function TripWorkspace({ tripId }: TripWorkspaceProps) {
  const router = useRouter();
  const { trips, createTrip, getTrip, planTrip, streamMessage } = useTrips();
  const [trip, setTrip] = useState<Trip | null>(null);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(Boolean(tripId));
  const [sending, setSending] = useState(false);
  const [startingPlan, setStartingPlan] = useState(false);
  const [planningError, setPlanningError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const sendingRef = useRef(false);
  const streamControllerRef = useRef<AbortController | null>(null);
  const displayTitle =
    (tripId ? trips.find((item) => item.id === tripId)?.title : null) ??
    trip?.title ??
    "New trip";
  const planGeneration = trip?.plan_generation ?? null;
  const generationActive =
    planGeneration?.status === "queued" || planGeneration?.status === "running";
  const planning = startingPlan || generationActive;

  useEffect(() => {
    if (!tripId) {
      setTrip(null);
      setLoading(false);
      setError(null);
      setPlanningError(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);
    setPlanningError(null);
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
  }, [trip?.chat_messages.at(-1)?.content]);

  useEffect(
    () => () => {
      streamControllerRef.current?.abort();
    },
    [tripId],
  );

  useEffect(() => {
    if (planGeneration?.status === "failed") {
      setPlanningError(
        planGeneration.error_message ?? "Unable to create itinerary",
      );
    } else if (planGeneration?.status === "succeeded") {
      setPlanningError(null);
    }
  }, [planGeneration?.error_message, planGeneration?.status]);

  useEffect(() => {
    if (!tripId || !generationActive) {
      return;
    }

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const poll = async () => {
      try {
        const updatedTrip = await getTrip(tripId);
        if (cancelled) {
          return;
        }
        if (updatedTrip.plan_generation?.status === "failed") {
          setPlanningError(
            updatedTrip.plan_generation.error_message ??
              "Unable to create itinerary",
          );
        } else if (updatedTrip.plan_generation?.status === "succeeded") {
          setPlanningError(null);
        }
        setTrip(updatedTrip);
        const stillActive =
          updatedTrip.plan_generation?.status === "queued" ||
          updatedTrip.plan_generation?.status === "running";
        if (stillActive) {
          timer = setTimeout(poll, 2_000);
        }
      } catch {
        if (!cancelled) {
          timer = setTimeout(poll, 4_000);
        }
      }
    };

    timer = setTimeout(poll, 2_000);
    return () => {
      cancelled = true;
      if (timer !== undefined) {
        clearTimeout(timer);
      }
    };
  }, [generationActive, getTrip, planGeneration?.id, tripId]);

  async function sendMessage(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    const content = message.trim();
    if (!content || sendingRef.current) {
      return;
    }

    sendingRef.current = true;
    setSending(true);
    setError(null);
    let currentTrip = trip;
    let createdTrip: Trip | null = null;
    let pendingAssistantTimestamp: string | null = null;
    let controller: AbortController | null = null;

    try {
      if (!currentTrip) {
        createdTrip = await createTrip();
        currentTrip = createdTrip;
        setTrip(createdTrip);
      }
      const activeTripId = currentTrip.id;

      const userMessage: ChatMessage = {
        role: "user",
        content,
        ts: new Date().toISOString(),
      };
      pendingAssistantTimestamp = `pending-${Date.now()}`;
      const pendingAssistant: ChatMessage = {
        role: "assistant",
        content: "",
        ts: pendingAssistantTimestamp,
      };
      setTrip({
        ...currentTrip,
        chat_messages: [
          ...currentTrip.chat_messages,
          userMessage,
          pendingAssistant,
        ],
      });
      setMessage("");

      controller = new AbortController();
      streamControllerRef.current = controller;
      const response = await streamMessage(
        activeTripId,
        content,
        (chunk) => {
          setTrip((activeTrip) => {
            if (!activeTrip || activeTrip.id !== activeTripId) {
              return activeTrip;
            }
            return {
              ...activeTrip,
              chat_messages: activeTrip.chat_messages.map((chatMessage) =>
                chatMessage.ts === pendingAssistantTimestamp
                  ? { ...chatMessage, content: chatMessage.content + chunk }
                  : chatMessage,
              ),
            };
          });
        },
        controller.signal,
      );
      setTrip((activeTrip) => {
        if (!activeTrip || activeTrip.id !== activeTripId) {
          return activeTrip;
        }
        return {
          ...activeTrip,
          chat_messages: activeTrip.chat_messages.map((chatMessage) =>
            chatMessage.ts === pendingAssistantTimestamp
              ? response.message
              : chatMessage,
          ),
          updated_at: response.trip_updated_at,
        };
      });

      if (createdTrip) {
        router.replace(`/trips/${createdTrip.id}`);
      }
    } catch (requestError) {
      if (pendingAssistantTimestamp) {
        setTrip((activeTrip) => {
          if (!activeTrip) {
            return activeTrip;
          }
          return {
            ...activeTrip,
            chat_messages: activeTrip.chat_messages.filter(
              (chatMessage) => chatMessage.ts !== pendingAssistantTimestamp,
            ),
          };
        });
      }
      if (createdTrip) {
        router.replace(`/trips/${createdTrip.id}`);
      }
      if (!controller?.signal.aborted) {
        setError(
          requestError instanceof Error
            ? requestError.message
            : "Unable to send message",
        );
      }
    } finally {
      if (streamControllerRef.current === controller) {
        streamControllerRef.current = null;
      }
      sendingRef.current = false;
      setSending(false);
    }
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  }

  async function createOrUpdatePlan() {
    if (!trip || planning) {
      return;
    }
    setStartingPlan(true);
    setPlanningError(null);
    try {
      const activeTripId = trip.id;
      const generation = await planTrip(activeTripId);
      setTrip((currentTrip) =>
        currentTrip?.id === activeTripId
          ? { ...currentTrip, plan_generation: generation }
          : currentTrip,
      );
    } catch (requestError) {
      setPlanningError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to create itinerary",
      );
    } finally {
      setStartingPlan(false);
    }
  }

  const itinerary = trip?.latest_itinerary?.data ?? null;

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
                  {chatMessage.content ||
                  (sending && index === trip.chat_messages.length - 1 ? (
                    <span className="loading-dots" aria-label="Puppycat is replying">
                      <span>●</span>
                      <span>●</span>
                      <span>●</span>
                    </span>
                  ) : null)}
                </div>
              </div>
            ))}

          <div ref={messagesEndRef} />
        </div>

        <div className="space-y-2 border-t border-line p-3">
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
          {planningError && <div className="notice-error">{planningError}</div>}
          <button
            type="button"
            disabled={
              loading ||
              sending ||
              planning ||
              !trip ||
              !trip.chat_messages.some((chatMessage) => chatMessage.role === "user")
            }
            className="button-secondary w-full"
            onClick={createOrUpdatePlan}
          >
            <RefreshCw
              aria-hidden="true"
              className={planning ? "animate-spin" : undefined}
              size={15}
            />
            {planning
              ? "Planning…"
              : itinerary
                ? "Update plan"
                : "Create plan"}
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
            {planning
              ? "Creating"
              : itinerary
              ? itinerary.verification_status === "verified"
                ? "Verified"
                : itinerary.verification_status === "partial"
                  ? "Partially verified"
                  : "Verification unavailable"
              : "Not created"}
          </span>
        </div>

        {planning && (
          <div
            className="mb-4 rounded-xl border border-brand/20 bg-brand/10 px-4 py-3 text-brand"
            role="status"
          >
            <p className="text-sm font-semibold">
              ✨ Creating your travel plan…
            </p>
            <p className="mt-1 text-sm">This may take a little while.</p>
          </div>
        )}

        {itinerary ? (
          <TripGuide itinerary={itinerary} />
        ) : planning ? (
          <div className="panel flex min-h-[calc(100%_-_9.5rem)] items-center justify-center border-dashed p-8 text-center">
            <div className="max-w-sm">
              <LoaderCircle
                aria-hidden="true"
                className="mx-auto animate-spin text-brand"
                size={24}
              />
              <p className="mt-4 text-sm leading-6 text-gray-500">
                We’ll refresh this guide automatically when it’s ready. You can
                safely leave this page.
              </p>
            </div>
          </div>
        ) : (
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
        )}
      </section>
    </div>
  );
}
