"use client";

import { useId } from "react";
import { GridDataTable } from "./GridDataTable";

export interface HeatmapPoint { baseline: number; dropout: number }
/** Proposed local handoff only: adapt to #72/#66 contracts before #76 wiring. */
export interface HeatmapContext {
  inputsHash: string;
  designHash: string;
  fixedEnrollment: { control: number; treatment: number };
  effectKind: "relative_risk" | "absolute_risk_reduction";
  effectValue: number;
  targetPower: number;
  selectedPoint: HeatmapPoint;
}
export interface HeatmapSnapshot extends HeatmapContext {
  method: "cohen_h_normal_v1";
  gridLabel: "expected_count_approximation";
  xBaseline: readonly number[];
  yDropout: readonly number[];
  /** Rows are dropout; columns are baseline. Null iff invalidMask is true. */
  power: readonly (readonly (number | null)[])[];
  invalidMask: readonly (readonly boolean[])[];
  /** Supplied target contours, each independently connected. Never flatten. */
  frontierSegments: readonly (readonly HeatmapPoint[])[];
  illustrative: boolean;
  warnings: readonly string[];
}
export interface StressHeatmapProps {
  current: HeatmapContext;
  result: HeatmapSnapshot | null;
  status: "idle" | "loading" | "ready" | "error";
  error?: string;
  onSelectPoint?: (point: HeatmapPoint) => void;
}
export const percent = (value: number) => `${(value * 100).toFixed(1)}%`;
const probability = (value: number) => Number.isFinite(value) && value > 0 && value < 1;
const dropout = (value: number) => Number.isFinite(value) && value >= 0 && value < 1;
const samePoint = (a: HeatmapPoint, b: HeatmapPoint) => a.baseline === b.baseline && a.dropout === b.dropout;
const ordered = (values: readonly number[], valid: (value: number) => boolean) => values.length >= 2
  && values.every((value, index) => valid(value) && (index === 0 || value > values[index - 1]));

export function heatmapProblem(current: HeatmapContext, result: HeatmapSnapshot | null): string | null {
  if (!result) return "No analytic grid is available.";
  if (!current.inputsHash || !current.designHash || current.inputsHash !== result.inputsHash
    || current.designHash !== result.designHash || current.effectKind !== result.effectKind
    || current.effectValue !== result.effectValue || current.targetPower !== result.targetPower
    || current.fixedEnrollment.control !== result.fixedEnrollment.control
    || current.fixedEnrollment.treatment !== result.fixedEnrollment.treatment
    || !samePoint(current.selectedPoint, result.selectedPoint)) return "Stale analytic grid: refresh for current design and stress inputs.";
  if (result.method !== "cohen_h_normal_v1" || result.gridLabel !== "expected_count_approximation"
    || !probability(result.targetPower) || !Number.isInteger(result.fixedEnrollment.control)
    || result.fixedEnrollment.control < 1 || result.fixedEnrollment.control !== result.fixedEnrollment.treatment
    || !probability(result.effectValue) || !["relative_risk", "absolute_risk_reduction"].includes(result.effectKind)
    || !ordered(result.xBaseline, probability) || !ordered(result.yDropout, dropout)) return "Invalid analytic grid metadata or axes.";
  if (result.power.length !== result.yDropout.length || result.invalidMask.length !== result.yDropout.length
    || result.power.some((row, r) => row.length !== result.xBaseline.length
      || result.invalidMask[r].length !== result.xBaseline.length || row.some((value, c) => {
        const invalid = result.invalidMask[r][c];
        return typeof invalid !== "boolean" || (invalid ? value !== null
          : value === null || !Number.isFinite(value) || value < 0 || value > 1)
          || (result.effectKind === "absolute_risk_reduction" && result.xBaseline[c] <= result.effectValue && !invalid);
      }))) return "Invalid grid dimensions, power values or null mask.";
  const inDomain = (point: HeatmapPoint) => probability(point.baseline) && dropout(point.dropout)
    && point.baseline >= result.xBaseline[0] && point.baseline <= result.xBaseline.at(-1)!
    && point.dropout >= result.yDropout[0] && point.dropout <= result.yDropout.at(-1)!;
  if (!inDomain(result.selectedPoint) || result.frontierSegments.some(segment => segment.length < 2 || segment.some(point => !inDomain(point)))) {
    return "Invalid selected point or frontier domain.";
  }
  return null;
}

