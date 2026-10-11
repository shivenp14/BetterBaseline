/** Isolated #75 adapter. #72 supplies the final shared transport; #76 wires it. */
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
function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Malformed simulation response.");
  return Object.fromEntries(Object.entries(value));
}
function number(value: unknown, min = 0, max = Infinity): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value < min || value > max) throw new Error("Invalid simulation number.");
  return value;
}
function integer(value: unknown, min: number, max: number): number {
  const result = number(value, min, max);
  if (!Number.isInteger(result)) throw new Error("Enter a whole number within the allowed range.");
  return result;
}
function text(value: unknown): string {
  if (typeof value !== "string" || !value) throw new Error("Missing simulation metadata.");
  return value;
}
function versions(value: unknown): Record<string, string> {
  return Object.fromEntries(Object.entries(object(value)).map(([key, item]) => [key, text(item)]));
}
function counts(value: unknown, min = 0): FixedEnrollment {
  const v = object(value), control = integer(v.control, min, MAX_ENROLLMENT), treatment = integer(v.treatment, min, MAX_ENROLLMENT);
  if (control !== treatment) throw new Error("Equal arm counts are required.");
  return { control, treatment };
}
function sources(value: unknown): Record<string, FieldSource> {
  return Object.fromEntries(Object.entries(object(value)).map(([key, item]) => {
    const v = object(item), tag = v.source;
    if (tag !== "manual_user" && tag !== "synthetic_preset" && tag !== "protocol_curated" && tag !== "clinicaltrials_registry") throw new Error("Invalid source metadata.");
    const result: FieldSource = { source: tag };
    for (const field of ["description", "retrieved_at", "source_url"] as const) {
      const entry = v[field];
      if (entry !== undefined) {
        if (entry !== null && typeof entry !== "string") throw new Error("Invalid source metadata.");
        result[field] = entry;
      }
    }
    return [key, result];
  }));
}
export function parseSimulationOptions(seed: string, replicates: string) {
  if (!/^\d+$/.test(seed.trim()) || !/^\d+$/.test(replicates.trim())) throw new Error("Seed and replicates must be whole numbers.");
  return { seed: integer(Number(seed), 0, MAX_SEED), replicates: integer(Number(replicates), 1, MAX_REPLICATES) };
}
function probability(value: number, zero = false) {
  number(value, 0, 1);
  if (value >= 1 || (!zero && value === 0)) throw new Error("Scenario rates are outside supported bounds.");
}
function effect(value: Effect, baseline: number) {
  probability(value.value);
  if (value.kind !== "relative_risk" && value.kind !== "absolute_risk_reduction") throw new Error("Unsupported effect.");
  if (value.kind === "absolute_risk_reduction" && value.value >= baseline) throw new Error("Absolute risk reduction must be smaller than selected baseline risk.");
}
export function validateSimulationRequest(request: SimulationRequest): void {
  const d = request.planned_design, s = request.stress_scenario;
  if (d.model_version !== "binary-v1" || d.allocation_ratio !== 1) throw new Error("Only equal-allocation binary-v1 is supported.");
  counts(request.fixed_enrollment, 1);
  for (const scenario of [d, s]) {
    probability(scenario.control_event_rate); probability(scenario.dropout.control, true); probability(scenario.dropout.treatment, true);
    if (scenario.dropout.control !== scenario.dropout.treatment) throw new Error("Symmetric dropout is required.");
  }
  probability(d.alpha); probability(d.target_power);
  if (d.target_power <= d.alpha) throw new Error("Target power must exceed alpha.");
  effect(d.effect, d.control_event_rate); effect(s.effect_override ?? d.effect, s.control_event_rate);
  integer(request.simulation.seed, 0, MAX_SEED); integer(request.simulation.replicates, 1, MAX_REPLICATES);
  if (request.provenance) sources(request.provenance);
}
export function simulationIdentity(request: SimulationRequest): string {
  function ordered(value: unknown): unknown {
    if (Array.isArray(value)) return value.map(ordered);
    if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).sort(([a], [b]) => a.localeCompare(b)).map(([key, item]) => [key, ordered(item)]));
    return value;
  }
  return JSON.stringify(ordered(request));
}
export function parseSimulationResult(value: unknown, request: SimulationRequest): SimulationResult {
  const r = object(value), a = object(r.analytic), metadata = object(r.metadata);
  if (r.model_version !== "binary-v1" || a.method !== "cohen_h_normal_v1") throw new Error("Unsupported simulation model or analytic method.");
  if (!r.monte_carlo) throw new Error("Simulation is unavailable in this response.");
  const m = object(r.monte_carlo);
  if (m.method !== "pooled_two_proportion_z_v1" || m.invalid_test_policy !== "nonrejection_over_all_replicates") throw new Error("Unsupported simulation method or invalid-test policy.");
  const mc: SimulationMetrics = {
    method: "pooled_two_proportion_z_v1", invalid_test_policy: "nonrejection_over_all_replicates",
    significant_two_sided_fraction: number(m.significant_two_sided_fraction, 0, 1), significant_favorable_fraction: number(m.significant_favorable_fraction, 0, 1),
    mcse_two_sided: number(m.mcse_two_sided, 0, .5), mcse_favorable: number(m.mcse_favorable, 0, .5), invalid_test_fraction: number(m.invalid_test_fraction, 0, 1),
    mean_retained_control: number(m.mean_retained_control, 0, request.fixed_enrollment.control), mean_retained_treatment: number(m.mean_retained_treatment, 0, request.fixed_enrollment.treatment),
    mean_control_events: number(m.mean_control_events), mean_treatment_events: number(m.mean_treatment_events),
    seed: integer(m.seed, 0, MAX_SEED), replicates: integer(m.replicates, 1, MAX_REPLICATES), rng: text(m.rng), software_versions: versions(m.software_versions),
  };
  const fixed = counts(metadata.fixed_enrollment, 1);
  if (mc.seed !== request.simulation.seed || mc.replicates !== request.simulation.replicates || fixed.control !== request.fixed_enrollment.control || fixed.treatment !== request.fixed_enrollment.treatment) throw new Error("Simulation response does not match requested seed, replicates or frozen enrollment.");
  if (mc.significant_favorable_fraction > mc.significant_two_sided_fraction || mc.mean_control_events > mc.mean_retained_control || mc.mean_treatment_events > mc.mean_retained_treatment) throw new Error("Inconsistent simulation aggregates.");
  if (!Array.isArray(r.warnings) || !r.warnings.every((item): item is string => typeof item === "string")) throw new Error("Invalid simulation warnings.");
  return { model_version: "binary-v1", monte_carlo: mc,
    analytic: { method: "cohen_h_normal_v1", conditional_power_approx: a.conditional_power_approx === null ? null : number(a.conditional_power_approx, 0, 1), assumed_evaluable_n: counts(a.assumed_evaluable_n) },
    warnings: r.warnings, metadata: { computed_at: text(metadata.computed_at), inputs_hash: text(metadata.inputs_hash), fixed_enrollment: fixed, software_versions: versions(metadata.software_versions) }, provenance: sources(r.provenance) };
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
/** Temporary HTTP seam for isolated acceptance, replaced by #72's shared helper at handoff. */
export function createHttpSimulationTransport(apiBase: string, fetcher: typeof fetch = fetch): SimulationTransport {
  return async (request, signal) => {
    const response = await fetcher(`${apiBase.replace(/\/$/, "")}/api/v1/scenarios/evaluate`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(request), signal });
    const body: unknown = await response.json();
    if (!response.ok) throw new Error(text(object(object(body).error).message));
    return body;
  };
}
