"use client";

import { useReducer, useRef } from "react";
import { calculateDesign, evaluateScenario, getStressGrid } from "@/lib/api";
import {
  initializeWorkspaceState,
  workspaceReducer,
} from "@/lib/workspace-state";
import { PresetSelector } from "@/components/PresetSelector";
import { StressControls } from "@/components/StressControls";

function percent(value: number, digits = 0): string {
  return `${(value * 100).toFixed(digits)}%`;
}

export default function Home() {
  const [state, dispatch] = useReducer(workspaceReducer, undefined, () =>
    initializeWorkspaceState("baseline-collapse-v1")
  );

  const calculateAbortRef = useRef<AbortController | null>(null);
  const evaluateAbortRef = useRef<AbortController | null>(null);
  const gridAbortRef = useRef<AbortController | null>(null);

  const {
    presetId,
    plannedDraft,
    calculatedDesign,
    frozenEnrollment,
    designStatus,
    stressBaseline,
    stressDropout,
    provenanceLedger,
    evaluateResult,
    evaluateStatus,
    evaluateError,
    gridResult,
    gridStatus,
    displayedInputsHash,
    requestRevision,
  } = state;

  const displayedDesign = calculatedDesign;
  const displayedEvaluate = evaluateResult;
  const displayedGrid = gridResult;

  function abortAllPending() {
    calculateAbortRef.current?.abort();
    evaluateAbortRef.current?.abort();
    gridAbortRef.current?.abort();
  }

  function handleSelectPreset(nextPresetId: string) {
    abortAllPending();
    dispatch({ type: "LOAD_PRESET", presetId: nextPresetId });
  }

  function handleResetPreset() {
    abortAllPending();
    dispatch({ type: "RESET_TO_PRESET" });
  }

  function handleStressBaselineChange(val: number) {
    // Abort pending evaluations on edit
    evaluateAbortRef.current?.abort();
    gridAbortRef.current?.abort();
    dispatch({ type: "UPDATE_STRESS_BASELINE", baseline: val });
  }

  function handleStressDropoutChange(val: number) {
    evaluateAbortRef.current?.abort();
    gridAbortRef.current?.abort();
    dispatch({ type: "UPDATE_STRESS_DROPOUT", dropout: val });
  }

  async function handleCalculate() {
    abortAllPending();
    const controller = new AbortController();
    calculateAbortRef.current = controller;
    const revision = requestRevision;

    dispatch({ type: "START_CALCULATE" });
    try {
      const response = await calculateDesign(
        {
          ...plannedDraft,
          preset_id: presetId,
          provenance_ledger: provenanceLedger,
        },
        controller.signal
      );
      dispatch({ type: "CALCULATE_SUCCESS", response, requestRevision: revision });
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      dispatch({
        type: "CALCULATE_ERROR",
        error: err instanceof Error ? err.message : String(err),
        requestRevision: revision,
      });
    }
  }

  async function handleEvaluate() {
    if (!frozenEnrollment) return;
    evaluateAbortRef.current?.abort();
    const controller = new AbortController();
    evaluateAbortRef.current = controller;
    const revision = requestRevision;

    dispatch({ type: "START_EVALUATE" });
    try {
      const response = await evaluateScenario(
        {
          planned_design: plannedDraft,
          fixed_enrollment: frozenEnrollment,
          stress_scenario: {
            control_event_rate: stressBaseline,
            dropout: { control: stressDropout, treatment: stressDropout },
            effect_override: null,
          },
          simulation: { replicates: 10000, seed: 42 },
          preset_id: presetId,
          provenance_ledger: provenanceLedger,
        },
        controller.signal
      );
      dispatch({ type: "EVALUATE_SUCCESS", response, requestRevision: revision });
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      dispatch({
        type: "EVALUATE_ERROR",
        error: err instanceof Error ? err.message : String(err),
        requestRevision: revision,
      });
    }
  }

  async function handleLoadGrid() {
    if (!frozenEnrollment || !displayedGrid) return;
    gridAbortRef.current?.abort();
    const controller = new AbortController();
    gridAbortRef.current = controller;
    const revision = requestRevision;

    dispatch({ type: "START_GRID" });
    try {
      const response = await getStressGrid(
        {
          planned_design: plannedDraft,
          fixed_enrollment: frozenEnrollment,
          x_baseline: displayedGrid.x_baseline,
          y_dropout: displayedGrid.y_dropout,
          preset_id: presetId,
          provenance_ledger: provenanceLedger,
        },
        controller.signal
      );
      dispatch({ type: "GRID_SUCCESS", response, requestRevision: revision });
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      dispatch({
        type: "GRID_ERROR",
        error: err instanceof Error ? err.message : String(err),
        requestRevision: revision,
      });
    }
  }

  return (
    <main>
      <header>
        <h1>Better Baseline</h1>
        <p>Offline synthetic trial planning shell</p>
        <p>
          <strong>Offline demo.</strong> No backend or network calls.
        </p>
      </header>

      {/* Preset Selector */}
      <PresetSelector
        selectedPresetId={presetId}
        onSelectPreset={handleSelectPreset}
        onResetPreset={handleResetPreset}
      />

      {/* Planned Design Section */}
      <section aria-labelledby="planned-heading">
        <h2 id="planned-heading">1. Planned design & Enrollment Locking</h2>
        <p>
          Binary undesirable event, two arms, equal 1:1 allocation, symmetric
          dropout.
        </p>
        <ul>
          <li>
            Planned control event risk:{" "}
            {percent(plannedDraft.control_event_rate)} (Provenance:{" "}
            <code>
              {provenanceLedger["/planned_design/control_event_rate"]?.source ??
                "synthetic_preset"}
            </code>
            )
          </li>
          <li>
            Effect:{" "}
            {plannedDraft.effect.kind === "relative_risk"
              ? `Relative Risk ${plannedDraft.effect.value}`
              : `ARR ${plannedDraft.effect.value}`}
          </li>
          <li>Alpha: {percent(plannedDraft.alpha)}</li>
          <li>Target power: {percent(plannedDraft.target_power)}</li>
          <li>Planned dropout: {percent(plannedDraft.dropout.control)}</li>
          {frozenEnrollment && (
            <li>
              <strong>LOCKED ENROLLMENT:</strong>{" "}
              {frozenEnrollment.control.toLocaleString()} control and{" "}
              {frozenEnrollment.treatment.toLocaleString()} treatment
              participants
            </li>
          )}
          {displayedDesign && (
            <>
              <li>
                Evaluable sample size:{" "}
                {displayedDesign.evaluable_n.control.toLocaleString()} per arm
              </li>
              <li>
                Illustrative nominal power:{" "}
                {percent(displayedDesign.nominal_power_evaluable, 1)}
              </li>
            </>
          )}
        </ul>

        {displayedDesign && (
          <p>Method label: {displayedDesign.method} (illustrative only).</p>
        )}

        <button
          type="button"
          onClick={handleCalculate}
          disabled={designStatus === "calculating"}
        >
          {designStatus === "calculating"
            ? "Calculating..."
            : "Recalculate & Lock Design (local mock)"}
        </button>

        {displayedDesign && (
          <ul>
            {displayedDesign.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        )}
      </section>

      {/* Stress Controls Section */}
      <StressControls
        frozenEnrollment={frozenEnrollment}
        stressBaseline={stressBaseline}
        stressDropout={stressDropout}
        onBaselineChange={handleStressBaselineChange}
        onDropoutChange={handleStressDropoutChange}
        onEvaluate={handleEvaluate}
        evaluateStatus={evaluateStatus}
        evaluateError={evaluateError}
      />

      {/* Power by baseline risk table */}
      {displayedGrid && (
        <section aria-labelledby="power-heading">
          <h2 id="power-heading">3. Power by baseline risk</h2>
          <p>
            Illustrative fixture values at the first dropout row. Native
            numerical table view.
          </p>
          <table>
            <caption>Mock power curve data</caption>
            <thead>
              <tr>
                <th scope="col">Control event risk</th>
                <th scope="col">Illustrative power</th>
              </tr>
            </thead>
            <tbody>
              {displayedGrid.x_baseline.map((baseline, index) => (
                <tr key={baseline}>
                  <td>{percent(baseline)}</td>
                  <td>
                    {displayedGrid.power[0][index] === null
                      ? "Invalid scenario (null)"
                      : percent(displayedGrid.power[0][index] ?? 0)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p>
            Target power: {percent(displayedGrid.target_power)}. Values are
            illustrative and do not describe trial outcomes.
          </p>
        </section>
      )}

      {/* Assumption sensitivity grid */}
      {displayedGrid && (
        <section aria-labelledby="grid-heading">
          <h2 id="grid-heading">4. Assumption sensitivity grid</h2>
          <p>
            Cell indexing follows [dropout][baseline]. All cell values are mock
            data. The contract represents invalid cells as null with a matching
            invalid mask.
          </p>
          <p>
            Grid method label: {displayedGrid.method}; {displayedGrid.grid_label}
            .
          </p>
          <table>
            <caption>
              Illustrative mock power grid by symmetric dropout and baseline
              event risk
            </caption>
            <thead>
              <tr>
                <th scope="col">Dropout ↓ / baseline →</th>
                {displayedGrid.x_baseline.map((baseline) => (
                  <th scope="col" key={baseline}>
                    {percent(baseline)}
                  </th>
                ))}
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
                        : value === null
                        ? "Invalid data (mask false)"
                        : percent(value)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          <p>
            Planned point: baseline{" "}
            {percent(displayedGrid.planned_point.baseline)}, dropout{" "}
            {percent(displayedGrid.planned_point.dropout)}.
          </p>
          <p>
            Selected point: baseline{" "}
            {percent(displayedGrid.selected_point.baseline)}, dropout{" "}
            {percent(displayedGrid.selected_point.dropout)}.
          </p>
          <button
            type="button"
            onClick={handleLoadGrid}
            disabled={gridStatus === "loading"}
          >
            {gridStatus === "loading"
              ? "Loading Grid..."
              : "Load grid response (local mock)"}
          </button>
          <span> Status: {gridStatus.toUpperCase()}</span>
          <ul>
            {displayedGrid.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </section>
      )}

      {/* Evaluate selected scenario */}
      {displayedEvaluate && (
        <section aria-labelledby="evaluate-heading">
          <h2 id="evaluate-heading">5. Evaluate selected scenario</h2>
          <p>
            Selected baseline {percent(stressBaseline)}; symmetric dropout{" "}
            {percent(stressDropout)}; fixed enrollment{" "}
            {frozenEnrollment?.control.toLocaleString() ?? "—"} per arm.
          </p>
          {evaluateStatus === "stale" && (
            <p>
              <strong>
                ⚠️ NOTICE: Inputs have changed since this result was
                evaluated. Results below are STALE. Click &ldquo;Evaluate Stress
                Scenario&rdquo; to update.
              </strong>
            </p>
          )}
          <p>Analytic method: {displayedEvaluate.analytic.method}.</p>
          <ul>
            <li>
              Conditional power:{" "}
              {displayedEvaluate.analytic.conditional_power_approx === null
                ? "Unavailable: zero expected retention"
                : percent(
                    displayedEvaluate.analytic.conditional_power_approx
                  )}
            </li>
            <li>
              Stress expected retained count (analytic floor):{" "}
              {displayedEvaluate.analytic.assumed_evaluable_n.control.toLocaleString()}{" "}
              control and{" "}
              {displayedEvaluate.analytic.assumed_evaluable_n.treatment.toLocaleString()}{" "}
              treatment participants
            </li>
            <li>
              Monte Carlo method: {displayedEvaluate.monte_carlo.method}
            </li>
            <li>
              Two-sided significance fraction:{" "}
              {percent(
                displayedEvaluate.monte_carlo.significant_two_sided_fraction
              )}
            </li>
            <li>
              Favorable-direction significance fraction:{" "}
              {percent(
                displayedEvaluate.monte_carlo.significant_favorable_fraction
              )}
            </li>
            <li>
              Two-sided significance MCSE:{" "}
              {percent(displayedEvaluate.monte_carlo.mcse_two_sided, 1)}
            </li>
            <li>
              Favorable-direction significance MCSE:{" "}
              {percent(displayedEvaluate.monte_carlo.mcse_favorable, 1)}
            </li>
            <li>
              Invalid-test fraction:{" "}
              {percent(
                displayedEvaluate.monte_carlo.invalid_test_fraction,
                1
              )}
            </li>
            <li>
              Replicates:{" "}
              {displayedEvaluate.monte_carlo.replicates.toLocaleString()}
            </li>
            <li>Seed: {displayedEvaluate.monte_carlo.seed}</li>
          </ul>
          <p>
            <strong>Statistical estimate only.</strong> An estimate of
            statistical power is not a prediction that treatment works.
          </p>
          <ul>
            {displayedEvaluate.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </section>
      )}

      {/* Field Provenance & Ledger Section */}
      <section aria-labelledby="provenance-heading">
        <h2 id="provenance-heading">6. Field Provenance & Audit Trail</h2>
        <p>
          Tracks the origin of every assumption. Editing preset values switches
          their source from <code>synthetic_preset</code> to{" "}
          <code>manual_user</code>.
        </p>
        <p>
          Displayed Inputs Hash: <code>{displayedInputsHash ?? "(stale/unhashed)"}</code>
        </p>
        <table>
          <caption>Active Field Provenance</caption>
          <thead>
            <tr>
              <th scope="col">Field Pointer</th>
              <th scope="col">Source Origin</th>
              <th scope="col">Description</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(provenanceLedger).map(([pointer, record]) => (
              <tr key={pointer}>
                <td>
                  <code>{pointer}</code>
                </td>
                <td>
                  <strong>{record.source}</strong>
                </td>
                <td>{record.description ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <footer>
        <p>
          <strong>Planning support only.</strong> This offline synthetic shell is
          not clinical evidence, medical advice, or a validated design tool.
          Conditional power depends on assumptions and method. Review real study
          decisions with a qualified statistician.
        </p>
      </footer>
    </main>
  );
}
