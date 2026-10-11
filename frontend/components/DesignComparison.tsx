"use client";

import { useId } from "react";
import { curveProblem, percent, workspaceCurveProps } from "./PowerCurve";
import type { PowerCurveProps } from "./PowerCurve";

export interface DesignComparisonProps extends Omit<PowerCurveProps, "onSelectBaseline"> {
  /** Original design power/dropout, supplied by Calculate; never recomputed here. */
  plannedPower: number | null;
  plannedDropout: number;
  plannedDesignHash: string;
}

export function DesignComparison({ current, result, status, error, plannedPower, plannedDropout, plannedDesignHash }: DesignComparisonProps) {
  const id = useId();
  const problem = curveProblem(current, result);
  if (status !== "ready" || problem || !result) {
    return <section className={"analytics-panel"} aria-labelledby={`${id}-heading`} aria-busy={status === "loading"}>
      <h2 id={`${id}-heading`}>Planned design and selected analytic scenario</h2>
      <p className={status === "error" ? "analytics-error" : problem?.startsWith("Stale") ? "analytics-warning" : undefined} role={status === "error" ? "alert" : "status"}>
        {status === "loading" ? "Loading current analytic comparison."
          : status === "error" ? (error || "Analytic comparison could not be loaded.")
            : status === "idle" ? "Calculate a design and evaluate a stress scenario." : problem}
      </p>
    </section>;
  }
  if (plannedDesignHash !== current.designHash) {
    return <p className="analytics-warning" role="status">Stale planned design: calculate the current design before comparing power.</p>;
  }
  if ((plannedPower !== null && (!Number.isFinite(plannedPower) || plannedPower < 0 || plannedPower > 1))
      || !Number.isFinite(plannedDropout) || plannedDropout < 0 || plannedDropout >= 1) {
    return <p className="analytics-error" role="alert">Invalid planned design comparison values.</p>;
  }
  const selectedPower = result.selectedPoint.power;
  return <section className={"analytics-panel"} aria-labelledby={`${id}-heading`}>
    <h2 id={`${id}-heading`}>Planned design and selected analytic scenario</h2>
    <p role="status">Current comparison. {result.illustrative ? "Illustrative synthetic fixture values." : "Supplied analytic API values."}</p>
    <div className={"analytics-tableScroll"} role="region" aria-label="Planned and selected design comparison" tabIndex={0}>
    <table>
      <caption>Enrollment stays frozen while baseline risk and dropout change</caption>
      <thead><tr><th scope="col">Assumption</th><th scope="col">Original planned design</th><th scope="col">Selected stress scenario</th></tr></thead>
      <tbody>
        <tr><th scope="row">Control baseline risk</th><td>{percent(current.plannedBaseline)}</td><td>{percent(current.selectedBaseline)}</td></tr>
        <tr><th scope="row">Symmetric dropout</th><td>{percent(plannedDropout)}</td><td>{percent(current.dropout)}</td></tr>
        <tr><th scope="row">Fixed enrolled control / treatment</th><td>{current.fixedEnrollment.control} / {current.fixedEnrollment.treatment}</td><td>{current.fixedEnrollment.control} / {current.fixedEnrollment.treatment}</td></tr>
        <tr><th scope="row">Approximate conditional power</th><td>{plannedPower === null ? "Unavailable (null)" : percent(plannedPower)}</td><td>{selectedPower === null ? "Invalid scenario (null)" : percent(selectedPower)}</td></tr>
      </tbody>
    </table>
    </div>
    <p>{selectedPower === null || plannedPower === null ? "Power change is unavailable for an invalid selected scenario."
      : `Power change: ${((selectedPower - plannedPower) * 100).toFixed(1)} percentage points.`}</p>
    <p>Target power: {percent(current.targetPower)}. Method: {result.method}.
      Effect: {current.effectKind === "relative_risk" ? "RR" : "ARR"}. Inputs hash: {result.inputsHash}.</p>
    <p>{result.plannedPointDropout === undefined
      ? "The curve’s triangle shows the planned baseline evaluated at the selected dropout; this table’s original planned power uses the original dropout. These are distinct comparisons."
      : "The triangle and original-plan column use the API’s original planned scenario; the curve and selected point use the selected stress dropout."}</p>
    <p>Analytic conditional power assumes the supplied risks, effect and method. It is not a prediction of treatment efficacy.</p>
  </section>;
}


/** Original-plan power comes from the same raw grid response as the curve. */
export function workspaceComparisonProps(
  current: Parameters<typeof workspaceCurveProps>[0],
  completed: Parameters<typeof workspaceCurveProps>[1],
): DesignComparisonProps {
  return { ...workspaceCurveProps(current, completed),
    plannedPower: completed?.response.planned_point.power ?? null,
    plannedDropout: completed?.requestState.plannedDraft.dropout.control ?? 0,
    plannedDesignHash: completed?.requestState.calculatedDesign?.inputs_hash ?? "" };
}
