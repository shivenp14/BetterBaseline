import type {
  TrialAssumptions,
  FixedEnrollment,
  CalculateResponse,
  EvaluateResponse,
  GridResponse,
  GridPoint,
} from "./contracts";
import type { ProvenanceLedger } from "./workspace-contracts";

export interface AnalyticPowerResult {
  power: number;
  effect_size_h: number;
  p_treatment: number;
  evaluable_per_arm: number;
}

/** Signed Cohen's h for two independent proportions: 2*asin(sqrt(p2)) - 2*asin(sqrt(p1)) */
export function cohenH(pControl: number, pTreatment: number): number {
  return 2.0 * Math.asin(Math.sqrt(pTreatment)) - 2.0 * Math.asin(Math.sqrt(pControl));
}

/** Error function approximation (Abramowitz & Stegun formula 7.1.26, max error: 1.5e-7) */
function erf(x: number): number {
  const sign = x < 0 ? -1 : 1;
  const absX = Math.abs(x);
  const a1 = 0.254829592;
  const a2 = -0.284496736;
  const a3 = 1.421413741;
  const a4 = -1.453152027;
  const a5 = 1.061405429;
  const p = 0.3275911;

  const t = 1.0 / (1.0 + p * absX);
  const y =
    1.0 -
    ((((a5 * t + a4) * t + a3) * t + a2) * t + a1) * t * Math.exp(-absX * absX);
  return sign * y;
}

function erfc(x: number): number {
  return 1.0 - erf(x);
}

/** Inverse standard normal CDF (Acklam algorithm) */
function invNormCdf(p: number): number {
  if (p <= 0 || p >= 1) {
    throw new Error("Probability must be in (0, 1)");
  }
  const a1 = -3.969683028665376e1;
  const a2 = 2.209460984245205e2;
  const a3 = -2.759285104469687e2;
  const a4 = 1.38357751867269e2;
  const a5 = -3.066479806614716e1;
  const a6 = 2.506628277459239;

  const b1 = -5.447609879822406e1;
  const b2 = 1.615858368580409e2;
  const b3 = -1.556989798598866e2;
  const b4 = 6.680131188771972e1;
  const b5 = -1.328068155288572e1;

  const c1 = -7.784894002430293e-3;
  const c2 = -3.223964580411365e-1;
  const c3 = -2.400758277161838;
  const c4 = -2.549732539343734;
  const c5 = 4.374664141464968;
  const c6 = 2.938163982698783;

  const d1 = 7.784695709041462e-3;
  const d2 = 3.224671290700398e-1;
  const d3 = 2.445134137142996;
  const d4 = 3.754408661907416;

  const pLow = 0.02425;
  const pHigh = 1.0 - pLow;

  if (p < pLow) {
    /* Lower tail */
    const q = Math.sqrt(-2.0 * Math.log(p));
    return (
      ((((c1 * q + c2) * q + c3) * q + c4) * q + c5) * q + c6
    ) / ((((d1 * q + d2) * q + d3) * q + d4) * q + 1.0);
  }

  if (p <= pHigh) {
    /* Central region */
    const q = p - 0.5;
    const r = q * q;
    return (
      (((((a1 * r + a2) * r + a3) * r + a4) * r + a5) * r + a6) *
      q /
      (((((b1 * r + b2) * r + b3) * r + b4) * r + b5) * r + 1.0)
    );
  }

  /* Upper tail */
  const q = Math.sqrt(-2.0 * Math.log(1.0 - p));
  return -(
    (((((c1 * q + c2) * q + c3) * q + c4) * q + c5) * q + c6) /
    ((((d1 * q + d2) * q + d3) * q + d4) * q + 1.0)
  );
}

/** Calculate two-sided Cohen's h normal approximation power matching backend */
export function calculateAnalyticPower(
  pControl: number,
  pTreatment: number,
  nPerArm: number,
  alpha = 0.05
): number {
  if (nPerArm <= 0) return 0;
  if (pControl <= 0 || pControl >= 1 || pTreatment <= 0 || pTreatment >= 1) return 0;

  const h = cohenH(pControl, pTreatment);
  const zAlpha = -invNormCdf(alpha / 2.0);
  const noncentralMean = Math.sqrt(nPerArm / 2.0) * Math.abs(h);

  const power =
    0.5 * erfc((zAlpha - noncentralMean) / Math.SQRT2) +
    0.5 * erfc((zAlpha + noncentralMean) / Math.SQRT2);
  return Math.min(1.0, Math.max(0.0, power));
}

