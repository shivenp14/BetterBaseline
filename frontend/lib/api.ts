import { getPresetById } from "./presets";
import type {
  CalculateRequest, CalculateResponse, EvaluateRequest, EvaluateResponse,
  GridRequest, GridResponse, Provenance,
} from "./contracts";
import type { ProvenanceLedger } from "./workspace-contracts";
import { computeLiveDesign, computeLiveEvaluation, computeLiveGrid } from "./statistical-engine";

export interface ExtendedCalculateRequest extends CalculateRequest {
  provenance_ledger?: ProvenanceLedger;
}
export interface ExtendedEvaluateRequest extends EvaluateRequest {
  provenance_ledger?: ProvenanceLedger;
}
export interface ExtendedGridRequest extends GridRequest {
  provenance_ledger?: ProvenanceLedger;
}

type ApiMode = "live" | "demo";
const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

function omitKeys<T extends object, K extends keyof T>(value: T, ...keys: K[]): Omit<T, K> {
  const result = { ...value } as Record<string, unknown>;
  for (const key of keys) delete result[String(key)];
  return result as Omit<T, K>;
}

export function getApiMode(): ApiMode {
  return process.env.NEXT_PUBLIC_API_MODE === "demo" ? "demo" : "live";
}

function backendProvenance(ledger?: ProvenanceLedger): Provenance {
  return {
    scenario_id: "backend-execution",
    scenario_kind: "synthetic",
    label: "Backend calculation",
    source: { type: "synthetic", citation_url: null, source_location: null },
    endpoint_type: "binary_undesirable_event",
    follow_up_label: "As specified by assumptions",
    method_version: "binary-v1",
    generated_by: "backend_service",
    field_provenance: ledger,
  };
}

function demoResult<T extends { mock: boolean; execution?: { mode: "backend" | "demo"; label: string } }>(value: T): T {
  return { ...value, mock: true, execution: { mode: "demo", label: "Demo only — not backend execution" } };
}

function backendResult<T extends { mock: boolean; execution?: { mode: "backend" | "demo"; label: string } }>(value: T): T {
  return { ...value, mock: false, execution: { mode: "backend", label: "Calculated by the local backend service" } };
}

async function readResponse<T>(response: Response): Promise<T> {
  let body: Record<string, unknown> | null;
  try {
    body = await response.json() as Record<string, unknown>;
  } catch (failure) {
    if (failure instanceof Error && failure.name === "AbortError") throw failure;
    body = null;
  }
  if (!response.ok) {
    const envelope = body?.error as { code?: string; message?: string; field?: string; recoverable?: boolean } | undefined;
    const detail = typeof body?.detail === "string" ? body.detail : undefined;
    const message = envelope?.message ?? detail ?? `Backend request failed (${response.status})`;
    const error = new Error(envelope?.code ? `${envelope.code}: ${message}` : message);
    Object.assign(error, { status: response.status, code: envelope?.code, field: envelope?.field, recoverable: envelope?.recoverable });
    throw error;
  }
  if (!body) throw new Error("Backend returned an empty or invalid JSON response");
  return body as T;
}

async function post<T>(path: string, payload: unknown, signal?: AbortSignal): Promise<T> {
  if (signal?.aborted) throw new DOMException("Request aborted", "AbortError");
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(payload),
    signal,
  });
  return readResponse<T>(response);
}

function axes(values: number[], name: string): { min: number; max: number; steps: number } {
  if (values.length < 2) throw new Error(`${name} axis requires at least two points`);
  const step = values[1] - values[0];
  if (step <= 0 || values.some((value, index) => index > 0 && Math.abs(value - values[0] - step * index) > 1e-8)) {
    throw new Error(`${name} axis must be evenly spaced for the backend grid contract`);
  }
  return { min: values[0], max: values[values.length - 1], steps: values.length };
}

export async function calculateDesign(request: ExtendedCalculateRequest, signal?: AbortSignal): Promise<CalculateResponse> {
  if (getApiMode() === "demo") {
    if (signal?.aborted) throw new DOMException("Calculation aborted", "AbortError");
    const preset = getPresetById(request.preset_id);
    const response = preset && matchesPresetDesign(request)
      ? { ...preset.design_response, provenance: { ...preset.design_response.provenance, field_provenance: request.provenance_ledger } }
      : computeLiveDesign(request, request.provenance_ledger);
    return demoResult(response);
  }
  const assumptions = omitKeys(request, "preset_id", "provenance_ledger");
  const result = await post<Omit<CalculateResponse, "provenance" | "mock">>("/api/v1/design/calculate", assumptions, signal);
  return backendResult({ ...result, provenance: backendProvenance(request.provenance_ledger), mock: false });
}

export async function evaluateScenario(request: ExtendedEvaluateRequest, signal?: AbortSignal): Promise<EvaluateResponse> {
  if (getApiMode() === "demo") {
    if (signal?.aborted) throw new DOMException("Evaluation aborted", "AbortError");
    const preset = getPresetById(request.preset_id);
    const response = preset && matchesPresetInputs(request)
      ? { ...preset.evaluate_response, provenance: { ...preset.evaluate_response.provenance, field_provenance: request.provenance_ledger } }
      : computeLiveEvaluation(request.planned_design, request.fixed_enrollment, request.stress_scenario.control_event_rate,
          request.stress_scenario.dropout.control, request.provenance_ledger, request.stress_scenario.effect_override);
    return demoResult(response);
  }
  const provenance_ledger = request.provenance_ledger;
  const acceptedFields = omitKeys(request, "preset_id", "provenance_ledger");
  const payload = { ...acceptedFields, provenance: provenance_ledger ?? {} };
  const result = await post<Omit<EvaluateResponse, "provenance" | "mock"> & { provenance?: ProvenanceLedger }>("/api/v1/scenarios/evaluate", payload, signal);
  const { provenance: ledgerFromBackend, ...core } = result;
  return backendResult({ ...core, provenance: backendProvenance(ledgerFromBackend ?? provenance_ledger), mock: false });
}

