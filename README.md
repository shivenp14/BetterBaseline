# Better Baseline

### Stress-test clinical trial assumptions *before* the trial begins.

A clinical trial can be designed for 80% statistical power **only under the assumptions used to calculate it**. What happens if the control group's event rate is lower than expected, the treatment effect is smaller, or more participants drop out?

**Better Baseline** makes those vulnerabilities visible. It is a reproducible, interactive planning tool for exploring how uncertain assumptions affect the statistical power and sample size of a proposed trial.

> **Project status:** Implemented local planning workspace with real FastAPI calculations, charts, seeded simulation, and validated JSON export. See the [judge runbook](docs/DEMO_SCRIPT.md) for measured rehearsals and remaining acceptance gates. This is a synthetic planning demonstration, not clinical validation.

## The real-world question behind Better Baseline

**What if fewer patients experience the event than your trial was designed to expect?**

In May 2025, Regeneron and Sanofi reported that AERIFY-1 met its primary endpoint
and AERIFY-2 missed it at 52 weeks. The sponsors also reported fewer COPD
exacerbations than anticipated and reduced statistical power in both trials.
See their [results announcement](https://investor.regeneron.com/news-releases/news-release-details/itepekimab-met-primary-endpoint-one-two-chronic-obstructive/)
and the registry records for [AERIFY-1](https://clinicaltrials.gov/study/NCT04701983)
and [AERIFY-2](https://clinicaltrials.gov/study/NCT04751487).

This motivates our planning question: **how sensitive is a trial's ability to
detect an assumed benefit to the event rate used to size it?** Better Baseline
lets a team freeze enrollment, lower the assumed control risk, and see where
conditional power falls below its target. That can prompt a discussion about
more conservative assumptions, enrollment margins, or whether the proposed
design is feasible before recruitment begins.

**How could this have helped with an AERIFY-like planning problem?** It could have
made sensitivity to fewer events easier to inspect and communicate during design
review. An AERIFY-specific analysis would need its original planning assumptions
and a validated recurrent-event model: its endpoint was an annualized exacerbation
rate, while our MVP supports binary risks. The example below illustrates the
mechanism, not a reconstruction of AERIFY-2 or proof that its outcome was preventable.

For the full evidence boundary, read the [historical case study](docs/HISTORICAL_CASE_STUDY.md).
For public-facing copy, see the [Devpost story](docs/DEVPOST_STORY.md) and
[presentation guide](docs/PRESENTATION_GUIDE.md).

## The idea in 30 seconds

1. **Plan:** Enter a baseline event rate, hypothetical treatment effect, desired power, and dropout assumptions.
2. **Freeze:** Calculate the required sample size, then hold that enrollment fixed.
3. **Stress-test:** Change the assumed *true* event rate or retention and see how conditional power changes.
4. **Explore:** Inspect power curves, an assumption-sensitivity heatmap, and the 80%-power boundary.
5. **Verify:** Run seeded Monte Carlo simulations and export a reproducible scenario.

### Example: a baseline that collapses

For a hypothetical two-arm trial with a binary adverse endpoint:

| Parameter | Original plan | Stress scenario |
| --- | ---: | ---: |
| Control event rate | 20% | 10% |
| Hypothetical relative risk | 0.75 | 0.75 |
| Treatment event rate | 15% | 7.5% |
| Evaluable participants per arm | **903** | **903 (fixed)** |
| Approximate conditional power | **80%** | **47%** |

*Illustrative values using the specified Cohen's-h/normal-approximation method, two-sided α = 0.05, equal allocation, and no dropout. Results depend on the method and assumptions; they are not actual trial outcomes.*

The insight: a design that looks adequately powered under a single forecast may be sensitive to plausible changes in the baseline rate.

## How the tool makes design risk visible

The core product is **statistical computation**, not generated text:

- **Sample-size engine:** computes evaluable and planned enrollment requirements using a defined analytic method.
- **Stress-testing engine:** evaluates a fixed design over alternative baseline risks, effect assumptions, and dropout rates.
- **Monte Carlo engine:** simulates synthetic trial outcomes with a reproducible random seed and reports simulation error.
- **Assumption Safety Envelope:** visualizes combinations of assumptions that do or do not meet a specified power threshold.
- **Transparent methods:** exposes inputs, method versions, limitations, and provenance rather than inventing clinical parameters.

**MVP boundaries:** individually randomized, two-arm, 1:1 superiority trials; one binary primary endpoint; a two-sided test. Survival outcomes, adaptive designs, multiple endpoints, and real-world efficacy predictions are **not** part of the initial release.

## Technology

| Layer | Technology | Purpose |
| --- | --- | --- |
| Frontend | Next.js, React, TypeScript, CSS modules | Design controls, comparisons, charts |
| Visualization | SVG charts and accessible tables | Power curves, heatmap, threshold boundary |
| API | Python, FastAPI, Pydantic | Validated scenario endpoints and contracts |
| Statistical core | NumPy, SciPy, statsmodels | Analytic power, sample sizing, Monte Carlo |
| Optional trial metadata | ClinicalTrials.gov API v2 | Optional source-linked study metadata; **not** original design inputs |
| QA and delivery | pytest, GitHub Actions, Docker | Numerical regression tests and reproducible deployment |

No database, authentication, paid AI API, or individual patient records are required for the hackathon MVP.

### Data flow

```text
User inputs + synthetic presets
             │
             ▼
    Next.js trial dashboard
             │ typed JSON API
             ▼
      FastAPI + Pydantic
             │
     ┌───────┼─────────┐
     ▼       ▼         ▼
 Sample size  Stress grid   Monte Carlo
     │       │         │
     └───────┼─────────┘
             ▼
    Results + assumptions
             │
             ▼
 Charts · comparisons · export
```

## Getting started

Use Python **3.12.x** (`>=3.12,<3.13`), **Node 24.15.0** (the CI version), npm, and **uv 0.9.26**. Install these tools and dependencies while online; a clean machine cannot install packages without a network or preloaded caches/images. Run from the repository root:

```bash
cd backend
uv sync --locked --python 3.12 --extra dev
uv run --locked python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a second terminal:

```bash
cd frontend
npm ci
cp .env.example .env.local
npm run dev
```

Open **http://localhost:3000**. The default configuration selects LIVE mode and the local API. Bundled presets need no NCT lookup. Calculate & Lock Design, evaluate stress, load the grid, run the selected simulation, and download/reopen JSON using the [105-second walkthrough](docs/DEMO_SCRIPT.md).

Set `NEXT_PUBLIC_API_MODE=demo`
in `frontend/.env.local` only when intentionally using labeled fixtures and local
analytic calculations. In live mode, the backend calculates the fixed-enrollment
power surface and target-power boundary; demo mode is explicitly labeled. The
default `baseline-collapse-v1` preset contains synthetic assumptions, even when
the backend calculates its results.

For production startup and prebuilt offline containers, follow [Deployment](docs/DEPLOYMENT.md). API addresses are embedded at frontend build time; rebuild when changing them.

Run checks from the repository root:

```bash
cd backend
uv run --locked pytest -q tests ../tests/fixtures
cd ../frontend
npm run lint
npm run typecheck
npm run build
npm run test:backend-integration
```

The integration command starts its own temporary backend. The [judge runbook](docs/DEMO_SCRIPT.md) also gives the isolated #118 E2E commands and the timed rehearsal runner. Fixture-only DEMO mode remains available when the backend is unavailable; it does not provide fresh backend Monte Carlo or a complete current export. Restore LIVE mode to complete acceptance.

## API overview

The v1 API has three core calculation endpoints:

| Endpoint | What it does |
| --- | --- |
| `POST /api/v1/design/calculate` | Plan sample size from stated assumptions |
| `POST /api/v1/scenarios/evaluate` | Evaluate a fixed design under a stress scenario; optionally run seeded simulation |
| `POST /api/v1/scenarios/grid` | Return the analytic power surface for charts |

Optional: `GET /api/v1/trials/{nct_id}` looks up public trial metadata without filling planning assumptions. See the [infrastructure specification](docs/02_INFRASTRUCTURE_ARCHITECTURE.md) for request/response examples and field definitions.

## Next steps

Extend validation and usability testing, then add endpoint-specific models for
recurrent events and survival outcomes. Historical replay would also require
curated protocols and verified planning assumptions. Adaptive re-estimation is a
future research direction, not a feature of this MVP.

## Documentation

| Read | Document | Contents |
| --- | --- | --- |
| **1** | [Product & Statistical Specification](docs/01_BASELINE_BREAKER_SPEC.md) | The problem, scope, mathematical definitions, UX requirements, scientific guardrails, and acceptance criteria |
| **2** | [Infrastructure & Architecture](docs/02_INFRASTRUCTURE_ARCHITECTURE.md) | Repository layout, stack decisions, JSON contracts, API design, caching, deployment, and CI |
| **3** | [Implementation Playbook](docs/03_IMPLEMENTATION_PLAYBOOK.md) | Module-by-module tasks, code examples, tests, four-person ownership, and the 24-hour build schedule |

**Ownership tracks:** A covers the statistical core; B covers API/contracts/provenance; C covers frontend workspace/charts/export; D covers QA, deployment, fixtures, and documentation. These are product tracks, not permanent people assignments. Active issues own their named files; shared wiring transfers only after the predecessor merges and records its handoff. #83 owns this README, `docs/DEMO_SCRIPT.md`, and `scripts/demo/**`; #85 retains presentation ownership.

**For contributors:** Start with the spec's MVP constraints, the statistical methods, and the numerical fixtures. Preserve the frozen-enrollment invariant and keep historical context separate from numerical input provenance.

## Scientific scope and responsibility

- **Power is conditional:** it estimates the chance that a specified test rejects its null hypothesis *assuming* the modeled event rates, effect, and analysis method hold. It does **not** predict whether a drug works.
- **Baseline risk means endpoint risk in the trial's eligible control population**, not geographic disease prevalence.
- **Planning and stress assumptions stay separate:** a change to the stress scenario must not automatically resize the original trial.
- **Simulation is not clinical evidence:** Monte Carlo trials use synthetic outcomes and require method validation.
- **No patient-level data or PHI:** the MVP uses entered assumptions, synthetic examples, and optional public metadata.
- **Not a regulatory-grade design tool:** outputs require independent review by qualified clinical statisticians before any real-world study decisions.

---

*Built for HackRU. Measured local behavior, recovery prerequisites, and dependency gates are recorded in the judge runbook. No public hosted deployment or clinical suitability is claimed.*
