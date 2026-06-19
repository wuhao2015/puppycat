// Domain types mirroring the backend Pydantic schemas in apps/api/app/schemas.py.
// `npm run gen:types` regenerates a fuller lib/api-types.ts from the live OpenAPI
// schema; these hand-written types keep the app type-safe without a running backend.

export type BusinessStatus =
  | "OPERATIONAL"
  | "CLOSED_TEMPORARILY"
  | "CLOSED_PERMANENTLY"
  | "UNKNOWN";

export type WarningSeverity = "info" | "caution" | "blocker";

export interface GeoPoint {
  lat: number;
  lng: number;
}

export interface Warning {
  severity: WarningSeverity;
  message: string;
  source?: string | null;
  related_item?: string | null;
}

export interface ItineraryItem {
  name: string;
  place_id?: string | null;
  category?: string | null;
  description?: string | null;
  start_time?: string | null;
  end_time?: string | null;
  location?: GeoPoint | null;
  address?: string | null;
  website?: string | null;
  reservation_url?: string | null;
  business_status: BusinessStatus;
  warnings: Warning[];
}

export interface DayWeather {
  date: string;
  summary?: string | null;
  temp_min_c?: number | null;
  temp_max_c?: number | null;
  precipitation_mm?: number | null;
}

export interface ItineraryDay {
  date: string;
  title?: string | null;
  summary?: string | null;
  items: ItineraryItem[];
  weather?: DayWeather | null;
}

export interface Itinerary {
  destination: string;
  start_date: string;
  end_date: string;
  days: ItineraryDay[];
  warnings: Warning[];
  disclaimer: string;
}

export interface ItineraryResponse {
  trip_id: string;
  itinerary_id: string;
  itinerary: Itinerary;
}

export type TripPace = "relaxed" | "balanced" | "packed";

export interface TripRequest {
  destination: string;
  start_date: string;
  end_date: string;
  interests: string[];
  budget?: string | null;
  pace: TripPace;
  travelers: number;
  notes?: string | null;
}

export interface VisaDocument {
  name: string;
  detail?: string | null;
  required: boolean;
}

export interface VisaChecklist {
  passport_country: string;
  destination_country: string;
  visa_required?: boolean | null;
  visa_type?: string | null;
  allowed_stay?: string | null;
  processing_time?: string | null;
  fees?: string | null;
  documents: VisaDocument[];
  steps: string[];
  official_links: string[];
  sources: string[];
  disclaimer: string;
}

export interface VisaRequest {
  passport_country: string;
  destination_country: string;
  purpose: string;
  duration_days: number;
}

export interface ChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
}

export interface AuthUser {
  id: string;
  email: string;
  display_name?: string | null;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: AuthUser;
}

export interface TripSummary {
  trip_id: string;
  destination: string;
  start_date: string;
  end_date: string;
  created_at: string;
  itinerary_id?: string | null;
}
