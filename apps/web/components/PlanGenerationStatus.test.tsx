import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { PlanGeneration } from "../lib/types";
import PlanGenerationStatus from "./PlanGenerationStatus";

function generation(
  overrides: Partial<PlanGeneration> = {},
): PlanGeneration {
  return {
    id: "generation-1",
    trip_id: "trip-1",
    itinerary_id: null,
    input_message_ts: "2026-09-01T00:00:00Z",
    status: "running",
    stage: "understanding",
    step_count: 1,
    tool_call_count: 0,
    clarification_question: null,
    error_code: null,
    error_message: null,
    created_at: "2026-09-01T00:00:00Z",
    started_at: "2026-09-01T00:00:01Z",
    completed_at: null,
    ...overrides,
  };
}

describe("PlanGenerationStatus", () => {
  it.each([
    ["understanding", "Understanding your trip…"],
    ["resolving_destination", "Resolving destinations…"],
    ["searching_places", "Finding places…"],
    ["drafting", "Drafting your itinerary…"],
    ["verifying", "Verifying details…"],
  ] as const)("renders the %s stage", (stage, label) => {
    render(
      <PlanGenerationStatus
        generation={generation({ stage, step_count: 3 })}
        hasClarificationAnswer={false}
      />,
    );

    const status = screen.getByRole("status");
    expect(status.textContent).toContain(label);
    expect(status.textContent).toContain("Planning step 3");
    expect(status.textContent).toContain("switch trips");
  });

  it("renders queued, clarification, and failure feedback", () => {
    const { rerender } = render(
      <PlanGenerationStatus
        generation={generation({ status: "queued", step_count: 0 })}
        hasClarificationAnswer={false}
      />,
    );
    expect(screen.getByRole("status").textContent).toContain(
      "Waiting to start…",
    );

    rerender(
      <PlanGenerationStatus
        generation={generation({
          status: "needs_input",
          clarification_question: "Which Springfield do you mean?",
        })}
        hasClarificationAnswer={false}
      />,
    );
    expect(screen.getByRole("status").textContent).toContain(
      "Which Springfield do you mean?",
    );
    expect(screen.getByRole("status").textContent).toContain("Reply in Chat");

    rerender(
      <PlanGenerationStatus
        generation={generation({
          status: "failed",
          error_message: "Puppycat could not finish planning",
        })}
        hasClarificationAnswer={false}
      />,
    );
    expect(screen.getByRole("alert").textContent).toContain(
      "Puppycat could not finish planning",
    );
  });

  it("renders nothing after success", () => {
    const { container } = render(
      <PlanGenerationStatus
        generation={generation({ status: "succeeded" })}
        hasClarificationAnswer={false}
      />,
    );

    expect(container.childElementCount).toBe(0);
  });
});
