"use client";

import Link from "next/link";
import { MonteCarloPanel } from "@/components/MonteCarloPanel";
import { ScenarioExport } from "@/components/ScenarioExport";
import { useWorkspace } from "@/components/WorkspaceProvider";

export default function SimulationPage() {
  const { state, selection, simulationUI, setSimulationUI, changeSimulationOptions, onSimulationRequestStart, onSimulationRequestFinish, isSimulationRequestCurrent, runSimulation, apiMode, payload, exportReason, exportFeedback, setExportFeedback } = useWorkspace();
  const ready = state.designStatus === "success" && Boolean(state.frozenEnrollment);
  return <>
    <header className="route-heading"><h1>Simulate and export</h1><p>Check one valid stress scenario with a reproducible seed, then export the current record.</p></header>
    {!ready && <p className="route-prerequisite" role="status">Calculate and lock a design before selecting a simulation scenario. <Link href="/">Go to planning</Link> · <Link href="/stress">Review stress testing</Link></p>}
    {ready && !selection && <p className="route-prerequisite" role="status">Choose a valid point on the analytic chart before running a simulation. <Link href="/stress">Go to stress testing</Link></p>}
    <div className="simulation-capture" onChangeCapture={event => {
      if (!(event.target instanceof HTMLInputElement)) return;
      const fields = event.currentTarget.querySelectorAll<HTMLInputElement>('input[type="text"]');
      if (fields.length === 2) changeSimulationOptions({ seed: fields[0].value, replicates: fields[1].value });
    }}>
      <MonteCarloPanel selection={selection} runSimulation={runSimulation} unavailableReason={apiMode === "demo" ? "Live simulation is unavailable in demo mode." : undefined} uiState={simulationUI} onUIStateChange={setSimulationUI} onRequestStart={onSimulationRequestStart} onRequestFinish={onSimulationRequestFinish} isRequestCurrent={isSimulationRequestCurrent} />
    </div>
    <ScenarioExport payload={payload} unavailableReason={exportReason} feedback={exportFeedback} onFeedbackChange={setExportFeedback} />
  </>;
}
