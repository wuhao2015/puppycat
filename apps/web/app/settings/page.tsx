"use client";

import { Plus, X } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";

import AppShell from "../../components/AppShell";
import { useAuth } from "../../lib/auth";

const PASSPORTS = [
  { code: "CN", name: "China" },
  { code: "US", name: "United States" },
  { code: "GB", name: "United Kingdom" },
  { code: "CA", name: "Canada" },
  { code: "AU", name: "Australia" },
  { code: "JP", name: "Japan" },
];

export default function SettingsPage() {
  const { user, updateProfile } = useAuth();
  const [displayName, setDisplayName] = useState("");
  const [passportCountries, setPassportCountries] = useState<string[]>([]);
  const [otherPassport, setOtherPassport] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (user) {
      setDisplayName(user.display_name ?? "");
      setPassportCountries(user.passport_countries);
    }
  }, [user]);

  function togglePassport(code: string) {
    setSaved(false);
    setPassportCountries((countries) =>
      countries.includes(code)
        ? countries.filter((country) => country !== code)
        : [...countries, code],
    );
  }

  function addOtherPassport() {
    const code = otherPassport.trim().toUpperCase();
    if (!/^[A-Z]{2}$/.test(code)) {
      setError("Use a two-letter country code, such as NZ.");
      return;
    }
    setError(null);
    setSaved(false);
    setPassportCountries((countries) =>
      countries.includes(code) ? countries : [...countries, code],
    );
    setOtherPassport("");
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    setSaved(false);
    try {
      await updateProfile({
        display_name: displayName.trim() || null,
        passport_countries: passportCountries,
      });
      setSaved(true);
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "Unable to save profile",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AppShell activePage="settings">
      <div className="h-full overflow-y-auto p-5 md:p-8">
        <form className="mx-auto max-w-2xl space-y-6" onSubmit={handleSubmit}>
          <div>
            <h1 className="text-2xl font-semibold text-ink">Profile</h1>
            <p className="mt-1 text-sm leading-6 text-gray-600">
              Add the name Puppycat should use and the passports you hold.
            </p>
          </div>

          {error && <div className="notice-error">{error}</div>}

          <section aria-labelledby="profile-details" className="panel p-5">
            <h2 id="profile-details" className="text-sm font-semibold text-ink">
              Profile details
            </h2>
            <div className="mt-4 space-y-1.5">
              <label className="text-sm font-medium text-ink" htmlFor="profile-name">
                Display name
              </label>
              <input
                id="profile-name"
                name="profile-name"
                type="text"
                autoComplete="name"
                placeholder="Your name"
                className="form-input"
                maxLength={100}
                value={displayName}
                onChange={(event) => {
                  setDisplayName(event.target.value);
                  setSaved(false);
                }}
              />
            </div>
          </section>

          <section aria-labelledby="passport-details" className="panel p-5">
            <div>
              <h2 id="passport-details" className="text-sm font-semibold text-ink">
                Passports / nationalities
              </h2>
              <p className="mt-1 text-xs leading-5 text-gray-500">
                Puppycat uses these to show the relevant visa checklist for a trip.
              </p>
            </div>

            <div className="mt-4 flex flex-wrap gap-2">
              {PASSPORTS.map((passport) => {
                const selected = passportCountries.includes(passport.code);
                return (
                  <button
                    key={passport.code}
                    type="button"
                    aria-pressed={selected}
                    onClick={() => togglePassport(passport.code)}
                    className={`rounded-full border px-3 py-1.5 text-sm transition-colors ${
                      selected
                        ? "border-brand bg-brand/10 text-brand"
                        : "border-gray-300 text-gray-700 hover:bg-gray-50"
                    }`}
                  >
                    {passport.name} ({passport.code})
                  </button>
                );
              })}
            </div>

            <div className="mt-4 max-w-sm space-y-1.5">
              <label className="text-sm font-medium text-ink" htmlFor="other-passport">
                Another country code
              </label>
              <div className="flex gap-2">
                <input
                  id="other-passport"
                  name="other-passport"
                  type="text"
                  inputMode="text"
                  maxLength={2}
                  placeholder="For example, NZ"
                  className="form-input uppercase"
                  value={otherPassport}
                  onChange={(event) => setOtherPassport(event.target.value)}
                />
                <button type="button" className="button-secondary" onClick={addOtherPassport}>
                  <Plus aria-hidden="true" size={15} />
                  Add
                </button>
              </div>
            </div>

            {passportCountries.length > 0 && (
              <div className="mt-4 flex flex-wrap gap-2" aria-label="Selected passports">
                {passportCountries.map((code) => (
                  <button
                    key={code}
                    type="button"
                    onClick={() => togglePassport(code)}
                    className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2.5 py-1 text-xs text-gray-600 hover:text-brand"
                    aria-label={`Remove ${code}`}
                  >
                    {code}
                    <X aria-hidden="true" size={12} />
                  </button>
                ))}
              </div>
            )}
          </section>

          <div className="flex items-center gap-3">
            <button type="submit" disabled={submitting} className="button-primary">
              {submitting ? "Saving…" : "Save profile"}
            </button>
            {saved && <span className="text-xs font-medium text-brand">Profile saved.</span>}
          </div>
        </form>
      </div>
    </AppShell>
  );
}
