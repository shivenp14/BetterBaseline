"use client";
import { useCallback, useEffect, useLayoutEffect, useMemo, useReducer, useRef, useState } from "react";
import { calculateDesign, evaluateScenario, getApiMode, getStressGrid } from "@/lib/api";
import type { CalculateRequest } from "@/lib/contracts";
import type { WorkspaceState } from "@/lib/workspace-contracts";
import { getPresetById } from "@/lib/presets";
import { plannedFieldUpdateAction } from "@/lib/workspace-planning";
import type { DraftField, PlanningDraft } from "@/lib/validation";
import { buildStressEvaluationRequest, initializeWorkspaceState, workspaceReducer } from "@/lib/workspace-state";
import { scheduleDebounced } from "@/lib/debounce";
import { buildScenarioExport, type ExportRuns, type ScenarioExportPayload } from "@/lib/export";
import { parseSimulationOptions, parseSimulationResult, simulationIdentity, type RunSimulation, type SimulationSelection } from "@/lib/simulation-client";
import { PresetSelector } from "@/components/PresetSelector";
import { HistoricalCaseStudy } from "@/components/HistoricalCaseStudy";
import { DesignForm } from "@/components/DesignForm";
import { DesignSummary } from "@/components/DesignSummary";
import { StressControls } from "@/components/StressControls";
import { PowerCurve, workspaceCurveProps } from "@/components/PowerCurve";
import { DesignComparison, workspaceComparisonProps } from "@/components/DesignComparison";
import { StressHeatmap, workspaceHeatmapProps } from "@/components/StressHeatmap";
import { MonteCarloPanel } from "@/components/MonteCarloPanel";
import { MethodDisclosures } from "@/components/MethodDisclosures";
import { ScenarioExport } from "@/components/ScenarioExport";
import styles from "./planning.module.css";

