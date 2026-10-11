"use client";

import caseStudy from "../lib/historical/aerify-v1.json";

interface HistoricalCaseStudyProps {
  onLoadExample: (presetId: string) => void;
}

export function HistoricalCaseStudy({ onLoadExample }: HistoricalCaseStudyProps) {
  return <section aria-labelledby="historical-case-heading">
    <h2 id="historical-case-heading">Historical case study: {caseStudy.title}</h2>
    <p>{caseStudy.drug}, developed by {caseStudy.developers}, was studied for {caseStudy.condition}.</p>
    <ul>{caseStudy.trials.map(trial => <li key={trial.nct_id}>
      <a href={trial.registry_url}>{trial.name} ({trial.nct_id})</a>: {trial.reported_outcome}
    </li>)}</ul>
    <p><strong>Reported endpoint:</strong> {caseStudy.endpoint}.</p>
    <p>{caseStudy.report.summary} <a href={caseStudy.report.url}>{caseStudy.report.label}</a>.</p>
    <p>{caseStudy.limitations}</p>
    <h3>What earlier stress-testing could have revealed</h3>
    <p>Before enrollment, a team could ask: if fewer events occur than our plan expects,
      will our fixed sample still give us the chance of detecting the assumed benefit?
      Better Baseline makes this sensitivity visible for binary-outcome designs, so
      teams can discuss more conservative assumptions or enrollment margins with a statistician.</p>
    <p>Applying that workflow to AERIFY would require a validated recurrent-event model
      and its original planning assumptions. This prototype illustrates the planning question;
      it does not establish that a different design would have changed AERIFY-2&apos;s result.</p>
    <h3>Explore the mechanism with default sample data</h3>
    <p>{caseStudy.illustrative_disclosure}</p>
    <button type="button" onClick={() => onLoadExample(caseStudy.illustrative_preset_id)}>
      Load default synthetic baseline-collapse example
    </button>
    <p>Calculate &amp; Lock Design, then compare the planned and stressed risks with enrollment fixed.
      This is an educational example, not regulatory advice.</p>
  </section>;
}
