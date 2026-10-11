import type { Metadata } from "next";
import "./globals.css";
import "./planning.css";
import "../components/analytics.css";
import "../components/audit.css";

export const metadata: Metadata = {
  title: "Better Baseline · Trial planning workspace",
  description:
    "Offline synthetic planning workspace for exploring clinical trial assumptions.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
