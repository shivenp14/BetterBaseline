"use client";
// Benchmark-owned route template, copied temporarily to app/d6-grid/page.tsx.
import { useState } from "react";
import { getApiMode, getStressGrid } from "../../lib/api";
import type { GridResponse } from "../../lib/contracts";

export default function GridBenchmarkPage() {
  const [result, setResult] = useState<GridResponse | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function run() {
    if (pending) return;
    setPending(true);
    setError(null);
    try {
      if (getApiMode() !== "live") throw new Error("Live API mode is required.");
      const response = await getStressGrid({
        preset_id: "baseline-collapse-v1",
        planned_design: { model_version: "binary-v1", allocation_ratio: 1,
          control_event_rate: .2, effect: { kind: "relative_risk", value: .75 },
          alpha: .05, target_power: .8, dropout: { control: 0, treatment: 0 } },
        fixed_enrollment: { control: 903, treatment: 903 },
        x_baseline: Array.from({ length: 31 }, (_, index) => (5 + index) / 100),
        y_dropout: Array.from({ length: 21 }, (_, index) => index / 100),
        selected_scenario: { control_event_rate: .1,
          dropout: { control: 0, treatment: 0 }, effect_override: null },
      });
      if (response.mock || response.execution?.mode !== "backend") throw new Error("Real backend grid required.");
      setResult(response);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Grid request failed.");
    } finally {
      setPending(false);
    }
  }
  return <main>
    <h1>Isolated 31×21 benchmark using the shared API helper</h1>
    <p>This is an educational benchmark page, not the production workspace.</p>
    <section aria-labelledby="grid-heading">
      <h2 id="grid-heading">Real 31×21 grid</h2>
      <button disabled={pending} onClick={run}>{pending ? "Loading Grid..." : "Run 31×21 grid"}</button>
      <span>Status: {pending ? "LOADING" : error ? "ERROR" : result ? "SUCCESS" : "IDLE"}</span>
      {error && <p role="alert">{error}</p>}
      {result && <table>
        <caption>Analytic power at frozen enrollment; dropout rows, baseline columns</caption>
        <thead><tr><th>Dropout</th>{result.x_baseline.map(baseline => <th key={baseline}>{baseline}</th>)}</tr></thead>
        <tbody>{result.power.map((row, rowIndex) => <tr key={rowIndex}>
          <th>{result.y_dropout[rowIndex]}</th>
          {row.map((power, column) => <td key={column}>{power === null ? "Invalid (power null)" : `${(power * 100).toFixed(0)}%`}</td>)}
        </tr>)}</tbody>
      </table>}
    </section>
  </main>;
}
