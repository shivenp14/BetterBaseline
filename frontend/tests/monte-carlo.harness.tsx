"use client";
import { useMemo, useState } from "react";
import { MonteCarloPanel } from "../components/MonteCarloPanel";
import { createSharedSimulationTransport, createSimulationClient, parseSimulationResult,
  type RunSimulation, type SimulationSelection } from "../lib/simulation-client";
const initial: SimulationSelection = {
  planned_design: { model_version: "binary-v1", allocation_ratio: 1, control_event_rate: .2,
    effect: { kind: "relative_risk", value: .75 }, alpha: .05, target_power: .8, dropout: { control: .1, treatment: .1 } },
  fixed_enrollment: { control: 1004, treatment: 1004 },
  stress_scenario: { control_event_rate: .1, dropout: { control: .1, treatment: .1 }, effect_override: null },
  provenance: { control_event_rate: { source: "manual_user" } },
};
/** Temporary isolated acceptance page; no production state or shared API wiring. */
export default function MonteCarloHarness() {
  const [selection, setSelection] = useState<SimulationSelection | null>(initial);
  const [mode, setMode] = useState("real");
  const [visible, setVisible] = useState(true);
  const [calls, setCalls] = useState(0), [aborts, setAborts] = useState(0);
  const [finished, setFinished] = useState<number[]>([]);
  const [accepted, setAccepted] = useState<number[]>([]);
  const runSimulation: RunSimulation = useMemo(() => {
    const transport = createSharedSimulationTransport();
    const run = createSimulationClient(transport);
    return async (request, signal) => {
      setCalls(count => count + 1);
      signal.addEventListener("abort", () => setAborts(count => count + 1), { once: true });
      if (mode === "failure") throw new Error("Acceptance transport failure");
      // Explicit stress case: this injected adapter ignores cancellation itself.
      // Both success responses are still fresh real backend calculations.
      if (mode === "late") {
        const result = parseSimulationResult(await transport(request, new AbortController().signal), request);
        if (request.simulation.seed === 42) await new Promise(resolve => setTimeout(resolve, 500));
        setFinished(list => [...list, request.simulation.seed]);
        return result;
      }
      return run(request, signal);
    };
  }, [mode]);
  return <main>
    <button onClick={() => setMode("late")}>Ignore cancellation</button>
    <button onClick={() => setMode("failure")}>Fail adapter</button>
    <button onClick={() => setMode("real")}>Real adapter</button>
    <button onClick={() => setSelection({ ...initial, stress_scenario: { ...initial.stress_scenario, control_event_rate: .15 } })}>Select new baseline</button>
    <button onClick={() => setSelection({ ...initial, stress_scenario: { ...initial.stress_scenario, effect_override: { kind: "relative_risk", value: .5 } } })}>Change effect</button>
    <button onClick={() => setSelection({ ...initial, stress_scenario: { ...initial.stress_scenario, effect_override: { kind: "absolute_risk_reduction", value: .2 } } })}>Invalid ARR</button>
    <button onClick={() => setSelection(null)}>Clear selection</button>
    <button onClick={() => setSelection(initial)}>Restore selection</button>
    <button onClick={() => setVisible(value => !value)}>Toggle panel</button>
    {visible && <MonteCarloPanel selection={selection} runSimulation={runSimulation}
      onResult={(result) => setAccepted(list => [...list, result.monte_carlo.seed])} />}
    <output aria-label="Run calls">{calls}</output><output aria-label="Abort calls">{aborts}</output>
    <output aria-label="Finished seeds">{JSON.stringify(finished)}</output>
    <output aria-label="Accepted seeds">{JSON.stringify(accepted)}</output>
  </main>;
}
