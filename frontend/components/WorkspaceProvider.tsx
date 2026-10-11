"use client";

import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useMemo, useReducer, useRef, useState, type Dispatch, type ReactNode, type SetStateAction } from "react";
import { calculateDesign, evaluateScenario, getApiMode, getStressGrid } from "@/lib/api";
import type { CalculateRequest } from "@/lib/contracts";
import type { WorkspaceState } from "@/lib/workspace-contracts";
import { getPresetById } from "@/lib/presets";
import { plannedFieldUpdateAction } from "@/lib/workspace-planning";
import { assumptionsToDraft, type DraftField, type PlanningDraft } from "@/lib/validation";
import { buildStressEvaluationRequest, initializeWorkspaceState, workspaceReducer } from "@/lib/workspace-state";
import { scheduleDebounced } from "@/lib/debounce";
import { buildScenarioExport, type ExportRuns, type ScenarioExportPayload } from "@/lib/export";
import { parseSimulationOptions, parseSimulationResult, simulationIdentity, type RunSimulation, type SimulationRequest, type SimulationSelection } from "@/lib/simulation-client";
import type { DesignFormUIState } from "./DesignForm";
import type { MonteCarloUIState } from "./MonteCarloPanel";

const emptyRuns = (): ExportRuns => ({ design: null, evaluation: null, grid: null });
const initialSimulationUI = (): MonteCarloUIState => ({ seed: "42", replicates: "10000", snapshot: null, pendingIdentity: null, pendingRequestId: null, failure: null });
const initialDesignUI = (presetId: string): DesignFormUIState => ({ draft: assumptionsToDraft(getPresetById(presetId).planned_design), errors: {}, submitted: false, pending: false, callbackError: null });

