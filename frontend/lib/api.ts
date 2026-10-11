import { getPresetById } from "./presets";
import type {
  CalculateRequest,
  CalculateResponse,
  EvaluateRequest,
  EvaluateResponse,
  GridRequest,
  GridResponse,
} from "./contracts";
import type { ProvenanceLedger } from "./workspace-contracts";
import {
  computeLiveDesign,
  computeLiveEvaluation,
  computeLiveGrid,
} from "./statistical-engine";

export interface ExtendedCalculateRequest extends CalculateRequest {
  provenance_ledger?: ProvenanceLedger;
}

export interface ExtendedEvaluateRequest extends EvaluateRequest {
  provenance_ledger?: ProvenanceLedger;
}

export interface ExtendedGridRequest extends GridRequest {
  provenance_ledger?: ProvenanceLedger;
}

function matchesPresetInputs(request: ExtendedEvaluateRequest): boolean {
  const preset = getPresetById(request.preset_id);
  if (!preset) return false;
  const p = preset.planned_design;
  const s = preset.stress_scenario;
  const f = preset.fixed_enrollment;

  const effectMatches =
    p.effect.kind === request.planned_design.effect.kind &&
    p.effect.value === request.planned_design.effect.value;

  const expectedOverride = s.effect_override;
  const requestedOverride = request.stress_scenario.effect_override;
  const effectOverrideMatches =
    expectedOverride === null
      ? requestedOverride === null
      : requestedOverride !== null &&
        expectedOverride.kind === requestedOverride.kind &&
        expectedOverride.value === requestedOverride.value;

  const simulationMatches =
    preset.simulation.replicates === request.simulation.replicates &&
    preset.simulation.seed === request.simulation.seed;

  return (
    p.model_version === request.planned_design.model_version &&
    p.control_event_rate === request.planned_design.control_event_rate &&
    effectMatches &&
    p.alpha === request.planned_design.alpha &&
    p.target_power === request.planned_design.target_power &&
    p.allocation_ratio === request.planned_design.allocation_ratio &&
    p.dropout.control === request.planned_design.dropout.control &&
    p.dropout.treatment === request.planned_design.dropout.treatment &&
    f.control === request.fixed_enrollment.control &&
    f.treatment === request.fixed_enrollment.treatment &&
    s.control_event_rate === request.stress_scenario.control_event_rate &&
    s.dropout.control === request.stress_scenario.dropout.control &&
    s.dropout.treatment === request.stress_scenario.dropout.treatment &&
    effectOverrideMatches &&
    simulationMatches
  );
}

function matchesPresetDesign(request: ExtendedCalculateRequest): boolean {
  const preset = getPresetById(request.preset_id);
  if (!preset) return false;
  const p = preset.planned_design;
  return (
    p.model_version === request.model_version &&
    p.control_event_rate === request.control_event_rate &&
    p.effect.kind === request.effect.kind &&
    p.effect.value === request.effect.value &&
    p.alpha === request.alpha &&
    p.target_power === request.target_power &&
    p.allocation_ratio === request.allocation_ratio &&
    p.dropout.control === request.dropout.control &&
    p.dropout.treatment === request.dropout.treatment
  );
}

function attachFieldProvenance<T extends { provenance: { field_provenance?: unknown } }>(
  response: T,
  provenanceLedger?: ProvenanceLedger
): T {
  if (!provenanceLedger) return response;
  return {
    ...response,
    provenance: { ...response.provenance, field_provenance: provenanceLedger },
  };
}

function arraysEqual(a: number[], b: number[]): boolean {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) {
    if (a[i] !== b[i]) return false;
  }
  return true;
}

/**
 * Calculates design enrollment and power.
 * If inputs match the unedited preset, returns the exact versioned preset response.
 * If inputs have been customized, performs live Cohen's-h minimum sample size calculation.
 */
export async function calculateDesign(
  request: ExtendedCalculateRequest,
  signal?: AbortSignal
): Promise<CalculateResponse> {
  if (signal?.aborted) {
    throw new DOMException("Calculation aborted", "AbortError");
  }
  await new Promise((resolve) => setTimeout(resolve, 10));
  if (signal?.aborted) {
    throw new DOMException("Calculation aborted", "AbortError");
  }

  if (matchesPresetDesign(request)) {
    return attachFieldProvenance(
      getPresetById(request.preset_id).design_response,
      request.provenance_ledger
    );
  }
  return computeLiveDesign(request, request.provenance_ledger);
}

/**
 * Evaluates stress scenario under fixed enrollment.
 * If inputs match the unedited preset, returns the exact versioned preset response.
 * If stress or design assumptions differ, computes live conditional power at floored expected retention.
 */
export async function evaluateScenario(
  request: ExtendedEvaluateRequest,
  signal?: AbortSignal
): Promise<EvaluateResponse> {
  if (signal?.aborted) {
    throw new DOMException("Evaluation aborted", "AbortError");
  }
  await new Promise((resolve) => setTimeout(resolve, 10));
  if (signal?.aborted) {
    throw new DOMException("Evaluation aborted", "AbortError");
  }

  if (matchesPresetInputs(request)) {
    return attachFieldProvenance(
      getPresetById(request.preset_id).evaluate_response,
      request.provenance_ledger
    );
  }
  return computeLiveEvaluation(
    request.planned_design,
    request.fixed_enrollment,
    request.stress_scenario.control_event_rate,
    request.stress_scenario.dropout.control,
    request.provenance_ledger,
    request.stress_scenario.effect_override
  );
}

/**
 * Generates sensitivity grid.
 * If inputs match the unedited preset, returns the preset grid response.
 * Otherwise, computes the live matrix of power values across axes.
 */
export async function getStressGrid(
  request: ExtendedGridRequest,
  signal?: AbortSignal
): Promise<GridResponse> {
  if (signal?.aborted) {
    throw new DOMException("Grid request aborted", "AbortError");
  }
  await new Promise((resolve) => setTimeout(resolve, 10));
  if (signal?.aborted) {
    throw new DOMException("Grid request aborted", "AbortError");
  }

  const preset = getPresetById(request.preset_id);
  const p = preset.planned_design;
  const isDefaultPreset =
    p.control_event_rate === request.planned_design.control_event_rate &&
    p.effect.kind === request.planned_design.effect.kind &&
    p.effect.value === request.planned_design.effect.value &&
    p.alpha === request.planned_design.alpha &&
    p.target_power === request.planned_design.target_power &&
    p.dropout.control === request.planned_design.dropout.control &&
    preset.fixed_enrollment.control === request.fixed_enrollment.control &&
    arraysEqual(preset.grid_response.x_baseline, request.x_baseline) &&
    arraysEqual(preset.grid_response.y_dropout, request.y_dropout);

  if (isDefaultPreset) {
    return preset.grid_response;
  }

  return computeLiveGrid(
    request.planned_design,
    request.fixed_enrollment,
    request.x_baseline,
    request.y_dropout,
    {
      baseline: request.planned_design.control_event_rate,
      dropout: request.planned_design.dropout.control,
    }
  );
}
