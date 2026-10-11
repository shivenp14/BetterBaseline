/** C2's local form values. These are not the shared API contract. */
import type { CalculateRequest, TrialAssumptions } from "./contracts";
export type EffectKind = "relative_risk" | "absolute_risk_reduction";

export interface PlanningDraft {
  controlPercent: string;
  effectKind: EffectKind;
  relativeRisk: string;
  reductionPoints: string;
  targetPercent: string;
  alphaPercent: string;
  dropoutPercent: string;
}

/** Validated fractions for the forthcoming C1 request adapter. */
export interface PlanningValues {
  controlRisk: number;
  effect: { kind: EffectKind; value: number };
  targetPower: number;
  alpha: number;
  dropout: number;
}

export type DraftField = keyof PlanningDraft;
export type FieldErrors = Partial<Record<DraftField, string>>;
export type ValidationResult =
  | { valid: true; values: PlanningValues; errors: FieldErrors }
  | { valid: false; errors: FieldErrors };

// Explicit decimal syntax: no coercion of blanks, hex, percentages, or junk.
const DECIMAL = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/;

function parseNumber(text: string): number | undefined {
  const trimmed = text.trim();
  if (!DECIMAL.test(trimmed)) return undefined;
  const number = Number(trimmed);
  return Number.isFinite(number) ? number : undefined;
}

/** Units are fixed by field, never inferred from the value's magnitude. */
export function validatePlanningDraft(draft: PlanningDraft): ValidationResult {
  const errors: FieldErrors = {};
  function fraction(field: DraftField, allowZero = false): number | undefined {
    const number = parseNumber(draft[field]);
    if (number === undefined) {
      errors[field] = "Enter a finite number in the displayed units.";
      return undefined;
    }
    const value = number / 100;
    if (!(value < 1 && (allowZero ? value >= 0 : value > 0))) {
      errors[field] = allowZero
        ? "Enter a percentage from 0 up to, but below, 100."
        : "Enter a percentage greater than 0 and below 100.";
      return undefined;
    }
    return value;
  }

  const controlRisk = fraction("controlPercent");
  const targetPower = fraction("targetPercent");
  const alpha = fraction("alphaPercent");
  const dropout = fraction("dropoutPercent", true);
  let effectValue: number | undefined;
  if (draft.effectKind === "relative_risk") {
    effectValue = parseNumber(draft.relativeRisk);
    if (effectValue === undefined || !(effectValue > 0 && effectValue < 1)) {
      errors.relativeRisk = "Enter a relative risk ratio greater than 0 and below 1.";
      effectValue = undefined;
    }
  } else if (draft.effectKind === "absolute_risk_reduction") {
    effectValue = fraction("reductionPoints");
    if (effectValue !== undefined && controlRisk !== undefined && effectValue >= controlRisk) {
      errors.reductionPoints = "Absolute risk reduction must be smaller than the control endpoint risk.";
    }
  } else {
    errors.effectKind = "Choose relative risk or absolute risk reduction.";
  }
  if (alpha !== undefined && targetPower !== undefined && targetPower <= alpha) {
    errors.targetPercent = "Target power must be greater than alpha.";
  }
  if (Object.keys(errors).length || controlRisk === undefined || targetPower === undefined ||
      alpha === undefined || dropout === undefined || effectValue === undefined) {
    return { valid: false, errors };
  }
  return {
    valid: true,
    values: { controlRisk, effect: { kind: draft.effectKind, value: effectValue }, targetPower, alpha, dropout },
    errors,
  };
}

/** Use unrounded editable strings; rounding belongs only in result display. */
export function planningValuesToDraft(values: PlanningValues): PlanningDraft {
  const draft: PlanningDraft = {
    controlPercent: String(values.controlRisk * 100),
    effectKind: values.effect.kind,
    relativeRisk: values.effect.kind === "relative_risk" ? String(values.effect.value) : "",
    reductionPoints: values.effect.kind === "absolute_risk_reduction" ? String(values.effect.value * 100) : "",
    targetPercent: String(values.targetPower * 100),
    alphaPercent: String(values.alpha * 100),
    dropoutPercent: String(values.dropout * 100),
  };
  if (!validatePlanningDraft(draft).valid) throw new RangeError("Unsupported planning values");
  return draft;
}

/** Reject unsupported preset scope before reducing it to one shared dropout. */
export function assumptionsToDraft(assumptions: TrialAssumptions): PlanningDraft {
  if (assumptions.model_version !== "binary-v1" || assumptions.allocation_ratio !== 1 ||
      assumptions.dropout.control !== assumptions.dropout.treatment) {
    throw new RangeError("Only binary-v1, equal allocation, and symmetric dropout are supported.");
  }
  return planningValuesToDraft({
    controlRisk: assumptions.control_event_rate, effect: assumptions.effect,
    targetPower: assumptions.target_power, alpha: assumptions.alpha,
    dropout: assumptions.dropout.control,
  });
}

/** C1 request seam: unit conversion does not perform statistical calculations. */
export function planningValuesToRequest(values: PlanningValues, presetId: string): CalculateRequest {
  // Revalidate external callers as well as values produced by the draft parser.
  planningValuesToDraft(values);
  return {
    model_version: "binary-v1", allocation_ratio: 1, preset_id: presetId,
    control_event_rate: values.controlRisk, effect: { ...values.effect },
    alpha: values.alpha, target_power: values.targetPower,
    dropout: { control: values.dropout, treatment: values.dropout },
  };
}
