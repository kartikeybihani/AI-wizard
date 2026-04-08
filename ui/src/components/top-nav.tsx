"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

const THEME_STORAGE_KEY = "ui-theme";

type Theme = "light" | "dark";

const NAV_LINKS = [
  { href: "/", label: "Discovery Run" },
  { href: "/results", label: "Results" },
  { href: "/monitor", label: "Monitor" },
  { href: "/engage", label: "Engage" },
];

function SunIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="4" />
      <path d="M12 3.5V5.5" />
      <path d="M12 18.5V20.5" />
      <path d="M5.64 5.64L7.05 7.05" />
      <path d="M16.95 16.95L18.36 18.36" />
      <path d="M3.5 12H5.5" />
      <path d="M18.5 12H20.5" />
      <path d="M5.64 18.36L7.05 16.95" />
      <path d="M16.95 7.05L18.36 5.64" />
    </svg>
  );
}

function MoonIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <path d="M20.5 13.3A8.5 8.5 0 1 1 10.7 3.5a7 7 0 1 0 9.8 9.8z" />
    </svg>
  );
}

export function TopNav() {
  const pathname = usePathname();
  const [theme, setTheme] = useState<Theme>(() => {
    if (typeof document === "undefined") {
      return "light";
    }
    return document.documentElement.classList.contains("dark") ? "dark" : "light";
  });

  const toggleTheme = () => {
    setTheme((currentTheme) => {
      const nextTheme: Theme = currentTheme === "dark" ? "light" : "dark";
      const root = document.documentElement;
      root.classList.toggle("dark", nextTheme === "dark");
      root.style.colorScheme = nextTheme;
      window.localStorage.setItem(THEME_STORAGE_KEY, nextTheme);
      return nextTheme;
    });
  };

  return (
    <header className="border-b border-slate-200/80 bg-white/85 backdrop-blur">
      <div className="mx-auto flex w-full max-w-7xl items-center justify-between gap-4 px-6 py-4">
        <div className="flex items-center gap-3">
          <div className="brand-mark h-9 w-9 rounded-lg" />
          <div>
            <p className="font-mono text-xs uppercase tracking-[0.18em] text-slate-500">
              AI WIZARD
            </p>
            <p className="text-sm font-semibold text-slate-900">
              Influencer Discovery
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <nav className="inline-flex rounded-full border border-slate-200 bg-white p-1 text-sm shadow-sm">
            {NAV_LINKS.map((link) => {
              const active = pathname === link.href;
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  className={`rounded-full px-4 py-1.5 transition ${
                    active
                      ? "bg-slate-900 text-white"
                      : "text-slate-600 hover:bg-slate-100"
                  }`}
                >
                  {link.label}
                </Link>
              );
            })}
          </nav>

          <button
            type="button"
            onClick={toggleTheme}
            className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold uppercase tracking-wide text-slate-700 shadow-sm transition hover:bg-slate-100"
            aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
            title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
          >
            {theme === "dark" ? (
              <SunIcon className="h-3.5 w-3.5" />
            ) : (
              <MoonIcon className="h-3.5 w-3.5" />
            )}
            <span>{theme === "dark" ? "Light" : "Dark"}</span>
          </button>
        </div>
      </div>
    </header>
  );
}
