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
    <section className={"analytics-panel"} aria-labelledby="stress-heading">
      <h2 id="stress-heading">Change the scenario</h2>
      <p>
        Try a different control-group event rate or expected dropout to see how the estimated chance of detecting the assumed difference changes. These are what-if assumptions; the planned enrollment stays fixed.
      </p>

      {frozenEnrollment ? (
        <div className={"analytics-enrollment"}>
          <strong>Planned enrollment (held fixed):</strong>{" "}
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
        <div className={"analytics-enrollment"}>
          <em>Calculate a planned design above to set the enrollment that this stress test holds fixed. You can adjust these assumptions now.</em>
        </div>
      )}

      <div className={"analytics-control"}>
        <label htmlFor="stress-baseline-slider">
          <strong>Control-group event rate:</strong>{" "}
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
          aria-describedby="stress-baseline-help"
          onChange={(e) => onBaselineChange(parseFloat(e.target.value))}
          className={"analytics-slider"}
        />
        <label htmlFor="stress-baseline-num">Enter as a decimal (0.20 means 20%):</label>{" "}
        <input
          id="stress-baseline-num"
          aria-label="Stress control risk fraction"
          type="number"
          min="0.01"
          max="0.99"
          step="0.01"
          value={stressBaseline}
          onChange={(e) => {
            const val = parseFloat(e.target.value);
            if (!isNaN(val) && val > 0 && val < 1) onBaselineChange(val);
          }}
          className={"analytics-numeric"}
        />
        <small className={"analytics-unit"}>Numeric value is a fraction (0.10 = 10%). Risk range: 1–99%.</small>
        <p id="stress-baseline-help">Share of people in the control group expected to have the outcome during follow-up.</p>
      </div>

      <div className={"analytics-control"}>
        <label htmlFor="stress-dropout-slider">
          <strong>Expected dropout in each group:</strong>{" "}
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
          aria-describedby="stress-dropout-help"
          onChange={(e) => onDropoutChange(parseFloat(e.target.value))}
          className={"analytics-slider"}
        />
        <label htmlFor="stress-dropout-num">Enter as a decimal (0.10 means 10%):</label>{" "}
        <input
          id="stress-dropout-num"
          aria-label="Stress symmetric dropout fraction"
          type="number"
          min="0.00"
          max="0.50"
          step="0.01"
          value={stressDropout}
          onChange={(e) => {
            const val = parseFloat(e.target.value);
            if (!isNaN(val) && val >= 0 && val < 1) onDropoutChange(val);
          }}
          className={"analytics-numeric"}
        />
        <p id="stress-dropout-help">The same estimate is applied to both groups. Actual retained counts may differ.</p>
      </div>

      <p className={"analytics-unit"}>Dropout numeric value is a fraction (0.10 = 10%). Slider range: 0–50%.</p>
      <div className={"analytics-actions"}>
        {onEvaluate && (
          <button
            type="button"
            onClick={onEvaluate}
            disabled={isCalculating || evaluateStatus === "evaluating" || !frozenEnrollment}
          >
            {evaluateStatus === "evaluating" ? "Updating estimate…" : "Update estimate now"}
          </button>
        )}
        <span className={evaluateStatus === "stale" ? "analytics-warning" : "analytics-status"}>
          Status:{" "}
          <strong>
            {evaluateStatus === "stale"
              ? "STALE (inputs changed, evaluation pending/out-of-date)"
              : evaluateStatus.toUpperCase()}
          </strong>
        </span>
      </div>

      {evaluateError && (
        <div className={"analytics-error"}>
          <strong>Could not update this estimate:</strong> {evaluateError} You can retry using “Update estimate now.”
        </div>
      )}
    </section>
  );
}