// The chart revision seam tracks inputs, independently of concurrent operation tokens.
const chartState = (state: WorkspaceState): WorkspaceState => ({ ...state, requestRevision: state.inputGeneration });
const emptyRuns = (): ExportRuns => ({ design: null, evaluation: null, grid: null });
export default function Home() {
  const [state, dispatch] = useReducer(workspaceReducer, undefined, () => initializeWorkspaceState("baseline-collapse-v1"));
  const [formResetKey, setFormResetKey] = useState(0), [runs, setRuns] = useState<ExportRuns>(emptyRuns);
  const [simulationDraft, setSimulationDraft] = useState({ seed: "42", replicates: "10000" });
  const stateRef = useRef(state), generation = useRef(state.inputGeneration), token = useRef(0);
  const cancelRefresh = useRef<(() => void) | null>(null);
  const nextToken = useCallback(() => { token.current = Math.max(token.current, stateRef.current.requestRevision) + 1; return token.current; }, []);
  const calculateAbort = useRef<AbortController | null>(null), evaluateAbort = useRef<AbortController | null>(null), gridAbort = useRef<AbortController | null>(null);
  useLayoutEffect(() => { stateRef.current = state; }, [state]);
  useEffect(() => () => { calculateAbort.current?.abort(); evaluateAbort.current?.abort(); gridAbort.current?.abort(); }, []);
  function changeInputs() { generation.current++; cancelRefresh.current?.(); calculateAbort.current?.abort(); evaluateAbort.current?.abort(); gridAbort.current?.abort(); }
  function selectPreset(presetId?: string) {
    changeInputs(); setRuns(emptyRuns()); setSimulationDraft({ seed: "42", replicates: "10000" }); setFormResetKey(k => k + 1);
    dispatch(presetId ? { type: "LOAD_PRESET", presetId } : { type: "RESET_TO_PRESET" });
  }
  function changeBaseline(baseline: number) { changeInputs(); dispatch({ type: "UPDATE_STRESS_BASELINE", baseline }); }
  function changeDropout(dropout: number) { changeInputs(); dispatch({ type: "UPDATE_STRESS_DROPOUT", dropout }); }
  function selectPoint(point: { baseline: number; dropout: number }) { changeInputs(); dispatch({ type: "SELECT_STRESS_POINT", ...point }); }
  function changePlanned(draft: PlanningDraft, field: DraftField) { changeInputs(); dispatch(plannedFieldUpdateAction(draft, field, state.presetId)); }
  async function calculate(request: CalculateRequest) {
    const captured = structuredClone(stateRef.current);
    if (captured.inputGeneration !== generation.current) return;
    changeInputs(); setRuns(emptyRuns());
    const controller = new AbortController(); calculateAbort.current = controller;
    const revision = nextToken(), expected = generation.current;
    dispatch({ type: "START_CALCULATE", requestRevision: revision, expectedInputGeneration: captured.inputGeneration });
    try {
      const response = await calculateDesign({ ...request, provenance_ledger: captured.provenanceLedger }, controller.signal);
      if (controller.signal.aborted || generation.current !== expected) return;
      const canonical = { ...response, provenance: response.provenance.field_provenance ?? {}, diagnostics: response.diagnostics ?? [] }; delete (canonical as Partial<typeof canonical>).mock; delete canonical.execution;
      setRuns(old => ({ ...old, design: { requestState: captured, response: canonical } }));
      dispatch({ type: "CALCULATE_SUCCESS", response, requestRevision: revision });
    } catch (error) {
      if (controller.signal.aborted || generation.current !== expected) return;
      dispatch({ type: "CALCULATE_ERROR", error: error instanceof Error ? error.message : String(error), requestRevision: revision });
    }
  }
  const loadGrid = useCallback(async () => {
    const captured = structuredClone(stateRef.current);
    if (captured.inputGeneration !== generation.current || captured.designStatus !== "success" || !captured.frozenEnrollment) return;
    gridAbort.current?.abort(); const controller = new AbortController(); gridAbort.current = controller;
    const revision = nextToken();
    dispatch({ type: "START_GRID", requestRevision: revision, expectedInputGeneration: captured.inputGeneration });
    try {
      const preset = getPresetById(captured.presetId);
      const response = await getStressGrid({ planned_design: captured.plannedDraft, fixed_enrollment: captured.frozenEnrollment,
        x_baseline: preset.grid_response.x_baseline, y_dropout: preset.grid_response.y_dropout,
        selected_scenario: { control_event_rate: captured.stressBaseline, dropout: { control: captured.stressDropout, treatment: captured.stressDropout }, effect_override: null },
        preset_id: captured.presetId, provenance_ledger: captured.provenanceLedger }, controller.signal,
      raw => { if (!controller.signal.aborted && captured.inputGeneration === generation.current) setRuns(old => ({ ...old, grid: { requestState: captured, response: raw } })); });
      if (controller.signal.aborted || captured.inputGeneration !== generation.current) return;
      dispatch({ type: "GRID_SUCCESS", response, requestRevision: revision });
    } catch (error) {
      if (controller.signal.aborted || captured.inputGeneration !== generation.current) return;
      dispatch({ type: "GRID_ERROR", error: error instanceof Error ? error.message : String(error), requestRevision: revision });
    }
  }, [nextToken]);
  const evaluateAnalytic = useCallback(async () => {
    const captured = structuredClone(stateRef.current);
    if (captured.inputGeneration !== generation.current || captured.designStatus !== "success" || !captured.frozenEnrollment) return;
    evaluateAbort.current?.abort(); const controller = new AbortController(); evaluateAbort.current = controller;
    const revision = nextToken();
    dispatch({ type: "START_EVALUATE", requestRevision: revision, expectedInputGeneration: captured.inputGeneration });
    try {
      const response = await evaluateScenario(buildStressEvaluationRequest(captured), controller.signal, "analytic");
      if (controller.signal.aborted || captured.inputGeneration !== generation.current) return;
      dispatch({ type: "EVALUATE_SUCCESS", response, requestRevision: revision });
    } catch (error) {
      if (controller.signal.aborted || captured.inputGeneration !== generation.current) return;
      dispatch({ type: "EVALUATE_ERROR", error: error instanceof Error ? error.message : String(error), requestRevision: revision });
    }
  }, [nextToken]);
  useEffect(() => {
    if (state.designStatus !== "success") return;
    const expectedGeneration = state.inputGeneration; let active = true;
    const cancelTimer = scheduleDebounced(() => {
      if (!active || generation.current !== expectedGeneration) return;
      cancelRefresh.current = null; void evaluateAnalytic(); void loadGrid();
    }, 350);
    const cancel = () => { active = false; cancelTimer(); };
    cancelRefresh.current = cancel;
    return () => { cancel(); if (cancelRefresh.current === cancel) cancelRefresh.current = null; };
  }, [state.inputGeneration, state.designStatus, evaluateAnalytic, loadGrid]);
  const runSimulation: RunSimulation = useCallback(async (request, signal) => {
    const captured = structuredClone(stateRef.current);
    if (captured.inputGeneration !== generation.current || captured.designStatus !== "success" || !captured.frozenEnrollment) throw new Error("Calculate the current design first.");
    if (getApiMode() !== "live") throw new Error("Monte Carlo requires the live backend; demo values are not replayable.");
    const expected = { planned_design: captured.plannedDraft, fixed_enrollment: captured.frozenEnrollment,
      stress_scenario: { control_event_rate: captured.stressBaseline, dropout: { control: captured.stressDropout, treatment: captured.stressDropout }, effect_override: null }, provenance: captured.provenanceLedger, simulation: request.simulation };
    if (simulationIdentity(request) !== simulationIdentity(expected)) throw new Error("Simulation selection does not match current inputs.");
    cancelRefresh.current?.(); cancelRefresh.current = null;
    if (captured.gridStatus === "stale" || captured.gridStatus === "idle" || captured.gridStatus === "error") void loadGrid();
    evaluateAbort.current?.abort(); const controller = new AbortController(); evaluateAbort.current = controller;
    const abort = () => controller.abort(); signal.addEventListener("abort", abort, { once: true }); if (signal.aborted) controller.abort();
    const revision = nextToken();
    setRuns(old => ({ ...old, evaluation: null }));
    dispatch({ type: "START_EVALUATE", requestRevision: revision, expectedInputGeneration: captured.inputGeneration });
    try {
      const response = await evaluateScenario({ ...buildStressEvaluationRequest(captured), simulation: request.simulation }, controller.signal);
      if (controller.signal.aborted || captured.inputGeneration !== generation.current) throw new DOMException("Simulation aborted", "AbortError");
      const result = { ...parseSimulationResult({ ...response, provenance: response.provenance.field_provenance ?? {} }, request), provenance: response.provenance.field_provenance ?? {}, diagnostics: response.diagnostics ?? [] };
      setRuns(old => ({ ...old, evaluation: { requestState: captured, response: result } }));
      dispatch({ type: "EVALUATE_SUCCESS", response, requestRevision: revision }); return result;
    } catch (error) {
      if (!controller.signal.aborted && captured.inputGeneration === generation.current) dispatch({ type: "EVALUATE_ERROR", error: error instanceof Error ? error.message : String(error), requestRevision: revision });
      throw error;
    } finally { signal.removeEventListener("abort", abort); }
  }, [nextToken, loadGrid]);
  const selection: SimulationSelection | null = state.designStatus === "success" && state.frozenEnrollment ? {
    planned_design: state.plannedDraft, fixed_enrollment: state.frozenEnrollment,
    stress_scenario: { control_event_rate: state.stressBaseline, dropout: { control: state.stressDropout, treatment: state.stressDropout }, effect_override: null }, provenance: state.provenanceLedger,
  } : null;
  const completedGrid = runs.grid ? { requestState: chartState(runs.grid.requestState), response: runs.grid.response } : null;
  const curve = workspaceCurveProps(chartState(state), completedGrid), heatmap = workspaceHeatmapProps(chartState(state), completedGrid);
  const { payload, exportReason } = useMemo((): { payload: ScenarioExportPayload | null; exportReason?: string } => {
    try {
      const options = parseSimulationOptions(simulationDraft.seed, simulationDraft.replicates);
      if (!runs.evaluation || runs.evaluation.response.monte_carlo.seed !== options.seed || runs.evaluation.response.monte_carlo.replicates !== options.replicates) throw new Error("Run the displayed seed and replicate configuration before exporting.");
      return { payload: buildScenarioExport(state, runs) };
    } catch (error) { return { payload: null, exportReason: error instanceof Error ? error.message : "Complete current calculations and a selected simulation before exporting." }; }
  }, [state, runs, simulationDraft]);
  return <main className={styles.workspace}>
    <header className={styles.header}><h1>Better Baseline</h1><p>Trial planning workspace backed by a local calculation service.</p><p><strong>Execution mode:</strong> {getApiMode() === "demo" ? "DEMO — fixtures and client calculations; no backend execution" : "LIVE — fresh calculations require the backend service"}</p></header>
    <PresetSelector selectedPresetId={state.presetId} onSelectPreset={selectPreset} onResetPreset={() => selectPreset()} />
    <HistoricalCaseStudy onLoadExample={selectPreset} />
    <div className={styles.planningGrid}>
    <section className={styles.planning} aria-labelledby="planned-heading"><h2 id="planned-heading">Planned design and enrollment locking</h2>
      <DesignForm key={`${state.presetId}:${formResetKey}`} initialAssumptions={getPresetById(state.presetId).planned_design} presetId={state.presetId} onCalculate={calculate} onDraftChange={changePlanned} isCalculating={state.designStatus === "calculating"} error={state.designError} submitLabel="Calculate & Lock Design" />
    </section>
    <DesignSummary result={state.calculatedDesign} isStale={state.designStatus !== "success"} isCalculating={state.designStatus === "calculating"} error={state.designError} />
    </div>
    <div className={styles.stressWorkspace}>
    <StressControls frozenEnrollment={state.frozenEnrollment} stressBaseline={state.stressBaseline} stressDropout={state.stressDropout} onBaselineChange={changeBaseline} onDropoutChange={changeDropout} onEvaluate={() => { void evaluateAnalytic(); }} evaluateStatus={state.evaluateStatus} evaluateError={state.evaluateError} isCalculating={state.designStatus !== "success"} />
    <section className={styles.gridRequest} aria-labelledby="grid-heading"><h2 id="grid-heading">Analytic chart requests</h2><button type="button" onClick={() => { void loadGrid(); }} disabled={state.designStatus !== "success" || state.gridStatus === "loading"}>{state.gridStatus === "loading" ? "Loading Grid..." : "Load grid response from backend"}</button><span> Status: {state.gridStatus.toUpperCase()}</span>{state.gridError && <p role="alert">{state.gridError}</p>}</section>
    </div>
    <DesignComparison {...workspaceComparisonProps(chartState(state), completedGrid)} />
    <div className={styles.analyticsGrid}>
    <PowerCurve {...curve} onSelectBaseline={changeBaseline} />
    <StressHeatmap {...heatmap} onSelectPoint={selectPoint} />
    </div>
    <div className={styles.simulation} onChangeCapture={event => {
      if (!(event.target instanceof HTMLInputElement)) return;
      const fields = event.currentTarget.querySelectorAll<HTMLInputElement>('input[type="text"]'); if (fields.length !== 2) return;
      const next = { seed: fields[0].value, replicates: fields[1].value };
      const pointers = [next.seed !== simulationDraft.seed ? "/simulation/seed" : "", next.replicates !== simulationDraft.replicates ? "/simulation/replicates" : ""].filter(Boolean);
      if (!pointers.length) return; changeInputs(); setSimulationDraft(next); dispatch({ type: "UPDATE_SIMULATION_PROVENANCE", pointers });
    }}><MonteCarloPanel key={`${state.presetId}:${formResetKey}`} selection={selection} runSimulation={runSimulation} unavailableReason={getApiMode() === "demo" ? "Live simulation is unavailable in demo mode." : undefined} /></div>
    <ScenarioExport payload={payload} unavailableReason={exportReason} />
    <section className={styles.provenance} aria-labelledby="provenance-heading"><h2 id="provenance-heading">Field provenance and audit trail</h2><p>Current result hash: <code>{state.displayedInputsHash ?? "stale/unhashed"}</code></p>
      <div className={styles.tableScroll} role="region" aria-label="Active field provenance table" tabIndex={0}><table><caption>Active field provenance</caption><thead><tr><th scope="col">Field</th><th scope="col">Source</th><th scope="col">Description</th></tr></thead><tbody>{Object.entries(state.provenanceLedger).map(([field, source]) => <tr key={field}><th scope="row">{field}</th><td>{source.source}</td><td>{source.description}{source.source_url && <> — <a href={source.source_url}>{source.source_url}</a></>}</td></tr>)}</tbody></table></div>
    </section><MethodDisclosures />
  </main>;
}