export async function getStressGrid(request: ExtendedGridRequest, signal?: AbortSignal): Promise<GridResponse> {
  if (getApiMode() === "demo") {
    if (signal?.aborted) throw new DOMException("Grid request aborted", "AbortError");
    const preset = getPresetById(request.preset_id);
    const ledger = request.provenance_ledger ?? preset?.provenance;
    const isDefault = preset && preset.planned_design.model_version === request.planned_design.model_version &&
      preset.planned_design.control_event_rate === request.planned_design.control_event_rate &&
      preset.planned_design.effect.kind === request.planned_design.effect.kind &&
      preset.planned_design.effect.value === request.planned_design.effect.value &&
      preset.planned_design.alpha === request.planned_design.alpha &&
      preset.planned_design.target_power === request.planned_design.target_power &&
      preset.planned_design.allocation_ratio === request.planned_design.allocation_ratio &&
      preset.planned_design.dropout.control === request.planned_design.dropout.control &&
      preset.planned_design.dropout.treatment === request.planned_design.dropout.treatment &&
      preset.fixed_enrollment.control === request.fixed_enrollment.control &&
      preset.fixed_enrollment.treatment === request.fixed_enrollment.treatment &&
      sameArray(preset.grid_response.x_baseline, request.x_baseline) && sameArray(preset.grid_response.y_dropout, request.y_dropout);
    const selectedScenario = request.selected_scenario ?? {
      control_event_rate: request.planned_design.control_event_rate,
      dropout: request.planned_design.dropout,
      effect_override: null,
    };
    const response = isDefault && !request.selected_scenario ? preset.grid_response : computeLiveGrid(request.planned_design, request.fixed_enrollment,
      request.x_baseline, request.y_dropout, { baseline: selectedScenario.control_event_rate, dropout: selectedScenario.dropout.control }, selectedScenario.effect_override);
    return demoResult({ ...response, provenance: { ...response.provenance, field_provenance: ledger } });
  }

  const payload = {
    planned_design: request.planned_design,
    fixed_enrollment: request.fixed_enrollment,
    x_baseline: axes(request.x_baseline, "baseline"),
    y_dropout: axes(request.y_dropout, "dropout"),
    selected_scenario: request.selected_scenario ?? {
      control_event_rate: request.planned_design.control_event_rate,
      dropout: request.planned_design.dropout,
      effect_override: null,
    },
  };
  const result = await post<Record<string, unknown>>("/api/v1/scenarios/grid", payload, signal);
  const point = (raw: unknown) => {
    const value = raw as { p_control: number; dropout: number };
    return { baseline: value.p_control, dropout: value.dropout };
  };
  const normalized = {
    ...result,
    grid_label: "expected_count_approximation" as const,
    planned_point: point(result.planned_point),
    selected_point: result.selected_point === null || result.selected_point === undefined
      ? null
      : point(result.selected_point),
    frontier_points: ((result.frontier_points ?? []) as unknown[]).map(point),
    provenance: backendProvenance(request.provenance_ledger ?? {}),
    mock: false,
  } as unknown as GridResponse;
  return backendResult(normalized);
}

function sameArray(a: number[], b: number[]): boolean {
  return a.length === b.length && a.every((value, index) => value === b[index]);
}

function matchesPresetDesign(request: ExtendedCalculateRequest): boolean {
  const p = getPresetById(request.preset_id)?.planned_design;
  return !!p && p.model_version === request.model_version && p.control_event_rate === request.control_event_rate &&
    p.effect.kind === request.effect.kind && p.effect.value === request.effect.value && p.alpha === request.alpha &&
    p.target_power === request.target_power && p.allocation_ratio === request.allocation_ratio &&
    p.dropout.control === request.dropout.control && p.dropout.treatment === request.dropout.treatment;
}

function matchesPresetInputs(request: ExtendedEvaluateRequest): boolean {
  const preset = getPresetById(request.preset_id);
  if (!preset) return false;
  const p = preset.planned_design, s = preset.stress_scenario, f = preset.fixed_enrollment;
  const override = s.effect_override;
  const requestedOverride = request.stress_scenario.effect_override;
  const overrideMatches = override === null
    ? requestedOverride === null
    : requestedOverride !== null && override.kind === requestedOverride.kind && override.value === requestedOverride.value;
  return p.control_event_rate === request.planned_design.control_event_rate &&
    p.effect.kind === request.planned_design.effect.kind && p.effect.value === request.planned_design.effect.value &&
    p.alpha === request.planned_design.alpha && p.target_power === request.planned_design.target_power &&
    p.allocation_ratio === request.planned_design.allocation_ratio &&
    p.dropout.control === request.planned_design.dropout.control &&
    p.dropout.treatment === request.planned_design.dropout.treatment &&
    f.control === request.fixed_enrollment.control && f.treatment === request.fixed_enrollment.treatment &&
    s.control_event_rate === request.stress_scenario.control_event_rate &&
    s.dropout.control === request.stress_scenario.dropout.control &&
    s.dropout.treatment === request.stress_scenario.dropout.treatment && overrideMatches &&
    request.simulation.replicates === preset.simulation.replicates && request.simulation.seed === preset.simulation.seed;
}
