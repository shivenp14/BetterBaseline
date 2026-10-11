# Baseline Breaker — Product & Statistical Specification

**Document:** `01_BASELINE_BREAKER_SPEC.md`  
**Version:** 1.0 (HackRU handoff, 10 October 2026)  
**Companions:** [`02_INFRASTRUCTURE_ARCHITECTURE.md`](02_INFRASTRUCTURE_ARCHITECTURE.md) · [`03_IMPLEMENTATION_PLAYBOOK.md`](03_IMPLEMENTATION_PLAYBOOK.md)  
**Status:** implementation-ready MVP specification; *not* a clinical or regulatory validation.

## 1. Product charter

### One-line description

**Baseline Breaker stress-tests the statistical power of a proposed clinical trial when its planning assumptions might be wrong.** It is a prospective, reproducible sensitivity-analysis and simulation workspace, **not** a protocol author, an AI wrapper, or an estimate of whether a drug will work.

### Motivating problem

A two-arm trial can be calculated to have 80% power under a particular control-arm event rate, treatment effect, follow-up window, and retention assumption. A materially lower control event rate or weaker effect may undermine that power at the originally planned enrollment. A single “80% powered” number hides that vulnerability.

**Core user question:** *For which combinations of baseline risk, treatment effect, and dropout does my proposed design meet its statistical-power target? What happens outside that region?*

### Target users

- **Primary:** biostatisticians and clinical development teams exploring *pre-study* assumptions.
- **Secondary:** trial feasibility and operations teams communicating sensitivity to collaborators.
- **HackRU judges:** a guided synthetic example shows a clear mathematical failure mode without requiring biomedical expertise.

### User benefit and differentiation

Traditional power calculators answer: *What sample size meets a target under one input scenario?* Baseline Breaker adds: *Show the entire set of scenarios in which the proposed enrollment meets or misses that target*, using fast analytic evaluation and reproducible Monte Carlo checks. The main differentiator is the **Assumption Safety Envelope**: an interactive boundary in baseline-risk × dropout/effect space, with clear limitations and source provenance.

Existing software can already perform power analysis and advanced simulation. Do **not** claim the underlying math is new. The prototype's value is interpretable, tightly scoped stress testing and live cause-and-effect comparison.

## 2. User story & acceptance narrative

> As a researcher planning an individually randomized, parallel, 1:1, two-arm superiority study with a binary adverse primary endpoint, I want to specify a control event probability and expected relative treatment effect, calculate an evaluable and enrolled sample size, and see how the planned enrollment performs if the baseline rate or retention is different—so I can understand the sensitivity of the proposed design before finalizing it with a statistician.

The user can:

1. Load a **Synthetic Baseline Collapse** preset or enter parameters manually.
2. See treatment event probability, required **evaluable** subjects, required **enrollment** under dropout assumptions, planned analytic power, and model version.
3. Freeze enrollment and change the **assumed true** control event rate (the “shock”) without silently recalculating the original enrollment.
4. Choose **constant relative risk** or **constant absolute risk reduction** and see their different implications.
5. Inspect power curve, stress heatmap, 80%-power boundary, and a reproducible Monte Carlo estimate at a selected scenario.
6. Compare “planning design” and “stress scenario” side by side; export input parameters, results, assumptions, and provenance.
7. Optionally import trial metadata via an NCT ID. The app must **not automatically equate posted outcome results with original planning assumptions**.

### Definition of success at HackRU

A judge can move a single slider from a 20% to 10% control event rate and see why approximately 80% **nominal power under the original design assumptions** becomes approximately 47% **conditional analytic power** with the same enrollment and a fixed relative effect, using the selected approximation. The judge can then view an independent Monte Carlo estimate with its simulation error.

## 3. Formal statistical scope (MVP)

| Dimension | MVP policy |
|---|---|
| Trial | Individually randomized, parallel, two-arm superiority |
| Endpoint | One **binary** primary endpoint; event denotes an undesirable outcome |
| Comparison | Treatment vs control, independent observations |
| Allocation | Equal 1:1 for the shipped MVP; unequal ratio only after validation |
| Hypothesis | Two-sided difference in event proportions, nominal alpha 0.05 |
| Statistical target | User-selectable desired conditional power, default 0.80 |
| Treatment effect | Relative risk `RR = p_treatment / p_control`, default 0.75; positive absolute risk reduction as alternate view |
| Planning sample size | Arcsine/Cohen's *h* normal approximation, integer search for minimal evaluable sample size |
| Monte Carlo test | Pooled two-proportion z test (two-sided) with separate favorable-direction indicator |
| Dropout | Independent, arm-specific retention; simplification disclosed |
| Multiplicity | Exactly one primary hypothesis; no multiple-comparison adjustment |
| Data | No individual patient data; generated outcomes are synthetic |
| Auth / database | Neither needed for the hackathon |

