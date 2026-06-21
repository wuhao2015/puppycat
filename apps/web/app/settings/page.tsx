"use client";

import { useEffect, useState } from "react";
import { Check, X } from "lucide-react";
import { updateProfile } from "@/lib/api";
import { useAuth } from "@/lib/auth";

// A small, common set; users can add any other ISO code by hand.
const COMMON_COUNTRIES: { code: string; name: string }[] = [
  { code: "US", name: "United States" },
  { code: "GB", name: "United Kingdom" },
  { code: "CA", name: "Canada" },
  { code: "AU", name: "Australia" },
  { code: "CN", name: "China" },
  { code: "IN", name: "India" },
  { code: "JP", name: "Japan" },
  { code: "DE", name: "Germany" },
  { code: "FR", name: "France" },
  { code: "SG", name: "Singapore" },
];

export default function SettingsPage() {
  const { user, setUser } = useAuth();
  const [passports, setPassports] = useState<string[]>([]);
  const [custom, setCustom] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (user) setPassports(user.passport_countries ?? []);
  }, [user]);

  function toggle(code: string) {
    setSaved(false);
    setPassports((prev) =>
      prev.includes(code) ? prev.filter((c) => c !== code) : [...prev, code],
    );
  }

  function addCustom() {
    const code = custom.trim().toUpperCase();
    if (code && !passports.includes(code)) setPassports((p) => [...p, code]);
    setCustom("");
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const updated = await updateProfile({ passport_countries: passports });
      setUser(updated);
      setSaved(true);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6 p-8">
      <div>
        <h1 className="text-2xl font-semibold">Profile</h1>
        <p className="text-sm text-gray-600">
          Tell Puppycat which passports you hold. We use this to attach basic visa
          reminders to each trip.
        </p>
      </div>

      <div className="space-y-3 rounded-xl border border-gray-200 bg-white p-5">
        <p className="text-sm font-medium">Passports / nationalities</p>

        <div className="flex flex-wrap gap-2">
          {COMMON_COUNTRIES.map((c) => {
            const on = passports.includes(c.code);
            return (
              <button
                key={c.code}
                type="button"
                onClick={() => toggle(c.code)}
                className={`flex items-center gap-1 rounded-full border px-3 py-1 text-sm ${
                  on
                    ? "border-brand bg-brand/10 text-brand"
                    : "border-gray-300 text-gray-700 hover:bg-gray-50"
                }`}
              >
                {on && <Check size={13} />} {c.name} ({c.code})
              </button>
            );
          })}
        </div>

        {/* Any custom/extra codes the user added that aren't in the common list */}
        {passports.filter((p) => !COMMON_COUNTRIES.some((c) => c.code === p)).length >
          0 && (
          <div className="flex flex-wrap gap-2 pt-1">
            {passports
              .filter((p) => !COMMON_COUNTRIES.some((c) => c.code === p))
              .map((code) => (
                <span
                  key={code}
                  className="flex items-center gap-1 rounded-full border border-brand bg-brand/10 px-3 py-1 text-sm text-brand"
                >
                  {code}
                  <button type="button" onClick={() => toggle(code)} aria-label="Remove">
                    <X size={13} />
                  </button>
                </span>
              ))}
          </div>
        )}

        <div className="flex items-center gap-2 pt-2">
          <input
            value={custom}
            onChange={(e) => setCustom(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                addCustom();
              }
            }}
            placeholder="Add ISO code, e.g. NZ"
            className="w-40 rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-brand"
          />
          <button
            type="button"
            onClick={addCustom}
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50"
          >
            Add
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={save}
          disabled={saving}
          className="rounded-lg bg-brand px-4 py-2 text-sm font-medium text-brand-fg disabled:opacity-50"
        >
          {saving ? "Saving…" : "Save"}
        </button>
        {saved && <span className="text-sm text-green-600">Saved.</span>}
      </div>
    </div>
  );
}
