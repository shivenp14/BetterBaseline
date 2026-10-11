"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";
import { getApiMode } from "@/lib/api";

const navigation = [
  { href: "/", label: "Plan & lock" },
  { href: "/stress", label: "Stress-test" },
  { href: "/simulation", label: "Simulate & export" },
  { href: "/methods", label: "Methods" },
];

export function WorkspaceFrame({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const mainRef = useRef<HTMLElement>(null);
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "auto" });
    const heading = mainRef.current?.querySelector<HTMLElement>("h1");
    if (heading) {
      heading.tabIndex = -1;
      heading.focus({ preventScroll: true });
    }
  }, [pathname]);
  return <div className="workspace-shell">
    <a className="skip-link" href="#route-content">Skip to this task</a>
    <header className="workspace-header">
      <div className="brand-lockup"><Link className="workspace-brand" href="/">Better Baseline</Link><span className="status-badge">{getApiMode() === "demo" ? "DEMO" : "LIVE"}</span></div>
      <nav className="workspace-nav" aria-label="Workspace tasks">
        {navigation.map(item => <Link key={item.href} href={item.href} aria-current={pathname === item.href ? "page" : undefined}>{item.label}</Link>)}
      </nav>
    </header>
    <main id="route-content" className="route-content" ref={mainRef}>{children}</main>
  </div>;
}
