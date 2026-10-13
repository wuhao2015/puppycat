import {
  CircleAlert,
  LoaderCircle,
  MessageCircleQuestion,
} from "lucide-react";

import type { PlanGeneration } from "../lib/types";

export const PLAN_STAGE_LABELS: Record<PlanGeneration["stage"], string> = {
  understanding: "Understanding your trip…",
  resolving_destination: "Resolving destinations…",
  searching_places: "Finding places…",
  drafting: "Drafting your itinerary…",
  verifying: "Verifying details…",
};

type PlanGenerationStatusProps = {
  generation: PlanGeneration;
  hasClarificationAnswer: boolean;
};

export default function PlanGenerationStatus({
  generation,
  hasClarificationAnswer,
}: PlanGenerationStatusProps) {
  if (generation.status === "succeeded") {
    return null;
  }

  if (generation.status === "needs_input") {
    return (
      <div
        className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5 text-amber-950"
        role="status"
      >
        <div className="flex items-start gap-2.5">
          <MessageCircleQuestion
            aria-hidden="true"
            className="mt-0.5 shrink-0 text-amber-600"
            size={16}
          />
          <div className="min-w-0">
            <p className="text-xs font-semibold">
              Puppycat needs more information
            </p>
            <p
              id="plan-clarification-question"
              className="mt-1 text-sm leading-5"
            >
              {generation.clarification_question ??
                "Please add the missing trip details in Chat."}
            </p>
            <p className="mt-1.5 text-xs text-amber-700">
              {hasClarificationAnswer
                ? "Answer received. Select Continue planning when you’re ready."
                : "Reply in Chat, then continue planning."}
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (generation.status === "failed") {
    return (
      <div
        className="rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 text-red-700"
        role="alert"
      >
        <div className="flex items-start gap-2.5">
          <CircleAlert
            aria-hidden="true"
            className="mt-0.5 shrink-0"
            size={16}
          />
          <div className="min-w-0">
            <p className="text-xs font-semibold">Planning stopped</p>
            <p className="mt-1 text-sm leading-5">
              {generation.error_message ?? "Unable to create itinerary"}
            </p>
          </div>
        </div>
      </div>
    );
  }

  const title =
    generation.status === "queued"
      ? "Waiting to start…"
      : PLAN_STAGE_LABELS[generation.stage];

  return (
    <div
      className="rounded-lg border border-brand/20 bg-brand/10 px-3 py-2.5 text-brand"
      role="status"
      aria-live="polite"
    >
      <div className="flex items-start gap-2.5">
        <LoaderCircle
          aria-hidden="true"
          className="mt-0.5 shrink-0 animate-spin"
          size={16}
        />
        <div className="min-w-0">
          <p className="text-sm font-semibold">{title}</p>
          <p className="mt-1 text-xs text-gray-600">
            {generation.status === "queued"
              ? "Your planner is queued."
              : generation.step_count > 0
                ? `Planning step ${generation.step_count}`
                : "Starting the planner…"}
            {" You can safely leave this page or switch trips."}
          </p>
        </div>
      </div>
    </div>
  );
}
