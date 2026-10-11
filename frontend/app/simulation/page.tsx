"use client";
import { getApiMode } from "@/lib/api";
import { useWorkspace } from "../WorkspaceProvider";
import { WorkspaceFrame } from "../WorkspaceFrame";
import { MonteCarloPanel } from "@/components/MonteCarloPanel";
import styles from "../planning.module.css";

export default function SimulationPage() {
  const { state, selection, runSimulation, simulationDraft, changeSimulationDraft, simulationStatus, simulationError, simulationResult, simulationResultIdentity } = useWorkspace();
  return <WorkspaceFrame title="Optional simulation" description="Run repeated synthetic trials for the selected scenario. This is an additional check, not clinical evidence.">
    {state.designStatus !== "success" && <p className={styles.recoveryNote} role="status">Calculate the current plan first. You can set the run options here, then return to Plan to calculate enrollment.</p>}
    <MonteCarloPanel selection={selection} runSimulation={runSimulation} unavailableReason={getApiMode() === "demo" ? "Switch to live mode and start the local backend service to run simulations." : undefined}
      seed={simulationDraft.seed} replicates={simulationDraft.replicates} onOptionsChange={changeSimulationDraft} sharedResult={simulationResult} sharedResultIdentity={simulationResultIdentity} sharedStatus={simulationStatus} sharedError={simulationError} />
  </WorkspaceFrame>;
}
