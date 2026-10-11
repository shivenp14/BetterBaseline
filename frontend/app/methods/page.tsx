"use client";
import { useWorkspace } from "../WorkspaceProvider";
import { WorkspaceFrame } from "../WorkspaceFrame";
import { MethodDisclosures } from "@/components/MethodDisclosures";
import { HistoricalCaseStudy } from "@/components/HistoricalCaseStudy";
import { ScenarioExport } from "@/components/ScenarioExport";
import styles from "../planning.module.css";

export default function MethodsPage() {
  const { state, selectPreset, payload, exportReason } = useWorkspace();
  return <WorkspaceFrame title="Methods and records" description="Review how results are calculated, where assumptions came from, and the historical case that motivated this planning workflow.">
    <section className={styles.methodSection} aria-labelledby="method-heading"><h2 id="method-heading">How to interpret the estimates</h2>
      <p>Analytical power uses Cohen’s-h and floored expected retained counts. Monte Carlo samples actual retained counts and applies a two-sided pooled-z test; these are different approximations.</p>
      <MethodDisclosures />
      <p>These tools explore a hypothetical two-arm binary-outcome design. They do not predict whether a treatment works, establish clinical benefit, or replace a statistician’s review.</p>
    </section>
    <section className={styles.methodSection} aria-labelledby="export-heading"><h2 id="export-heading">Current results and export</h2>
      <p>Exports include only current results whose inputs match the active assumptions. A new calculation or edited input makes earlier results ineligible.</p>
      <ScenarioExport payload={payload} unavailableReason={exportReason} />
    </section>
    <section className={styles.methodSection} aria-labelledby="provenance-heading"><h2 id="provenance-heading">Assumption sources and audit trail</h2>
      <p>Current result fingerprint: <code className={styles.hash}>{state.designStatus === "success" ? state.displayedInputsHash ?? "unhashed" : "no current calculated design"}</code></p>
      <div className={styles.tableScroll} role="region" aria-label="Active field source table" tabIndex={0}><table><caption>Where each assumption came from</caption><thead><tr><th scope="col">Field</th><th scope="col">Source</th><th scope="col">Description</th></tr></thead><tbody>{Object.entries(state.provenanceLedger).map(([field, source]) => <tr key={field}><th scope="row">{field}</th><td>{source.source}</td><td>{source.description}{source.source_url && <> — <a href={source.source_url}>{source.source_url}</a></>}</td></tr>)}</tbody></table></div>
    </section>
    <section className={styles.methodSection} aria-labelledby="case-heading"><h2 id="case-heading">Historical case study</h2>
      <p>This example gives context for the planning question. Applying the workflow to a real program requires its original assumptions and an appropriate validated model.</p>
      <HistoricalCaseStudy onLoadExample={selectPreset} />
    </section>
  </WorkspaceFrame>;
}
