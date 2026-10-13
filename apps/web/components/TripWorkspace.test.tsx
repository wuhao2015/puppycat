import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type {
  ItineraryResponse,
  PlanGeneration,
  Trip,
} from "../lib/types";
import TripWorkspace from "./TripWorkspace";

const mocks = vi.hoisted(() => ({
  createTrip: vi.fn(),
  getTrip: vi.fn(),
  planTrip: vi.fn(),
  routerReplace: vi.fn(),
  streamMessage: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mocks.routerReplace }),
}));

vi.mock("../lib/trips", () => ({
  useTrips: () => ({
    trips: [
      {
        id: "trip-1",
        title: "Japan",
        destination: "Tokyo",
        start_date: "2026-09-20",
        end_date: "2026-09-20",
        created_at: "2026-09-01T00:00:00Z",
        updated_at: "2026-09-01T00:00:00Z",
      },
    ],
    createTrip: mocks.createTrip,
    getTrip: mocks.getTrip,
    planTrip: mocks.planTrip,
    streamMessage: mocks.streamMessage,
  }),
}));

vi.mock("./TripGuide", () => ({
  default: () => <div>Rendered itinerary</div>,
}));

vi.mock("./VisaChecklistPanel", () => ({
  default: () => <div>Visa checklist</div>,
}));

function generation(
  status: PlanGeneration["status"],
  overrides: Partial<PlanGeneration> = {},
): PlanGeneration {
  return {
    id: "generation-1",
    trip_id: "trip-1",
    itinerary_id: status === "succeeded" ? "itinerary-1" : null,
    input_message_ts: "2026-09-01T00:00:00Z",
    status,
    stage: status === "succeeded" ? "verifying" : "understanding",
    step_count: 0,
    tool_call_count: 0,
    clarification_question: null,
    error_code: null,
    error_message: null,
    created_at: "2026-09-01T00:00:00Z",
    started_at: status === "queued" ? null : "2026-09-01T00:00:01Z",
    completed_at:
      status === "succeeded" || status === "failed" || status === "needs_input"
        ? "2026-09-01T00:00:02Z"
        : null,
    ...overrides,
  };
}

const itinerary: ItineraryResponse = {
  id: "itinerary-1",
  trip_id: "trip-1",
  created_at: "2026-09-01T00:00:02Z",
  data: {
    destination: "Tokyo",
    start_date: "2026-09-20",
    end_date: "2026-09-20",
    days: [],
    warnings: [],
    verification_status: "verified",
    verified_sources: [],
    unavailable_sources: [],
  },
};

function trip(
  planGeneration: PlanGeneration,
  latestItinerary: ItineraryResponse | null = null,
): Trip {
  return {
    id: "trip-1",
    title: "Japan",
    destination: "Tokyo",
    start_date: "2026-09-20",
    end_date: "2026-09-20",
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
    preferences: {},
    chat_messages: [
      {
        role: "user",
        content: "Plan Tokyo.",
        ts: "2026-09-01T00:00:00Z",
      },
    ],
    latest_itinerary: latestItinerary,
    plan_generation: planGeneration,
  };
}

async function renderLoadedTrip(initialTrip: Trip) {
  mocks.getTrip.mockResolvedValueOnce(initialTrip);
  const rendered = render(<TripWorkspace tripId="trip-1" />);
  await act(async () => {
    await Promise.resolve();
  });
  return rendered;
}

describe("TripWorkspace plan generation", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-09-02T00:00:00Z"));
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("polls queued and running stages, then refreshes the succeeded guide", async () => {
    const queued = trip(generation("queued"));
    const running = trip(
      generation("running", { stage: "searching_places", step_count: 2 }),
    );
    const succeeded = trip(generation("succeeded", { step_count: 3 }), itinerary);
    mocks.getTrip
      .mockResolvedValueOnce(queued)
      .mockResolvedValueOnce(running)
      .mockResolvedValueOnce(succeeded);

    render(<TripWorkspace tripId="trip-1" />);
    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.getByText("Waiting to start…")).toBeDefined();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2_000);
    });
    expect(screen.getByText("Finding places…")).toBeDefined();
    expect(screen.getByText(/Planning step 2/)).toBeDefined();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2_000);
    });
    expect(screen.getByText("Rendered itinerary")).toBeDefined();
    expect(screen.getByText("Verified")).toBeDefined();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(4_000);
    });
    expect(mocks.getTrip).toHaveBeenCalledTimes(3);
  });

  it("stops for clarification and continues only after a Chat answer", async () => {
    const needsInput = trip(
      generation("needs_input", {
        clarification_question: "Which Springfield do you mean?",
      }),
    );
    const queued = generation("queued", {
      id: "generation-2",
      input_message_ts: "2026-09-02T00:00:00Z",
    });
    mocks.streamMessage.mockResolvedValue({
      message: {
        role: "assistant",
        content: "Thanks, I have that.",
        ts: "2026-09-02T00:00:01Z",
      },
      trip_updated_at: "2026-09-02T00:00:01Z",
    });
    mocks.planTrip.mockResolvedValue(queued);

    await renderLoadedTrip(needsInput);
    expect(screen.getAllByText("Which Springfield do you mean?").length).toBe(2);
    const blocked = screen.getByRole("button", {
      name: "Answer in chat to continue",
    }) as HTMLButtonElement;
    expect(blocked.disabled).toBe(true);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(6_000);
    });
    expect(mocks.getTrip).toHaveBeenCalledTimes(1);

    fireEvent.change(screen.getByLabelText("Trip message"), {
      target: { value: "Springfield, Illinois." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));
    await act(async () => {
      await Promise.resolve();
    });

    const continueButton = screen.getByRole("button", {
      name: "Continue planning",
    }) as HTMLButtonElement;
    expect(continueButton.disabled).toBe(false);
    fireEvent.click(continueButton);
    await act(async () => {
      await Promise.resolve();
    });

    expect(mocks.planTrip).toHaveBeenCalledWith("trip-1");
    expect(screen.getByText("Waiting to start…")).toBeDefined();
  });

  it("shows public failures without polling terminal generations", async () => {
    const failed = trip(
      generation("failed", {
        error_code: "agent_execution_limit",
        error_message: "Puppycat could not finish planning within the safety limits",
      }),
    );

    await renderLoadedTrip(failed);
    expect(screen.getAllByText("Planning stopped").length).toBe(2);
    expect(
      screen.getAllByText(
        "Puppycat could not finish planning within the safety limits",
      ).length,
    ).toBe(2);
    expect(screen.getByRole("button", { name: "Try planning again" })).toBeDefined();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(6_000);
    });
    expect(mocks.getTrip).toHaveBeenCalledTimes(1);
  });

  it("cleans up page polling without cancelling the background job", async () => {
    const queued = trip(generation("queued"));
    const { unmount } = await renderLoadedTrip(queued);

    unmount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(4_000);
    });

    expect(mocks.getTrip).toHaveBeenCalledTimes(1);
    expect(mocks.planTrip).not.toHaveBeenCalled();
  });
});