**Out of scope:** treatment efficacy prediction; selecting clinical endpoints for sponsors; survival/time-to-event outcomes; competing risks; repeated measures; clusters; Bayesian adaptive allocation; sequential stopping; unblinded interim analysis; protocol approval; financial ROI; clinical advice; regulatory-grade design certification.

## 4. Critical definitions (include verbatim in UI tooltips)

- **Baseline risk** `p_control`: the probability that a *protocol-eligible control-arm participant* experiences the specified binary endpoint over the defined follow-up period. It is **not disease prevalence in the general population**.
- **Treatment event risk** `p_treatment`: a *hypothetical* rate implied by the user's selected effect model; no evidence that a medication actually achieves it.
- **Conditional statistical power**: probability that the specified analysis rejects its null hypothesis **if** the selected true event probabilities, retention behavior, and analysis method hold.
- **Monte Carlo standard error (MCSE)**: numerical uncertainty in the *simulated estimate of power* due to a finite number of simulations. It is not a confidence interval for the biological effect.
- **Assumption Safety Envelope**: region of *explicitly specified, hypothetical* inputs where the estimated conditional power meets the target. Not a regulatory safe zone.
- **Enrollment**: number randomized/recruited before losses; **evaluable sample size**: participants assumed to contribute usable binary outcomes in the simplified model. These are not interchangeable.
- **Two-sided significance vs favorable significance**: a two-sided test rejects for extreme effects in either direction; a separately reported “favorable-direction significance” requires rejection *and* the estimated effect to favor treatment. Under a true null and a symmetric two-sided test, favorable-direction significance is approximately alpha/2, not alpha.
- **Assurance / averaged conditional power** (stretch): mean conditional power over a user-specified uncertainty distribution. Do **not** call it “the probability that the drug succeeds”; it depends on the assumed distribution of true effects and rates.

## 5. Mathematical specification and method consistency

### 5.1 Event probabilities

For a lower-is-better event:

\[
X_C \sim \mathrm{Binomial}(n_C,p_C), \qquad X_T \sim \mathrm{Binomial}(n_T,p_T).
\]

**Constant relative-risk shock:** `p_T = RR × p_C`, with `0 < RR < 1` for the lower-event-benefit MVP.

**Constant absolute-risk-reduction shock:** `p_T = p_C − ARR`, with `0 < ARR < p_C`. If the stress slider moves below `ARR`, mark that scenario **invalid**; never silently clip to zero.

### 5.2 Planning power and integer sample-size search

The *canonical MVP analytical method* is the Cohen's h/arcsine normal approximation used by `statsmodels.stats.power.NormalIndPower`:

\[
h = 2\arcsin(\sqrt{p_T}) - 2\arcsin(\sqrt{p_C}).
\]

For equal evaluable sample sizes of `n` participants/arm and a two-sided test:

\[
\text{Power}_{h}(n) \approx \Phi\big(\sqrt{n/2}|h| - z_{1-\alpha/2}\big)
+\Phi\big(-\sqrt{n/2}|h| - z_{1-\alpha/2}\big).
\]

Implement an **integer search** for the smallest `n` with `Power_h(n) >= target_power`. Use `statsmodels` as an independent numerical oracle; round **up** and re-check the chosen integer. With the canonical equal-arm arcsine method:

| Scenario | Control event risk | Treatment event risk | Evaluable per arm | Power at 903 evaluable/arm |
|---|---:|---:|---:|---:|
| Planned | 20% | 15% | **903** | ~80.0% |
| Baseline collapse; RR remains 0.75 | 10% | 7.5% | **~1,996 to target 80%** | **~47.0%** |

These figures were cross-checked using `statsmodels`' Cohen's-h/NormalIndPower route. **Important correction to the research report:** its **906 per arm** estimate uses a different conventional pooled/unpooled two-proportion approximation; it is *not* the exact integer result of the specified statsmodels arcsine method. Do not mix 903 and 906 within one chart without labeling the methods. Method discrepancies are expected and should be visible in developer documentation.

