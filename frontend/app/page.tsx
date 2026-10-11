"use client";

import { useState } from "react";
import { calculateDesign, evaluateScenario, getStressGrid } from "@/lib/api";
import { presets } from "@/lib/mocks";
import type { CalculateResponse, EvaluateResponse, GridResponse } from "@/lib/contracts";

function percent(value: number, digits = 0): string {
  return `${(value * 100).toFixed(digits)}%`;
}

export default function Home() {
  const [presetId, setPresetId] = useState("baseline-collapse-v1");
  const preset = presets.find((item) => item.id === presetId) ?? presets[1];
  const [stressBaseline, setStressBaseline] = useState(preset.stress.control_event_rate);
  const [stressDropout, setStressDropout] = useState(preset.stress.dropout);
  const [designResult, setDesignResult] = useState<CalculateResponse | null>(null);
  const [evaluateResult, setEvaluateResult] = useState<EvaluateResponse | null>(null);
  const [gridResult, setGridResult] = useState<GridResponse | null>(null);
  const [status, setStatus] = useState("Ready. All values shown are fixed illustrative mock fixtures.");

  const displayedDesign = designResult ?? preset.design_response;
  const displayedEvaluate = evaluateResult ?? preset.evaluate_response;
  const displayedGrid = gridResult ?? preset.grid_response;

  function changePreset(nextId: string) {
    const nextPreset = presets.find((item) => item.id === nextId) ?? presets[1];
    setPresetId(nextPreset.id);
    setStressBaseline(nextPreset.stress.control_event_rate);
    setStressDropout(nextPreset.stress.dropout);
    setDesignResult(null);
    setEvaluateResult(null);
    setGridResult(null);
    setStatus("Preset changed. Results are local illustrative fixtures.");
  }

  async function calculate() {
    const response = await calculateDesign({ ...preset.assumptions, preset_id: preset.id });
    setDesignResult(response);
    setStatus("Calculate returned a fixed local mock response. No statistical calculation was performed.");
  }

  async function evaluate() {
    const response = await evaluateScenario({
      planned_design: preset.assumptions,
      fixed_enrollment: displayedDesign.enrolled_n,
      stress_scenario: {
        control_event_rate: stressBaseline,
        dropout: { control: stressDropout, treatment: stressDropout },
        effect_override: null,
      },
      simulation: { replicates: 10000, seed: 42 },
      preset_id: preset.id,
    });
    setEvaluateResult(response);
    setStatus("Evaluate returned a fixed local mock response. Enrollment remains fixed; no simulation was run.");
  }

  async function loadGrid() {
    const response = await getStressGrid({
      planned_design: preset.assumptions,
      fixed_enrollment: displayedDesign.enrolled_n,
      x_baseline: preset.grid_response.x_baseline,
      y_dropout: preset.grid_response.y_dropout,
      preset_id: preset.id,
    });
    setGridResult(response);
    setStatus("Grid returned a fixed local mock response. Its values and contour are illustrative.");
  }

  return (
    <main>
      <header>
        <h1>Better Baseline</h1>
        <p>Offline synthetic trial planning shell</p>
        <p><strong>Offline demo.</strong> No backend or network calls.</p>
      </header>

      <section aria-labelledby="preview-heading">
        <h2 id="preview-heading">Illustrative mock preview</h2>
        <p>Every number is a fixed local fixture, not a statistical result. Changing inputs exercises the typed request boundary; results remain illustrative examples.</p>
        <p role="status">{status}</p>
        <label htmlFor="preset">Synthetic scenario</label>{" "}
        <select id="preset" value={presetId} onChange={(event) => changePreset(event.target.value)}>
          {presets.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}
        </select>
        <p>{preset.description}</p>
        <p>Provenance: synthetic fixture; no citation URL or source study.</p>
      </section>

      <section aria-labelledby="planned-heading">
        <h2 id="planned-heading">1. Planned design</h2>
        <p>Binary undesirable event, two arms, equal 1:1 allocation, symmetric dropout.</p>
        <ul>
          <li>Planned control event risk: {percent(preset.assumptions.control_event_rate)}</li>
          <li>Hypothetical effect: {preset.effect_label}</li>
          <li>Alpha: {percent(preset.assumptions.alpha)}</li>
          <li>Power target: {percent(preset.assumptions.target_power)}</li>
          <li>Planned dropout: {percent(preset.assumptions.dropout.control)}</li>
          <li>Planned enrollment: {displayedDesign.enrolled_n.control.toLocaleString()} control and {displayedDesign.enrolled_n.treatment.toLocaleString()} treatment participants</li>
          <li>Evaluable sample: {displayedDesign.evaluable_n.control.toLocaleString()} per arm</li>
          <li>Illustrative nominal power: {percent(displayedDesign.nominal_power_evaluable, 1)}</li>
        </ul>
        <p>Method label: {displayedDesign.method} (illustrative only).</p>
        <button type="button" onClick={calculate}>Calculate design (local mock)</button>
        <ul>
          {displayedDesign.warnings.map((warning) => <li key={warning}>{warning}</li>)}
        </ul>
      </section>

      <section aria-labelledby="stress-heading">
        <h2 id="stress-heading">2. Stress scenario</h2>
        <p>Stress controls do not resize the planned enrollment. Dropout is symmetric between arms.</p>
        <p>
          <label htmlFor="baseline">Stress control event risk: {percent(stressBaseline)}</label><br />
          <input id="baseline" type="range" min="5" max="30" step="1" value={Math.round(stressBaseline * 100)} onChange={(event) => setStressBaseline(Number(event.target.value) / 100)} />
          <span> 5% to 30%</span>
        </p>
        <p>
          <label htmlFor="dropout">Stress symmetric dropout: {percent(stressDropout)}</label><br />
          <input id="dropout" type="range" min="0" max="30" step="1" value={Math.round(stressDropout * 100)} onChange={(event) => setStressDropout(Number(event.target.value) / 100)} />
          <span> 0% to 30%</span>
        </p>
        <button type="button" onClick={evaluate}>Evaluate fixed enrollment (local mock)</button>
        <p>Selected request values: baseline {percent(stressBaseline)}, symmetric dropout {percent(stressDropout)}. The response remains the selected preset fixture.</p>
      </section>

      <section aria-labelledby="power-heading">
        <h2 id="power-heading">3. Power by baseline risk</h2>
        <p>Illustrative fixture values at the first dropout row. This is a numerical view, not a styled chart.</p>
        <table>
          <caption>Mock power curve data</caption>
          <thead><tr><th scope="col">Control event risk</th><th scope="col">Illustrative power</th></tr></thead>
          <tbody>
            {displayedGrid.x_baseline.map((baseline, index) => (
              <tr key={baseline}>
                <td>{percent(baseline)}</td>
                <td>{displayedGrid.power[0][index] === null ? "Invalid scenario (null)" : percent(displayedGrid.power[0][index] ?? 0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p>Target power: {percent(displayedGrid.target_power)}. Values are illustrative and do not describe trial outcomes.</p>
      </section>

      <section aria-labelledby="grid-heading">
        <h2 id="grid-heading">4. Assumption sensitivity grid</h2>
        <p>Cell indexing follows [dropout][baseline]. All cell values are mock data. The contract represents invalid cells as null with a matching invalid mask.</p>
        <p>Grid method label: {displayedGrid.method}; {displayedGrid.grid_label}.</p>
        <table>
          <caption>Illustrative mock power grid by symmetric dropout and baseline event risk</caption>
          <thead>
            <tr>
              <th scope="col">Dropout ↓ / baseline →</th>
              {displayedGrid.x_baseline.map((baseline) => <th scope="col" key={baseline}>{percent(baseline)}</th>)}
            </tr>
          </thead>
          <tbody>
            {displayedGrid.y_dropout.map((dropout, row) => (
              <tr key={dropout}>
                <th scope="row">{percent(dropout)}</th>
                {displayedGrid.power[row].map((value, column) => (
                  <td key={`${row}-${column}`}>
                    {displayedGrid.invalid_mask[row][column]
                      ? `Invalid (power ${value === null ? "null" : "unexpected value"})`
                      : value === null ? "Invalid data (mask false)" : percent(value)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        <p>Planned point: baseline {percent(displayedGrid.planned_point.baseline)}, dropout {percent(displayedGrid.planned_point.dropout)}.</p>
        <p>Selected point: baseline {percent(displayedGrid.selected_point.baseline)}, dropout {percent(displayedGrid.selected_point.dropout)}.</p>
        <p>Target-power contour points (fixture only):</p>
        <ol>
          {displayedGrid.frontier_points.map((point, index) => <li key={`${point.baseline}-${point.dropout}-${index}`}>Baseline {percent(point.baseline)}, dropout {percent(point.dropout)}</li>)}
        </ol>
        <button type="button" onClick={loadGrid}>Load grid response (local mock)</button>
        <ul>{displayedGrid.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
      </section>

      <section aria-labelledby="evaluate-heading">
        <h2 id="evaluate-heading">5. Evaluate selected scenario</h2>
        <p>Selected baseline {percent(stressBaseline)}; symmetric dropout {percent(stressDropout)}; fixed enrollment {displayedDesign.enrolled_n.control.toLocaleString()} per arm.</p>
        <p>Analytic method: {displayedEvaluate.analytic.method}.</p>
        <ul>
          <li>Illustrative conditional power: {displayedEvaluate.analytic.conditional_power_approx === null
            ? "Unavailable: zero expected retention"
            : percent(displayedEvaluate.analytic.conditional_power_approx)}</li>
          <li>Stress expected retained count: {displayedEvaluate.analytic.assumed_evaluable_n.control.toLocaleString()} control and {displayedEvaluate.analytic.assumed_evaluable_n.treatment.toLocaleString()} treatment participants</li>
          <li>Monte Carlo method: {displayedEvaluate.monte_carlo.method}</li>
          <li>Two-sided significance fraction: {percent(displayedEvaluate.monte_carlo.significant_two_sided_fraction)}</li>
          <li>Favorable-direction significance fraction: {percent(displayedEvaluate.monte_carlo.significant_favorable_fraction)}</li>
          <li>Two-sided significance MCSE: {percent(displayedEvaluate.monte_carlo.mcse_two_sided, 1)}</li>
          <li>Favorable-direction significance MCSE: {percent(displayedEvaluate.monte_carlo.mcse_favorable, 1)}</li>
          <li>Invalid-test fraction: {percent(displayedEvaluate.monte_carlo.invalid_test_fraction, 1)}</li>
          <li>Replicates: {displayedEvaluate.monte_carlo.replicates.toLocaleString()}</li>
          <li>Seed: {displayedEvaluate.monte_carlo.seed}</li>
        </ul>
        <p><strong>Mock simulation fields only.</strong> No Monte Carlo run occurred. An estimate of statistical power is not a prediction that treatment works.</p>
        <ul>{displayedEvaluate.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
      </section>

      <section aria-labelledby="provenance-heading">
        <h2 id="provenance-heading">Provenance</h2>
        <ul>
          <li>Scenario: {displayedEvaluate.provenance.label} ({displayedEvaluate.provenance.scenario_id})</li>
          <li>Scenario kind: {displayedEvaluate.provenance.scenario_kind}</li>
          <li>Source type: {displayedEvaluate.provenance.source.type}</li>
          <li>Citation URL: none</li>
          <li>Endpoint: {displayedEvaluate.provenance.endpoint_type}</li>
          <li>Follow-up: {displayedEvaluate.provenance.follow_up_label}</li>
          <li>Model version: {displayedEvaluate.provenance.method_version}</li>
          <li>Fixture source: {displayedEvaluate.provenance.generated_by}</li>
          <li>Inputs hash: {displayedEvaluate.metadata.inputs_hash}</li>
          <li>Fixture timestamp: {displayedEvaluate.metadata.computed_at}</li>
        </ul>
      </section>

      <footer>
        <p><strong>Planning support only.</strong> This offline synthetic shell is not clinical evidence, medical advice, or a validated design tool. Conditional power depends on assumptions and method. Review real study decisions with a qualified statistician.</p>
      </footer>
    </main>
  );
}
