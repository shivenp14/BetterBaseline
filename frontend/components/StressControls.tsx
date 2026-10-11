"use client";

import React from "react";
import type { FixedEnrollment } from "@/lib/contracts";

interface StressControlsProps {
  frozenEnrollment: FixedEnrollment | null;
  stressBaseline: number;
  stressDropout: number;
  onBaselineChange: (baseline: number) => void;
  onDropoutChange: (dropout: number) => void;
  onEvaluate?: () => void;
  evaluateStatus: "idle" | "evaluating" | "stale" | "success" | "error";
  evaluateError: string | null;
  isCalculating?: boolean;
}

export function StressControls({
  frozenEnrollment,
  stressBaseline,
  stressDropout,
  onBaselineChange,
  onDropoutChange,
  onEvaluate,
  evaluateStatus,
  evaluateError,
  isCalculating = false,
}: StressControlsProps) {
  const controlN = frozenEnrollment?.control ?? 0;
  const treatmentN = frozenEnrollment?.treatment ?? 0;
  const expectedRetainedControl = Math.floor(controlN * (1 - stressDropout));
  const expectedRetainedTreatment = Math.floor(treatmentN * (1 - stressDropout));

  return (
    <section aria-labelledby="stress-heading">
      <h2 id="stress-heading">Stress Controls & Fixed Enrollment Invariant</h2>
      <p>
        Vary underlying control risk or attrition under fixed sample size. Notice that
        adjusting stress parameters <strong>never</strong> alters the locked enrolled counts.
      </p>

      {frozenEnrollment ? (
        <div style={{ padding: "8px", border: "1px solid #ccc", marginBottom: "12px" }}>
          <strong>LOCKED ENROLLMENT (Immutable):</strong>{" "}
          <span>Control: {controlN.toLocaleString()} enrolled</span> |{" "}
          <span>Treatment: {treatmentN.toLocaleString()} enrolled</span>
          <br />
          <small>
            Analytic expected retained floor at {Math.round(stressDropout * 100)}% dropout:{" "}
            {expectedRetainedControl.toLocaleString()} control /{" "}
            {expectedRetainedTreatment.toLocaleString()} treatment evaluable
          </small>
        </div>
      ) : (
        <div style={{ padding: "8px", border: "1px solid #ccc", marginBottom: "12px" }}>
          <em>No calculated design locked yet. Run calculation to lock enrollment.</em>
        </div>
      )}

      <div>
        <label htmlFor="stress-baseline-slider">
          <strong>Stress Control Risk (Eligible-Control Event Rate):</strong>{" "}
          {(stressBaseline * 100).toFixed(1)}%
        </label>
        <br />
        <input
          id="stress-baseline-slider"
          type="range"
          min="0.01"
          max="0.99"
          step="0.01"
          value={stressBaseline}
          onChange={(e) => onBaselineChange(parseFloat(e.target.value))}
          style={{ width: "300px" }}
        />
        <input
          id="stress-baseline-num"
          type="number"
          min="0.01"
          max="0.99"
          step="0.01"
          value={stressBaseline}
          onChange={(e) => {
            const val = parseFloat(e.target.value);
            if (!isNaN(val) && val > 0 && val < 1) onBaselineChange(val);
          }}
          style={{ width: "70px", marginLeft: "8px" }}
        />
      </div>

      <div style={{ marginTop: "12px" }}>
        <label htmlFor="stress-dropout-slider">
          <strong>Stress Symmetric Dropout Rate:</strong>{" "}
          {(stressDropout * 100).toFixed(1)}%
        </label>
        <br />
        <input
          id="stress-dropout-slider"
          type="range"
          min="0.00"
          max="0.50"
          step="0.01"
          value={stressDropout}
          onChange={(e) => onDropoutChange(parseFloat(e.target.value))}
          style={{ width: "300px" }}
        />
        <input
          id="stress-dropout-num"
          type="number"
          min="0.00"
          max="0.50"
          step="0.01"
          value={stressDropout}
          onChange={(e) => {
            const val = parseFloat(e.target.value);
            if (!isNaN(val) && val >= 0 && val < 1) onDropoutChange(val);
          }}
          style={{ width: "70px", marginLeft: "8px" }}
        />
      </div>

      <div style={{ marginTop: "16px" }}>
        {onEvaluate && (
          <button
            type="button"
            onClick={onEvaluate}
            disabled={isCalculating || evaluateStatus === "evaluating" || !frozenEnrollment}
          >
            {evaluateStatus === "evaluating" ? "Evaluating Stress..." : "Evaluate Stress Scenario"}
          </button>
        )}
        <span style={{ marginLeft: "10px" }}>
          Status:{" "}
          <strong>
            {evaluateStatus === "stale"
              ? "STALE (inputs changed, evaluation pending/out-of-date)"
              : evaluateStatus.toUpperCase()}
          </strong>
        </span>
      </div>

      {evaluateError && (
        <div style={{ color: "red", marginTop: "8px" }}>
          <strong>Error:</strong> {evaluateError}
        </div>
      )}
    </section>
  );
}