export interface WorkspaceContextValue {
  state: WorkspaceState;
  designUI: DesignFormUIState;
  setDesignUI: Dispatch<SetStateAction<DesignFormUIState>>;
  simulationUI: MonteCarloUIState;
  setSimulationUI: Dispatch<SetStateAction<MonteCarloUIState>>;
  exportFeedback: { error: boolean; message: string } | null;
  setExportFeedback: Dispatch<SetStateAction<{ error: boolean; message: string } | null>>;
  runs: ExportRuns;
  selection: SimulationSelection | null;
  payload: ScenarioExportPayload | null;
  exportReason?: string;
  apiMode: "demo" | "live";
  selectPreset(presetId?: string): void;
  changeBaseline(baseline: number): void;
  changeDropout(dropout: number): void;
  selectPoint(point: { baseline: number; dropout: number }): void;
  changePlanned(draft: PlanningDraft, field: DraftField): void;
  changeSimulationOptions(next: { seed: string; replicates: string }): void;
  onSimulationRequestStart(requestId: string): void;
  onSimulationRequestFinish(requestId: string): void;
  isSimulationRequestCurrent(requestId: string): boolean;
  calculate(request: CalculateRequest): Promise<void>;
  loadGrid(): Promise<void>;
  evaluateAnalytic(): Promise<void>;
  runSimulation: RunSimulation;
}

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(workspaceReducer, undefined, () => initializeWorkspaceState("baseline-collapse-v1"));
  const [runs, setRuns] = useState<ExportRuns>(emptyRuns);
  const [designUI, setDesignUI] = useState<DesignFormUIState>(() => initialDesignUI("baseline-collapse-v1"));
  const [simulationUI, setSimulationUI] = useState<MonteCarloUIState>(initialSimulationUI);
  const [exportFeedback, setExportFeedback] = useState<WorkspaceContextValue["exportFeedback"]>(null);
  const simulationRequestId = useRef<string | null>(null);
  const stateRef = useRef(state), generation = useRef(state.inputGeneration), token = useRef(0);
  const cancelRefresh = useRef<(() => void) | null>(null);
  const calculateAbort = useRef<AbortController | null>(null), evaluateAbort = useRef<AbortController | null>(null), gridAbort = useRef<AbortController | null>(null);
  const nextToken = useCallback(() => { token.current = Math.max(token.current, stateRef.current.requestRevision) + 1; return token.current; }, []);
  useLayoutEffect(() => { stateRef.current = state; }, [state]);
  useEffect(() => () => { cancelRefresh.current?.(); calculateAbort.current?.abort(); evaluateAbort.current?.abort(); gridAbort.current?.abort(); }, []);

  const changeInputs = useCallback(() => {
    generation.current++; cancelRefresh.current?.(); calculateAbort.current?.abort(); evaluateAbort.current?.abort(); gridAbort.current?.abort();
    simulationRequestId.current = null;
    setSimulationUI(current => current.pendingRequestId ? { ...current, pendingIdentity: null, pendingRequestId: null } : current);
  }, []);
  const selectPreset = useCallback((presetId?: string) => {
    changeInputs(); setRuns(emptyRuns()); setSimulationUI(initialSimulationUI()); setDesignUI(initialDesignUI(presetId ?? stateRef.current.presetId)); setExportFeedback(null);
    dispatch(presetId ? { type: "LOAD_PRESET", presetId } : { type: "RESET_TO_PRESET" });
  }, [changeInputs]);
  const changeBaseline = useCallback((baseline: number) => { changeInputs(); dispatch({ type: "UPDATE_STRESS_BASELINE", baseline }); }, [changeInputs]);
  const changeDropout = useCallback((dropout: number) => { changeInputs(); dispatch({ type: "UPDATE_STRESS_DROPOUT", dropout }); }, [changeInputs]);
  const selectPoint = useCallback((point: { baseline: number; dropout: number }) => { changeInputs(); dispatch({ type: "SELECT_STRESS_POINT", ...point }); }, [changeInputs]);
  const changePlanned = useCallback((draft: PlanningDraft, field: DraftField) => { changeInputs(); dispatch(plannedFieldUpdateAction(draft, field, stateRef.current.presetId)); }, [changeInputs]);
  const changeSimulationOptions = useCallback((next: { seed: string; replicates: string }) => {
    const pointers = [next.seed !== simulationUI.seed ? "/simulation/seed" : "", next.replicates !== simulationUI.replicates ? "/simulation/replicates" : ""].filter(Boolean);
    if (!pointers.length) return;
    changeInputs(); setSimulationUI(currentUI => ({ ...currentUI, ...next })); dispatch({ type: "UPDATE_SIMULATION_PROVENANCE", pointers });
  }, [changeInputs, simulationUI.seed, simulationUI.replicates]);
  const onSimulationRequestStart = useCallback((requestId: string) => { simulationRequestId.current = requestId; }, []);
  const onSimulationRequestFinish = useCallback((requestId: string) => { if (simulationRequestId.current === requestId) simulationRequestId.current = null; }, []);
  const isSimulationRequestCurrent = useCallback((requestId: string) => simulationRequestId.current === requestId, []);

  const calculate = useCallback(async (request: CalculateRequest) => {
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
  }, [changeInputs, nextToken]);

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

  const runSimulation: RunSimulation = useCallback(async (request: SimulationRequest, signal: AbortSignal) => {
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
  const exportModel = useMemo((): { payload: ScenarioExportPayload | null; exportReason?: string } => {
    try {
      const options = parseSimulationOptions(simulationUI.seed, simulationUI.replicates);
      if (!runs.evaluation || runs.evaluation.response.monte_carlo.seed !== options.seed || runs.evaluation.response.monte_carlo.replicates !== options.replicates) throw new Error("Run the displayed seed and replicate configuration before exporting.");
      return { payload: buildScenarioExport(state, runs) };
    } catch (error) { return { payload: null, exportReason: error instanceof Error ? error.message : "Complete current calculations and a selected simulation before exporting." }; }
  }, [state, runs, simulationUI.seed, simulationUI.replicates]);
  const value: WorkspaceContextValue = { state, designUI, setDesignUI, simulationUI, setSimulationUI, exportFeedback, setExportFeedback, runs, selection, ...exportModel, apiMode: getApiMode(), selectPreset, changeBaseline, changeDropout, selectPoint, changePlanned, changeSimulationOptions, onSimulationRequestStart, onSimulationRequestFinish, isSimulationRequestCurrent, calculate, loadGrid, evaluateAnalytic, runSimulation };
  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspace() {
  const value = useContext(WorkspaceContext);
  if (!value) throw new Error("useWorkspace must be used inside WorkspaceProvider.");
  return value;
}

export function useWorkspaceCharts() {
  const { state, runs } = useWorkspace();
  const chartState = { ...state, requestRevision: state.inputGeneration };
  const completedGrid = runs.grid ? { requestState: { ...runs.grid.requestState, requestRevision: runs.grid.requestState.inputGeneration }, response: runs.grid.response } : null;
  return { chartState, completedGrid };
}
