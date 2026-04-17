import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Blake AI Interview v1",
  description: "Minimal realtime interview UI for AI Blake",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
