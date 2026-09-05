import Link from "next/link";

export default function LoginPage() {
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
            <h1 className="text-2xl font-semibold text-ink">Sign in</h1>
            <p className="mt-1 text-sm text-gray-600">
              Welcome back to Puppycat Travel.
            </p>
          </div>

          <form className="space-y-4">
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-ink" htmlFor="email">
                Email
              </label>
              <input
                id="email"
                name="email"
                type="email"
                autoComplete="email"
                placeholder="you@example.com"
                className="form-input"
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-sm font-medium text-ink" htmlFor="password">
                Password
              </label>
              <input
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                placeholder="Enter your password"
                className="form-input"
              />
            </div>

            <button type="button" className="button-primary w-full">
              Sign in
            </button>
          </form>

          <p className="mt-5 text-center text-sm text-gray-600">
            Need an account?{" "}
            <Link href="/register" className="font-medium text-brand hover:underline">
              Register
            </Link>
          </p>
        </div>
      </div>
    </main>
  );
}
