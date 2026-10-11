import { planningValuesToRequest, validatePlanningDraft } from "./validation";
import type { DraftField, PlanningDraft } from "./validation";
import type { WorkspaceAction } from "./workspace-state";

const plannedPointers: Record<DraftField, string[]> = {
  controlPercent: ["/planned_design/control_event_rate"],
  effectKind: ["/planned_design/effect/kind", "/planned_design/effect/value"],
  relativeRisk: ["/planned_design/effect/value"],
  reductionPoints: ["/planned_design/effect/value"],
  targetPercent: ["/planned_design/target_power"],
  alphaPercent: ["/planned_design/alpha"],
  dropoutPercent: ["/planned_design/dropout/control", "/planned_design/dropout/treatment"],
};

/** Adapt each editable form change to the workspace draft and provenance ledger. */
export function plannedFieldUpdateAction(
  draft: PlanningDraft,
  changedField: DraftField,
  presetId: string
): Extract<WorkspaceAction, { type: "UPDATE_PLANNED_FIELD" }> {
  const validation = validatePlanningDraft(draft);
  const request = validation.valid
    ? planningValuesToRequest(validation.values, presetId)
    : null;
  const fieldPointers = plannedPointers[changedField];
  return {
    type: "UPDATE_PLANNED_FIELD",
    fieldPointer: fieldPointers[0],
    fieldPointers,
    update: request ? {
      model_version: request.model_version,
      allocation_ratio: request.allocation_ratio,
      control_event_rate: request.control_event_rate,
      effect: request.effect,
      alpha: request.alpha,
      target_power: request.target_power,
      dropout: request.dropout,
    } : {},
  };
}