/** Resolve treatment event rate from control rate and effect */
export function resolveTreatmentRisk(
  controlRate: number,
  effect: TrialAssumptions["effect"]
): number | null {
  if (effect.kind === "relative_risk") {
    const val = controlRate * effect.value;
    return val > 0 && val < 1 ? val : null;
  } else {
    const val = controlRate - effect.value;
    return val > 0 && val < 1 ? val : null;
  }
}

/** Solve minimal equal-arm evaluable N meeting target power */
export function solveMinimumN(
  pControl: number,
  pTreatment: number,
  targetPower = 0.8,
  alpha = 0.05
): number {
  let low = 2;
  let high = 4;
  while (calculateAnalyticPower(pControl, pTreatment, high, alpha) < targetPower) {
    low = high;
    high *= 2;
    if (high > 1_000_000) break;
  }
  while (low < high) {
    const mid = Math.floor((low + high) / 2);
    if (calculateAnalyticPower(pControl, pTreatment, mid, alpha) >= targetPower) {
      high = mid;
    } else {
      low = mid + 1;
    }
  }
  return low;
}

export function computeLiveDesign(
  assumptions: TrialAssumptions,
  provenanceLedger?: ProvenanceLedger
): CalculateResponse {
  const pTreatment = resolveTreatmentRisk(
    assumptions.control_event_rate,
    assumptions.effect
  );
  if (pTreatment === null) {
    throw new Error("Invalid effect: treatment risk outside (0, 1)");
  }

  const evaluable = solveMinimumN(
    assumptions.control_event_rate,
    pTreatment,
    assumptions.target_power,
    assumptions.alpha
  );

  const dropout = assumptions.dropout.control;
  const enrolled = Math.ceil(evaluable / (1 - dropout));
  const nominalPower = calculateAnalyticPower(
    assumptions.control_event_rate,
    pTreatment,
    evaluable,
    assumptions.alpha
  );

  const hasManualPlanned =
    provenanceLedger &&
    Object.entries(provenanceLedger).some(
      ([k, v]) => k.startsWith("/planned_design") && v.source === "manual_user"
    );

  return {
    model_version: "binary-v1",
    method: "cohen_h_normal_v1",
    p_treatment: Math.round(pTreatment * 10000) / 10000,
    evaluable_n: { control: evaluable, treatment: evaluable },
    enrolled_n: { control: enrolled, treatment: enrolled },
    nominal_power_evaluable: Math.round(nominalPower * 1000) / 1000,
    warnings: [
      "Calculated via canonical Cohen's-h normal approximation.",
      "Dropout inflation represents expected retention floor, not guaranteed evaluable counts.",
    ],
    inputs_hash: `calc:${Date.now()}`,
    provenance: {
      scenario_id: hasManualPlanned ? "user-customized" : "live-calculation",
      scenario_kind: "synthetic",
      label: hasManualPlanned ? "User Customized Design" : "Live Calculated Scenario",
      source: { type: "synthetic", citation_url: null, source_location: null },
      endpoint_type: "binary_undesirable_event",
      follow_up_label: "12 months",
      method_version: "binary-v1",
      generated_by: "local_fixture",
    },
    mock: true,
  };
}

