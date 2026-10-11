"use client";

import { useId } from "react";
import type { WorkspaceState } from "../lib/workspace-contracts";

/** Presentational identity adapted from #72 by workspaceCurveProps. */
export interface CurveContext {
  inputsHash: string;
  designHash: string;
  fixedEnrollment: { control: number; treatment: number };
  dropout: number;
  effectKind: "relative_risk" | "absolute_risk_reduction";
  targetPower: number;
  plannedBaseline: number;
  selectedBaseline: number;
}

export interface CurvePoint {
  baseline: number;
  power: number | null;
}

/** B4-supplied analytic curve at the exact selected dropout; never a grid row. */
export interface CurveSnapshot extends CurveContext {
  method: "cohen_h_normal_v1";
  powerCurve: readonly CurvePoint[];
  plannedPoint: CurvePoint;
  selectedPoint: CurvePoint;
  illustrative: boolean;
  plannedPointDropout?: number;
}

export interface PowerCurveProps {
  current: CurveContext;
  result: CurveSnapshot | null;
  status: "idle" | "loading" | "ready" | "error";
  error?: string;
  onSelectBaseline?: (baseline: number) => void;
}

export function percent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

const probability = (value: number) => Number.isFinite(value) && value > 0 && value < 1;
const powerValue = (value: number | null) => value === null || (Number.isFinite(value) && value >= 0 && value <= 1);

/** Reject mismatched snapshots before presenting their curve or comparison. */
export function curveProblem(current: CurveContext, result: CurveSnapshot | null): string | null {
  if (!result) return "No analytic curve is available.";
  if (!current.inputsHash || !current.designHash || result.inputsHash !== current.inputsHash
      || result.designHash !== current.designHash
      || result.dropout !== current.dropout || result.effectKind !== current.effectKind
      || result.targetPower !== current.targetPower
      || result.plannedBaseline !== current.plannedBaseline
      || result.selectedBaseline !== current.selectedBaseline
      || result.fixedEnrollment.control !== current.fixedEnrollment.control
      || result.fixedEnrollment.treatment !== current.fixedEnrollment.treatment) {
    return "Stale analytic curve: refresh for the current design and stress inputs.";
  }
  if (!probability(result.dropout) && result.dropout !== 0) return "Invalid curve dropout.";
  if (!probability(result.targetPower) || result.method !== "cohen_h_normal_v1"
      || !Number.isInteger(result.fixedEnrollment.control) || result.fixedEnrollment.control < 1
      || result.fixedEnrollment.control !== result.fixedEnrollment.treatment) {
    return "Invalid analytic curve metadata.";
  }
  if (result.plannedPointDropout !== undefined && (!Number.isFinite(result.plannedPointDropout)
      || result.plannedPointDropout < 0 || result.plannedPointDropout >= 1)) return "Invalid planned point dropout.";
  if (result.powerCurve.length < 2 || result.powerCurve.some((point, index) => (
    !probability(point.baseline) || !powerValue(point.power)
    || (index > 0 && point.baseline <= result.powerCurve[index - 1].baseline)
  ))) return "Invalid curve values or baseline ordering.";
  for (const [point, baseline] of [[result.plannedPoint, current.plannedBaseline],
                                    [result.selectedPoint, current.selectedBaseline]] as const) {
    if (!probability(point.baseline) || point.baseline !== baseline || !powerValue(point.power)) {
      return "Invalid analytic point marker.";
    }
    const exact = result.powerCurve.find((sample) => sample.baseline === point.baseline);
    if (exact && (point !== result.plannedPoint || result.plannedPointDropout === undefined
        || result.plannedPointDropout === current.dropout) && exact.power !== point.power) return "Point marker disagrees with the analytic curve.";
  }
  return null;
}

