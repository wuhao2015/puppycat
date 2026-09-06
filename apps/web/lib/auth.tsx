"use client";

import { useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import {
  ApiError,
  apiRequest,
  getMe,
  login as loginRequest,
  register as registerRequest,
  updateProfile as updateProfileRequest,
} from "./api";
import type { ProfileInput, RegisterInput, User } from "./types";

const TOKEN_KEY = "puppycat_access_token";

type AuthContextValue = {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (input: RegisterInput) => Promise<void>;
  updateProfile: (input: ProfileInput) => Promise<void>;
  request: <T>(path: string, init?: RequestInit) => Promise<T>;
  signOut: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const clearSession = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    setToken(null);
    setUser(null);
  }, []);

  useEffect(() => {
    const savedToken = localStorage.getItem(TOKEN_KEY);
    if (!savedToken) {
      setLoading(false);
      return;
    }

    getMe(savedToken)
      .then((currentUser) => {
        setToken(savedToken);
        setUser(currentUser);
      })
      .catch(() => {
        clearSession();
      })
      .finally(() => {
        setLoading(false);
      });
  }, [clearSession]);

  const saveSession = useCallback(
    (accessToken: string, currentUser: User) => {
      localStorage.setItem(TOKEN_KEY, accessToken);
      setToken(accessToken);
      setUser(currentUser);
      router.replace("/");
    },
    [router],
  );

  const login = useCallback(
    async (email: string, password: string) => {
      const response = await loginRequest(email, password);
      saveSession(response.access_token, response.user);
    },
    [saveSession],
  );

  const register = useCallback(
    async (input: RegisterInput) => {
      const response = await registerRequest(input);
      saveSession(response.access_token, response.user);
    },
    [saveSession],
  );

  const handleUnauthorized = useCallback(
    (error: unknown) => {
      if (error instanceof ApiError && error.status === 401) {
        clearSession();
        router.replace("/login");
      }
    },
    [clearSession, router],
  );

  const request = useCallback(
    async <T,>(path: string, init?: RequestInit): Promise<T> => {
      if (!token) {
        clearSession();
        router.replace("/login");
        throw new ApiError(401, "Authentication required");
      }

      try {
        return await apiRequest<T>(path, init, token);
      } catch (error) {
        handleUnauthorized(error);
        throw error;
      }
    },
    [clearSession, handleUnauthorized, router, token],
  );

  const updateProfile = useCallback(
    async (input: ProfileInput) => {
      if (!token) {
        clearSession();
        router.replace("/login");
        throw new ApiError(401, "Authentication required");
      }

      try {
        setUser(await updateProfileRequest(token, input));
      } catch (error) {
        handleUnauthorized(error);
        throw error;
      }
    },
    [clearSession, handleUnauthorized, router, token],
  );

  const signOut = useCallback(() => {
    clearSession();
    router.replace("/login");
  }, [clearSession, router]);

  const value = useMemo(
    () => ({ user, loading, login, register, updateProfile, request, signOut }),
    [loading, login, register, request, signOut, updateProfile, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (context === null) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return context;
}