Enrollment inflation under independently missing outcomes is initially approximated as:

\[
N^{enroll}_a = \left\lceil \frac{n^{evaluable}_a}{1-d_a} \right\rceil, \quad a\in\{C,T\}.
\]

For example, 903 evaluable per arm at 10% assumed dropout produces `ceil(903 / 0.9) = 1,004` enrollees per arm. This is expectation-based inflation, not a promise of exactly 903 retained participants.

### 5.3 Simulated trial analysis

For each replication `r`, generate retained counts and events:

\[
R_{a,r} \sim \mathrm{Binomial}(N_a,1-d_a), \qquad X_{a,r} \sim \mathrm{Binomial}(R_{a,r},p_a).
\]

For the simulated hypothesis test, use a pooled two-sample z statistic:

\[
\hat p = \frac{X_C+X_T}{R_C+R_T},\quad
Z = \frac{X_T/R_T-X_C/R_C}{\sqrt{\hat p(1-\hat p)(1/R_C+1/R_T)}}.
\]

Compute `p_two_sided = 2 × norm.sf(abs(Z))`, mark `p_two_sided < alpha`, and separately record whether the observed effect is in the prespecified beneficial direction. Return **both** `significant_two_sided_rate` and `significant_favorable_rate`. No valid normal statistic exists for some degenerate/very small samples; return an **invalid-test frequency** and a method warning, rather than dividing by zero or hiding failures. Decide and document conservative handling for undefined tests before publishing results.

Because the analytical method uses an arcsine normal approximation and the simulation uses a pooled z test on discrete counts, **small numeric differences are expected**. Validate within a justified tolerance that accounts for both approximation differences and MCSE. Do not force both outputs to match exactly.

### 5.4 Robustness metrics

For a grid `p_C ∈ [0.05,0.30]`, `dropout ∈ [0,0.30]` at **fixed originally planned enrolled N**:

- `power[p_index][dropout_index]`: approximate conditional power at each point.
- `below_target`: Boolean mask of cells with power < target.
- `critical_baseline`: lowest modeled baseline attaining target, if applicable; state it depends on chosen effect parameterization and grid resolution.
- `frontier`: interpolated 80%-power contour; never extrapolate beyond the grid.
- `worst_case_power`: minimum over the displayed, user-defined domain **only**.
- `delta_from_nominal`: power at stress point minus power at planned scenario, in percentage points.
- `simulation_vs_analytic`: side-by-side at chosen stress point, including MCSE, invalid-test rate, and method name.

**Stretch only:** robust N search over a declared scenario domain, weighted percentiles, Beta-distributed control risk, uncertain RR, and Pareto frontier of enrollment vs worst-case power. If using a prior distribution, preserve its parameters and origin; show a range-based view as a non-probabilistic alternative.

### 5.5 Validation and edge constraints

- Reject control or treatment probabilities outside `(0,1)` for the MVP normal-power method; reject null effect for sample-size search (`p_C == p_T` implies no finite target-N solution when target power > alpha).
- Reject RR ≤ 0 and RR ≥ 1 in the lower-is-better MVP; reject ARR outside `(0,p_C)`.
- Reject `alpha` outside `(0,1)`, `target_power` outside `(0,1)`, negative dropout, dropout ≥ 1, nonpositive ratio or enrollment, excessive grid dimensions/replicates.
- Use an explicit upper bound for sample-size search; return a structured `UNBOUNDED_OR_INFEASIBLE` error if not reached.
- When simulation yields zero retained in either arm or a degenerate standard error, do not return NaN; include the count in `invalid_test_fraction`.
- Warn when expected cell event counts are small and pooled normal approximations become questionable; Fisher exact may be a separate validated analysis path later.
- Under the null, check the **two-sided** rejection rate is approximately alpha (within a sampling tolerance). If checking **favorable-direction** rejection under the null, expect approximately alpha/2 for a symmetric test.
- Validate reproducibility with the same seed and identical software configuration. Record method and version in every result.
- Dropout independent of latent outcomes is **an illustrative assumption**. Informative missingness, estimands, treatment discontinuation, and intercurrent events need specialized methods; do not claim handling them in MVP.

## 6. Detailed functional requirements

### P0 — required for a complete hackathon submission

