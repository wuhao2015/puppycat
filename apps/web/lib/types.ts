export type User = {
  id: string;
  email: string;
  display_name: string | null;
  passport_countries: string[];
  created_at: string;
};

export type AuthResponse = {
  access_token: string;
  token_type: "bearer";
  user: User;
};

export type RegisterInput = {
  email: string;
  password: string;
  signup_code: string;
  display_name?: string;
};

export type ProfileInput = {
  display_name: string | null;
  passport_countries: string[];
};

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  ts: string;
};

export type PlaceCoordinate = {
  latitude: number;
  longitude: number;
};

export type Place = {
  place_id: string;
  name: string;
  address: string | null;
  location: PlaceCoordinate | null;
  google_maps_uri: string | null;
  website_uri: string | null;
  business_status: string | null;
  types: string[];
  primary_type: string | null;
  country_code: string | null;
  opening_hours: {
    periods: {
      opens_at: { day: number; hour: number; minute: number };
      closes_at: { day: number; hour: number; minute: number } | null;
    }[];
    weekday_descriptions: string[];
  } | null;
};

export type ItineraryWarning = {
  level: "caution" | "blocker";
  code: string;
  message: string;
  source: "google_places" | "open_meteo" | "tavily" | null;
  item_id: string | null;
  source_url: string | null;
};

export type ItineraryItem = {
  id: string;
  start_time: string;
  end_time: string;
  title: string;
  description: string;
  kind: "place" | "generic";
  place_id: string | null;
  place: Place | null;
  warnings: ItineraryWarning[];
};

export type ItineraryDay = {
  date: string;
  title: string;
  accommodation: string | null;
  items: ItineraryItem[];
};

export type DailyWeather = {
  date: string;
  weather_code: number | null;
  summary: string;
  temperature_max_c: number | null;
  temperature_min_c: number | null;
  precipitation_probability_max: number | null;
  precipitation_sum_mm: number | null;
  wind_speed_max_kmh: number | null;
};

export type Itinerary = {
  destination: string;
  destination_location: PlaceCoordinate | null;
  start_date: string;
  end_date: string;
  days: ItineraryDay[];
  weather: DailyWeather[];
  warnings: ItineraryWarning[];
  verification_status: "verified" | "partial" | "unavailable";
  verified_sources: string[];
  unavailable_sources: string[];
};

export type ItineraryResponse = {
  id: string;
  trip_id: string;
  data: Itinerary;
  created_at: string;
};

export type PlanGeneration = {
  id: string;
  trip_id: string;
  itinerary_id: string | null;
  input_message_ts: string;
  status: "queued" | "running" | "succeeded" | "failed";
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
};

export type TripListItem = {
  id: string;
  title: string | null;
  destination: string | null;
  start_date: string | null;
  end_date: string | null;
  created_at: string;
  updated_at: string;
};

export type Trip = TripListItem & {
  preferences: {
    interests?: string[];
    budget?: string;
    pace?: string;
    travelers?: number;
    notes?: string;
  };
  chat_messages: ChatMessage[];
  latest_itinerary: ItineraryResponse | null;
  plan_generation: PlanGeneration | null;
};

export type ChatStreamResult = {
  message: ChatMessage;
  trip_updated_at: string;
};
