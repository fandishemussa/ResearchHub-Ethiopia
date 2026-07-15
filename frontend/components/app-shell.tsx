"use client";
import {
  BarChart3,
  BookOpen,
  Building2,
  Database,
  FileSearch,
  Menu,
  Moon,
  Search,
  Bot,
  Sun,
  X,
} from "lucide-react";
import { useTheme } from "next-themes";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";

const links = [
  { href: "/", label: "Dashboard", icon: BarChart3 },
  { href: "/publications", label: "Publications", icon: FileSearch },
  { href: "/documents", label: "Indexed documents", icon: BookOpen },
  { href: "/search/semantic", label: "Semantic search", icon: Search },
  { href: "/ai/assistant", label: "AI research assistant", icon: Bot },
  { href: "/universities", label: "Universities", icon: Building2 },
  { href: "/repositories", label: "Repositories", icon: Database },
];

export function AppShell({ children }: { children: ReactNode }) {
  const path = usePathname();
  const [open, setOpen] = useState(false);
  const { resolvedTheme, setTheme } = useTheme();
  return (
    <div className="min-h-screen bg-stone-50 text-stone-950 dark:bg-stone-950 dark:text-stone-50">
      <a
        href="#main-content"
        className="sr-only z-50 rounded-lg bg-white p-3 text-emerald-900 focus:not-sr-only focus:fixed focus:left-3 focus:top-3"
      >
        Skip to main content
      </a>
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 w-64 border-r border-emerald-950/15 bg-emerald-950 p-5 text-white transition-transform lg:translate-x-0",
          open ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className="mb-10 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-3">
            <span className="grid size-10 place-items-center rounded-xl bg-amber-400 text-emerald-950">
              <BookOpen />
            </span>
            <span className="font-serif text-lg font-bold leading-4">
              ResearchHub
              <small className="mt-1 block font-sans text-[10px] uppercase tracking-[.24em] text-amber-300">
                Ethiopia
              </small>
            </span>
          </Link>
          <button className="lg:hidden" onClick={() => setOpen(false)}>
            <X />
          </button>
        </div>
        <nav className="space-y-1">
          {links.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              onClick={() => setOpen(false)}
              className={cn(
                "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-emerald-100/75 hover:bg-white/10 hover:text-white",
                path === href && "bg-white/12 text-white",
              )}
            >
              <Icon size={18} />
              {label}
            </Link>
          ))}
        </nav>
        <p className="absolute bottom-5 text-xs text-emerald-100/45">
          AI-Powered Research
          <br />
          Information Platform
        </p>
      </aside>
      <div className="lg:pl-64">
        <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-stone-200/80 bg-white/85 px-4 backdrop-blur dark:border-stone-800 dark:bg-stone-950/85 lg:px-8">
          <button
            aria-label="Open navigation"
            className="lg:hidden"
            onClick={() => setOpen(true)}
          >
            <Menu />
          </button>
          <span className="hidden text-sm text-stone-500 sm:block">
            Ethiopian scholarship, connected.
          </span>
          <button
            aria-label="Toggle theme"
            className="rounded-lg border border-stone-200 p-2 dark:border-stone-800"
            onClick={() =>
              setTheme(resolvedTheme === "dark" ? "light" : "dark")
            }
          >
            {resolvedTheme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
          </button>
        </header>
        <main
          id="main-content"
          className={cn(
            "mx-auto p-4 sm:p-6 lg:p-8",
            path === "/ai/assistant" ? "max-w-none" : "max-w-7xl",
          )}
        >
          {children}
        </main>
      </div>
    </div>
  );
}
