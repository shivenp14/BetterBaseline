import type { Metadata } from "next";
import "./globals.css";
import { WorkspaceProvider } from "@/components/WorkspaceProvider";
import { WorkspaceFrame } from "@/components/WorkspaceFrame";

export const metadata: Metadata = {
  title: "Better Baseline · Trial planning workspace",
  description:
    "Offline synthetic planning workspace for exploring clinical trial assumptions.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body><WorkspaceProvider><WorkspaceFrame>{children}</WorkspaceFrame></WorkspaceProvider></body>
    </html>
  );
}
