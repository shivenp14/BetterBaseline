import type {
  ApiDesignCalculateResponse,
  ApiExportPayload,
  ApiProvenanceMap,
  ApiScenarioEvaluateResponse,
  ApiScenarioGridResponse,
  CalculateResponse,
  EvaluateResponse,
  GridResponse,
  TrialAssumptions,
} from "./contracts";
import type { ProvenanceLedger, WorkspaceState } from "./workspace-contracts";

/** Canonical backend ExportPayload assembled from current live API responses. */
export interface WorkspaceExportPayload extends Omit<ApiExportPayload, "stress_scenario" | "provenance"> {
  stress_scenario: NonNullable<ApiExportPayload["stress_scenario"]>;
  provenance: ApiProvenanceMap;
  design_result?: ApiDesignCalculateResponse;
  evaluation_result?: ApiScenarioEvaluateResponse;
  grid_result?: ApiScenarioGridResponse;
}

type ProvenanceRecord = ApiProvenanceMap[string];
type CanonicalFloat = { readonly __canonical_python_float__: number };

function asCanonicalFloat(value: number): CanonicalFloat {
  return { __canonical_python_float__: value };
}

function canonicalInputs(
  plannedDesign: TrialAssumptions,
  fixedEnrollment: { control: number; treatment: number },
  stressScenario: WorkspaceExportPayload["stress_scenario"],
  provenance: ApiProvenanceMap,
): Record<string, unknown> {
  return {
    planned_design: {
      model_version: plannedDesign.model_version,
      control_event_rate: asCanonicalFloat(plannedDesign.control_event_rate),
      effect: { kind: plannedDesign.effect.kind, value: asCanonicalFloat(plannedDesign.effect.value) },
      alpha: asCanonicalFloat(plannedDesign.alpha),
      target_power: asCanonicalFloat(plannedDesign.target_power),
      allocation_ratio: asCanonicalFloat(plannedDesign.allocation_ratio),
      dropout: {
        control: asCanonicalFloat(plannedDesign.dropout.control),
        treatment: asCanonicalFloat(plannedDesign.dropout.treatment),
      },
    },
    fixed_enrollment: fixedEnrollment,
    stress_scenario: stressScenario ? {
      control_event_rate: asCanonicalFloat(stressScenario.control_event_rate),
      dropout: {
        control: asCanonicalFloat(stressScenario.dropout.control),
        treatment: asCanonicalFloat(stressScenario.dropout.treatment),
      },
      effect_override: stressScenario.effect_override
        ? { kind: stressScenario.effect_override.kind, value: asCanonicalFloat(stressScenario.effect_override.value) }
        : null,
    } : null,
    provenance,
  };
}

function pythonFloat(value: number): string {
  if (!Number.isFinite(value)) throw new Error("Export inputs must contain only finite numbers.");
  if (Object.is(value, -0)) return "-0.0";
  const absolute = Math.abs(value);
  if (value === 0 || (Number.isInteger(value) && absolute < 1e16)) return `${value}.0`;

  // Pydantic's canonical hash uses Python json.dumps float formatting. All
  // probability/effect inputs are in [0, 1), but preserve Python's exponent
  // threshold and two-digit exponent for small valid rates as well.
  if (absolute < 1e-4 || absolute >= 1e16) {
    const [mantissa, exponent] = value.toExponential().split("e");
    const exponentValue = Number(exponent);
    const sign = exponentValue >= 0 ? "+" : "-";
    return `${mantissa}e${sign}${String(Math.abs(exponentValue)).padStart(2, "0")}`;
  }
  return String(value);
}

function pythonString(value: string): string {
  return JSON.stringify(value).replace(/[\u007f-\uffff]/g, (character) => {
    const code = character.charCodeAt(0).toString(16).padStart(4, "0");
    return `\\u${code}`;
  });
}

function canonicalJson(value: unknown): string {
  if (value && typeof value === "object" && "__canonical_python_float__" in value) {
    return pythonFloat((value as CanonicalFloat).__canonical_python_float__);
  }
  if (value === null) return "null";
  if (typeof value === "string") return pythonString(value);
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") {
    if (!Number.isFinite(value)) throw new Error("Export inputs must contain only finite numbers.");
    return String(value);
  }
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    return `{${Object.keys(record).sort().map((key) => `${pythonString(key)}:${canonicalJson(record[key])}`).join(",")}}`;
  }
  throw new Error("Export inputs contain a value that cannot be represented as canonical JSON.");
}

