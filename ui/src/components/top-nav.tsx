"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_LINKS = [
  { href: "/", label: "Run" },
  { href: "/results", label: "Results" },
];

export function TopNav() {
  const pathname = usePathname();

  return (
    <header className="border-b border-slate-200/80 bg-white/85 backdrop-blur">
      <div className="mx-auto flex w-full max-w-7xl items-center justify-between px-6 py-4">
        <div className="flex items-center gap-3">
          <div className="h-9 w-9 rounded-lg bg-[linear-gradient(140deg,#0ea5e9,#14b8a6)] shadow-[0_8px_24px_rgba(14,165,233,0.25)]" />
          <div>
            <p className="font-mono text-xs uppercase tracking-[0.18em] text-slate-500">
              AI WIZARD
            </p>
            <p className="text-sm font-semibold text-slate-900">
              Influencer Discovery
            </p>
          </div>
        </div>

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
      </div>
    </header>
  );
}
