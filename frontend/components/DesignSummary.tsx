"use client";


import { useId } from "react";
import type { CalculateResponse } from "../lib/contracts";

/** Accept the live design response and optional parent-owned source metadata. */
export type DesignSummaryResult = Omit<CalculateResponse, "mock" | "provenance"> & {
  mock?: boolean;
  /** Source metadata belongs to the parent; the live design API omits it. */
  provenance?: CalculateResponse["provenance"];
};

export interface DesignSummaryProps {
  result: DesignSummaryResult | null;
  isStale?: boolean;
  isCalculating?: boolean;
  error?: string | null;
}

function percent(fraction: number) {
  return `${(fraction * 100).toFixed(2)}%`;
}

/** Read-only view. Network and result identity belong to the parent (#72). */
export function DesignSummary({ result, isStale = false, isCalculating = false, error = null }: DesignSummaryProps) {
  const id = useId();
  const stale = isStale || isCalculating || Boolean(error);
  return <section className="planning-summary" aria-labelledby={`${id}-summary-heading`} aria-busy={isCalculating}>
    <h2 id={`${id}-summary-heading`}>Enrollment estimate</h2>
    {error && <p role="alert">{error}</p>}
    {isCalculating && <p role="status">Calculating a new planned design.</p>}
    {!result ? <p>No calculated design available. Enter assumptions and calculate a design.</p> : <>
      {stale && <p role="status"><strong>Stale result.</strong> These values belong to the previous calculation; recalculate to match current assumptions.</p>}
      {result.mock && <p><strong>Illustrative mock response.</strong> These fixed fixture values are not a fresh statistical calculation.</p>}
      <div className="planning-tableScroll" role="region" aria-label="Planned enrollment counts" tabIndex={0}><table>
        <caption>People to enroll versus people expected to have usable outcome data</caption>
        <thead><tr><th scope="col">Count</th><th scope="col">Control arm</th><th scope="col">Treatment arm</th></tr></thead>
        <tbody>
          <tr><th scope="row">Needed with outcome data</th><td>{result.evaluable_n.control}</td><td>{result.evaluable_n.treatment}</td></tr>
          <tr><th scope="row">Planned to enroll</th><td>{result.enrolled_n.control}</td><td>{result.enrolled_n.treatment}</td></tr>
        </tbody>
      </table></div>
      <p>Enrollment accounts for expected dropout. It cannot guarantee how many people will remain or have usable outcome data.</p>
      <dl>
        <dt>Estimated chance of detecting the assumed difference</dt><dd>{percent(result.nominal_power_evaluable)}</dd>
        <dt>Assumed treatment-group event rate</dt><dd>{percent(result.p_treatment)}</dd>
        <dt>Method</dt><dd>Cohen’s-h two-sided normal approximation ({result.method})</dd>
        <dt>Model version</dt><dd>{result.model_version}</dd>
        <dt>Inputs fingerprint</dt><dd style={{ overflowWrap: "anywhere" }}>{result.inputs_hash}</dd>
        {result.provenance ? <>
        <dt>Source</dt><dd>{result.provenance.label} — {result.provenance.scenario_kind}; {result.provenance.source.type}</dd>
        <dt>Scenario ID</dt><dd>{result.provenance.scenario_id}</dd>
        <dt>Follow-up</dt><dd>{result.provenance.follow_up_label}</dd>
        <dt>Source generator</dt><dd>{result.provenance.generated_by}</dd>
        <dt>Provenance method version</dt><dd>{result.provenance.method_version}</dd>
        </> : <><dt>Source</dt><dd>Source metadata was not supplied with this result.</dd></>}
      </dl>
      {result.warnings.length > 0 && <><h3>Method warnings</h3><ul>{result.warnings.map((warning, index) => <li key={`${index}-${warning}`}>{warning}</li>)}</ul></>}
      <p>Power is conditional on the specified assumptions and method. It does not predict whether treatment works.</p>
    </>}
  </section>;
}
