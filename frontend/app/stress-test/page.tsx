"use client";
import { getApiMode } from "@/lib/api";
import { useWorkspace } from "../WorkspaceProvider";
import { WorkspaceFrame } from "../WorkspaceFrame";
import { StressControls } from "@/components/StressControls";
import { DesignComparison, workspaceComparisonProps } from "@/components/DesignComparison";
import { PowerCurve } from "@/components/PowerCurve";
import { StressHeatmap } from "@/components/StressHeatmap";
import styles from "../planning.module.css";

export default function StressTestPage() {
  const { state, completedGrid, curve, heatmap, changeBaseline, changeDropout, selectPoint, loadGrid, evaluateAnalytic } = useWorkspace();
  return <WorkspaceFrame title="Stress-test the plan" description="Change the expected control event rate or dropout and see what happens to estimated power while planned enrollment stays fixed.">
    <StressControls frozenEnrollment={state.designStatus === "success" ? state.frozenEnrollment : null} stressBaseline={state.stressBaseline} stressDropout={state.stressDropout} onBaselineChange={changeBaseline} onDropoutChange={changeDropout} onEvaluate={() => { void evaluateAnalytic(); }} evaluateStatus={state.evaluateStatus} evaluateError={state.evaluateError} isCalculating={state.designStatus !== "success"} />
    {state.designStatus !== "success" && <p className={styles.recoveryNote} role="status">Calculate the current plan first. Your stress assumptions can be explored now; a fresh estimate needs a calculated enrollment.</p>}
    <section className={styles.gridRequest} aria-labelledby="grid-heading"><h2 id="grid-heading">Compare a range of assumptions</h2>
      <p>Request the full range analysis to compare event-rate and dropout combinations. You can also use the single-scenario estimate above.</p>
      <button type="button" onClick={() => { void loadGrid(); }} disabled={state.designStatus !== "success" || state.gridStatus === "loading"}>{state.gridStatus === "loading" ? "Loading range analysis…" : "Load range analysis"}</button>
      <span>Status: {state.gridStatus.toUpperCase()}</span>
      {state.gridError && <p role="alert">{state.gridError} {getApiMode() === "live" && "The live range-analysis endpoint is not available yet; you can still review one scenario above."}</p>}
      {getApiMode() === "live" && <p>Live range analysis is not available yet. You can change one scenario above and review its estimate.</p>}
    </section>
    <DesignComparison {...workspaceComparisonProps({ ...state, requestRevision: state.inputGeneration }, completedGrid)} />
    <details className={styles.advancedRanges}><summary>Advanced: inspect range charts and grid data</summary>
      <p>These analytical charts use expected retained participant counts and are a separate approximation from the selected-scenario simulation.</p>
      <div className={styles.analyticsGrid}><PowerCurve {...curve} onSelectBaseline={changeBaseline} /><StressHeatmap {...heatmap} onSelectPoint={selectPoint} /></div>
    </details>
  </WorkspaceFrame>;
}
