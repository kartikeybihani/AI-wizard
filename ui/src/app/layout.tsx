import type { Metadata } from "next";
import { Manrope, Space_Grotesk } from "next/font/google";

import { TopNav } from "@/components/top-nav";
import "./globals.css";

const themeInitScript = `
(() => {
  try {
    const key = "ui-theme";
    const saved = window.localStorage.getItem(key);
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const theme = saved === "dark" || saved === "light" ? saved : prefersDark ? "dark" : "light";
    const root = document.documentElement;
    root.classList.toggle("dark", theme === "dark");
    root.style.colorScheme = theme;
  } catch {
    // Ignore startup theme errors.
  }
})();
`;

const sans = Manrope({
  variable: "--font-sans",
  subsets: ["latin"],
});

const mono = Space_Grotesk({
  variable: "--font-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "AI Wizard UI",
  description: "Run, monitor, and inspect influencer discovery pipeline runs.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${sans.variable} ${mono.variable}`}
      suppressHydrationWarning
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body className="min-h-screen bg-app text-slate-900">
        <div className="app-background" aria-hidden="true" />
        <div className="relative z-10 flex min-h-screen flex-col">
          <TopNav />
          {children}
        </div>
      </body>
    </html>
  );
}