// Synchronous SHA-256 keeps the existing download button contract intact while
// producing the same stable digest as backend.schemas.compute_export_inputs_hash.
function sha256(value: string): string {
  const constants = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
  ];
  const source = new TextEncoder().encode(value);
  const bitLength = source.length * 8;
  const paddedLength = Math.ceil((source.length + 9) / 64) * 64;
  const bytes = new Uint8Array(paddedLength);
  bytes.set(source);
  bytes[source.length] = 0x80;
  const view = new DataView(bytes.buffer);
  view.setUint32(paddedLength - 8, Math.floor(bitLength / 0x1_0000_0000));
  view.setUint32(paddedLength - 4, bitLength >>> 0);

  const hash = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19];
  const words = new Uint32Array(64);
  const rotateRight = (word: number, count: number) => (word >>> count) | (word << (32 - count));
  for (let offset = 0; offset < paddedLength; offset += 64) {
    for (let index = 0; index < 16; index++) words[index] = view.getUint32(offset + index * 4);
    for (let index = 16; index < 64; index++) {
      const x = words[index - 15], y = words[index - 2];
      const sigma0 = rotateRight(x, 7) ^ rotateRight(x, 18) ^ (x >>> 3);
      const sigma1 = rotateRight(y, 17) ^ rotateRight(y, 19) ^ (y >>> 10);
      words[index] = (words[index - 16] + sigma0 + words[index - 7] + sigma1) >>> 0;
    }
    let [a, b, c, d, e, f, g, h] = hash;
    for (let index = 0; index < 64; index++) {
      const sum1 = rotateRight(e, 6) ^ rotateRight(e, 11) ^ rotateRight(e, 25);
      const choice = (e & f) ^ (~e & g);
      const temp1 = (h + sum1 + choice + constants[index] + words[index]) >>> 0;
      const sum0 = rotateRight(a, 2) ^ rotateRight(a, 13) ^ rotateRight(a, 22);
      const majority = (a & b) ^ (a & c) ^ (b & c);
      const temp2 = (sum0 + majority) >>> 0;
      h = g; g = f; f = e; e = (d + temp1) >>> 0;
      d = c; c = b; b = a; a = (temp1 + temp2) >>> 0;
    }
    hash[0] = (hash[0] + a) >>> 0; hash[1] = (hash[1] + b) >>> 0;
    hash[2] = (hash[2] + c) >>> 0; hash[3] = (hash[3] + d) >>> 0;
    hash[4] = (hash[4] + e) >>> 0; hash[5] = (hash[5] + f) >>> 0;
    hash[6] = (hash[6] + g) >>> 0; hash[7] = (hash[7] + h) >>> 0;
  }
  return hash.map((word) => word.toString(16).padStart(8, "0")).join("");
}

function exportProvenance(ledger: ProvenanceLedger): ApiProvenanceMap {
  return Object.fromEntries(Object.entries(ledger).map(([field, record]) => {
    const extended = record as ProvenanceRecord;
    return [field, {
      source: record.source,
      description: record.description ?? null,
      retrieved_at: record.retrieved_at ?? null,
      source_url: record.source_url ?? null,
      source_location: extended.source_location ?? null,
      verified_by_user: extended.verified_by_user ?? null,
      is_observed_registry_result: extended.is_observed_registry_result ?? null,
    } satisfies ProvenanceRecord];
  }));
}

export function computeWorkspaceExportInputsHash(
  plannedDesign: TrialAssumptions,
  fixedEnrollment: { control: number; treatment: number },
  stressScenario: WorkspaceExportPayload["stress_scenario"],
  provenance: ApiProvenanceMap,
): string {
  return `sha256:${sha256(canonicalJson(canonicalInputs(plannedDesign, fixedEnrollment, stressScenario, provenance)))}`;
}

function fieldMap(result: { provenance: CalculateResponse["provenance"] }): ApiProvenanceMap {
  return result.provenance.field_provenance ?? {};
}

function designForExport(result: CalculateResponse): ApiDesignCalculateResponse {
  const canonical = { ...result } as unknown as Record<string, unknown>;
  delete canonical.provenance;
  delete canonical.mock;
  delete canonical.execution;
  canonical.provenance = fieldMap(result);
  return canonical as unknown as ApiDesignCalculateResponse;
}

