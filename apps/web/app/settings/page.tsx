import AppShell from "../../components/AppShell";

const PASSPORTS = [
  { code: "CN", name: "China" },
  { code: "US", name: "United States" },
  { code: "GB", name: "United Kingdom" },
  { code: "CA", name: "Canada" },
  { code: "AU", name: "Australia" },
  { code: "JP", name: "Japan" },
];

export default function SettingsPage() {
  return (
    <AppShell activePage="settings">
      <div className="h-full overflow-y-auto p-5 md:p-8">
        <div className="mx-auto max-w-2xl space-y-6">
          <div>
            <h1 className="text-2xl font-semibold text-ink">Profile</h1>
            <p className="mt-1 text-sm leading-6 text-gray-600">
              Add the name Puppycat should use and the passports you hold.
            </p>
          </div>

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
              />
            </div>
          </section>

          <section aria-labelledby="passport-details" className="panel p-5">
            <div>
              <h2 id="passport-details" className="text-sm font-semibold text-ink">
                Passports / nationalities
              </h2>
              <p className="mt-1 text-xs leading-5 text-gray-500">
                This will later help Puppycat show the relevant visa checklist for a trip.
              </p>
            </div>

            <div className="mt-4 flex flex-wrap gap-2">
              {PASSPORTS.map((passport) => (
                <label key={passport.code} className="cursor-pointer">
                  <input
                    type="checkbox"
                    name="passport"
                    value={passport.code}
                    className="peer sr-only"
                  />
                  <span className="flex items-center gap-1.5 rounded-full border border-gray-300 px-3 py-1.5 text-sm text-gray-700 transition-colors hover:bg-gray-50 peer-checked:border-brand peer-checked:bg-brand/10 peer-checked:text-brand">
                    {passport.name} ({passport.code})
                  </span>
                </label>
              ))}
            </div>

            <div className="mt-4 max-w-xs space-y-1.5">
              <label className="text-sm font-medium text-ink" htmlFor="other-passport">
                Another country code
              </label>
              <input
                id="other-passport"
                name="other-passport"
                type="text"
                placeholder="For example, NZ"
                className="form-input"
              />
            </div>
          </section>

          <div className="flex items-center gap-3">
            <button type="button" className="button-primary">
              Save profile
            </button>
            <span className="text-xs text-gray-400">Changes are not connected yet.</span>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