/** Cell boundaries in data space; nonuniform axes retain their actual spacing. */
export function cellEdges(values: readonly number[]): number[] {
  return [values[0], ...values.slice(1).map((value, i) => (values[i] + value) / 2), values.at(-1)!];
}
/** Conservative clipping: suppress any contour edge touching an unavailable cell. */
export function frontierEdgeAllowed(result: HeatmapSnapshot, a: HeatmapPoint, b: HeatmapPoint): boolean {
  const xs = cellEdges(result.xBaseline), ys = cellEdges(result.yDropout);
  return !result.invalidMask.some((row, r) => row.some((invalid, c) => {
    if (!invalid) return false;
    let lo = 0, hi = 1;
    for (const [start, delta, min, max] of [[a.baseline, b.baseline - a.baseline, xs[c], xs[c + 1]],
      [a.dropout, b.dropout - a.dropout, ys[r], ys[r + 1]]]) {
      if (delta === 0) { if (start < min || start > max) return false; }
      else { const t1 = (min - start) / delta, t2 = (max - start) / delta;
        lo = Math.max(lo, Math.min(t1, t2)); hi = Math.min(hi, Math.max(t1, t2)); }
    }
    return lo <= hi;
  }));
}
export function selectGridCell(result: HeatmapSnapshot, row: number, column: number,
  onSelectPoint?: (point: HeatmapPoint) => void): void {
  if (!Number.isInteger(row) || !Number.isInteger(column) || result.invalidMask[row]?.[column] !== false
    || result.power[row]?.[column] == null) return;
  onSelectPoint?.({ baseline: result.xBaseline[column], dropout: result.yDropout[row] });
}

