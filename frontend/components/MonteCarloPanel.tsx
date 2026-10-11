"use client";
import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { MethodDisclosures } from "./MethodDisclosures";
import { simulationErrorMessage, MAX_REPLICATES, MAX_SEED, parseSimulationOptions, simulationIdentity, validateSimulationRequest,
  type RunSimulation, type SimulationRequest, type SimulationResult, type SimulationSelection } from "../lib/simulation-client";
export interface MonteCarloPanelProps {
  selection: SimulationSelection | null;
  runSimulation?: RunSimulation;
  unavailableReason?: string;
  /** Only a current successful run reaches parent state/export. */
  onResult?: (result: SimulationResult, request: SimulationRequest) => void;
  seed?: string;
  replicates?: string;
  onOptionsChange?: (options: { seed: string; replicates: string }) => void;
  sharedResult?: SimulationResult | null;
  sharedStatus?: "idle" | "running" | "error";
  sharedError?: string | null;
  sharedResultIdentity?: string | null;
}
const percent = (n: number) => `${(n * 100).toFixed(3)}%`;
export function MonteCarloResults({ result }: { result: SimulationResult }) {
  const mc = result.monte_carlo;
  return <div className={"auditResults"}>
    <MethodDisclosures />
    <div className={"auditResultColumns"}>
    <dl className={"auditReadings"}>
      <dt>Two-sided significance fraction</dt><dd>{percent(mc.significant_two_sided_fraction)}</dd>
      <dt>Two-sided MCSE (percentage points)</dt><dd>{(mc.mcse_two_sided * 100).toFixed(3)}</dd>
      <dt>Favorable-direction significance fraction</dt><dd>{percent(mc.significant_favorable_fraction)}</dd>
      <dt>Favorable-direction MCSE (percentage points)</dt><dd>{(mc.mcse_favorable * 100).toFixed(3)}</dd>
      <dt>Invalid-test fraction (nonrejections over all replicates)</dt><dd>{percent(mc.invalid_test_fraction)}</dd>
      <dt>Seed</dt><dd>{mc.seed}</dd><dt>Replicates</dt><dd>{mc.replicates}</dd>
      <dt>Simulation method</dt><dd>{mc.method}</dd><dt>Model version</dt><dd>{result.model_version}</dd>
      <dt>Random number generator</dt><dd>{mc.rng}</dd>
      <dt>Inputs hash</dt><dd>{result.metadata.inputs_hash}</dd><dt>Computed at</dt><dd>{result.metadata.computed_at}</dd>
    </dl>
    <div className={"auditTableScroll"} role="region" aria-label="Simulation participant counts" tabIndex={0}><table><caption>Expected analytical counts and sampled simulation means per arm</caption>
      <thead><tr><th scope="col">Count</th><th scope="col">Control</th><th scope="col">Treatment</th></tr></thead>
      <tbody>
        <tr><th scope="row">Frozen enrolled participants</th><td>{result.metadata.fixed_enrollment.control}</td><td>{result.metadata.fixed_enrollment.treatment}</td></tr>
        <tr><th scope="row">Floored expected evaluable participants (analytic)</th><td>{result.analytic.assumed_evaluable_n.control}</td><td>{result.analytic.assumed_evaluable_n.treatment}</td></tr>
        <tr><th scope="row">Mean actual retained participants (simulation)</th><td>{mc.mean_retained_control.toFixed(2)}</td><td>{mc.mean_retained_treatment.toFixed(2)}</td></tr>
        <tr><th scope="row">Mean events (simulation)</th><td>{mc.mean_control_events.toFixed(2)}</td><td>{mc.mean_treatment_events.toFixed(2)}</td></tr>
      </tbody>
    </table></div></div>
    <h3>Software versions</h3><dl className={"auditMetadata"}>{Object.entries(result.metadata.software_versions).map(([name, value]) => <div key={name}><dt>{name}</dt><dd>{value}</dd></div>)}</dl>
    <h3>Field provenance</h3>{Object.keys(result.provenance).length ? <dl className={"auditMetadata"}>{Object.entries(result.provenance).map(([field, source]) => <div key={field}>
      <dt>{field}</dt><dd>{source.source}{source.description && ` — ${source.description}`}{source.retrieved_at && `; retrieved ${source.retrieved_at}`}{source.source_url && `; source URL: ${source.source_url}`}</dd>
    </div>)}</dl> : <p>No field provenance supplied.</p>}
    {result.warnings.length > 0 && <><h3>Simulation warnings</h3><ul className={"auditWarning"}>{result.warnings.map((warning, index) => <li key={`${index}-${warning}`}>{warning}</li>)}</ul></>}
  </div>;
}
export function MonteCarloPanel({ selection, runSimulation, unavailableReason, onResult, seed: seedProp, replicates: replicatesProp,
  onOptionsChange, sharedResult, sharedStatus, sharedError, sharedResultIdentity }: MonteCarloPanelProps) {
  const id = useId();
  const controlled = seedProp !== undefined && replicatesProp !== undefined;
  const [localSeed, setLocalSeed] = useState("42"), [localReplicates, setLocalReplicates] = useState("10000");
  const seed = seedProp ?? localSeed, replicates = replicatesProp ?? localReplicates;
  const [snapshot, setSnapshot] = useState<{ identity: string; result: SimulationResult } | null>(null);
  const [pendingRequest, setPendingRequest] = useState<{ identity: string; signal: AbortSignal } | null>(null);
  const [failure, setFailure] = useState<{ identity: string; message: string } | null>(null);
  const controller = useRef<AbortController | null>(null), generation = useRef(0);
  const inFlight = useRef<string | null>(null);
  let request: SimulationRequest | null = null, invalid: string | null = null;
  try {
    const options = parseSimulationOptions(seed, replicates);
    if (selection) { request = { ...selection, simulation: options }; validateSimulationRequest(request); }
  } catch (error) { invalid = simulationErrorMessage(error); }
  const identity = request ? simulationIdentity(request) : JSON.stringify([selection, seed, replicates]);
  const available = Boolean(selection && runSimulation && !unavailableReason);
  const pending = controlled ? sharedStatus === "running" : pendingRequest?.identity === identity && !pendingRequest.signal.aborted;
  const error = controlled ? (sharedStatus === "error" ? sharedError : null) : failure?.identity === identity ? failure.message : null;
  const currentResult = controlled ? sharedResult ?? null : snapshot?.result ?? null;
  const stale = currentResult !== null && ((controlled ? sharedResultIdentity !== identity : snapshot?.identity !== identity) || pending || Boolean(error) || !available || Boolean(invalid));
  useEffect(() => () => { if (!controlled) { generation.current += 1; controller.current?.abort(); inFlight.current = null; } }, [identity, runSimulation, available, controlled]);
  async function run(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!available || invalid || !request || !runSimulation || pending || (!controlled && inFlight.current === identity)) return;
    if (controlled) {
      try { await runSimulation(request, new AbortController().signal); } catch { /* Shared workspace state presents the current failure. */ }
      return;
    }
    controller.current?.abort();
    const active = new AbortController(); controller.current = active;
    const token = ++generation.current, captured = request;
    inFlight.current = identity; setPendingRequest({ identity, signal: active.signal }); setFailure(null);
    try {
      const result = await runSimulation(captured, active.signal);
      if (generation.current !== token || active.signal.aborted) return;
      setSnapshot({ identity, result });
      onResult?.(result, captured);
    } catch (error) {
      if (generation.current !== token || active.signal.aborted) return;
      setFailure({ identity, message: simulationErrorMessage(error) });
    } finally {
      if (generation.current === token) { setPendingRequest(null); controller.current = null; inFlight.current = null; }
    }
  }
  return <section className={"auditPanel"} aria-labelledby={`${id}-heading`} aria-busy={pending}>
    <h2 id={`${id}-heading`}>Selected-scenario Monte Carlo simulation</h2>
    {selection && <div className={"auditSelection"}><h3>Selected scenario · frozen enrollment</h3><dl className={"auditSelectionReadings"}>
      <div><dt>Control endpoint risk</dt><dd>{percent(selection.stress_scenario.control_event_rate)}</dd></div>
      <div><dt>Dropout · control / treatment</dt><dd>{percent(selection.stress_scenario.dropout.control)} / {percent(selection.stress_scenario.dropout.treatment)}</dd></div>
      <div><dt>Selected effect</dt><dd>{(selection.stress_scenario.effect_override ?? selection.planned_design.effect).kind === "relative_risk" ? `RR ${(selection.stress_scenario.effect_override ?? selection.planned_design.effect).value}` : `ARR ${((selection.stress_scenario.effect_override ?? selection.planned_design.effect).value * 100).toFixed(3)} percentage points`}</dd></div>
      <div><dt>Two-sided alpha / target power</dt><dd>{percent(selection.planned_design.alpha)} / {percent(selection.planned_design.target_power)}</dd></div>
      <div><dt>Frozen enrolled · control / treatment</dt><dd>{selection.fixed_enrollment.control} / {selection.fixed_enrollment.treatment}</dd></div>
    </dl></div>}
    {!available && <p className={"auditWarningStatus"} role="status">Simulation unavailable: {unavailableReason ?? (!selection ? "calculate and select a valid frozen design first." : "the live simulation adapter is not connected.")}</p>}
    <form className={"auditSettings"} onSubmit={run} noValidate>
      <div className={"auditField"}>
      <label htmlFor={`${id}-seed`}>Simulation seed</label>{" "}<input id={`${id}-seed`} type="text" inputMode="numeric" value={seed} onChange={(event) => { const value = event.target.value; if (controlled) onOptionsChange?.({ seed: value, replicates }); else setLocalSeed(value); }} aria-describedby={`${id}-bounds`} />
      </div><div className={"auditField"}><label htmlFor={`${id}-reps`}>Simulation replicates</label>{" "}<input id={`${id}-reps`} type="text" inputMode="numeric" value={replicates} onChange={(event) => { const value = event.target.value; if (controlled) onOptionsChange?.({ seed, replicates: value }); else setLocalReplicates(value); }} aria-describedby={`${id}-bounds`} />
      </div><p className={"auditBounds"} id={`${id}-bounds`}>Whole numbers: seed 0–{MAX_SEED}; replicates 1–{MAX_REPLICATES}. Each run simulates one selected scenario at frozen enrollment.</p>
      <button type="submit" disabled={!available || Boolean(invalid) || pending}>{pending ? "Running simulation…" : "Run simulation"}</button>
    </form>
    {invalid && <p className={"auditErrorStatus"} role="alert">{invalid}</p>}{error && <p className={"auditErrorStatus"} role="alert">{error}</p>}
    {pending && <p className={"auditCurrentStatus"} role="status">Running the selected seeded simulation.</p>}
    {currentResult ? <>{!stale && <p className={"auditCurrentStatus"} role="status"><strong>Current simulation.</strong> These values match the selected scenario and displayed execution settings.</p>}{stale && <p className={"auditWarningStatus"} role="status"><strong>Stale simulation.</strong> These values belong to a previous run; run the current selection to refresh.</p>}<MonteCarloResults result={currentResult} /></> : <p>No simulation result yet.</p>}
  </section>;
}
