"use client";

import { useId, useRef, useState, type FormEvent } from "react";
import type { CalculateRequest, TrialAssumptions } from "../lib/contracts";
import {
  assumptionsToDraft, planningValuesToRequest, validatePlanningDraft,
  type DraftField, type FieldErrors, type PlanningDraft,
} from "../lib/validation";

export interface DesignFormProps {
  initialAssumptions: TrialAssumptions;
  presetId: string;
  onCalculate: (request: CalculateRequest) => void | Promise<void>;
  /** Parent marks prior results stale and tracks edited input provenance here. */
  onDraftChange?: (draft: PlanningDraft, changedField: DraftField) => void;
  isCalculating?: boolean;
  error?: string | null;
}

/** Initial assumptions apply on mount. Parent remounts with a new key on preset reset. */
export function DesignForm({ initialAssumptions, presetId, onCalculate, onDraftChange,
  isCalculating = false, error = null }: DesignFormProps) {
  const id = useId();
  const form = useRef<HTMLFormElement>(null);
  const submitting = useRef(false);
  const [draft, setDraft] = useState(() => assumptionsToDraft(initialAssumptions));
  const [errors, setErrors] = useState<FieldErrors>({});
  const [submitted, setSubmitted] = useState(false);
  const [pending, setPending] = useState(false);
  const [callbackError, setCallbackError] = useState<string | null>(null);
  const busy = pending || isCalculating;

  function change(field: DraftField, value: string) {
    const next = { ...draft, [field]: value } as PlanningDraft;
    setDraft(next);
    setCallbackError(null);
    if (submitted) setErrors(validatePlanningDraft(next).errors);
    onDraftChange?.(next, field);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || submitting.current) return;
    const result = validatePlanningDraft(draft);
    setSubmitted(true);
    setErrors(result.errors);
    if (!result.valid) {
      const first = Array.from(form.current?.elements ?? []).find((element) =>
        element instanceof HTMLElement && result.errors[element.getAttribute("name") as DraftField]);
      if (first instanceof HTMLElement) first.focus();
      return;
    }
    submitting.current = true;
    setPending(true);
    setCallbackError(null);
    try {
      await onCalculate(planningValuesToRequest(result.values, presetId));
    } catch (failure) {
      setCallbackError(failure instanceof Error ? failure.message : "Design calculation failed. Try again.");
    } finally {
      submitting.current = false;
      setPending(false);
    }
  }

  function input(field: Exclude<DraftField, "effectKind">, label: string, help?: string) {
    const inputId = `${id}-${field}`;
    const describedBy = [help && `${inputId}-help`, errors[field] && `${inputId}-error`].filter(Boolean).join(" ");
    return <div>
      <label htmlFor={inputId}>{label}</label>{" "}
      <input id={inputId} name={field} type="text" inputMode="decimal" required
        value={draft[field]} aria-invalid={Boolean(errors[field])}
        aria-describedby={describedBy || undefined}
        onChange={(event) => change(field, event.target.value)} />
      {help && <p id={`${inputId}-help`}>{help}</p>}
      {errors[field] && <p id={`${inputId}-error`}>{errors[field]}</p>}
    </div>;
  }

  return <section aria-labelledby={`${id}-heading`}>
    <h2 id={`${id}-heading`}>Planning assumptions</h2>
    <p>Binary adverse endpoint, two-sided test, equal 1:1 arm enrollment, and symmetric dropout.</p>
    <p>Percent fields use the displayed percent units: enter 20 for 20%. Relative risk uses a decimal ratio.</p>
    <form ref={form} onSubmit={submit} noValidate aria-busy={busy}>
      <fieldset disabled={busy}>
        <legend>Planned design inputs</legend>
        {input("controlPercent", "Control endpoint risk (%)",
          `Endpoint risk in the trial’s eligible control population over the stated follow-up period. This is not general-population disease prevalence.`)}
        <div>
          <label htmlFor={`${id}-effectKind`}>Hypothetical treatment effect</label>{" "}
          <select id={`${id}-effectKind`} name="effectKind" value={draft.effectKind}
            aria-invalid={Boolean(errors.effectKind)} aria-describedby={errors.effectKind ? `${id}-effect-error` : undefined}
            onChange={(event) => change("effectKind", event.target.value)}>
            <option value="relative_risk">Relative risk</option>
            <option value="absolute_risk_reduction">Absolute risk reduction</option>
          </select>
          {errors.effectKind && <p id={`${id}-effect-error`}>{errors.effectKind}</p>}
        </div>
        {draft.effectKind === "relative_risk"
          ? input("relativeRisk", "Relative risk (decimal ratio)", "For example, 0.75. Enter a ratio greater than 0 and below 1.")
          : input("reductionPoints", "Absolute risk reduction (percentage points)", "For example, 5 means a reduction of 5 percentage points. It must be smaller than the control endpoint risk.")}
        {input("targetPercent", "Target power (%)")}
        {input("alphaPercent", "Two-sided alpha (%)")}
        {input("dropoutPercent", "Dropout in each arm (%)", "One shared fraction applies to both arms. Dropout assumes independent missingness; retained participant counts are not guaranteed.")}
        <button type="submit">{busy ? "Calculating design…" : "Calculate design"}</button>
      </fieldset>
      {Object.keys(errors).length > 0 && <p role="alert">Correct the marked planning inputs before calculating.</p>}
      {(callbackError || error) && <p role="alert">{callbackError || error}</p>}
      {busy && <p role="status">Calculating design under the entered assumptions.</p>}
    </form>
  </section>;
}