export function computeLiveEvaluation(
  plannedDesign: TrialAssumptions,
  fixedEnrollment: FixedEnrollment,
  stressBaseline: number,
  stressDropout: number,
  provenanceLedger?: ProvenanceLedger
): EvaluateResponse {
  const pTreatment = resolveTreatmentRisk(stressBaseline, plannedDesign.effect);
  const enrolledPerArm = fixedEnrollment.control;
  const expectedRetainedFloor = Math.floor(enrolledPerArm * (1 - stressDropout));

  let conditionalPower: number | null = null;
  if (expectedRetainedFloor > 0 && pTreatment !== null) {
    conditionalPower = calculateAnalyticPower(
      stressBaseline,
      pTreatment,
      expectedRetainedFloor,
      plannedDesign.alpha
    );
  }

  const warnings = [
    "Calculated live at fixed enrollment; analytic retention uses floor(N * (1 - dropout)).",
    "Monte Carlo simulation unavailable for custom inputs without backend execution; simulation metrics nullified.",
  ];

  return {
    model_version: "binary-v1",
    analytic: {
      method: "cohen_h_normal_v1",
      conditional_power_approx:
        conditionalPower !== null ? Math.round(conditionalPower * 1000) / 1000 : null,
      assumed_evaluable_n: {
        control: expectedRetainedFloor,
        treatment: expectedRetainedFloor,
      },
    },
    monte_carlo: null,
    warnings,
    metadata: {
      computed_at: new Date().toISOString(),
      inputs_hash: `eval:${Date.now()}`,
    },
    provenance: {
      scenario_id: "live-evaluated",
      scenario_kind: "synthetic",
      label: "Live Evaluated Scenario",
      source: { type: "synthetic", citation_url: null, source_location: null },
      endpoint_type: "binary_undesirable_event",
      follow_up_label: "12 months",
      method_version: "binary-v1",
      generated_by: "local_fixture",
    },
    mock: true,
  };
}

/** Live sensitivity grid calculation matching canonical matrix and axes */
export function computeLiveGrid(
  plannedDesign: TrialAssumptions,
  fixedEnrollment: FixedEnrollment,
  xBaseline: number[],
  yDropout: number[],
  selectedPoint: GridPoint
): GridResponse {
  const enrolledPerArm = fixedEnrollment.control;
  const powerMatrix: (number | null)[][] = [];
  const invalidMask: boolean[][] = [];
  const frontierPoints: GridPoint[] = [];

  for (let r = 0; r < yDropout.length; r++) {
    const dropout = yDropout[r];
    const retained = Math.floor(enrolledPerArm * (1 - dropout));
    const powerRow: (number | null)[] = [];
    const maskRow: boolean[] = [];

    for (let c = 0; c < xBaseline.length; c++) {
      const baseline = xBaseline[c];
      const pTreat = resolveTreatmentRisk(baseline, plannedDesign.effect);

      if (pTreat === null || retained <= 0) {
        powerRow.push(null);
        maskRow.push(true);
      } else {
        const p = calculateAnalyticPower(
          baseline,
          pTreat,
          retained,
          plannedDesign.alpha
        );
        const roundedP = Math.round(p * 1000) / 1000;
        powerRow.push(roundedP);
        maskRow.push(false);

        if (Math.abs(roundedP - plannedDesign.target_power) <= 0.02) {
          frontierPoints.push({ baseline, dropout });
        }
      }
    }
    powerMatrix.push(powerRow);
    invalidMask.push(maskRow);
  }

  return {
    model_version: "binary-v1",
    method: "cohen_h_normal_v1",
    grid_label: "expected_count_approximation",
    x_baseline: xBaseline,
    y_dropout: yDropout,
    power: powerMatrix,
    invalid_mask: invalidMask,
    target_power: plannedDesign.target_power,
    planned_point: {
      baseline: plannedDesign.control_event_rate,
      dropout: plannedDesign.dropout.control,
    },
    selected_point: selectedPoint,
    frontier_points: frontierPoints,
    warnings: [
      "Calculated live at fixed enrollment; rows are dropout, columns are baseline risk.",
    ],
    computed_at: new Date().toISOString(),
    inputs_hash: `grid:${Date.now()}`,
    provenance: {
      scenario_id: "live-grid",
      scenario_kind: "synthetic",
      label: "Live Sensitivity Grid",
      source: { type: "synthetic", citation_url: null, source_location: null },
      endpoint_type: "binary_undesirable_event",
      follow_up_label: "12 months",
      method_version: "binary-v1",
      generated_by: "local_fixture",
    },
    mock: true,
  };
}
