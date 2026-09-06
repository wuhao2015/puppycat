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
};

export type ChatDevelopmentResponse = {
  message: ChatMessage;
  trip_updated_at: string;
  assistant_status: "gemini_not_connected";
};
