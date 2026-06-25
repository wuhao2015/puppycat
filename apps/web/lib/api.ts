import type {
  AuthUser,
  Itinerary,
  ItineraryResponse,
  ProfileUpdate,
  SummaryItinerary,
  TokenResponse,
  TripDetail,
  TripSummary,
  TripVisaNotices,
} from "./types";

const BASE_URL = "";
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

export async function updateProfile(payload: ProfileUpdate): Promise<AuthUser> {
  const resp = await fetch(`${BASE_URL}/api/auth/profile`, {
    method: "PATCH",
    headers: headers(),
    body: JSON.stringify(payload),
  });
  return handle<AuthUser>(resp);
}

// --- Trip sessions ----------------------------------------------------------

export async function createTrip(): Promise<TripDetail> {
  const resp = await fetch(`${BASE_URL}/api/trips`, {
    method: "POST",
    headers: headers(),
  });
  return handle<TripDetail>(resp);
}

export async function listTrips(): Promise<TripSummary[]> {
  const resp = await fetch(`${BASE_URL}/api/trips`, { headers: headers() });
  return handle<TripSummary[]>(resp);
}

export async function getTrip(tripId: string): Promise<TripDetail> {
  const resp = await fetch(`${BASE_URL}/api/trips/${tripId}`, { headers: headers() });
  return handle<TripDetail>(resp);
}

export async function renameTrip(tripId: string, title: string): Promise<TripSummary> {
  const resp = await fetch(`${BASE_URL}/api/trips/${tripId}`, {
    method: "PATCH",
    headers: headers(),
    body: JSON.stringify({ title }),
  });
  return handle<TripSummary>(resp);
}

export async function deleteTrip(tripId: string): Promise<void> {
  const resp = await fetch(`${BASE_URL}/api/trips/${tripId}`, {
    method: "DELETE",
    headers: headers(),
  });
  await handle<{ status: string }>(resp);
}

export async function updateTripPlan(tripId: string): Promise<ItineraryResponse> {
  const resp = await fetch(`${BASE_URL}/api/trips/${tripId}/plan`, {
    method: "POST",
    headers: headers(),
  });
  return handle<ItineraryResponse>(resp);
}

export async function getTripSummary(tripId: string): Promise<SummaryItinerary> {
  const resp = await fetch(`${BASE_URL}/api/trips/${tripId}/summary`, {
    headers: headers(),
  });
  return handle<SummaryItinerary>(resp);
}

export async function getTripVisaNotice(tripId: string): Promise<TripVisaNotices> {
  const resp = await fetch(`${BASE_URL}/api/trips/${tripId}/visa-notice`, {
    headers: headers(),
  });
  return handle<TripVisaNotices>(resp);
}

/** Stream a chat turn for a trip. Persists both messages server-side. */
export async function sendTripMessage(
  tripId: string,
  content: string,
  onChunk: (text: string) => void,
): Promise<void> {
  const resp = await fetch(`${BASE_URL}/api/trips/${tripId}/chat`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ content }),
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

/** POST an itinerary to the PDF endpoint and trigger a download. */
export async function downloadPdf(
  path: "itinerary" | "visa" | "cover-letter",
  payload: Itinerary | Record<string, unknown>,
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
