"use client";

import { getPresetById } from "@/lib/presets";
import { DesignForm } from "@/components/DesignForm";
import { DesignSummary } from "@/components/DesignSummary";
import { PresetSelector } from "@/components/PresetSelector";
import { useWorkspace } from "@/components/WorkspaceProvider";

export default function PlanningPage() {
  const { state, designUI, setDesignUI, selectPreset, changePlanned, calculate } = useWorkspace();
  return <>
    <header className="route-heading"><h1>Plan and lock enrollment</h1><p>Set hypothetical assumptions, calculate the design, and freeze enrollment for comparison.</p></header>
    <PresetSelector selectedPresetId={state.presetId} onSelectPreset={selectPreset} onResetPreset={() => selectPreset()} />
    <div className="planning-columns route-planning-columns">
      <DesignForm initialAssumptions={getPresetById(state.presetId).planned_design} presetId={state.presetId} onCalculate={calculate} onDraftChange={changePlanned} isCalculating={state.designStatus === "calculating"} error={state.designError} submitLabel="Calculate & Lock Design" uiState={designUI} onUIStateChange={setDesignUI} />
      <div className="enrollment-panel"><DesignSummary result={state.calculatedDesign} isStale={state.designStatus !== "success"} isCalculating={state.designStatus === "calculating"} error={state.designError} /></div>
    </div>
  </>;
}