export function StressHeatmap({ current, result, status, error, onSelectPoint }: StressHeatmapProps) {
  const id = useId();
  const problem = heatmapProblem(current, result);
  if (status !== "ready" || problem || !result) return <section aria-labelledby={`${id}-heading`} aria-busy={status === "loading"}>
    <h2 id={`${id}-heading`}>Sensitivity heatmap</h2>
    <p role={status === "error" ? "alert" : "status"}>{status === "loading" ? "Loading analytic grid for current inputs."
      : status === "error" ? error || "Analytic grid could not be loaded."
        : status === "idle" ? "Calculate a design and request its analytic grid." : problem}</p>
  </section>;
  const left = 85, right = 585, top = 35, bottom = 265;
  const xs = cellEdges(result.xBaseline), ys = cellEdges(result.yDropout);
  const x = (v: number) => left + (v - xs[0]) / (xs.at(-1)! - xs[0]) * (right - left);
  const y = (v: number) => bottom - (v - ys[0]) / (ys.at(-1)! - ys[0]) * (bottom - top);
  const selectedValid = result.effectKind !== "absolute_risk_reduction" || result.selectedPoint.baseline > result.effectValue;
  const selectedCell = result.invalidMask.some((row, r) => row.some((invalid, c) => invalid
    && result.selectedPoint.baseline >= xs[c] && result.selectedPoint.baseline <= xs[c + 1]
    && result.selectedPoint.dropout >= ys[r] && result.selectedPoint.dropout <= ys[r + 1]));
  return <section aria-labelledby={`${id}-heading`}>
    <h2 id={`${id}-heading`}>Sensitivity heatmap</h2>
    <p role="status">{result.illustrative ? "Illustrative synthetic fixture; not a measured result." : "Supplied analytic grid."}</p>
    <p>Analytic power at floor-based expected retained counts: floor(enrolled × (1 − dropout)) per arm.
      This expected-count approximation uses frozen enrollment: {current.fixedEnrollment.control} control / {current.fixedEnrollment.treatment} treatment.
      Selected Monte Carlo results are shown separately by the simulation panel; they use sampled actual retained counts.</p>
    <p>Method: {result.method}. Effect: {result.effectKind === "relative_risk" ? "RR" : "ARR"} {result.effectValue}.
      Target: {percent(result.targetPower)}. Conditional power does not predict efficacy.</p>
    <figure>
      <svg viewBox="0 0 650 345" width="650" height="345" role="img" aria-labelledby={`${id}-title ${id}-desc`}>
        <title id={`${id}-title`}>Analytic sensitivity grid, baseline horizontally and dropout vertically</title>
        <desc id={`${id}-desc`}>Rows are dropout and columns are baseline. Higher dropout is at the top.
          Gray crossed cells are invalid, never zero power. Darker blue means higher power.
          Dashed lines show supplied target frontier segments. Circle marks the selected point. Select cells using the table below.</desc>
        {result.power.map((row, r) => row.map((power, c) => <g key={`${r}-${c}`} data-cell={`${r}-${c}`} data-baseline={result.xBaseline[c]} data-dropout={result.yDropout[r]} data-power={power === null ? "null" : power}
          role={onSelectPoint ? "button" : undefined} tabIndex={onSelectPoint && power !== null ? 0 : undefined}
          aria-disabled={onSelectPoint ? power === null : undefined}
          aria-label={`Baseline ${percent(result.xBaseline[c])}, dropout ${percent(result.yDropout[r])}: ${power === null ? "Invalid scenario; ARR requires baseline greater than ARR" : `power ${percent(power)}`}`}
          onClick={() => selectGridCell(result, r, c, onSelectPoint)}
          onKeyDown={event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); selectGridCell(result, r, c, onSelectPoint); } }}>
          <rect x={x(xs[c])} y={y(ys[r + 1])} width={x(xs[c + 1]) - x(xs[c])} height={y(ys[r]) - y(ys[r + 1])}
            fill={power === null ? "#bdbdbd" : "#2166ac"} fillOpacity={power === null ? 1 : .12 + power * .88} stroke="currentColor" />
          {power === null ? <path data-invalid="true" d={`M ${x(xs[c])} ${y(ys[r])} L ${x(xs[c + 1])} ${y(ys[r + 1])} M ${x(xs[c])} ${y(ys[r + 1])} L ${x(xs[c + 1])} ${y(ys[r])}`} stroke="currentColor" /> : null}
          <title>{`Baseline ${percent(result.xBaseline[c])}, dropout ${percent(result.yDropout[r])}: ${power === null ? "Invalid scenario (null)" : percent(power)}`}</title>
        </g>))}
        {result.frontierSegments.map((segment, s) => segment.slice(1).map((point, i) => frontierEdgeAllowed(result, segment[i], point)
          ? <line key={`${s}-${i}`} data-frontier-segment={`${s}-${i}`} data-target-power={result.targetPower}
            x1={x(segment[i].baseline)} y1={y(segment[i].dropout)} x2={x(point.baseline)} y2={y(point.dropout)} stroke="black" strokeWidth="2" strokeDasharray="5 5" /> : null))}
        {selectedValid && !selectedCell ? <circle data-marker="selected" data-baseline={result.selectedPoint.baseline} data-dropout={result.selectedPoint.dropout}
          cx={x(result.selectedPoint.baseline)} cy={y(result.selectedPoint.dropout)} r="7" fill="none" stroke="black" strokeWidth="3" /> : null}
        {result.xBaseline.map(v => <text key={v} x={x(v)} y={bottom + 20} textAnchor="middle">{percent(v)}</text>)}
        {result.yDropout.map(v => <text key={v} x={left - 8} y={y(v) + 4} textAnchor="end">{percent(v)}</text>)}
        <text x={(left + right) / 2} y={bottom + 50} textAnchor="middle">Control baseline event risk (%)</text>
        <text transform="translate(18 150) rotate(-90)" textAnchor="middle">Symmetric dropout (%)</text>
      </svg>
      <figcaption>Blue: analytic power (pale = zero, dark = one). Gray with cross: invalid/null.
        Dashed: supplied {percent(result.targetPower)} target frontier; segments never join across invalid cells.
        Circle: selected stress point. Use the native selection buttons below with click, Enter or Space.</figcaption>
    </figure>
    {!selectedValid || selectedCell ? <p role="status">Selected scenario is invalid; no simulation selection is emitted. ARR requires baseline greater than ARR so treatment risk stays positive.</p> : null}
    {result.warnings.map((warning, i) => <p key={i}>Warning: {warning}</p>)}
    <GridDataTable result={result} onSelectPoint={onSelectPoint} />
    <p>Inputs hash: {result.inputsHash}. Design hash: {result.designHash}.</p>
  </section>;
}
