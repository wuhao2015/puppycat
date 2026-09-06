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
