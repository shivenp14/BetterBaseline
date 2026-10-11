"use client";

import { useId } from "react";
import { GridDataTable } from "./GridDataTable";
import type { WorkspaceState } from "../lib/workspace-contracts";
import type { GridResponse, FixedEnrollment, StatisticalDiagnostic } from "../lib/contracts";

export interface HeatmapPoint { baseline: number; dropout: number }
/** Presentational identity populated by workspaceHeatmapProps from #72 state. */
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
  diagnostics?: readonly StatisticalDiagnostic[];
  selectedPower?: number | null;
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
  if (result.selectedPower !== undefined && result.selectedPower !== null
    && (!Number.isFinite(result.selectedPower) || result.selectedPower < 0 || result.selectedPower > 1)) {
    return "Invalid selected analytic power.";
  }
  const selectedRow = result.yDropout.indexOf(result.selectedPoint.dropout);
  const selectedColumn = result.xBaseline.indexOf(result.selectedPoint.baseline);
  if (result.selectedPower !== undefined && selectedRow >= 0 && selectedColumn >= 0
    && result.power[selectedRow][selectedColumn] !== result.selectedPower) return "Selected point disagrees with the analytic grid.";
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
  if (status !== "ready" || problem || !result) return <section className="workspace-section chart-panel" aria-labelledby={`${id}-heading`} aria-busy={status === "loading"}>
    <h2 className="section-heading" id={`${id}-heading`}>Sensitivity heatmap</h2>
    <p className={status === "error" ? "status-error" : problem?.startsWith("Stale") ? "status-warning" : "chart-empty"} role={status === "error" ? "alert" : "status"}>{status === "loading" ? "Loading analytic grid for current inputs."
      : status === "error" ? error || "Analytic grid could not be loaded."
        : status === "idle" ? "Calculate a design and request its analytic grid." : problem}</p>
  </section>;
  const left = 85, right = 585, top = 35, bottom = 265;
  const xs = cellEdges(result.xBaseline), ys = cellEdges(result.yDropout);
  const x = (v: number) => left + (v - xs[0]) / (xs.at(-1)! - xs[0]) * (right - left);
  const y = (v: number) => bottom - (v - ys[0]) / (ys.at(-1)! - ys[0]) * (bottom - top);
  const selectedValid = result.selectedPower !== null
    && (result.effectKind !== "absolute_risk_reduction" || result.selectedPoint.baseline > result.effectValue);
  const selectedCell = result.selectedPower === undefined && result.invalidMask.some((row, r) => row.some((invalid, c) => invalid
    && result.selectedPoint.baseline >= xs[c] && result.selectedPoint.baseline <= xs[c + 1]
    && result.selectedPoint.dropout >= ys[r] && result.selectedPoint.dropout <= ys[r + 1]));
  return <section className="workspace-section chart-panel" aria-labelledby={`${id}-heading`}>
    <h2 className="section-heading" id={`${id}-heading`}>Sensitivity heatmap</h2>
    <p className={result.illustrative ? "status-warning" : "status-success"} role="status">{result.illustrative ? "Illustrative synthetic fixture; not a measured result." : "Supplied analytic grid."}</p>
    <p>Analytic power at floor-based expected retained counts: floor(enrolled × (1 − dropout)) per arm.
      This expected-count approximation uses frozen enrollment: {current.fixedEnrollment.control} control / {current.fixedEnrollment.treatment} treatment.
      Selected Monte Carlo results are shown separately by the simulation panel; they use sampled actual retained counts.</p>
    <p>Method: {result.method}. Effect: {result.effectKind === "relative_risk" ? "RR" : "ARR"} {result.effectValue}.
      Target: {percent(result.targetPower)}. Conditional power does not predict efficacy.</p>
    <figure className="chart-figure">
      <p className="chart-scroll-hint">Scroll horizontally to inspect the full chart; focus the chart region and use arrow keys.</p>
      <div className="chart-scroll" role="region" aria-label="Sensitivity heatmap, horizontally scrollable" tabIndex={0}>
      <svg className="chart-svg" viewBox="0 0 650 345" width="650" height="345" role="img" aria-labelledby={`${id}-title ${id}-desc`}>
        <title id={`${id}-title`}>Analytic sensitivity grid, baseline horizontally and dropout vertically</title>
        <desc id={`${id}-desc`}>Rows are dropout and columns are baseline. Higher dropout is at the top.
          Slate crossed cells are invalid, never zero power. Stronger mint means higher power.
          Dashed lines show supplied target frontier segments. Circle marks the selected point. Select cells using the table below.</desc>
        {result.power.map((row, r) => row.map((power, c) => <g className="heatmap-cell" key={`${r}-${c}`} data-cell={`${r}-${c}`} data-baseline={result.xBaseline[c]} data-dropout={result.yDropout[r]} data-power={power === null ? "null" : power}
          role={onSelectPoint ? "button" : undefined} tabIndex={onSelectPoint && power !== null ? 0 : undefined}
          aria-disabled={onSelectPoint ? power === null : undefined}
          aria-label={`Baseline ${percent(result.xBaseline[c])}, dropout ${percent(result.yDropout[r])}: ${power === null ? "Invalid scenario; ARR requires baseline greater than ARR and retained counts must support the analytic test" : `power ${percent(power)}`}`}
          onClick={() => selectGridCell(result, r, c, onSelectPoint)}
          onKeyDown={event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); selectGridCell(result, r, c, onSelectPoint); } }}>
          <rect className="heatmap-cell-body" x={x(xs[c])} y={y(ys[r + 1])} width={x(xs[c + 1]) - x(xs[c])} height={y(ys[r]) - y(ys[r + 1])}
            fill={power === null ? "#17262E" : "#A8E6C5"} fillOpacity={power === null ? 1 : .12 + power * .88} stroke="currentColor" />
          {power === null ? <path data-invalid="true" d={`M ${x(xs[c])} ${y(ys[r])} L ${x(xs[c + 1])} ${y(ys[r + 1])} M ${x(xs[c])} ${y(ys[r + 1])} L ${x(xs[c + 1])} ${y(ys[r])}`} stroke="currentColor" /> : null}
          <rect className="heatmap-cell-focus" aria-hidden="true" x={x(xs[c])} y={y(ys[r + 1])}
            width={x(xs[c + 1]) - x(xs[c])} height={y(ys[r]) - y(ys[r + 1])} />
          <title>{`Baseline ${percent(result.xBaseline[c])}, dropout ${percent(result.yDropout[r])}: ${power === null ? "Invalid scenario (null)" : percent(power)}`}</title>
        </g>))}
        {result.frontierSegments.map((segment, s) => segment.slice(1).map((point, i) => frontierEdgeAllowed(result, segment[i], point)
          ? <g key={`${s}-${i}`} className="heatmap-frontier">
            <line aria-hidden="true" className="heatmap-marker-halo" x1={x(segment[i].baseline)} y1={y(segment[i].dropout)}
              x2={x(point.baseline)} y2={y(point.dropout)} strokeWidth="6" strokeDasharray="5 5" />
            <line data-frontier-segment={`${s}-${i}`} data-target-power={result.targetPower}
            x1={x(segment[i].baseline)} y1={y(segment[i].dropout)} x2={x(point.baseline)} y2={y(point.dropout)} stroke="#EAF2F2" strokeWidth="2" strokeDasharray="5 5" /></g> : null))}
        {selectedValid && !selectedCell ? <g className="heatmap-selected-marker">
          <circle aria-hidden="true" className="heatmap-marker-halo" cx={x(result.selectedPoint.baseline)}
            cy={y(result.selectedPoint.dropout)} r="7" fill="none" strokeWidth="7" />
          <circle data-marker="selected" data-baseline={result.selectedPoint.baseline} data-dropout={result.selectedPoint.dropout}
          cx={x(result.selectedPoint.baseline)} cy={y(result.selectedPoint.dropout)} r="7" fill="none" stroke="#EAF2F2" strokeWidth="3" /></g> : null}
        {result.xBaseline.map(v => <text key={v} x={x(v)} y={bottom + 20} textAnchor="middle">{percent(v)}</text>)}
        {result.yDropout.map(v => <text key={v} x={left - 8} y={y(v) + 4} textAnchor="end">{percent(v)}</text>)}
        <text x={(left + right) / 2} y={bottom + 50} textAnchor="middle">Control baseline event risk (%)</text>
        <text transform="translate(18 150) rotate(-90)" textAnchor="middle">Symmetric dropout (%)</text>
      </svg>
      </div>
      <figcaption>Mint: analytic power (faint = zero, strong = one). Slate with cross: invalid/null.
        Dashed: supplied {percent(result.targetPower)} target frontier; segments never join across invalid cells.
        Circle: selected stress point. Use the native selection buttons below with click, Enter or Space.</figcaption>
    </figure>
    {!selectedValid || selectedCell ? <p className="status-badge" role="status">Selected scenario is invalid; no simulation selection is emitted. ARR requires baseline greater than ARR so treatment risk stays positive; expected retained counts must also support the analytic test.</p> : null}
    {result.warnings.map((warning, i) => <p className="status-warning" key={i}>Warning: {warning}</p>)}
    {result.diagnostics?.map((diagnostic, i) => <p className={diagnostic.severity === "error" ? "status-error" : "status-warning"} key={i}>
      {diagnostic.severity}: {diagnostic.code} ({diagnostic.field}, {diagnostic.method}): {diagnostic.message}
    </p>)}
    <GridDataTable result={result} onSelectPoint={onSelectPoint} />
    <details className="disclosure"><summary>Grid identity</summary><p className="inline-code">Inputs hash: {result.inputsHash}. Design hash: {result.designHash}.</p></details>
  </section>;
}


