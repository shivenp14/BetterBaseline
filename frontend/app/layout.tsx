import type { Metadata } from "next";
import "./globals.css";
import "./planning.css";
import "../components/analytics.css";
import "../components/audit.css";
import { WorkspaceProvider } from "./WorkspaceProvider";

export const metadata: Metadata = {
  title: "Better Baseline · Trial planning workspace",
  description:
    "Stress-test binary clinical trial assumptions before enrollment: freeze sample size and explore how lower event risk or greater dropout affects statistical power.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body><WorkspaceProvider>{children}</WorkspaceProvider></body>
    </html>
  );
}
