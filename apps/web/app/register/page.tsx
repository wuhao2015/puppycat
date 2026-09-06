"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { useAuth } from "../../lib/auth";

export default function RegisterPage() {
  const router = useRouter();
  const { user, loading: authLoading, register } = useAuth();
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [signupCode, setSignupCode] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!authLoading && user) {
      router.replace("/");
    }
  }, [authLoading, router, user]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await register({
        email,
        password,
        signup_code: signupCode,
        ...(displayName.trim() ? { display_name: displayName.trim() } : {}),
      });
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to create account",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="grid min-h-screen place-items-center bg-page px-5 py-10">
      <div className="w-full max-w-sm">
        <Link
          href="/"
          className="mb-6 flex items-center justify-center gap-2 font-semibold text-brand"
        >
          <span aria-hidden="true" className="text-2xl">
            🐾
          </span>
          Puppycat Travel
        </Link>

        <div className="panel p-6">
          <div className="mb-6">
            <h1 className="text-2xl font-semibold text-ink">Create account</h1>
            <p className="mt-1 text-sm leading-5 text-gray-600">
              Registration is invite-only. You&apos;ll need a signup code.
            </p>
          </div>

          <form className="space-y-4" onSubmit={handleSubmit}>
            {error && <div className="notice-error">{error}</div>}

            <div className="space-y-1.5">
              <label className="text-sm font-medium text-ink" htmlFor="display-name">
                Display name{" "}
                <span className="font-normal text-gray-400">(optional)</span>
              </label>
              <input
                id="display-name"
                name="display-name"
                type="text"
                autoComplete="name"
                placeholder="How Puppycat should address you"
                className="form-input"
                maxLength={100}
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-sm font-medium text-ink" htmlFor="register-email">
                Email
              </label>
              <input
                id="register-email"
                name="email"
                type="email"
                autoComplete="email"
                placeholder="you@example.com"
                className="form-input"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-sm font-medium text-ink" htmlFor="register-password">
                Password
              </label>
              <input
                id="register-password"
                name="password"
                type="password"
                autoComplete="new-password"
                placeholder="At least 8 characters"
                className="form-input"
                minLength={8}
                required
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-sm font-medium text-ink" htmlFor="signup-code">
                Signup code
              </label>
              <input
                id="signup-code"
                name="signup-code"
                type="password"
                autoComplete="off"
                placeholder="Enter your invitation code"
                className="form-input"
                required
                value={signupCode}
                onChange={(event) => setSignupCode(event.target.value)}
              />
            </div>

            <button type="submit" disabled={submitting} className="button-primary w-full">
              {submitting ? "Creating account…" : "Create account"}
            </button>
          </form>

          <p className="mt-5 text-center text-sm text-gray-600">
            Already have an account?{" "}
            <Link href="/login" className="font-medium text-brand hover:underline">
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </main>
  );
}
