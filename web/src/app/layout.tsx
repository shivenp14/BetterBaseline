import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "TrialSync · Study workspace",
  description:
    "Trace clinical study artifacts and findings in a synthetic TrialSync workspace.",
};
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
