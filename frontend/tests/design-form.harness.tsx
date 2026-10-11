"use client";

// Isolated acceptance harness. #72 owns production API/state/page integration.
import { useState } from "react";
import { DesignForm } from "../components/DesignForm";
import { DesignSummary, type DesignSummaryResult } from "../components/DesignSummary";
import type { CalculateRequest, TrialAssumptions } from "../lib/contracts";

const assumptions: TrialAssumptions = {
  model_version: "binary-v1", allocation_ratio: 1, control_event_rate: .2,
  effect: { kind: "relative_risk", value: .75 }, alpha: .05, target_power: .8,
  dropout: { control: .1, treatment: .1 },
};

export default function DesignFormHarness() {
  const [result, setResult] = useState<DesignSummaryResult | null>(null);
  const [stale, setStale] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [calls, setCalls] = useState(0);
  const [payload, setPayload] = useState<CalculateRequest | null>(null);
  async function calculate(request: CalculateRequest) {
    setCalls((count) => count + 1);
    setPayload(request);
    setPending(true);
    setError(null);
    try {
      // preset_id is C1 UI metadata, not a numerical API input.
      const { preset_id: presetId, ...body } = request;
      void presetId;
      const response = await fetch("http://127.0.0.1:8000/api/v1/design/calculate", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      if (!response.ok) throw new Error(`Design request failed (${response.status})`);
      setResult(await response.json());
      setStale(false);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Design request failed");
      setStale(true);
    } finally { setPending(false); }
  }
  return <main>
    <DesignForm initialAssumptions={assumptions} presetId="manual-test" onCalculate={calculate}
      onDraftChange={() => setStale(true)} isCalculating={pending} error={error} />
    <DesignSummary result={result} isStale={stale} isCalculating={pending} error={error} />
    <output aria-label="Calculation calls">{calls}</output>
    <pre aria-label="Submitted payload">{JSON.stringify(payload)}</pre>
  </main>;
}
