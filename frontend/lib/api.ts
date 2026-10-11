import { presets } from "./mocks";
import type {
  CalculateRequest,
  CalculateResponse,
  EvaluateRequest,
  EvaluateResponse,
  GridRequest,
  GridResponse,
} from "./contracts";

function fixture(presetId: string) {
  return presets.find((preset) => preset.id === presetId) ?? presets[1];
}

/** Local typed mock boundary. This adapter never performs a fetch or other I/O. */
export async function calculateDesign(
  request: CalculateRequest,
): Promise<CalculateResponse> {
  return fixture(request.preset_id).design_response;
}

export async function evaluateScenario(
  request: EvaluateRequest,
): Promise<EvaluateResponse> {
  return fixture(request.preset_id).evaluate_response;
}

export async function getStressGrid(request: GridRequest): Promise<GridResponse> {
  return fixture(request.preset_id).grid_response;
}
