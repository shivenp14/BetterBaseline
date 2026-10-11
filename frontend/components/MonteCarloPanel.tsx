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
}
const percent = (n: number) => `${(n * 100).toFixed(3)}%`;
export function MonteCarloResults({ result }: { result: SimulationResult }) {
  const mc = result.monte_carlo;
  return <>
    <MethodDisclosures />
    <dl>
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
    <table><caption>Expected analytical counts and sampled simulation means per arm</caption>
      <thead><tr><th scope="col">Count</th><th scope="col">Control</th><th scope="col">Treatment</th></tr></thead>
      <tbody>
        <tr><th scope="row">Frozen enrolled participants</th><td>{result.metadata.fixed_enrollment.control}</td><td>{result.metadata.fixed_enrollment.treatment}</td></tr>
        <tr><th scope="row">Floored expected evaluable participants (analytic)</th><td>{result.analytic.assumed_evaluable_n.control}</td><td>{result.analytic.assumed_evaluable_n.treatment}</td></tr>
        <tr><th scope="row">Mean actual retained participants (simulation)</th><td>{mc.mean_retained_control.toFixed(2)}</td><td>{mc.mean_retained_treatment.toFixed(2)}</td></tr>
        <tr><th scope="row">Mean events (simulation)</th><td>{mc.mean_control_events.toFixed(2)}</td><td>{mc.mean_treatment_events.toFixed(2)}</td></tr>
      </tbody>
    </table>
    <h3>Software versions</h3><dl>{Object.entries(result.metadata.software_versions).map(([name, value]) => <div key={name}><dt>{name}</dt><dd>{value}</dd></div>)}</dl>
    <h3>Field provenance</h3>{Object.keys(result.provenance).length ? <dl>{Object.entries(result.provenance).map(([field, source]) => <div key={field}>
      <dt>{field}</dt><dd>{source.source}{source.description && ` — ${source.description}`}{source.retrieved_at && `; retrieved ${source.retrieved_at}`}{source.source_url && `; source URL: ${source.source_url}`}</dd>
    </div>)}</dl> : <p>No field provenance supplied.</p>}
    {result.warnings.length > 0 && <><h3>Simulation warnings</h3><ul>{result.warnings.map((warning, index) => <li key={`${index}-${warning}`}>{warning}</li>)}</ul></>}
  </>;
}
export function MonteCarloPanel({ selection, runSimulation, unavailableReason, onResult }: MonteCarloPanelProps) {
  const id = useId();
  const [seed, setSeed] = useState("42"), [replicates, setReplicates] = useState("10000");
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
  const pending = pendingRequest?.identity === identity && !pendingRequest.signal.aborted;
  const error = failure?.identity === identity ? failure.message : null;
  const stale = snapshot !== null && (snapshot.identity !== identity || pending || Boolean(error) || !available || Boolean(invalid));
  useEffect(() => () => { generation.current += 1; controller.current?.abort(); inFlight.current = null; }, [identity, runSimulation, available]);
  async function run(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!available || invalid || !request || !runSimulation || pending || inFlight.current === identity) return;
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
  return <section aria-labelledby={`${id}-heading`} aria-busy={pending}>
    <h2 id={`${id}-heading`}>Selected-scenario Monte Carlo simulation</h2>
    {!available && <p role="status">Simulation unavailable: {unavailableReason ?? (!selection ? "calculate and select a valid frozen design first." : "the live simulation adapter is not connected.")}</p>}
    <form onSubmit={run} noValidate>
      <label htmlFor={`${id}-seed`}>Simulation seed</label>{" "}<input id={`${id}-seed`} type="text" inputMode="numeric" value={seed} onChange={(event) => setSeed(event.target.value)} aria-describedby={`${id}-bounds`} />
      <label htmlFor={`${id}-reps`}>Simulation replicates</label>{" "}<input id={`${id}-reps`} type="text" inputMode="numeric" value={replicates} onChange={(event) => setReplicates(event.target.value)} aria-describedby={`${id}-bounds`} />
      <p id={`${id}-bounds`}>Whole numbers: seed 0–{MAX_SEED}; replicates 1–{MAX_REPLICATES}. Each run simulates one selected scenario at frozen enrollment.</p>
      <button type="submit" disabled={!available || Boolean(invalid) || pending}>{pending ? "Running simulation…" : "Run simulation"}</button>
    </form>
    {invalid && <p role="alert">{invalid}</p>}{error && <p role="alert">{error}</p>}
    {pending && <p role="status">Running the selected seeded simulation.</p>}
    {snapshot ? <>{stale && <p role="status"><strong>Stale simulation.</strong> These values belong to a previous run; run the current selection to refresh.</p>}<MonteCarloResults result={snapshot.result} /></> : <p>No simulation result yet.</p>}
  </section>;
}
