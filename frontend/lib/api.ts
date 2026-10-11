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

function fixture(presetId: string) {
  return getPresetById(presetId);
}

export interface ExtendedCalculateRequest extends CalculateRequest {
  provenance_ledger?: ProvenanceLedger;
}

export interface ExtendedEvaluateRequest extends EvaluateRequest {
  provenance_ledger?: ProvenanceLedger;
}

/** Local typed mock boundary. Supports cancelation, provenance inspection, and mock response fetching. */
export async function calculateDesign(
  request: CalculateRequest,
  signal?: AbortSignal
): Promise<CalculateResponse> {
  if (signal?.aborted) {
    throw new DOMException("Calculation aborted", "AbortError");
  }
  // Simulate minimal async microtask debounce
  await new Promise((resolve) => setTimeout(resolve, 10));
  if (signal?.aborted) {
    throw new DOMException("Calculation aborted", "AbortError");
  }
  return fixture(request.preset_id).design_response;
}

export async function evaluateScenario(
  request: EvaluateRequest,
  signal?: AbortSignal
): Promise<EvaluateResponse> {
  if (signal?.aborted) {
    throw new DOMException("Evaluation aborted", "AbortError");
  }
  await new Promise((resolve) => setTimeout(resolve, 10));
  if (signal?.aborted) {
    throw new DOMException("Evaluation aborted", "AbortError");
  }
  return fixture(request.preset_id).evaluate_response;
}

export async function getStressGrid(
  request: GridRequest,
  signal?: AbortSignal
): Promise<GridResponse> {
  if (signal?.aborted) {
    throw new DOMException("Grid request aborted", "AbortError");
  }
  await new Promise((resolve) => setTimeout(resolve, 10));
  if (signal?.aborted) {
    throw new DOMException("Grid request aborted", "AbortError");
  }
  return fixture(request.preset_id).grid_response;
}
