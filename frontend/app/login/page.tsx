"use client";

import { BookOpen, LogIn } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { ApiError, api } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await api.login(identifier.trim(), password);
      await api.currentUser();
      router.replace("/");
      router.refresh();
    } catch (cause) {
      setError(
        cause instanceof ApiError
          ? cause.message
          : "Sign in could not be completed. Please try again.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="grid min-h-screen place-items-center bg-stone-100 p-4 dark:bg-stone-950">
      <section
        className="w-full max-w-md rounded-2xl border border-stone-200 bg-white p-6 shadow-sm dark:border-stone-800 dark:bg-stone-900 sm:p-8"
        aria-labelledby="login-heading"
      >
        <div className="mb-7 flex items-center gap-3">
          <span className="grid size-11 place-items-center rounded-xl bg-amber-400 text-emerald-950">
            <BookOpen aria-hidden="true" />
          </span>
          <div>
            <p className="font-serif text-lg font-bold">ResearchHub Ethiopia</p>
            <p className="text-xs text-stone-500">
              Enterprise prototype access
            </p>
          </div>
        </div>
        <h1 id="login-heading" className="font-serif text-3xl font-bold">
          Sign in
        </h1>
        <p className="mt-2 text-sm text-stone-600 dark:text-stone-300">
          Use an account provisioned by your platform or university
          administrator.
        </p>
        <form className="mt-7 space-y-5" onSubmit={submit}>
          <div>
            <label
              htmlFor="identifier"
              className="mb-1.5 block text-sm font-medium"
            >
              Email or username
            </label>
            <input
              id="identifier"
              name="identifier"
              autoComplete="username"
              required
              value={identifier}
              onChange={(event) => setIdentifier(event.target.value)}
              className="w-full rounded-xl border border-stone-300 bg-transparent px-3 py-2.5 outline-none focus:border-emerald-700 focus:ring-2 focus:ring-emerald-700/20 dark:border-stone-700"
            />
          </div>
          <div>
            <label
              htmlFor="password"
              className="mb-1.5 block text-sm font-medium"
            >
              Password
            </label>
            <input
              id="password"
              name="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="w-full rounded-xl border border-stone-300 bg-transparent px-3 py-2.5 outline-none focus:border-emerald-700 focus:ring-2 focus:ring-emerald-700/20 dark:border-stone-700"
            />
          </div>
          {error ? (
            <p
              role="alert"
              className="rounded-xl bg-red-50 p-3 text-sm text-red-800 dark:bg-red-950/40 dark:text-red-200"
            >
              {error}
            </p>
          ) : null}
          <button
            type="submit"
            disabled={submitting}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-800 px-4 py-3 font-semibold text-white hover:bg-emerald-700 disabled:cursor-wait disabled:opacity-60"
          >
            <LogIn size={18} aria-hidden="true" />
            {submitting ? "Signing in…" : "Sign in"}
          </button>
        </form>
        <p className="mt-6 text-xs text-stone-500">
          Sessions are stored only in this browser tab. Contact an administrator
          if you need access; no default password is embedded in the
          application.
        </p>
      </section>
    </main>
  );
}
