import type {
  AuthUser,
  Itinerary,
  ItineraryResponse,
  TokenResponse,
  TripRequest,
  TripSummary,
  VisaChecklist,
  VisaRequest,
} from "./types";

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8001";
const TOKEN_KEY = "puppycat_token";

/** Raised when the API returns 401; the UI uses this to redirect to /login. */
export class UnauthorizedError extends Error {}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null): void {
  if (typeof window === "undefined") return;
  if (token) window.localStorage.setItem(TOKEN_KEY, token);
  else window.localStorage.removeItem(TOKEN_KEY);
}

function headers(): HeadersInit {
  const h: Record<string, string> = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) h["Authorization"] = `Bearer ${token}`;
  return h;
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
    if (resp.status === 401) throw new UnauthorizedError(detail);
    throw new Error(detail);
  }
  return resp.json() as Promise<T>;
}

// --- Auth -------------------------------------------------------------------

export async function register(payload: {
  email: string;
  password: string;
  display_name?: string;
  signup_code: string;
}): Promise<TokenResponse> {
  const resp = await fetch(`${BASE_URL}/api/auth/register`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(payload),
  });
  return handle<TokenResponse>(resp);
}

export async function login(email: string, password: string): Promise<TokenResponse> {
  const resp = await fetch(`${BASE_URL}/api/auth/login`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ email, password }),
  });
  return handle<TokenResponse>(resp);
}

export async function getMe(): Promise<AuthUser> {
  const resp = await fetch(`${BASE_URL}/api/auth/me`, { headers: headers() });
  return handle<AuthUser>(resp);
}

export async function listTrips(): Promise<TripSummary[]> {
  const resp = await fetch(`${BASE_URL}/api/trips`, { headers: headers() });
  return handle<TripSummary[]>(resp);
}

export async function getItinerary(itineraryId: string): Promise<ItineraryResponse> {
  const resp = await fetch(`${BASE_URL}/api/itineraries/${itineraryId}`, {
    headers: headers(),
  });
  return handle<ItineraryResponse>(resp);
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
  if (resp.status === 401) throw new UnauthorizedError("Please sign in to chat.");
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
