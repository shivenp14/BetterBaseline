"use client";

import Link from "next/link";
import { useWorkspace, useWorkspaceCharts } from "@/components/WorkspaceProvider";
import { StressControls } from "@/components/StressControls";
import { DesignComparison, workspaceComparisonProps } from "@/components/DesignComparison";
import { PowerCurve, workspaceCurveProps } from "@/components/PowerCurve";
import { StressHeatmap, workspaceHeatmapProps } from "@/components/StressHeatmap";

export default function StressPage() {
  const { state, changeBaseline, changeDropout, selectPoint, evaluateAnalytic, loadGrid } = useWorkspace();
  const { chartState, completedGrid } = useWorkspaceCharts();
  const curve = workspaceCurveProps(chartState, completedGrid);
  const heatmap = workspaceHeatmapProps(chartState, completedGrid);
  const ready = state.designStatus === "success" && Boolean(state.frozenEnrollment);
  return <>
    <header className="route-heading"><h1>Stress-test assumptions</h1><p>Explore event risk and dropout while keeping the planned enrollment fixed.</p></header>
    {!ready && <p className="route-prerequisite" role="status">Calculate and lock a design before comparing scenarios. <Link href="/">Go to planning</Link></p>}
    <StressControls frozenEnrollment={state.frozenEnrollment} stressBaseline={state.stressBaseline} stressDropout={state.stressDropout} onBaselineChange={changeBaseline} onDropoutChange={changeDropout} onEvaluate={() => { void evaluateAnalytic(); }} evaluateStatus={state.evaluateStatus} evaluateError={state.evaluateError} isCalculating={!ready} />
    <section className="grid-request panel" aria-labelledby="grid-heading"><div><h2 id="grid-heading">Analytic response grid</h2><p className="muted">Load the backend grid for this fixed enrollment and selected scenario.</p></div><button className="button-secondary" type="button" onClick={() => { void loadGrid(); }} disabled={!ready || state.gridStatus === "loading"}>{state.gridStatus === "loading" ? "Loading grid…" : "Load analytic grid"}</button><span className={`status-badge ${state.gridStatus === "error" ? "status-error" : state.gridStatus === "stale" ? "status-warning" : ""}`}>Status: {state.gridStatus.toUpperCase()}</span>{state.gridError && <p role="alert">{state.gridError}</p>}</section>
    <DesignComparison {...workspaceComparisonProps(chartState, completedGrid)} />
    <div className="analysis-columns"><PowerCurve {...curve} onSelectBaseline={changeBaseline} /><StressHeatmap {...heatmap} onSelectPoint={selectPoint} /></div>
  </>;
}
