import type { Metadata } from "next";
import { Manrope, Space_Grotesk } from "next/font/google";

import { TopNav } from "@/components/top-nav";
import "./globals.css";

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
    <html lang="en" className={`${sans.variable} ${mono.variable}`}>
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
