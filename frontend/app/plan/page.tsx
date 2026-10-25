"use client";
import { getApiMode } from "@/lib/api";
import { getPresetById } from "@/lib/presets";
import { useWorkspace } from "../WorkspaceProvider";
import { WorkspaceFrame } from "../WorkspaceFrame";
import { PresetSelector } from "@/components/PresetSelector";
import { DesignForm } from "@/components/DesignForm";
import { DesignSummary } from "@/components/DesignSummary";
import styles from "../planning.module.css";

export default function PlanPage() {
  const { state, presetDraft, formResetKey, selectPreset, calculate, changePlanned } = useWorkspace();
  return <WorkspaceFrame title="Plan a trial" description="Choose or edit the planning assumptions, then calculate the enrollment needed for your hypothetical two-arm study.">
    <p className={styles.modeNote}><strong>Mode:</strong> {getApiMode() === "demo" ? "Demo — labeled examples and local calculations; no backend service." : "Live — fresh calculations require the local backend service."}</p>
    <PresetSelector selectedPresetId={state.presetId} onSelectPreset={selectPreset} onResetPreset={() => selectPreset()} />
    <div className={styles.planningGrid}>
      <section>
        <DesignForm key={`${state.presetId}:${formResetKey}`} draft={presetDraft} initialAssumptions={getPresetById(state.presetId).planned_design} presetId={state.presetId} onCalculate={calculate} onDraftChange={changePlanned} isCalculating={state.designStatus === "calculating"} error={state.designError} submitLabel="Calculate & Lock Design" />
      </section>
      <DesignSummary result={state.calculatedDesign} isStale={state.designStatus !== "success"} isCalculating={state.designStatus === "calculating"} error={state.designError} />
    </div>
  </WorkspaceFrame>;
}
