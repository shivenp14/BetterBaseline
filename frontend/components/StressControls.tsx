"use client";

import React from "react";
import type { FixedEnrollment } from "@/lib/contracts";
import { expectedRetainedCount } from "../lib/expected-retained";

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
  const expectedRetainedControl = frozenEnrollment ? expectedRetainedCount(controlN, stressDropout) : 0;
  const expectedRetainedTreatment = frozenEnrollment ? expectedRetainedCount(treatmentN, stressDropout) : 0;

  return (
    <section className="panel stress-panel" aria-labelledby="stress-heading">
      <h2 className="section-heading" id="stress-heading">Stress assumptions · fixed enrollment</h2>
      <p className="muted">
        Vary underlying control risk or attrition under fixed sample size. Notice that
        adjusting stress parameters <strong>never</strong> alters the locked enrolled counts.
      </p>

      {frozenEnrollment ? (
        <div className="enrollment-readout status-success">
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
        <div className="chart-empty">
          <em>No calculated design locked yet. Run calculation to lock enrollment.</em>
        </div>
      )}

      <div className="field-grid">
      <div className="field stress-field">
        <label htmlFor="stress-baseline-slider">
          <strong>Stress Control Risk (Eligible-Control Event Rate):</strong>{" "}
          {(stressBaseline * 100).toFixed(1)}%
        </label>

        <input
          id="stress-baseline-slider"
          type="range"
          min="0.01"
          max="0.99"
          step="0.01"
          value={stressBaseline}
          onChange={(e) => onBaselineChange(parseFloat(e.target.value))}

        />
        <label htmlFor="stress-baseline-num" className="field-help">Control risk (fraction)</label>
        <input
          id="stress-baseline-num"
          aria-label="Stress control risk (fraction)"
          aria-describedby="stress-baseline-help"
          type="number"
          min="0.01"
          max="0.99"
          step="0.01"
          value={stressBaseline}
          onChange={(e) => {
            const val = parseFloat(e.target.value);
            if (!isNaN(val) && val > 0 && val < 1) onBaselineChange(val);
          }}

        />
        <p className="field-help" id="stress-baseline-help">Fraction of eligible control participants with the endpoint: 0.20 means 20%.</p>
      </div>

      <div className="field stress-field">
        <label htmlFor="stress-dropout-slider">
          <strong>Stress Symmetric Dropout Rate:</strong>{" "}
          {(stressDropout * 100).toFixed(1)}%
        </label>

        <input
          id="stress-dropout-slider"
          type="range"
          min="0.00"
          max="0.50"
          step="0.01"
          value={stressDropout}
          onChange={(e) => onDropoutChange(parseFloat(e.target.value))}

        />
        <label htmlFor="stress-dropout-num" className="field-help">Dropout in each arm (fraction)</label>
        <input
          id="stress-dropout-num"
          aria-label="Stress symmetric dropout rate (fraction)"
          aria-describedby="stress-dropout-help"
          type="number"
          min="0.00"
          max="0.50"
          step="0.01"
          value={stressDropout}
          onChange={(e) => {
            const val = parseFloat(e.target.value);
            if (!isNaN(val) && val >= 0 && val < 1) onDropoutChange(val);
          }}

        />
        <p className="field-help" id="stress-dropout-help">Fraction lost in each arm: 0.10 means 10%. Retention is expected, not guaranteed.</p>
      </div></div>

      <div className="action-row">
        {onEvaluate && (
          <button
            className="button-primary"
            type="button"
            aria-describedby="stress-evaluate-help"
            onClick={onEvaluate}
            disabled={isCalculating || evaluateStatus === "evaluating" || !frozenEnrollment}
          >
            {evaluateStatus === "evaluating" ? "Evaluating Stress..." : "Evaluate Stress Scenario"}
          </button>
        )}
        <span className={`status-badge ${evaluateStatus === "error" ? "status-error" : evaluateStatus === "stale" ? "status-warning" : evaluateStatus === "success" ? "status-success" : ""}`} role="status">
          Status:{" "}
          <strong>
            {evaluateStatus === "stale"
              ? "STALE (inputs changed, evaluation pending/out-of-date)"
              : evaluateStatus.toUpperCase()}
          </strong>
        </span>
      </div>

      {onEvaluate && <p className="field-help" id="stress-evaluate-help">{!frozenEnrollment ? "Calculate and lock a design before evaluating stress." : isCalculating ? "Wait for the design calculation to finish." : evaluateStatus === "evaluating" ? "Evaluation is in progress." : "Evaluate these assumptions using the locked enrollment."}</p>}

      {evaluateError && (
        <div className="status-error" role="alert">
          <strong>Error:</strong> {evaluateError}
        </div>
      )}
    </section>
  );
}
