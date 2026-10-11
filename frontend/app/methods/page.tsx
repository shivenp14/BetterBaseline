"use client";

import { MethodDisclosures } from "@/components/MethodDisclosures";
import { useWorkspace } from "@/components/WorkspaceProvider";

export default function MethodsPage() {
  const { state } = useWorkspace();
  return <>
    <header className="route-heading"><h1>Methods and provenance</h1><p>Review how assumptions were sourced and how calculations should be interpreted.</p></header>
    <section className="workspace-section provenance-workspace panel" aria-labelledby="provenance-heading">
      <h2 id="provenance-heading">Active field provenance</h2>
      <p>Current result hash: <code className="inline-code">{state.displayedInputsHash ?? "stale/unhashed"}</code></p>
      <details className="disclosure"><summary>Inspect active field provenance and audit trail</summary><div className="table-scroll" tabIndex={0} role="region" aria-label="Active field provenance table"><table className="data-table"><caption>Active field provenance</caption><thead><tr><th scope="col">Field</th><th scope="col">Source</th><th scope="col">Description</th></tr></thead><tbody>{Object.entries(state.provenanceLedger).map(([field, source]) => <tr key={field}><th scope="row">{field}</th><td>{source.source}</td><td>{source.description}{source.source_url && <> — <a href={source.source_url}>{source.source_url}</a></>}</td></tr>)}</tbody></table></div></details>
      <MethodDisclosures />
    </section>
  </>;
}
