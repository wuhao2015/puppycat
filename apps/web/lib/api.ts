import type {
  Itinerary,
  ItineraryResponse,
  TripRequest,
  VisaChecklist,
  VisaRequest,
} from "./types";

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const API_KEY = process.env.NEXT_PUBLIC_API_KEY ?? "dev-local-key";

function headers(): HeadersInit {
  return { "Content-Type": "application/json", "X-API-Key": API_KEY };
}

async function handle<T>(resp: Response): Promise<T> {
  if (!resp.ok) {
    let detail = `Request failed (${resp.status})`;
    try {
      const body = await resp.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }
  return resp.json() as Promise<T>;
}

export async function createItinerary(req: TripRequest): Promise<ItineraryResponse> {
  const resp = await fetch(`${BASE_URL}/api/itinerary`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(req),
  });
  return handle<ItineraryResponse>(resp);
}

export async function getVisaChecklist(req: VisaRequest): Promise<VisaChecklist> {
  const resp = await fetch(`${BASE_URL}/api/visa-checklist`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(req),
  });
  return handle<VisaChecklist>(resp);
}

/** Stream chat tokens as plain text chunks. Calls `onChunk` for each delta. */
export async function streamChat(
  messages: { role: string; content: string }[],
  onChunk: (text: string) => void,
): Promise<void> {
  const resp = await fetch(`${BASE_URL}/api/chat`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ messages }),
  });
  if (!resp.ok || !resp.body) {
    throw new Error(`Chat failed (${resp.status})`);
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    onChunk(decoder.decode(value, { stream: true }));
  }
}

/** POST a payload to a document endpoint and trigger a PDF download. */
export async function downloadPdf(
  path: "itinerary" | "visa" | "cover-letter",
  payload: Itinerary | VisaChecklist | Record<string, unknown>,
  filename: string,
): Promise<void> {
  const resp = await fetch(`${BASE_URL}/api/documents/${path}`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(payload),
  });
  if (!resp.ok) throw new Error(`Document generation failed (${resp.status})`);
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
