"use client";

import { useId, useState } from "react";
import { serializeScenarioExport, parseScenarioExport, type ScenarioExportPayload } from "../lib/export";

export interface ScenarioExportProps {
  payload: ScenarioExportPayload | null;
  unavailableReason?: string;
}

/** Parent supplies only a validated, current snapshot. Reload validates a
 * detached artifact; it never overwrites the current workspace or reruns it.
 */
export function ScenarioExport({ payload, unavailableReason }: ScenarioExportProps) {
  const id = useId();
  const [feedback, setFeedback] = useState<{ error: boolean; message: string } | null>(null);
  let json: string | null = null, validationError: string | null = null;
  try { if (payload) json = serializeScenarioExport(payload); }
  catch (error) { validationError = error instanceof Error ? error.message : "Invalid export snapshot."; }
  async function reopen(file: File | undefined) {
    if (!file) return;
    try {
      const loaded = parseScenarioExport(await file.text());
      setFeedback({ error: false, message: `Valid complete v${loaded.export_schema_version} scenario exported ${loaded.exported_at}; seed ${loaded.evaluation_result.monte_carlo.seed}, ${loaded.evaluation_result.monte_carlo.replicates} replicates. Recorded environment and assumptions are preserved for independent replay.` });
    } catch (error) {
      setFeedback({ error: true, message: error instanceof Error ? error.message : "Unable to read scenario JSON." });
    }
  }
  return <section aria-labelledby={`${id}-heading`}>
    <h2 id={`${id}-heading`}>Scenario export</h2>
    <p>JSON v1 records complete assumptions, locked enrollment, analytic grid and curve, selected simulation, separate MCSEs, warnings, hashes, software versions, RNG and field provenance.</p>
    {json ? <a download="better-baseline-scenario-v1.json" href={`data:application/json;charset=utf-8,${encodeURIComponent(json)}`}>Download current scenario JSON</a>
      : <><button type="button" disabled>Download current scenario JSON</button><p role={validationError ? "alert" : "status"}>{validationError ?? unavailableReason ?? "Complete current results are required before export."}</p></>}
    <p>Reconstruction requires the recorded software environment. Schema validation does not independently verify statistical correctness.</p>
    <label htmlFor={`${id}-reload`}>Reopen and validate scenario JSON</label>{" "}
    <input id={`${id}-reload`} type="file" accept=".json,application/json" onChange={event => { void reopen(event.target.files?.[0]); event.target.value = ""; }} />
    {feedback && <p role={feedback.error ? "alert" : "status"}>{feedback.message}</p>}
  </section>;
}
