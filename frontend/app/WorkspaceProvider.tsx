"use client";

import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useMemo, useReducer, useRef, useState, type ReactNode } from "react";
import { calculateDesign, evaluateScenario, getApiMode, getStressGrid } from "@/lib/api";
import type { CalculateRequest } from "@/lib/contracts";
import type { WorkspaceState } from "@/lib/workspace-contracts";
import { getPresetById } from "@/lib/presets";
import { plannedFieldUpdateAction } from "@/lib/workspace-planning";
import { assumptionsToDraft, type DraftField, type PlanningDraft } from "@/lib/validation";
import { buildStressEvaluationRequest, initializeWorkspaceState, workspaceReducer } from "@/lib/workspace-state";
import { scheduleDebounced } from "@/lib/debounce";
import { buildScenarioExport, type ExportRuns, type ScenarioExportPayload } from "@/lib/export";
import { parseSimulationOptions, parseSimulationResult, simulationIdentity, type RunSimulation, type SimulationResult, type SimulationSelection } from "@/lib/simulation-client";
import { workspaceCurveProps } from "@/components/PowerCurve";
import { workspaceHeatmapProps } from "@/components/StressHeatmap";

const chartState = (state: WorkspaceState): WorkspaceState => ({ ...state, requestRevision: state.inputGeneration });
const emptyRuns = (): ExportRuns => ({ design: null, evaluation: null, grid: null });
type SimulationDraft = { seed: string; replicates: string };
interface WorkspaceValue {
  state: WorkspaceState; presetDraft: PlanningDraft; formResetKey: number; runs: ExportRuns; simulationDraft: SimulationDraft;
  simulationStatus: "idle" | "running" | "error"; simulationError: string | null; simulationResult: SimulationResult | null; simulationResultIdentity: string | null;
  selection: SimulationSelection | null; completedGrid: { requestState: WorkspaceState; response: NonNullable<ExportRuns["grid"]>["response"] } | null;
  curve: ReturnType<typeof workspaceCurveProps>; heatmap: ReturnType<typeof workspaceHeatmapProps>;
  payload: ScenarioExportPayload | null; exportReason?: string;
  selectPreset: (presetId?: string) => void; changeBaseline: (baseline: number) => void; changeDropout: (dropout: number) => void;
  selectPoint: (point: { baseline: number; dropout: number }) => void; changePlanned: (draft: PlanningDraft, field: DraftField) => void;
  calculate: (request: CalculateRequest) => Promise<void>; loadGrid: () => Promise<void>; evaluateAnalytic: () => Promise<void>;
  changeSimulationDraft: (draft: SimulationDraft) => void; runSimulation: RunSimulation;
}
const Context = createContext<WorkspaceValue | null>(null);
export function useWorkspace() { const value = useContext(Context); if (!value) throw new Error("WorkspaceProvider is missing."); return value; }

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(workspaceReducer, undefined, () => initializeWorkspaceState("baseline-collapse-v1"));
  const [formResetKey, setFormResetKey] = useState(0), [presetDraft, setPresetDraft] = useState(() => assumptionsToDraft(initializeWorkspaceState("baseline-collapse-v1").plannedDraft));
  const [runs, setRuns] = useState<ExportRuns>(emptyRuns), [simulationDraft, setSimulationDraft] = useState<SimulationDraft>({ seed: "42", replicates: "10000" });
  const [simulationStatus, setSimulationStatus] = useState<"idle" | "running" | "error">("idle"), [simulationError, setSimulationError] = useState<string | null>(null);
  const [simulationResult, setSimulationResult] = useState<SimulationResult | null>(null), [simulationResultIdentity, setSimulationResultIdentity] = useState<string | null>(null);
  const stateRef = useRef(state), generation = useRef(state.inputGeneration), token = useRef(0), cancelRefresh = useRef<(() => void) | null>(null);
  const calculateAbort = useRef<AbortController | null>(null), evaluateAbort = useRef<AbortController | null>(null), gridAbort = useRef<AbortController | null>(null), simulationAbort = useRef<AbortController | null>(null);
  const nextToken = useCallback(() => { token.current = Math.max(token.current, stateRef.current.requestRevision) + 1; return token.current; }, []);
  useLayoutEffect(() => { stateRef.current = state; }, [state]);
  useEffect(() => () => { calculateAbort.current?.abort(); evaluateAbort.current?.abort(); gridAbort.current?.abort(); simulationAbort.current?.abort(); }, []);
  function changeInputs() { generation.current++; cancelRefresh.current?.(); calculateAbort.current?.abort(); evaluateAbort.current?.abort(); gridAbort.current?.abort(); simulationAbort.current?.abort(); setSimulationStatus("idle"); setSimulationError(null); }
  function selectPreset(presetId?: string) {
    changeInputs(); setRuns(emptyRuns()); setSimulationResult(null); setSimulationResultIdentity(null); setSimulationDraft({ seed: "42", replicates: "10000" }); setPresetDraft(assumptionsToDraft(getPresetById(presetId ?? stateRef.current.presetId).planned_design)); setFormResetKey(k => k + 1);
    dispatch(presetId ? { type: "LOAD_PRESET", presetId } : { type: "RESET_TO_PRESET" });
  }
  function changeBaseline(baseline: number) { changeInputs(); dispatch({ type: "UPDATE_STRESS_BASELINE", baseline }); }
  function changeDropout(dropout: number) { changeInputs(); dispatch({ type: "UPDATE_STRESS_DROPOUT", dropout }); }
  function selectPoint(point: { baseline: number; dropout: number }) { changeInputs(); dispatch({ type: "SELECT_STRESS_POINT", ...point }); }
  function changePlanned(draft: PlanningDraft, field: DraftField) { setPresetDraft(draft); changeInputs(); dispatch(plannedFieldUpdateAction(draft, field, stateRef.current.presetId)); }
  async function calculate(request: CalculateRequest) {
    const captured = structuredClone(stateRef.current); if (captured.inputGeneration !== generation.current) return;
    changeInputs(); setRuns(emptyRuns()); const controller = new AbortController(); calculateAbort.current = controller;
    const revision = nextToken(), expected = generation.current; dispatch({ type: "START_CALCULATE", requestRevision: revision, expectedInputGeneration: captured.inputGeneration });
    try {
      const response = await calculateDesign({ ...request, provenance_ledger: captured.provenanceLedger }, controller.signal);
      if (controller.signal.aborted || generation.current !== expected) return;
      const canonical = { ...response, provenance: response.provenance.field_provenance ?? {}, diagnostics: response.diagnostics ?? [] }; delete (canonical as Partial<typeof canonical>).mock; delete canonical.execution;
      setRuns(old => ({ ...old, design: { requestState: captured, response: canonical } })); dispatch({ type: "CALCULATE_SUCCESS", response, requestRevision: revision });
    } catch (error) { if (!controller.signal.aborted && generation.current === expected) dispatch({ type: "CALCULATE_ERROR", error: error instanceof Error ? error.message : String(error), requestRevision: revision }); }
  }
  const loadGrid = useCallback(async () => {
    const captured = structuredClone(stateRef.current); if (captured.inputGeneration !== generation.current || captured.designStatus !== "success" || !captured.frozenEnrollment) return;
    gridAbort.current?.abort(); const controller = new AbortController(); gridAbort.current = controller; const revision = nextToken();
    dispatch({ type: "START_GRID", requestRevision: revision, expectedInputGeneration: captured.inputGeneration });
    try {
      const preset = getPresetById(captured.presetId);
      const response = await getStressGrid({ planned_design: captured.plannedDraft, fixed_enrollment: captured.frozenEnrollment,
        x_baseline: preset.grid_response.x_baseline, y_dropout: preset.grid_response.y_dropout,
        selected_scenario: { control_event_rate: captured.stressBaseline, dropout: { control: captured.stressDropout, treatment: captured.stressDropout }, effect_override: null },
        preset_id: captured.presetId, provenance_ledger: captured.provenanceLedger }, controller.signal,
      raw => { if (!controller.signal.aborted && captured.inputGeneration === generation.current) setRuns(old => ({ ...old, grid: { requestState: captured, response: raw } })); });
      if (controller.signal.aborted || captured.inputGeneration !== generation.current) return; dispatch({ type: "GRID_SUCCESS", response, requestRevision: revision });
    } catch (error) { if (!controller.signal.aborted && captured.inputGeneration === generation.current) dispatch({ type: "GRID_ERROR", error: error instanceof Error ? error.message : String(error), requestRevision: revision }); }
  }, [nextToken]);
  const evaluateAnalytic = useCallback(async () => {
    cancelRefresh.current?.(); cancelRefresh.current = null;
    const captured = structuredClone(stateRef.current); if (captured.inputGeneration !== generation.current || captured.designStatus !== "success" || !captured.frozenEnrollment) return;
    evaluateAbort.current?.abort(); const controller = new AbortController(); evaluateAbort.current = controller; const revision = nextToken();
    dispatch({ type: "START_EVALUATE", requestRevision: revision, expectedInputGeneration: captured.inputGeneration });
    try { const response = await evaluateScenario(buildStressEvaluationRequest(captured), controller.signal, "analytic");
      if (!controller.signal.aborted && captured.inputGeneration === generation.current) dispatch({ type: "EVALUATE_SUCCESS", response, requestRevision: revision });
    } catch (error) { if (!controller.signal.aborted && captured.inputGeneration === generation.current) dispatch({ type: "EVALUATE_ERROR", error: error instanceof Error ? error.message : String(error), requestRevision: revision }); }
  }, [nextToken]);
  useEffect(() => {
    if (state.designStatus !== "success") return;
    const expectedGeneration = state.inputGeneration; let active = true;
    const cancelTimer = scheduleDebounced(() => { if (!active || generation.current !== expectedGeneration) return; cancelRefresh.current = null; void evaluateAnalytic(); void loadGrid(); }, 350);
    const cancel = () => { active = false; cancelTimer(); }; cancelRefresh.current = cancel;
    return () => { cancel(); if (cancelRefresh.current === cancel) cancelRefresh.current = null; };
  }, [state.inputGeneration, state.designStatus, evaluateAnalytic, loadGrid]);
  function changeSimulationDraft(draft: SimulationDraft) {
    const pointers = [draft.seed !== simulationDraft.seed ? "/simulation/seed" : "", draft.replicates !== simulationDraft.replicates ? "/simulation/replicates" : ""].filter(Boolean);
    if (!pointers.length) return; changeInputs(); setSimulationDraft(draft); dispatch({ type: "UPDATE_SIMULATION_PROVENANCE", pointers });
  }
  const runSimulation: RunSimulation = useCallback(async request => {
    const captured = structuredClone(stateRef.current);
    if (captured.inputGeneration !== generation.current || captured.designStatus !== "success" || !captured.frozenEnrollment) throw new Error("Calculate the current design first.");
    if (getApiMode() !== "live") throw new Error("Monte Carlo requires the live backend; demo values are not replayable.");
    const expected = { planned_design: captured.plannedDraft, fixed_enrollment: captured.frozenEnrollment,
      stress_scenario: { control_event_rate: captured.stressBaseline, dropout: { control: captured.stressDropout, treatment: captured.stressDropout }, effect_override: null }, provenance: captured.provenanceLedger, simulation: request.simulation };
    if (simulationIdentity(request) !== simulationIdentity(expected)) throw new Error("Simulation selection does not match current inputs.");
    cancelRefresh.current?.(); cancelRefresh.current = null;
    if (["stale", "idle", "error"].includes(captured.gridStatus)) void loadGrid();
    evaluateAbort.current?.abort(); simulationAbort.current?.abort(); const controller = new AbortController(); simulationAbort.current = controller;
    setSimulationStatus("running"); setSimulationError(null); const revision = nextToken(); setRuns(old => ({ ...old, evaluation: null }));
    dispatch({ type: "START_EVALUATE", requestRevision: revision, expectedInputGeneration: captured.inputGeneration });
    try {
      const response = await evaluateScenario({ ...buildStressEvaluationRequest(captured), simulation: request.simulation }, controller.signal);
      if (controller.signal.aborted || captured.inputGeneration !== generation.current) throw new DOMException("Simulation aborted", "AbortError");
      const result = { ...parseSimulationResult({ ...response, provenance: response.provenance.field_provenance ?? {} }, request), provenance: response.provenance.field_provenance ?? {}, diagnostics: response.diagnostics ?? [] };
      setSimulationResult(result); setSimulationResultIdentity(simulationIdentity(request));
      setRuns(old => ({ ...old, evaluation: { requestState: captured, response: result } })); dispatch({ type: "EVALUATE_SUCCESS", response, requestRevision: revision }); setSimulationStatus("idle"); return result;
    } catch (error) {
      if (!controller.signal.aborted && captured.inputGeneration === generation.current) { const message = error instanceof Error ? error.message : String(error); setSimulationStatus("error"); setSimulationError(message); dispatch({ type: "EVALUATE_ERROR", error: message, requestRevision: revision }); }
      throw error;
    }
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
      if (!runs.evaluation || runs.evaluation.response.monte_carlo?.seed !== options.seed || runs.evaluation.response.monte_carlo?.replicates !== options.replicates) throw new Error("Run the displayed seed and replicate configuration before exporting.");
      return { payload: buildScenarioExport(state, runs) };
    } catch (error) { return { payload: null, exportReason: error instanceof Error ? error.message : "Complete current calculations and a selected simulation before exporting." }; }
  }, [state, runs, simulationDraft]);
  const value: WorkspaceValue = { state, presetDraft, formResetKey, runs, simulationDraft, simulationStatus, simulationError, simulationResult, simulationResultIdentity, selection, completedGrid, curve, heatmap, payload, exportReason,
    selectPreset, changeBaseline, changeDropout, selectPoint, changePlanned, calculate, loadGrid, evaluateAnalytic, changeSimulationDraft, runSimulation };
  return <Context.Provider value={value}>{children}</Context.Provider>;
}
