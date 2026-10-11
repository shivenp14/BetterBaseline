"use client";

import { useId, useState, type Dispatch, type SetStateAction } from "react";
import { serializeScenarioExport, parseScenarioExport, type ScenarioExportPayload } from "../lib/export";

export interface ScenarioExportProps {
  payload: ScenarioExportPayload | null;
  unavailableReason?: string;
  /** Optional persistent validation feedback for route transitions. */
  feedback?: { error: boolean; message: string } | null;
  onFeedbackChange?: Dispatch<SetStateAction<{ error: boolean; message: string } | null>>;
}

/** Parent supplies only a validated, current snapshot. Reload validates a
 * detached artifact; it never overwrites the current workspace or reruns it.
 */
export function ScenarioExport({ payload, unavailableReason, feedback: controlledFeedback, onFeedbackChange }: ScenarioExportProps) {
  const id = useId();
  const [localFeedback, setLocalFeedback] = useState<{ error: boolean; message: string } | null>(null);
  const feedback = controlledFeedback === undefined ? localFeedback : controlledFeedback;
  const setFeedback = onFeedbackChange ?? setLocalFeedback;
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
  return <section className="workspace-section panel" aria-labelledby={`${id}-heading`}>
    <h2 className="section-heading" id={`${id}-heading`}>Scenario export</h2>
    <p>JSON v1 records complete assumptions, locked enrollment, analytic grid and curve, selected simulation, separate MCSEs, warnings, hashes, software versions, RNG and field provenance.</p>
    {json ? <a className="button-primary" download="better-baseline-scenario-v1.json" href={`data:application/json;charset=utf-8,${encodeURIComponent(json)}`}>Download current scenario JSON</a>
      : <><button className="button-primary" type="button" disabled>Download current scenario JSON</button><p className={validationError ? "status-error" : "status-warning"} role={validationError ? "alert" : "status"}>{validationError ?? unavailableReason ?? "Complete current results are required before export."}</p></>}
    <p>Reconstruction requires the recorded software environment. Schema validation does not independently verify statistical correctness.</p>
    <div className="field"><label htmlFor={`${id}-reload`}>Reopen and validate scenario JSON</label>{" "}
    <input id={`${id}-reload`} type="file" accept=".json,application/json" onChange={event => { void reopen(event.target.files?.[0]); event.target.value = ""; }} aria-describedby={`${id}-detached`} /></div>
    <p className="field-help" id={`${id}-detached`}>Validation checks a detached record. It does not restore workspace inputs or rerun calculations.</p>
    {feedback && <p className={feedback.error ? "status-error" : "status-success"} role={feedback.error ? "alert" : "status"}>{feedback.message}</p>}
  </section>;
}
