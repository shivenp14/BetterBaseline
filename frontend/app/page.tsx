"use client";

import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { calculateDesign, evaluateScenario, getApiMode, getStressGrid } from "@/lib/api";
import type { CalculateRequest } from "@/lib/contracts";
import { getPresetById } from "@/lib/presets";
import { plannedFieldUpdateAction } from "@/lib/workspace-planning";
import type { DraftField, PlanningDraft } from "@/lib/validation";
import {
  buildStressEvaluationRequest,
  initializeWorkspaceState,
  workspaceReducer,
} from "@/lib/workspace-state";
import { PresetSelector } from "@/components/PresetSelector";
import { DesignForm } from "@/components/DesignForm";
import { StressControls } from "@/components/StressControls";
import { buildWorkspaceExport, downloadWorkspaceExport, hasCurrentExportableResults } from "@/lib/workspace-export";
import { scheduleDebounced } from "@/lib/debounce";

function percent(value: number, digits = 0): string {
  return `${(value * 100).toFixed(digits)}%`;
}

export default function Home() {
  const [state, dispatch] = useReducer(workspaceReducer, undefined, () =>
    initializeWorkspaceState("baseline-collapse-v1")
  );
  const [formResetKey, setFormResetKey] = useState(0);

  const calculateAbortRef = useRef<AbortController | null>(null);
  const evaluateAbortRef = useRef<AbortController | null>(null);
  const gridAbortRef = useRef<AbortController | null>(null);
  const stressEvaluationPendingRef = useRef(false);
  const nextRequestRevisionRef = useRef(0);
  const inputGenerationRef = useRef(state.inputGeneration);

  const {
    presetId,
    plannedDraft,
    calculatedDesign,
    frozenEnrollment,
    designStatus,
    designError,
    stressBaseline,
    stressDropout,
    provenanceLedger,
    evaluateResult,
    evaluateStatus,
    evaluateError,
    gridResult,
    gridStatus,
    gridError,
    displayedInputsHash,
    requestRevision,
    inputGeneration,
  } = state;

  const displayedDesign = calculatedDesign;
  const displayedEvaluate = evaluateResult;
  const displayedGrid = gridResult;

  function abortAllPending() {
    calculateAbortRef.current?.abort();
    evaluateAbortRef.current?.abort();
    gridAbortRef.current?.abort();
  }

  function advanceInputGeneration() {
    inputGenerationRef.current += 1;
    return inputGenerationRef.current;
  }

  function handleSelectPreset(nextPresetId: string) {
    advanceInputGeneration();
    abortAllPending();
    stressEvaluationPendingRef.current = false;
    dispatch({ type: "LOAD_PRESET", presetId: nextPresetId });
  }

  function handleResetPreset() {
    advanceInputGeneration();
    abortAllPending();
    stressEvaluationPendingRef.current = false;
    dispatch({ type: "RESET_TO_PRESET" });
    setFormResetKey((key) => key + 1);
  }

  function handleStressBaselineChange(val: number) {
    advanceInputGeneration();
    abortAllPending();
    stressEvaluationPendingRef.current = true;
    dispatch({ type: "UPDATE_STRESS_BASELINE", baseline: val });
  }

  function handleStressDropoutChange(val: number) {
    advanceInputGeneration();
    abortAllPending();
    stressEvaluationPendingRef.current = true;
    dispatch({ type: "UPDATE_STRESS_DROPOUT", dropout: val });
  }

  function handlePlannedDraftChange(draft: PlanningDraft, changedField: DraftField) {
    advanceInputGeneration();
    stressEvaluationPendingRef.current = false;
    dispatch(plannedFieldUpdateAction(draft, changedField, presetId));
  }

  async function handleCalculate(request: CalculateRequest) {
    const expectedInputGeneration = inputGeneration;
    if (expectedInputGeneration !== inputGenerationRef.current) return;

    // Recalculation is an input-snapshot transition because it replaces the
    // enrollment lock. Advance synchronously so a pending debounce cannot
    // start against the old lock before React applies the reducer action.
    advanceInputGeneration();
    stressEvaluationPendingRef.current = false;
    abortAllPending();
    const controller = new AbortController();
    calculateAbortRef.current = controller;
    const revision = Math.max(requestRevision, nextRequestRevisionRef.current) + 1;
    nextRequestRevisionRef.current = revision;

    dispatch({
      type: "START_CALCULATE",
      requestRevision: revision,
      expectedInputGeneration,
    });
    try {
      const response = await calculateDesign(
        { ...request, provenance_ledger: provenanceLedger },
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

  const handleEvaluate = useCallback(async (expectedInputGeneration = inputGeneration) => {
    if (
      expectedInputGeneration !== inputGenerationRef.current ||
      expectedInputGeneration !== inputGeneration
    ) return;
    if (designStatus === "calculating" || !frozenEnrollment ||
      (getApiMode() === "live" && designStatus !== "success")) return;
    evaluateAbortRef.current?.abort();
    const controller = new AbortController();
    evaluateAbortRef.current = controller;
    const revision = Math.max(requestRevision, nextRequestRevisionRef.current) + 1;
    nextRequestRevisionRef.current = revision;

    dispatch({
      type: "START_EVALUATE",
      requestRevision: revision,
      expectedInputGeneration,
    });
    try {
      const response = await evaluateScenario(buildStressEvaluationRequest(state), controller.signal);
      dispatch({ type: "EVALUATE_SUCCESS", response, requestRevision: revision });
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      dispatch({
        type: "EVALUATE_ERROR",
        error: err instanceof Error ? err.message : String(err),
        requestRevision: revision,
      });
    }
  }, [designStatus, frozenEnrollment, inputGeneration, requestRevision, state]);

  useEffect(() => {
    if (!stressEvaluationPendingRef.current || !frozenEnrollment || designStatus === "calculating" ||
      (getApiMode() === "live" && designStatus !== "success")) return;
    const expectedInputGeneration = inputGeneration;
    return scheduleDebounced(() => {
      if (expectedInputGeneration !== inputGenerationRef.current) return;
      stressEvaluationPendingRef.current = false;
      void handleEvaluate(expectedInputGeneration);
    }, 350);
  }, [stressBaseline, stressDropout, frozenEnrollment, designStatus, inputGeneration, handleEvaluate]);

  async function handleLoadGrid() {
    const expectedInputGeneration = inputGeneration;
    if (expectedInputGeneration !== inputGenerationRef.current) return;
    if (designStatus === "calculating" || !frozenEnrollment || !displayedGrid) return;
    gridAbortRef.current?.abort();
    const controller = new AbortController();
    gridAbortRef.current = controller;
    const revision = Math.max(requestRevision, nextRequestRevisionRef.current) + 1;
    nextRequestRevisionRef.current = revision;

    dispatch({
      type: "START_GRID",
      requestRevision: revision,
      expectedInputGeneration,
    });
    try {
      const response = await getStressGrid(
        {
          planned_design: plannedDraft,
          fixed_enrollment: frozenEnrollment,
          x_baseline: displayedGrid.x_baseline,
          y_dropout: displayedGrid.y_dropout,
          selected_scenario: {
            control_event_rate: stressBaseline,
            dropout: { control: stressDropout, treatment: stressDropout },
            effect_override: null,
          },
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

  function handleDownloadExport() {
    const payload = buildWorkspaceExport(state);
    downloadWorkspaceExport(payload);
  }

  return (
    <main>
      <header>
        <h1>Better Baseline</h1>
        <p>Trial planning workspace backed by a local calculation service.</p>
        <p><strong>Execution mode:</strong> {getApiMode() === "demo" ? "DEMO — fixtures and client calculations; no backend execution" : "LIVE — fresh calculations require the backend service"}</p>
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
        <DesignForm
          key={`${presetId}:${formResetKey}`}
          initialAssumptions={getPresetById(presetId).planned_design}
          presetId={presetId}
          onCalculate={handleCalculate}
          onDraftChange={handlePlannedDraftChange}
          isCalculating={designStatus === "calculating"}
          error={designError}
          submitLabel={getApiMode() === "demo" ? "Calculate & Lock Design (demo)" : "Calculate & Lock Design"}
        />
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
          <p>Method label: {displayedDesign.method}. {designStatus === "success" ? displayedDesign.execution?.label : "Preset fixture or stale result — run a fresh calculation for current assumptions."}</p>
        )}

        {displayedDesign && (displayedDesign.execution?.mode === "demo" || designStatus !== "success") && (
          <p role="status"><strong>Demo/stale result.</strong> This preset fixture is not a fresh calculation. {displayedDesign.execution?.label}</p>
        )}

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
        onEvaluate={() => { void handleEvaluate(); }}
        evaluateStatus={evaluateStatus}
        evaluateError={evaluateError}
        isCalculating={designStatus === "calculating"}
      />

      {/* Power by baseline risk table */}
      {displayedGrid && (
        <section aria-labelledby="power-heading">
          <h2 id="power-heading">3. Power by baseline risk</h2>
          <p>
            Backend or demo values at the first dropout row. Native numerical table view.
          </p>
          <table>
            <caption>Power curve data ({displayedGrid.execution?.label ?? "execution source unavailable"})</caption>
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
            Target power: {percent(displayedGrid.target_power)}. Values are statistical estimates and do not describe trial outcomes.
          </p>
        </section>
      )}

      {/* Assumption sensitivity grid */}
      {displayedGrid && (
        <section aria-labelledby="grid-heading">
          <h2 id="grid-heading">4. Assumption sensitivity grid</h2>
          <p>
            Cell indexing follows [dropout][baseline]. The contract represents invalid cells as null with a matching
            invalid mask.
          </p>
          <p>
            Grid method label: {displayedGrid.method}; {displayedGrid.grid_label}
            .
          </p>
          <table>
            <caption>
              Power grid by symmetric dropout and baseline
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
            Selected point: {displayedGrid.selected_point
              ? <>baseline {percent(displayedGrid.selected_point.baseline)}, dropout{" "}
                {percent(displayedGrid.selected_point.dropout)}.</>
              : "Unavailable from backend."}
          </p>
          <button
            type="button"
            onClick={handleLoadGrid}
            disabled={designStatus === "calculating" || gridStatus === "loading"}
          >
            {gridStatus === "loading"
              ? "Loading Grid..."
              : getApiMode() === "demo" ? "Load grid response (demo)" : "Load grid response from backend"}
          </button>
          <span> Status: {gridStatus.toUpperCase()}</span>
          {gridError && <p role="alert"><strong>Grid request failed:</strong> {gridError}</p>}
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
          <p>{evaluateStatus === "success" ? displayedEvaluate.execution?.label : "Preset fixture or stale result — run a fresh evaluation for current assumptions."}</p>
          {(displayedEvaluate.execution?.mode === "demo" || evaluateStatus !== "success") && (
            <p role="status"><strong>Demo/stale result.</strong> This fixture is not a fresh backend evaluation.</p>
          )}
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
            {displayedEvaluate.monte_carlo ? (
              <>
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
              </>
            ) : (
              <li>
                Monte Carlo simulation:{" "}
                <em>
                  Unavailable in demo mode; select live mode and run the backend for pooled-z results.
                </em>
              </li>
            )}
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

      <section aria-labelledby="export-heading">
        <h2 id="export-heading">7. Export current results</h2>
        <p>Downloads a canonical JSON snapshot with the active assumptions, frozen enrollment, current field provenance, and only results that match the current inputs.</p>
        <button
          type="button"
          onClick={handleDownloadExport}
          disabled={!frozenEnrollment || !hasCurrentExportableResults(state)}
        >
          Download current results (JSON)
        </button>
      </section>

      <footer>
        <p>
          <strong>Planning support only.</strong> This workspace is
          not clinical evidence, medical advice, or a validated design tool.
          Conditional power depends on assumptions and method. Review real study
          decisions with a qualified statistician.
        </p>
      </footer>
    </main>
  );
}