export function PowerCurve({ current, result, status, error, onSelectBaseline }: PowerCurveProps) {
  const id = useId();
  const problem = curveProblem(current, result);
  if (status !== "ready" || problem || !result) {
    return <section aria-labelledby={`${id}-heading`} aria-busy={status === "loading"}>
      <h2 id={`${id}-heading`}>Analytic conditional power by baseline risk</h2>
      <p role={status === "error" ? "alert" : "status"}>
        {status === "loading" ? "Loading analytic curve for current inputs."
          : status === "error" ? (error || "Analytic curve could not be loaded.")
            : status === "idle" ? "Calculate a design and request its analytic curve." : problem}
      </p>
    </section>;
  }

  const plannedLabel = result.plannedPointDropout === undefined ? "planned baseline at selected dropout"
    : `original planned scenario at ${percent(result.plannedPointDropout)} dropout`;
  const left = 70, right = 590, top = 30, bottom = 250;
  const baselines = [...result.powerCurve.map((point) => point.baseline),
    result.plannedPoint.baseline, result.selectedPoint.baseline];
  const min = Math.min(...baselines), max = Math.max(...baselines);
  const x = (baseline: number) => left + (baseline - min) / (max - min) * (right - left);
  const y = (power: number) => bottom - power * (bottom - top);

  return <section aria-labelledby={`${id}-heading`}>
    <h2 id={`${id}-heading`}>Analytic conditional power by baseline risk</h2>
    <p role="status">Current analytic curve. {result.illustrative ? "Illustrative synthetic fixture; not a measured result." : "Calculated from the supplied API response."}</p>
    <p>Method: {result.method}. Effect: {result.effectKind === "relative_risk" ? "RR" : "ARR"}.
      Fixed enrolled counts: {current.fixedEnrollment.control} control / {current.fixedEnrollment.treatment} treatment.
      Symmetric selected dropout: {percent(current.dropout)}.</p>
    <p>Risk and power use fractions in data and percentages in labels. Power is conditional on assumptions; it does not predict efficacy.</p>
    <figure>
      <svg viewBox="0 0 640 320" width="640" height="320" role="img" aria-labelledby={`${id}-title ${id}-description`}>
        <title id={`${id}-title`}>Approximate conditional power versus control baseline event risk</title>
        <desc id={`${id}-description`}>Analytic values at {percent(current.dropout)} dropout and fixed enrollment.
          Dashed line: target {percent(current.targetPower)}. Triangle: {plannedLabel}.
          Circle: selected stress baseline. Invalid values break the trace. The numerical table follows.</desc>
        <line x1={left} y1={bottom} x2={right} y2={bottom} stroke="currentColor" />
        <line x1={left} y1={top} x2={left} y2={bottom} stroke="currentColor" />
        {[0, .5, 1].map((power) => <g key={power}>
          <line x1={left - 5} x2={left} y1={y(power)} y2={y(power)} stroke="currentColor" />
          <text x={left - 10} y={y(power) + 4} textAnchor="end">{percent(power)}</text>
        </g>)}
        {[min, max].map((baseline) => <text key={baseline} x={x(baseline)} y={bottom + 20} textAnchor="middle">{percent(baseline)}</text>)}
        <text x={(left + right) / 2} y={bottom + 48} textAnchor="middle">Control baseline event risk (%)</text>
        <text transform="translate(16 150) rotate(-90)" textAnchor="middle">Conditional power (%)</text>
        <line data-target-power={current.targetPower} x1={left} x2={right}
          y1={y(current.targetPower)} y2={y(current.targetPower)} stroke="currentColor" strokeDasharray="5 5" />
        <text x={right} y={y(current.targetPower) - 5} textAnchor="end">Target {percent(current.targetPower)}</text>
        {result.powerCurve.slice(1).map((point, index) => {
          const previous = result.powerCurve[index];
          if (previous.power === null || point.power === null) return null;
          return <line key={point.baseline} data-curve-segment={index} x1={x(previous.baseline)} y1={y(previous.power)}
            x2={x(point.baseline)} y2={y(point.power)} stroke="currentColor" />;
        })}
        {result.plannedPoint.power !== null ? <polygon data-marker="planned" data-baseline={result.plannedPoint.baseline}
          data-power={result.plannedPoint.power} points={`${x(result.plannedPoint.baseline)},${y(result.plannedPoint.power)-6} ${x(result.plannedPoint.baseline)-6},${y(result.plannedPoint.power)+6} ${x(result.plannedPoint.baseline)+6},${y(result.plannedPoint.power)+6}`} fill="none" stroke="currentColor" /> : null}
        {result.selectedPoint.power !== null ? <circle data-marker="selected" data-baseline={result.selectedPoint.baseline}
          data-power={result.selectedPoint.power} cx={x(result.selectedPoint.baseline)} cy={y(result.selectedPoint.power)} r="5" fill="none" stroke="currentColor" /> : null}
      </svg>
      <figcaption>Solid segments: supplied analytic power. Dashed line: selected target.
        Triangle: {plannedLabel}. Circle: selected baseline.
        Null/invalid scenarios have no point marker or connecting segment.</figcaption>
    </figure>
    <table>
      <caption>Analytic curve at symmetric dropout {percent(current.dropout)}; target {percent(current.targetPower)}</caption>
      <thead><tr><th scope="col">Control baseline risk</th><th scope="col">Approximate conditional power</th>
        {onSelectBaseline ? <th scope="col">Select baseline</th> : null}</tr></thead>
      <tbody>{result.powerCurve.map((point) => <tr key={point.baseline}>
        <th scope="row">{percent(point.baseline)} ({point.baseline} fraction)</th>
        <td>{point.power === null ? "Invalid scenario (null)" : percent(point.power)}</td>
        {onSelectBaseline ? <td><button type="button" disabled={point.power === null}
          onClick={() => onSelectBaseline(point.baseline)}>Select baseline {percent(point.baseline)}</button></td> : null}
      </tr>)}</tbody>
    </table>
    <p>Inputs hash: {result.inputsHash}</p>
  </section>;
}


