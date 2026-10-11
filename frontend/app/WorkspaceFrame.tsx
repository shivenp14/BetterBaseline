"use client";
import { useEffect, useRef, type ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import styles from "./planning.module.css";

const steps = [
  { href: "/plan", label: "Plan" },
  { href: "/stress-test", label: "Stress-test" },
  { href: "/simulation", label: "Simulation" },
  { href: "/methods", label: "Methods" },
] as const;
export function WorkspaceFrame({ title, description, children }: { title: string; description: string; children: ReactNode }) {
  const pathname = usePathname();
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { heading.current?.focus(); }, [pathname]);
  const index = steps.findIndex(step => step.href === pathname);
  return <main className={styles.workspace}>
    <header className={styles.header}><h1 ref={heading} tabIndex={-1}>{title}</h1><p>{description}</p></header>
    <nav className={styles.stepNav} aria-label="Workspace pages"><ol>{steps.map((step, i) => <li key={step.href}>
      <Link href={step.href} aria-current={pathname === step.href ? "step" : undefined}><span aria-hidden="true">{i + 1}</span>{step.label}</Link>
    </li>)}</ol></nav>
    <div className={styles.pageContent}>{children}</div>
    <nav className={styles.pageControls} aria-label="Page navigation">
      {index > 0 && <Link className={styles.backLink} href={steps[index - 1].href}>← Back to {steps[index - 1].label}</Link>}
      {index >= 0 && index < steps.length - 1 && <Link className={styles.nextLink} href={steps[index + 1].href}>Continue to {steps[index + 1].label} →</Link>}
    </nav>
  </main>;
}