| ID | Requirement | Definition of done |
|---|---|---|
| FR-01 | Design form | Validated control risk, RR/ARR, alpha, target power, dropout, seed, sample size |
| FR-02 | Analytical design calculation | Smallest feasible integer evaluable N; enrollment inflation; method documented |
| FR-03 | Freeze-design stress test | Design N stays fixed while shocked scenario values change |
| FR-04 | Monte Carlo | Seeded 10,000-run selected-scenario simulation; MCSE and counts returned |
| FR-05 | Power curve | Power vs baseline; original and shocked point visible; target line |
| FR-06 | Heatmap/safety envelope | Power vs baseline/dropout under fixed N and selected effect model |
| FR-07 | Three presets | Stable, baseline collapse, attrition shock; clearly labeled synthetic |
| FR-08 | Scientific disclosures | Source provenance, scope, invalid scenarios, analytic method, no-advice claim |
| FR-09 | Export | Download JSON with user inputs, results, seed, method/version, timestamp |
| FR-10 | Automated tests | Deterministic power, edge, API and Monte Carlo checks pass |

### P1 — high-value if the core demo is working

| ID | Feature | Limitation |
|---|---|---|
| FR-11 | NCT metadata import | Import title, eligibility text, arms, endpoints, posted data only; planning risk entered separately |
| FR-12 | Real curated case | Protocol/SAP values manually checked with source locations |
| FR-13 | Cached stress scenarios | Avoid redundant compute during slider movement |
| FR-14 | Side-by-side method comparison | Label Cohen's h vs empirical pooled-z methodology |
| FR-15 | Interactive explanation drawer | Show formulas and why RR vs ARR changes sensitivity |

### P2 — explicit stretch

Beta prior/assurance, robust N selection, risk uncertainty ribbon, separate Fisher exact, arm-asymmetric loss, sample-size budget constraints. **Do not start P2 before all P0 test and deployment gates pass.**

## 7. Interface specification

Desktop-first single-screen workspace:

```text
┌───────────────────────────────────────────────────────────────────────────┐
│ BASELINE BREAKER       [Synthetic case v1 ▼] [Import NCT] [Export JSON] │
├───────────────────────┬───────────────────────────────────────────────────┤
│ PLANNED DESIGN        │ POWER VS BASELINE                                │
│ control risk 20%      │ 80% threshold ─────────────────                 │
│ relative risk .75     │ planned ●       stressed ▲                       │
│ power target 80%      │                                                  │
│ dropout 10%           ├───────────────────────────────────────────────────┤
│ eval N 903/arm        │ BASELINE × DROPOUT POWER HEATMAP                 │
│ enroll 1004/arm       │ overlaid 80% robustness boundary                 │
├───────────────────────┼───────────────────────────────────────────────────┤
│ STRESS SCENARIO       │ ANALYTIC vs SIMULATED                            │
│ baseline [---●---]    │ chosen scenario, 10k replicates, seed, MCSE      │
│ dropout [--●----]     │ warning states + method transparency             │
│ hold RR / ARR (o)     │                                                  │
└───────────────────────┴───────────────────────────────────────────────────┘
```

Interaction rules:

- **Never** mutate “planned design” N merely because the stress controls move; provide a separate **Recalculate design** action.
- Debounce interactive updates, cancel stale requests, display current calculation status and a stale-data indicator.
- Always show whether a value is user input, curated, API-derived, or simulated.
- A confidence bar must not look like a “probability drug succeeds” badge.
- Show robust vs fragile regions without blanket “good/bad trial” judgment.
- Provide a numerical accessible view of charts (table/CSV export) and basic keyboard control.

## 8. Data contract & provenance

Types and API paths are specified in the infrastructure document. At the product level every scenario must carry:

```json
{
  "scenario_id": "baseline-collapse-v1",
  "scenario_kind": "synthetic",
  "label": "Baseline Collapse",
  "source": {"type": "synthetic", "citation_url": null},
  "planned_control_risk": 0.2,
  "stress_control_risk": 0.1,
  "effect_type": "relative_risk",
  "effect_value": 0.75,
  "endpoint_type": "binary_undesirable_event",
  "follow_up_label": "12 months (illustrative)",
  "method": "cohen_h_normal_v1"
}
```

Never infer `planned_control_risk` from observed aggregate event results. If a clinical-trial record lacks a sourced original planning rate, UI must explicitly say **“Planning baseline unavailable — manual entry required.”**

## 9. Nonfunctional requirements

