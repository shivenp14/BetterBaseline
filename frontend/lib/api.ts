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

function matchesPresetInputs(request: EvaluateRequest): boolean {
  const preset = getPresetById(request.preset_id);
  if (!preset) return false;
  const p = preset.planned_design;
  const s = preset.stress_scenario;
  const f = preset.fixed_enrollment;

  return (
    p.control_event_rate === request.planned_design.control_event_rate &&
    p.alpha === request.planned_design.alpha &&
    p.target_power === request.planned_design.target_power &&
    p.dropout.control === request.planned_design.dropout.control &&
    f.control === request.fixed_enrollment.control &&
    s.control_event_rate === request.stress_scenario.control_event_rate &&
    s.dropout.control === request.stress_scenario.dropout.control
  );
}

function matchesPresetDesign(request: CalculateRequest): boolean {
  const preset = getPresetById(request.preset_id);
  if (!preset) return false;
  const p = preset.planned_design;
  return (
    p.control_event_rate === request.control_event_rate &&
    p.alpha === request.alpha &&
    p.target_power === request.target_power &&
    p.dropout.control === request.dropout.control
  );
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
    return getPresetById(request.preset_id).design_response;
  }
  return computeLiveDesign(request);
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
    return getPresetById(request.preset_id).evaluate_response;
  }
  return computeLiveEvaluation(
    request.planned_design,
    request.fixed_enrollment,
    request.stress_scenario.control_event_rate,
    request.stress_scenario.dropout.control
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
  const isDefaultPreset =
    preset.planned_design.control_event_rate === request.planned_design.control_event_rate &&
    preset.fixed_enrollment.control === request.fixed_enrollment.control;

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