/** #66 wire response before #76's coordinate-only API normalization. A flat
 * frontier_points list is intentionally unused: only supplied edges connect.
 */
export interface HeatmapApiResponse extends Pick<GridResponse,
  "method" | "grid_label" | "inputs_hash" | "x_baseline" | "y_dropout" |
  "power" | "invalid_mask" | "target_power" | "warnings" | "diagnostics"> {
  fixed_enrollment: FixedEnrollment;
  selected_point: { p_control: number; dropout: number; power: number | null; is_valid: boolean } | null;
  contour_segments: readonly {
    start: { p_control: number; dropout: number };
    end: { p_control: number; dropout: number };
  }[];
}

function workspaceIdentity(state: WorkspaceState): string {
  return JSON.stringify([state.requestRevision, state.calculatedDesign?.inputs_hash,
    state.plannedDraft, state.frozenEnrollment, state.stressBaseline,
    state.stressDropout, state.provenanceLedger]);
}

/** Pure #72/#66 handoff for #76. Capture a detached requestState at request
 * start; preserve raw grid/contour data before the shared API normalizes points.
 * Does no fetching, power calculation, contour synthesis or matrix transposition.
 */
export function workspaceHeatmapProps(currentState: WorkspaceState,
  completed: { requestState: WorkspaceState; response: HeatmapApiResponse } | null): StressHeatmapProps {
  const captured = completed?.requestState, raw = completed?.response;
  const fresh = captured && workspaceIdentity(currentState) === workspaceIdentity(captured);
  function context(state: WorkspaceState, inputsHash: string): HeatmapContext {
    return { inputsHash, designHash: state.calculatedDesign?.inputs_hash ?? "",
      fixedEnrollment: state.frozenEnrollment ?? { control: 0, treatment: 0 },
      effectKind: state.plannedDraft.effect.kind, effectValue: state.plannedDraft.effect.value,
      targetPower: state.plannedDraft.target_power,
      selectedPoint: { baseline: state.stressBaseline, dropout: state.stressDropout } };
  }
  const current = context(currentState, raw ? (fresh ? raw.inputs_hash : `stale:${raw.inputs_hash}`) : "");
  if (currentState.designStatus === "calculating" || currentState.gridStatus === "loading") {
    return { current, result: null, status: "loading" };
  }
  if (currentState.gridStatus === "error") {
    return { current, result: null, status: "error", error: currentState.gridError ?? "Grid request failed." };
  }
  if (!captured || !raw || !captured.calculatedDesign || !captured.frozenEnrollment) {
    return { current, result: null, status: "idle" };
  }
  const expected = context(captured, raw.inputs_hash);
  if (!raw.selected_point || raw.selected_point.power === undefined || !raw.fixed_enrollment
      || !Array.isArray(raw.contour_segments) || !Array.isArray(raw.power) || !Array.isArray(raw.invalid_mask)
      || raw.target_power !== expected.targetPower
      || raw.fixed_enrollment.control !== expected.fixedEnrollment.control
      || raw.fixed_enrollment.treatment !== expected.fixedEnrollment.treatment
      || raw.selected_point.p_control !== expected.selectedPoint.baseline
      || raw.selected_point.dropout !== expected.selectedPoint.dropout
      || raw.selected_point.is_valid !== (raw.selected_point.power !== null)) {
    return { current, result: null, status: "error", error: "Analytic grid disagrees with its captured workspace request or lacks segmented contours." };
  }
  const point = (p: { p_control: number; dropout: number }): HeatmapPoint => ({ baseline: p.p_control, dropout: p.dropout });
  const result: HeatmapSnapshot = { ...expected, method: raw.method, gridLabel: raw.grid_label,
    xBaseline: raw.x_baseline, yDropout: raw.y_dropout, power: raw.power,
    invalidMask: raw.invalid_mask, selectedPoint: point(raw.selected_point), selectedPower: raw.selected_point.power,
    frontierSegments: raw.contour_segments.map(edge => [point(edge.start), point(edge.end)]),
    warnings: raw.warnings, diagnostics: raw.diagnostics, illustrative: false };
  if (currentState.designStatus !== "success" || currentState.gridStatus !== "success") {
    current.inputsHash = `stale:${raw.inputs_hash}`;
  }
  return { current, result, status: "ready" };
}
