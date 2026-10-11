"use client";

import { heatmapProblem, percent, selectGridCell, type HeatmapSnapshot, type HeatmapPoint } from "./StressHeatmap";

/** Null is exported literally and the mask is preserved, never coerced to zero. */
export function gridCsv(result: HeatmapSnapshot): string {
  const rows = ["baseline_fraction,dropout_fraction,analytic_power_fraction,invalid,selected,target_power_fraction,inputs_hash,design_hash"];
  const quote = (value: string) => `"${value.replaceAll('"', '""')}"`;
  result.power.forEach((row, r) => row.forEach((power, c) => rows.push([
    result.xBaseline[c], result.yDropout[r], power === null ? "null" : power, result.invalidMask[r][c],
    result.selectedPoint.baseline === result.xBaseline[c] && result.selectedPoint.dropout === result.yDropout[r],
    result.targetPower, quote(result.inputsHash), quote(result.designHash),
  ].join(","))));
  return rows.join("\r\n") + "\r\n";
}
export function GridDataTable({ result, onSelectPoint }: {
  result: HeatmapSnapshot;
  onSelectPoint?: (point: HeatmapPoint) => void;
}) {
  const problem = heatmapProblem(result, result);
  if (problem) return <p role="alert">{problem}</p>;
  return <>
    <table>
      <caption>Analytic power matrix [dropout][baseline], floor-based expected retained counts; selected MC shown separately.</caption>
      <thead><tr><th scope="col">Symmetric dropout ↓ / Baseline →</th>{result.xBaseline.map(baseline =>
        <th key={baseline} scope="col">{percent(baseline)} ({baseline} fraction)</th>)}</tr></thead>
      <tbody>{result.power.map((row, r) => <tr key={result.yDropout[r]}>
        <th scope="row">{percent(result.yDropout[r])} ({result.yDropout[r]} fraction)</th>
        {row.map((power, c) => {
          const selected = result.selectedPoint.baseline === result.xBaseline[c] && result.selectedPoint.dropout === result.yDropout[r];
          return <td key={result.xBaseline[c]}>
            {power === null ? "Invalid scenario (null). ARR requires baseline greater than ARR; unavailable cells cannot be simulated." : `${percent(power)} (${power} fraction)`}
            {selected ? " — selected" : ""}
            {onSelectPoint ? <button type="button" disabled={power === null} aria-pressed={selected}
              onClick={() => selectGridCell(result, r, c, onSelectPoint)}>
              Select baseline {percent(result.xBaseline[c])}, dropout {percent(result.yDropout[r])}
            </button> : null}
          </td>;
        })}
      </tr>)}</tbody>
    </table>
    <a download="analytic-grid.csv" href={`data:text/csv;charset=utf-8,${encodeURIComponent(gridCsv(result))}`}>Download analytic grid CSV (fractions, nulls and invalid mask)</a>
  </>;
}