/** Raw #66 data before coordinate-only frontend normalization. #76 passes this
 * with a detached #72 state snapshot captured at grid request start.
 */
export interface CurveApiResponse {
  method: "cohen_h_normal_v1";
  inputs_hash: string;
  fixed_enrollment: { control: number; treatment: number };
  target_power: number;
  power_curve: readonly { p_control: number; power: number | null; is_valid: boolean }[];
  planned_point: { p_control: number; dropout: number; power: number | null };
  selected_point: { p_control: number; dropout: number; power: number | null } | null;
}

function workspaceIdentity(state: WorkspaceState): string {
  return JSON.stringify([state.requestRevision, state.calculatedDesign?.inputs_hash,
    state.plannedDraft, state.frozenEnrollment, state.stressBaseline,
    state.stressDropout, state.provenanceLedger]);
}

/** Pure handoff adapter; no API calls, interpolation or statistical calculation. */
export function workspaceCurveProps(currentState: WorkspaceState,
  completed: { requestState: WorkspaceState; response: CurveApiResponse } | null): PowerCurveProps {
  const captured = completed?.requestState, raw = completed?.response;
  const fresh = captured && workspaceIdentity(currentState) === workspaceIdentity(captured);
  function context(state: WorkspaceState, inputsHash: string): CurveContext {
    return { inputsHash, designHash: state.calculatedDesign?.inputs_hash ?? "",
      fixedEnrollment: state.frozenEnrollment ?? { control: 0, treatment: 0 },
      dropout: state.stressDropout, effectKind: state.plannedDraft.effect.kind,
      targetPower: state.plannedDraft.target_power,
      plannedBaseline: state.plannedDraft.control_event_rate, selectedBaseline: state.stressBaseline };
  }
  const current = context(currentState, raw ? (fresh ? raw.inputs_hash : `stale:${raw.inputs_hash}`) : "");
  if (currentState.designStatus === "calculating" || currentState.gridStatus === "loading") {
    return { current, result: null, status: "loading" };
  }
  if (currentState.gridStatus === "error") {
    return { current, result: null, status: "error", error: currentState.gridError ?? "Grid request failed." };
  }
  if (!captured || !raw || !captured.frozenEnrollment || !captured.calculatedDesign) {
    return { current, result: null, status: "idle" };
  }
  if (!raw.power_curve || !raw.selected_point || raw.planned_point.power === undefined
      || raw.selected_point.power === undefined || !raw.fixed_enrollment) {
    return { current, result: null, status: "error", error: "Raw analytic curve and comparison powers are required." };
  }
  const expected = context(captured, raw.inputs_hash);
  if (raw.target_power !== expected.targetPower
      || raw.fixed_enrollment.control !== expected.fixedEnrollment.control
      || raw.fixed_enrollment.treatment !== expected.fixedEnrollment.treatment
      || raw.planned_point.p_control !== expected.plannedBaseline
      || raw.planned_point.dropout !== captured.plannedDraft.dropout.control
      || raw.selected_point.p_control !== expected.selectedBaseline
      || raw.selected_point.dropout !== expected.dropout
      || raw.power_curve.some(p => p.is_valid !== (p.power !== null))) {
    return { current, result: null, status: "error", error: "Analytic response disagrees with its captured workspace request." };
  }
  const result: CurveSnapshot = { ...expected, method: raw.method,
    powerCurve: raw.power_curve.map(p => ({ baseline: p.p_control, power: p.power })),
    plannedPoint: { baseline: raw.planned_point.p_control, power: raw.planned_point.power },
    selectedPoint: { baseline: raw.selected_point.p_control, power: raw.selected_point.power },
    plannedPointDropout: raw.planned_point.dropout, illustrative: false };
  if (currentState.designStatus !== "success" || currentState.gridStatus !== "success") {
    current.inputsHash = `stale:${raw.inputs_hash}`;
  }
  return { current, result, status: "ready" };
}