function evaluationForExport(result: EvaluateResponse): ApiScenarioEvaluateResponse | undefined {
  if (!result.monte_carlo) return undefined;
  const canonical = { ...result } as unknown as Record<string, unknown>;
  delete canonical.provenance;
  delete canonical.mock;
  delete canonical.execution;
  canonical.provenance = fieldMap(result);
  return canonical as unknown as ApiScenarioEvaluateResponse;
}

function isCanonicalGridResult(result: GridResponse): boolean {
  const raw = result as unknown as Record<string, unknown>;
  return ["fixed_enrollment", "below_target", "software_versions", "analytic_delta", "contour_segments", "power_curve", "invalid_cell_count", "worst_case_power"].every(
    (key) => key in raw
  );
}

function gridForExport(result: GridResponse): ApiScenarioGridResponse {
  const canonical = { ...result } as unknown as Record<string, unknown>;
  delete canonical.execution;
  delete canonical.mock;
  const canonicalPoint = (point: unknown) => {
    if (!point || typeof point !== "object") return point;
    const value = { ...(point as Record<string, unknown>) };
    delete value.baseline;
    return value;
  };
  canonical.planned_point = canonicalPoint(result.planned_point);
  canonical.selected_point = canonicalPoint(result.selected_point);
  canonical.frontier_points = result.frontier_points.map(canonicalPoint);
  canonical.provenance = fieldMap(result);
  return canonical as unknown as ApiScenarioGridResponse;
}

export function buildWorkspaceExport(
  state: WorkspaceState,
  exportedAt = new Date().toISOString()
): WorkspaceExportPayload {
  if (!state.frozenEnrollment) throw new Error("Calculate a design before exporting results.");
  const provenance = exportProvenance(state.provenanceLedger);
  const payload: WorkspaceExportPayload = {
    export_schema_version: 1,
    model_version: "binary-v1",
    planned_design: state.plannedDraft,
    fixed_enrollment: state.frozenEnrollment,
    stress_scenario: {
      control_event_rate: state.stressBaseline,
      dropout: { control: state.stressDropout, treatment: state.stressDropout },
      effect_override: null,
    },
    software_versions: {},
    provenance,
    exported_at: exportedAt,
    inputs_hash: "",
  };
  payload.inputs_hash = computeWorkspaceExportInputsHash(
    payload.planned_design, payload.fixed_enrollment, payload.stress_scenario, payload.provenance
  );

  if (state.designStatus === "success" && state.calculatedDesign && !state.calculatedDesign.mock) {
    payload.design_result = designForExport(state.calculatedDesign);
  }
  if (state.evaluateStatus === "success" && state.evaluateResult && !state.evaluateResult.mock) {
    payload.evaluation_result = evaluationForExport(state.evaluateResult);
  }
  if (state.gridStatus === "success" && state.gridResult && !state.gridResult.mock && isCanonicalGridResult(state.gridResult)) {
    payload.grid_result = gridForExport(state.gridResult);
  }

  const gridVersions = payload.grid_result?.software_versions;
  const evaluationVersions = payload.evaluation_result?.metadata.software_versions;
  if (gridVersions) payload.software_versions = gridVersions;
  else if (evaluationVersions) payload.software_versions = evaluationVersions;
  return payload;
}

export function hasCurrentExportableResults(state: WorkspaceState): boolean {
  return Boolean(
    (state.designStatus === "success" && state.calculatedDesign && !state.calculatedDesign.mock) ||
    (state.evaluateStatus === "success" && state.evaluateResult && !state.evaluateResult.mock && state.evaluateResult.monte_carlo) ||
    (state.gridStatus === "success" && state.gridResult && !state.gridResult.mock && isCanonicalGridResult(state.gridResult))
  );
}

export function serializeWorkspaceExport(payload: WorkspaceExportPayload): string {
  return `${JSON.stringify(payload, null, 2)}\n`;
}

export function downloadWorkspaceExport(payload: WorkspaceExportPayload): void {
  const blob = new Blob([serializeWorkspaceExport(payload)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `better-baseline-export-${payload.exported_at.replace(/[:.]/g, "-")}.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}
