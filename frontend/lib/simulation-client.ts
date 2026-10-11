/** #75 validates shared #72 execution; #76 owns production assembly. */
import { evaluateScenario } from "./api";
import type { EvaluateRequest, EvaluateResponse } from "./contracts";
import type { Effect, FixedEnrollment, TrialAssumptions } from "./contracts";
export interface FieldSource {
  source: "manual_user" | "synthetic_preset" | "protocol_curated" | "clinicaltrials_registry";
  description?: string | null; retrieved_at?: string | null; source_url?: string | null;
}
export interface SimulationSelection {
  planned_design: TrialAssumptions; fixed_enrollment: FixedEnrollment;
  stress_scenario: { control_event_rate: number; dropout: { control: number; treatment: number }; effect_override: Effect | null };
  provenance?: Record<string, FieldSource>;
}
export interface SimulationRequest extends SimulationSelection { simulation: { seed: number; replicates: number } }
export interface SimulationMetrics {
  method: "pooled_two_proportion_z_v1"; invalid_test_policy: "nonrejection_over_all_replicates";
  significant_two_sided_fraction: number; significant_favorable_fraction: number;
  mcse_two_sided: number; mcse_favorable: number; invalid_test_fraction: number;
  mean_retained_control: number; mean_retained_treatment: number; mean_control_events: number; mean_treatment_events: number;
  seed: number; replicates: number; rng: string; software_versions: Record<string, string>;
}
export interface SimulationResult {
  model_version: "binary-v1";
  analytic: { method: "cohen_h_normal_v1"; conditional_power_approx: number | null; assumed_evaluable_n: FixedEnrollment };
  monte_carlo: SimulationMetrics; warnings: string[];
  metadata: { computed_at: string; inputs_hash: string; fixed_enrollment: FixedEnrollment; software_versions: Record<string, string> };
  provenance: Record<string, FieldSource>;
}
export type SimulationTransport = (request: SimulationRequest, signal: AbortSignal) => Promise<unknown>;
export type RunSimulation = (request: SimulationRequest, signal: AbortSignal) => Promise<SimulationResult>;
export const MAX_REPLICATES = 100_000, MAX_SEED = 2 ** 32 - 1, MAX_ENROLLMENT = 1_000_000;
export type SimulationErrorCode = "INVALID_MODEL_INPUT" | "UNSUPPORTED_MODEL" | "INVALID_RESPONSE" | "SIMULATION_UNAVAILABLE";
export class SimulationError extends Error {
  constructor(readonly code: SimulationErrorCode, message: string, readonly field: string | null = null) {
    super(message);
    this.name = "SimulationError";
  }
}
export function simulationErrorMessage(error: unknown): string {
  if (error instanceof SimulationError) return `${error.code}${error.field ? ` (${error.field})` : ""}: ${error.message}`;
  return error instanceof Error ? error.message : "Simulation failed. Try again.";
}
function requireRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new SimulationError("INVALID_RESPONSE", "Malformed simulation response.");
  return Object.fromEntries(Object.entries(value));
}
function requireNumber(value: unknown, min = 0, max = Infinity, field: string | null = null): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value < min || value > max) throw new SimulationError("INVALID_MODEL_INPUT", "Enter a finite number within the allowed range.", field);
  return value;
}
function requireInteger(value: unknown, min: number, max: number, field: string | null = null): number {
  const result = requireNumber(value, min, max, field);
  if (!Number.isInteger(result)) throw new SimulationError("INVALID_MODEL_INPUT", "Enter a whole number within the allowed range.", field);
  return result;
}
function requireText(value: unknown): string {
  if (typeof value !== "string" || !value) throw new SimulationError("INVALID_RESPONSE", "Missing simulation metadata.");
  return value;
}
function requireVersions(value: unknown): Record<string, string> {
  return Object.fromEntries(Object.entries(requireRecord(value)).map(([key, item]) => [key, requireText(item)]));
}
function requireCounts(value: unknown, min = 0, field: string | null = null): FixedEnrollment {
  const armCounts = requireRecord(value);
  const control = requireInteger(armCounts.control, min, MAX_ENROLLMENT, field ? `${field}.control` : null);
  const treatment = requireInteger(armCounts.treatment, min, MAX_ENROLLMENT, field ? `${field}.treatment` : null);
  if (control !== treatment) throw new SimulationError("UNSUPPORTED_MODEL", "Equal arm counts are required.", field);
  return { control, treatment };
}
function requireSources(value: unknown): Record<string, FieldSource> {
  return Object.fromEntries(Object.entries(requireRecord(value)).map(([key, item]) => {
    const sourceRecord = requireRecord(item);
    const tag = sourceRecord.source;
    if (tag !== "manual_user" && tag !== "synthetic_preset" && tag !== "protocol_curated" && tag !== "clinicaltrials_registry") throw new SimulationError("INVALID_RESPONSE", "Invalid source metadata.");
    const result: FieldSource = { source: tag };
    for (const field of ["description", "retrieved_at", "source_url"] as const) {
      const entry = sourceRecord[field];
      if (entry !== undefined) {
        if (entry !== null && typeof entry !== "string") throw new SimulationError("INVALID_RESPONSE", "Invalid source metadata.");
        result[field] = entry;
      }
    }
    return [key, result];
  }));
}
export function parseSimulationOptions(seed: string, replicates: string) {
  for (const [field, value] of [["simulation.seed", seed], ["simulation.replicates", replicates]]) {
    if (!/^\d+$/.test(value.trim())) {
      throw new SimulationError("INVALID_MODEL_INPUT", "Seed and replicates must be whole numbers.", field);
    }
  }
  return { seed: requireInteger(Number(seed), 0, MAX_SEED, "simulation.seed"),
    replicates: requireInteger(Number(replicates), 1, MAX_REPLICATES, "simulation.replicates") };
}
function validateProbability(value: number, zero = false, field: string | null = null) {
  requireNumber(value, 0, 1, field);
  if (value >= 1 || (!zero && value === 0)) throw new SimulationError("INVALID_MODEL_INPUT", "Scenario rates are outside supported bounds.", field);
}
function validateEffect(value: Effect, baseline: number, field: string | null = null) {
  validateProbability(value.value, false, field);
  if (value.kind !== "relative_risk" && value.kind !== "absolute_risk_reduction") throw new SimulationError("UNSUPPORTED_MODEL", "Unsupported effect.", field);
  if (value.kind === "absolute_risk_reduction" && value.value >= baseline) throw new SimulationError("INVALID_MODEL_INPUT", "Absolute risk reduction must be smaller than selected baseline risk.", field);
}
export function validateSimulationRequest(request: SimulationRequest): void {
  const plannedDesign = request.planned_design;
  const stressScenario = request.stress_scenario;
  if (plannedDesign.model_version !== "binary-v1" || plannedDesign.allocation_ratio !== 1) {
    throw new SimulationError("UNSUPPORTED_MODEL", "Only equal-allocation binary-v1 is supported.", "planned_design");
  }
  requireCounts(request.fixed_enrollment, 1, "fixed_enrollment");
  for (const [field, scenario] of [["planned_design", plannedDesign], ["stress_scenario", stressScenario]] as const) {
    validateProbability(scenario.control_event_rate, false, `${field}.control_event_rate`);
    validateProbability(scenario.dropout.control, true, `${field}.dropout.control`);
    validateProbability(scenario.dropout.treatment, true, `${field}.dropout.treatment`);
    if (scenario.dropout.control !== scenario.dropout.treatment) {
      throw new SimulationError("UNSUPPORTED_MODEL", "Symmetric dropout is required.", `${field}.dropout`);
    }
  }
  validateProbability(plannedDesign.alpha, false, "planned_design.alpha");
  validateProbability(plannedDesign.target_power, false, "planned_design.target_power");
  if (plannedDesign.target_power <= plannedDesign.alpha) {
    throw new SimulationError("INVALID_MODEL_INPUT", "Target power must exceed alpha.", "planned_design.target_power");
  }
  validateEffect(plannedDesign.effect, plannedDesign.control_event_rate, "planned_design.effect");
  validateEffect(stressScenario.effect_override ?? plannedDesign.effect, stressScenario.control_event_rate, "stress_scenario.effect_override");
  requireInteger(request.simulation.seed, 0, MAX_SEED, "simulation.seed");
  requireInteger(request.simulation.replicates, 1, MAX_REPLICATES, "simulation.replicates");
  if (request.provenance) {
    try {
      requireSources(request.provenance);
    } catch (error) {
      throw new SimulationError("INVALID_MODEL_INPUT", simulationErrorMessage(error), "provenance");
    }
  }
}
export function simulationIdentity(request: SimulationRequest): string {
  function ordered(value: unknown): unknown {
    if (Array.isArray(value)) return value.map(ordered);
    if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).sort(([firstKey], [secondKey]) => firstKey.localeCompare(secondKey)).map(([key, item]) => [key, ordered(item)]));
    return value;
  }
  return JSON.stringify(ordered(request));
}
export function parseSimulationResult(value: unknown, request: SimulationRequest): SimulationResult {
  try {
    return validateSimulationResult(value, request);
  } catch (error) {
    if (error instanceof SimulationError && error.code === "INVALID_MODEL_INPUT") {
      throw new SimulationError("INVALID_RESPONSE", error.message, error.field);
    }
    throw error;
  }
}
function validateSimulationResult(value: unknown, request: SimulationRequest): SimulationResult {
  const response = requireRecord(value);
  const analytic = requireRecord(response.analytic);
  const metadata = requireRecord(response.metadata);
  if (response.model_version !== "binary-v1" || analytic.method !== "cohen_h_normal_v1") throw new SimulationError("UNSUPPORTED_MODEL", "Unsupported simulation model or analytic method.");
  if (!response.monte_carlo) throw new SimulationError("SIMULATION_UNAVAILABLE", "Simulation is unavailable in this response.");
  const monteCarlo = requireRecord(response.monte_carlo);
  if (monteCarlo.method !== "pooled_two_proportion_z_v1" || monteCarlo.invalid_test_policy !== "nonrejection_over_all_replicates") throw new SimulationError("UNSUPPORTED_MODEL", "Unsupported simulation method or invalid-test policy.");
  const metrics: SimulationMetrics = {
    method: "pooled_two_proportion_z_v1", invalid_test_policy: "nonrejection_over_all_replicates",
    significant_two_sided_fraction: requireNumber(monteCarlo.significant_two_sided_fraction, 0, 1), significant_favorable_fraction: requireNumber(monteCarlo.significant_favorable_fraction, 0, 1),
    mcse_two_sided: requireNumber(monteCarlo.mcse_two_sided, 0, .5), mcse_favorable: requireNumber(monteCarlo.mcse_favorable, 0, .5), invalid_test_fraction: requireNumber(monteCarlo.invalid_test_fraction, 0, 1),
    mean_retained_control: requireNumber(monteCarlo.mean_retained_control, 0, request.fixed_enrollment.control), mean_retained_treatment: requireNumber(monteCarlo.mean_retained_treatment, 0, request.fixed_enrollment.treatment),
    mean_control_events: requireNumber(monteCarlo.mean_control_events), mean_treatment_events: requireNumber(monteCarlo.mean_treatment_events),
    seed: requireInteger(monteCarlo.seed, 0, MAX_SEED), replicates: requireInteger(monteCarlo.replicates, 1, MAX_REPLICATES), rng: requireText(monteCarlo.rng), software_versions: requireVersions(monteCarlo.software_versions),
  };
  const fixedEnrollment = requireCounts(metadata.fixed_enrollment, 1);
  if (metrics.seed !== request.simulation.seed || metrics.replicates !== request.simulation.replicates || fixedEnrollment.control !== request.fixed_enrollment.control || fixedEnrollment.treatment !== request.fixed_enrollment.treatment) throw new SimulationError("INVALID_RESPONSE", "Simulation response does not match requested seed, replicates or frozen enrollment.");
  if (metrics.significant_favorable_fraction > metrics.significant_two_sided_fraction || metrics.mean_control_events > metrics.mean_retained_control || metrics.mean_treatment_events > metrics.mean_retained_treatment) throw new SimulationError("INVALID_RESPONSE", "Inconsistent simulation aggregates.");
  if (!Array.isArray(response.warnings) || !response.warnings.every((item): item is string => typeof item === "string")) throw new SimulationError("INVALID_RESPONSE", "Invalid simulation warnings.");
  return { model_version: "binary-v1", monte_carlo: metrics,
    analytic: { method: "cohen_h_normal_v1", conditional_power_approx: analytic.conditional_power_approx === null ? null : requireNumber(analytic.conditional_power_approx, 0, 1), assumed_evaluable_n: requireCounts(analytic.assumed_evaluable_n) },
    warnings: response.warnings, metadata: { computed_at: requireText(metadata.computed_at), inputs_hash: requireText(metadata.inputs_hash), fixed_enrollment: fixedEnrollment, software_versions: requireVersions(metadata.software_versions) }, provenance: requireSources(response.provenance) };
}
export function createSimulationClient(transport: SimulationTransport): RunSimulation {
  return async (request, signal) => {
    validateSimulationRequest(request);
    const snapshot: SimulationRequest = structuredClone(request);
    if (signal.aborted) throw new DOMException("Simulation aborted", "AbortError");
    const response = await transport(snapshot, signal);
    if (signal.aborted) throw new DOMException("Simulation aborted", "AbortError");
    return parseSimulationResult(response, snapshot);
  };
}
/** Use #72's unchanged helper; normalize its app-level provenance envelope. */
export function createSharedSimulationTransport(
  evaluate: (request: EvaluateRequest, signal?: AbortSignal) => Promise<EvaluateResponse> = evaluateScenario,
): SimulationTransport {
  return async (request, signal) => {
    const response = await evaluate({
      planned_design: request.planned_design, fixed_enrollment: request.fixed_enrollment,
      stress_scenario: request.stress_scenario, simulation: request.simulation,
      preset_id: "selected-simulation", provenance_ledger: request.provenance ?? {},
    }, signal);
    if (response.mock !== false || response.execution?.mode !== "backend") {
      throw new SimulationError("SIMULATION_UNAVAILABLE", "Live simulation unavailable: shared API is in demo mode.");
    }
    return { ...response, provenance: response.provenance.field_provenance ?? {} };
  };
}
/** Stable module-level adapter suitable for the #76 parent. */
export const runSelectedSimulation = createSimulationClient(createSharedSimulationTransport());
