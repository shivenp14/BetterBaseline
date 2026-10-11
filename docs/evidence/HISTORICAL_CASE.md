# Historical sensitivity demonstration — #110 preparation

No historical case has been selected or reconstructed in this draft. The
source-review handoff from #108 is pending. The template contains unknown values,
not trial facts or simulated evidence. The numerical evidence in #109 validates
parts of the mathematical engine; it cannot supply missing historical inputs.

## Question the demonstration should answer

Could a planning team have noticed that its planned participant count was
sensitive to reasonable uncertainty in event risk, expected benefit or dropout?
The demonstration should show the measured change in detection probability at
the original enrollment, followed by a separately labeled alternative design.
It cannot prove that the sponsor would have changed its protocol or that a
treatment would succeed.

## Intake handoff

[intake-template.json](../../evidence/case-studies/intake-template.json) is a
proposed case-study worksheet, not a replacement for #108's source ledger or
the production request/export contracts. Fill it only after the source reviewer
accepts the case; link that review and the authoritative ledger. Adapt its field
references to the ledger's delivered format rather than changing that format.

Every original planning number needs a source reference that identifies the
URL, page/table/section, publication date, units and planning-date availability.
Keep later observations in their separate record. Unknown planning assumptions
remain null; neither final event counts nor an observed treatment effect can
reconstruct what researchers originally assumed.

| Required handoff | Owner/dependency | Use in this issue |
| --- | --- | --- |
| Compatible case, verified original assumptions, source-review signoff | #108 | Select inputs and decide whether reconstruction is possible |
| Numerical validation and method limits | #109, #82 | Interpret analytic power, pooled-z results and MCSE |
| Final live page and independently downloadable export | #76 | Capture the actual product result rather than manufacture export JSON |
| Acceptance, provenance and installed offline workflow | #78, #79, #81 | Rerun and verify the complete demonstration |

The proposed AERIFY, RESPECT and STICH examples remain research leads. Rate,
recurrent-event and survival endpoints need source screening by #108. Do not
convert patient-year rates to probabilities, substitute hazard ratios for risk
ratios, or use median follow-up as the model's binary observation window. If no
case fits, publish the compatibility gap and retain a clearly synthetic demo.

## Execution protocol after intake approval

1. Before looking at simulation output, record the original assumptions and
   original per-arm enrollment. Check a fixed-window binary adverse outcome,
   equal allocation, symmetric dropout and compatible risk/effect definitions.
   Any approximation or departure from the original analysis must be explicit.
2. Record scenario ranges justified by information available at planning time:
   original assumptions, lower control risk, weaker *assumed* benefit and higher
   dropout. Do not invent numeric ranges in this preparation. If later observed
   rates are included, add a separate hindsight scenario with that label. An
   observed-effect post-hoc power calculation is not an explanation of failure.
3. Use the actual calculate endpoint to document the reconstructed design, but
   keep the source-documented enrollment frozen in the historical stress/grid
   and seeded simulation requests. If the calculated enrollment differs, report
   the difference; never silently replace the original count with the solver's.
4. Capture each raw request/response, its hash, source references, software,
   methods, warnings, seed, replicate count, timestamp and engine commit. Obtain
   the real UI export separately and compare it with the capture using #79's
   checker. Hand-authored JSON cannot stand in for a downloaded export.
5. Calculate a candidate larger enrollment in a separate scenario. Preserve the
   historical inputs/results. Follow-up-duration alternatives remain out of
   scope until a compatible time/endpoint model is validated.
6. Rerun on a clean installed environment and obtain scientific review. Add the
   concrete command only when the case runner and approved inputs exist; this
   preparation deliberately has no executable historical reconstruction.

## Judge-facing output to produce

The final page should state the question in one sentence and show a table with
original assumptions, each sourced planning-time sensitivity scenario, any
explicit hindsight scenario, and the separately labeled candidate design.
Columns should include fixed enrollment, expected retention, assumed risks,
analytic power, two-sided/favorable simulated fractions, their separate MCSEs,
invalid-test frequency and source links. Add one chart of detection probability
across a sourced uncertainty range at original enrollment; do not cherry-pick a
single dramatic point or bridge invalid scenarios.

Only after measurements, use this conditional narrative with actual values:

> Under these sourced assumptions, Better Baseline would have flagged [measured
> sensitivity] at [original enrollment], allowing the planning team to examine
> [specific supported design alternative] with its statistician.

Explain that retrospective sensitivity analysis does not predict efficacy,
establish causality, prove a trial could have been saved or measure dollars saved.
A nonsignificant original result does not establish no benefit, and additional
follow-up does not itself establish that the initial design was flawed.

## Current completion boundary

This PR starts #110's intake and execution plan only. There are no historical
measurements, selected sponsor claims, completed chart, downloaded export,
successful case rerun or scientific signoff. Those deliverables remain gated by
the handoffs above. Product code, model semantics and #108's ledger are untouched.
