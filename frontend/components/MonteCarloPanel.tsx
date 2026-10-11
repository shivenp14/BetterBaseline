"use client";
import { useCallback, useEffect, useId, useRef, useState, type Dispatch, type FormEvent, type SetStateAction } from "react";
import { MethodDisclosures } from "./MethodDisclosures";
import { simulationErrorMessage, MAX_REPLICATES, MAX_SEED, parseSimulationOptions, simulationIdentity, validateSimulationRequest,
  type RunSimulation, type SimulationRequest, type SimulationResult, type SimulationSelection } from "../lib/simulation-client";
export interface MonteCarloPanelProps {
  selection: SimulationSelection | null;
  runSimulation?: RunSimulation;
  unavailableReason?: string;
  /** Only a current successful run reaches parent state/export. */
  onResult?: (result: SimulationResult, request: SimulationRequest) => void;
  /** Optional persistent UI state, supplied by the workspace across route changes. */
  uiState?: MonteCarloUIState;
  onUIStateChange?: Dispatch<SetStateAction<MonteCarloUIState>>;
  /** Workspace ownership hooks keep completions from an older mounted panel inert. */
  onRequestStart?: (requestId: string) => void;
  onRequestFinish?: (requestId: string) => void;
  isRequestCurrent?: (requestId: string) => boolean;
}
export interface MonteCarloUIState {
  seed: string;
  replicates: string;
  snapshot: { identity: string; result: SimulationResult } | null;
  pendingIdentity: string | null;
  pendingRequestId: string | null;
  failure: { identity: string; message: string } | null;
}
let requestSequence = 0;
const nextRequestId = () => `${Date.now()}-${++requestSequence}`;
const percent = (n: number) => `${(n * 100).toFixed(3)}%`;
export function MonteCarloResults({ result }: { result: SimulationResult }) {
  const mc = result.monte_carlo;
  return <>
    <MethodDisclosures />
    <dl className="simulation-readings">
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
    <div className="table-scroll" role="region" aria-label="Enrollment and retention counts" tabIndex={0}><table className="data-table"><caption>Expected analytical counts and sampled simulation means per arm</caption>
      <thead><tr><th scope="col">Count</th><th scope="col">Control</th><th scope="col">Treatment</th></tr></thead>
      <tbody>
        <tr><th scope="row">Frozen enrolled participants</th><td>{result.metadata.fixed_enrollment.control}</td><td>{result.metadata.fixed_enrollment.treatment}</td></tr>
        <tr><th scope="row">Floored expected evaluable participants (analytic)</th><td>{result.analytic.assumed_evaluable_n.control}</td><td>{result.analytic.assumed_evaluable_n.treatment}</td></tr>
        <tr><th scope="row">Mean actual retained participants (simulation)</th><td>{mc.mean_retained_control.toFixed(2)}</td><td>{mc.mean_retained_treatment.toFixed(2)}</td></tr>
        <tr><th scope="row">Mean events (simulation)</th><td>{mc.mean_control_events.toFixed(2)}</td><td>{mc.mean_treatment_events.toFixed(2)}</td></tr>
      </tbody>
    </table></div>
    <details className="disclosure"><summary>Software versions and field provenance</summary><h3>Software versions</h3><dl className="simulation-readings">{Object.entries(result.metadata.software_versions).map(([name, value]) => <div key={name}><dt>{name}</dt><dd>{value}</dd></div>)}</dl>
    <h3>Field provenance</h3>{Object.keys(result.provenance).length ? <dl className="simulation-readings">{Object.entries(result.provenance).map(([field, source]) => <div key={field}>
      <dt>{field}</dt><dd>{source.source}{source.description && ` — ${source.description}`}{source.retrieved_at && `; retrieved ${source.retrieved_at}`}{source.source_url && `; source URL: ${source.source_url}`}</dd>
    </div>)}</dl> : <p>No field provenance supplied.</p>}
    </details>
    {result.warnings.length > 0 && <div className="status-warning"><h3>Simulation warnings</h3><ul>{result.warnings.map((warning, index) => <li key={`${index}-${warning}`}>{warning}</li>)}</ul></div>}
  </>;
}
export function MonteCarloPanel({ selection, runSimulation, unavailableReason, onResult, uiState, onUIStateChange, onRequestStart, onRequestFinish, isRequestCurrent }: MonteCarloPanelProps) {
  const id = useId();
  const [localUI, setLocalUI] = useState<MonteCarloUIState>({ seed: "42", replicates: "10000", snapshot: null, pendingIdentity: null, pendingRequestId: null, failure: null });
  const ui = uiState ?? localUI;
  const { seed, replicates, snapshot, failure } = ui;
  const updateUI: Dispatch<SetStateAction<MonteCarloUIState>> = useCallback(update => onUIStateChange ? onUIStateChange(update) : setLocalUI(update), [onUIStateChange]);
  const controller = useRef<AbortController | null>(null), generation = useRef(0);
  const inFlight = useRef<string | null>(null);
  const activeRequestId = useRef<string | null>(null);
  let request: SimulationRequest | null = null, invalid: string | null = null;
  try {
    const options = parseSimulationOptions(seed, replicates);
    if (selection) { request = { ...selection, simulation: options }; validateSimulationRequest(request); }
  } catch (error) { invalid = simulationErrorMessage(error); }
  const identity = request ? simulationIdentity(request) : JSON.stringify([selection, seed, replicates]);
  const available = Boolean(selection && runSimulation && !unavailableReason);
  const pending = ui.pendingIdentity === identity && ui.pendingRequestId !== null;
  const error = failure?.identity === identity ? failure.message : null;
  const stale = snapshot !== null && (snapshot.identity !== identity || pending || Boolean(error) || !available || Boolean(invalid));
  useEffect(() => {
    if (uiState) return;
    return () => {
      generation.current += 1;
      controller.current?.abort();
      inFlight.current = null;
      const requestId = activeRequestId.current;
      if (requestId) {
        updateUI(current => current.pendingRequestId === requestId ? { ...current, pendingIdentity: null, pendingRequestId: null } : current);
        if (!isRequestCurrent || isRequestCurrent(requestId)) onRequestFinish?.(requestId);
        activeRequestId.current = null;
      }
    };
  }, [identity, runSimulation, available, uiState, updateUI, isRequestCurrent, onRequestFinish]);
  async function run(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!available || invalid || !request || !runSimulation || pending || inFlight.current === identity) return;
    controller.current?.abort();
    const active = new AbortController(); controller.current = active;
    const token = ++generation.current, captured = request;
    const requestId = nextRequestId();
    inFlight.current = identity;
    activeRequestId.current = requestId;
    onRequestStart?.(requestId);
    updateUI(current => ({ ...current, pendingIdentity: identity, pendingRequestId: requestId, failure: null }));
    try {
      const result = await runSimulation(captured, active.signal);
      if (generation.current !== token || active.signal.aborted) return;
      if (isRequestCurrent && !isRequestCurrent(requestId)) return;
      updateUI(current => current.pendingRequestId === requestId ? { ...current, snapshot: { identity, result } } : current);
      onResult?.(result, captured);
    } catch (error) {
      if (generation.current !== token || active.signal.aborted) return;
      if (error instanceof DOMException && error.name === "AbortError") return;
      if (isRequestCurrent && !isRequestCurrent(requestId)) return;
      updateUI(current => current.pendingRequestId === requestId ? { ...current, failure: { identity, message: simulationErrorMessage(error) } } : current);
    } finally {
      if (generation.current === token) {
        updateUI(current => current.pendingRequestId === requestId ? { ...current, pendingIdentity: null, pendingRequestId: null } : current);
        if (!isRequestCurrent || isRequestCurrent(requestId)) onRequestFinish?.(requestId);
        controller.current = null;
        if (inFlight.current === identity) inFlight.current = null;
        if (activeRequestId.current === requestId) activeRequestId.current = null;
      }
    }
  }
  return <section className="workspace-section panel" aria-labelledby={`${id}-heading`} aria-busy={pending}>
    <h2 className="section-heading" id={`${id}-heading`}>Selected-scenario Monte Carlo simulation</h2>
    {!available && <p className="status-badge" role="status">Simulation unavailable: {unavailableReason ?? (!selection ? "calculate and select a valid frozen design first." : "the live simulation adapter is not connected.")}</p>}
    <form className="simulation-form" onSubmit={run} noValidate>
      <div className="field-grid"><div className="field">
      <label htmlFor={`${id}-seed`}>Simulation seed</label>{" "}<input id={`${id}-seed`} type="text" inputMode="numeric" value={seed} onChange={(event) => updateUI(current => ({ ...current, seed: event.target.value }))} aria-invalid={Boolean(invalid)} aria-describedby={`${id}-bounds`} /></div><div className="field">
      <label htmlFor={`${id}-reps`}>Simulation replicates</label>{" "}<input id={`${id}-reps`} type="text" inputMode="numeric" value={replicates} onChange={(event) => updateUI(current => ({ ...current, replicates: event.target.value }))} aria-invalid={Boolean(invalid)} aria-describedby={`${id}-bounds`} /></div></div>
      <p className="field-help" id={`${id}-bounds`}>Whole numbers: seed 0–{MAX_SEED}; replicates 1–{MAX_REPLICATES}. Each run simulates one selected scenario at frozen enrollment.</p>
      <button className="button-primary" type="submit" disabled={!available || Boolean(invalid) || pending}>{pending ? "Running simulation…" : "Run simulation"}</button>
    </form>
    {invalid && <p className="status-error" role="alert">{invalid}</p>}{error && <p className="status-error" role="alert">{error}</p>}
    {pending && <p className="status-badge" role="status">Running the selected seeded simulation.</p>}
    {snapshot ? <>{!stale && <p className="status-success" role="status">Current simulation for the selected scenario and execution settings.</p>}{stale && <p className="status-warning" role="status"><strong>Stale simulation.</strong> These values belong to a previous run; run the current selection to refresh.</p>}<MonteCarloResults result={snapshot.result} /></> : <p className="chart-empty">No simulation result yet. Select a valid scenario, then run a seeded simulation to inspect its significance fractions.</p>}
  </section>;
}