| Area | Target / constraint |
|---|---|
| Speed | Analytic point update target < 500 ms; initial heatmap target < 3 s on demo machine; measure, don't promise |
| Simulations | 10k selected-scenario replicates normally < 3 s on demo hardware; benchmark and adapt |
| Reproducibility | Same input, seed, Python/NumPy/scipy versions ⇒ same result under one environment |
| Robustness | No unhandled NaNs, invalid JSON, undefined divisions, blank charts, or API stack traces in UI |
| Data privacy | No patient identifiers, uploads of patient records, or PHI in MVP |
| Availability | Working **offline demo** with preset responses independent of ClinicalTrials.gov availability |
| Documentation | Publicly readable explanation of tested design, formula, model version, limitations |
| Auditability | Every chart can be traced to a named method and input configuration |

## 10. Explicit nonclaims

- No algorithm predicts drug efficacy, FDA approval, commercial success, or trial recruitment success.
- No generalized treatment-effect model fits all diseases or trial endpoints.
- No automatic regulatory-grade power calculation or sponsor-recommended protocol.
- No use of general-population disease prevalence to infer protocol-eligible endpoint risk.
- No claim that post-hoc “observed power” proves anything about a completed trial.
- No interpretation of missingness as innocuous without assumptions.

## 11. Risk register and reviewer checklist

| Priority | Risk | Why it matters | Control |
|---|---|---|---|
| Critical | Confusing prevalence with endpoint risk | Invalid sample-size inputs | Baseline definition in UI/schema; never auto-fill from CDC PLACES |
| Critical | Changing planned N during shock | Destroys demonstration's counterfactual | Separate immutable planned design and mutable stress scenario |
| High | RR/ARR switch hidden | Can reverse trend of required N | Prominent model toggle and formula explanation |
| High | Mixing analytic methods | Misleading discrepancies | Canonical Cohen's-h method; label pooled-z MC separately |
| High | Invalid/degenerate Z test | Undefined numerics or wrong results | Detect zero-retained/zero-SE and disclose invalid fraction |
| High | Endpoint/estimand mismatch | Clinical interpretation wrong | Explicit binary undesirable event and follow-up; independent-loss caveat |
| High | NCT assumptions fabricated | Misleading medical provenance | Separate metadata vs manually sourced protocol assumptions |
| High | API or deployment outage | Broken judge demo | Deterministic local presets and captured backup |
| Medium | Monte Carlo jitter | Judge distrust | Fixed seed, MCSE, controlled recomputation |
| Medium | Scope creep | Incomplete product | P0 gate, P1/P2 backlog, freeze date |
| Medium | Method unreliable for rare events | Unsupported z approximation | Expected-count warnings, out-of-scope label |

### Validation questions for Regeneron/clinical scientist

1. Is a **control-arm endpoint event rate for an eligible population/time horizon** the right baseline for the selected trial class?
2. Is the constant-RR stress model reasonable for the demo indication, or would a constant absolute treatment difference be more defensible?
3. Which dropout/intercurrent-event mechanism is most appropriate to flag as a limitation?
4. Is an uncertainty envelope around planned power more useful than a single nominal power output?
5. Which design dimensions would the expert insist on adding before use beyond a hackathon prototype?

## 12. Reference links

- [FDA / ICH E9(R1), estimands and sensitivity analysis](https://www.fda.gov/regulatory-information/search-fda-guidance-documents/e9r1-statistical-principles-clinical-trials-addendum-estimands-and-sensitivity-analysis-clinical)
- [ClinicalTrials.gov API v2](https://clinicaltrials.gov/data-api/about-api) and [NLM API upgrade notes](https://www.nlm.nih.gov/pubs/techbull/ma24/ma24_clinicaltrials_api.html)
- [statsmodels NormalIndPower.solve_power](https://www.statsmodels.org/stable/generated/statsmodels.stats.power.NormalIndPower.solve_power.html)
- [statsmodels proportion_effectsize](https://www.statsmodels.org/stable/generated/statsmodels.stats.proportion.proportion_effectsize.html)
- [statsmodels proportions_ztest](https://www.statsmodels.org/stable/generated/statsmodels.stats.proportion.proportions_ztest.html)
- [SciPy fisher_exact](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.fisher_exact.html)
- [CDC PLACES: definitions/limitations (context only)](https://www.cdc.gov/places/about/index.html)

---

**Product gate:** If an evaluator cannot explain the different meaning of *planning baseline*, *stress baseline*, *clinical prevalence*, *conditional power*, and *trial success probability* after using the UI, the interface is not yet ready for judging.
