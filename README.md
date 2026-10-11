# Better Baseline

### Stress-test clinical trial assumptions *before* the trial begins.

A clinical trial can be designed for 80% statistical power **only under the assumptions used to calculate it**. What happens if the control group's event rate is lower than expected, the treatment effect is smaller, or more participants drop out?

**Better Baseline** makes those vulnerabilities visible. It is a reproducible, interactive planning tool for exploring how uncertain assumptions affect the statistical power and sample size of a proposed trial.

> **Project status:** HackRU implementation blueprint. This folder currently contains planning documents; the application and commands below describe the intended build, not a deployed or verified product.

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

## What makes it more than an AI wrapper?

The core product is **statistical computation**, not generated text:

- **Sample-size engine:** computes evaluable and planned enrollment requirements using a defined analytic method.
- **Stress-testing engine:** evaluates a fixed design over alternative baseline risks, effect assumptions, and dropout rates.
- **Monte Carlo engine:** simulates synthetic trial outcomes with a reproducible random seed and reports simulation error.
- **Assumption Safety Envelope:** visualizes combinations of assumptions that do or do not meet a specified power threshold.
- **Transparent methods:** exposes inputs, method versions, limitations, and provenance rather than inventing clinical parameters.

**MVP boundaries:** individually randomized, two-arm, 1:1 superiority trials; one binary primary endpoint; a two-sided test. Survival outcomes, adaptive designs, multiple endpoints, and real-world efficacy predictions are **not** part of the initial release.

## Planned technology

| Layer | Technology | Purpose |
| --- | --- | --- |
| Frontend | Next.js, React, TypeScript, Tailwind | Design controls, comparisons, charts |
| Visualization | Plotly or a compatible chart library | Power curves, heatmap, threshold boundary |
| API | Python, FastAPI, Pydantic | Validated scenario endpoints and contracts |
| Statistical core | NumPy, SciPy, statsmodels | Analytic power, sample sizing, Monte Carlo |
| Optional trial metadata | ClinicalTrials.gov API v2 | Source-linked study metadata; **not** assumed original design inputs |
| QA and delivery | pytest, GitHub Actions, Docker | Numerical regression tests and reproducible deployment |

No database, authentication, paid AI API, or individual patient records are required for the hackathon MVP.

### Intended data flow

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

## Getting started (after the code is implemented)

**Prerequisites:** Python 3.12, Node.js LTS, and npm. Install and pin compatible dependency versions when scaffolding.

Start the backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
uvicorn app.main:app --reload --port 8000
```

Start the frontend in another terminal:

```bash
cd backend
uv sync --locked --extra dev
uv run --locked python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a second terminal:

```bash
cd frontend
npm ci
cp .env.example .env.local
npm run dev
```

Open **http://localhost:3000**. The default frontend configuration sends fresh
calculate and evaluate requests to the local API. Set `NEXT_PUBLIC_API_MODE=demo`
in `frontend/.env.local` only when intentionally using labeled fixtures and local
analytic calculations. The backend grid endpoint is currently a #66 scaffold that
returns HTTP 501; the live frontend reports that limitation and does not substitute
client-side grid formulas.

Run backend tests and the frontend's real-service integration check:

```bash
cd backend
uv run --locked --extra dev pytest -q
cd ../frontend
npm run test:backend-integration
```

The integration command starts and cleans up its own temporary Uvicorn process. See
[`frontend/README.md`](frontend/README.md) for frontend lint, typecheck, build, and
workspace invariant commands.

## API overview

The planned v1 API has three essential endpoints:

| Endpoint | What it does |
| --- | --- |
| `POST /api/v1/design/calculate` | Plan sample size from stated assumptions |
| `POST /api/v1/scenarios/evaluate` | Evaluate a fixed design under a stress scenario; optionally run seeded simulation |
| `POST /api/v1/scenarios/grid` | Return the analytic power surface for charts |

Optional: `GET /api/v1/trials/{nct_id}` for public trial metadata. See the [infrastructure specification](02_INFRASTRUCTURE_ARCHITECTURE.md) for request/response examples and field definitions.

## Development priorities

**Ship first:** validated sample-size calculation → immutable planned design vs. stress scenario → live power comparison → sensitivity heatmap → seeded Monte Carlo → reproducible export.

**Only if time permits:** ClinicalTrials.gov metadata import and curated real-world context. An explicit demo mode remains available for synthetic fixture exploration.

## Documentation

| Read | Document | Contents |
| --- | --- | --- |
| **1** | [Product & Statistical Specification](01_BETTER_BASELINE_SPEC.md) | The problem, scope, mathematical definitions, UX requirements, scientific guardrails, and acceptance criteria |
| **2** | [Infrastructure & Architecture](02_INFRASTRUCTURE_ARCHITECTURE.md) | Repository layout, stack decisions, JSON contracts, API design, caching, deployment, and CI |
| **3** | [Implementation Playbook](03_IMPLEMENTATION_PLAYBOOK.md) | Module-by-module tasks, code examples, tests, four-person ownership, and the 24-hour build schedule |

**For contributors:** Start with the spec's MVP constraints and numerical test fixture. Freeze the API contract before splitting into parallel branches. Keep one reproducible synthetic demo working throughout development.

## Scientific scope and responsibility

- **Power is conditional:** it estimates the chance that a specified test rejects its null hypothesis *assuming* the modeled event rates, effect, and analysis method hold. It does **not** predict whether a drug works.
- **Baseline risk means endpoint risk in the trial's eligible control population**, not geographic disease prevalence.
- **Planning and stress assumptions stay separate:** a change to the stress scenario must not automatically resize the original trial.
- **Simulation is not clinical evidence:** Monte Carlo trials use synthetic outcomes and require method validation.
- **No patient-level data or PHI:** the MVP uses entered assumptions, synthetic examples, and optional public metadata.
- **Not a regulatory-grade design tool:** outputs require independent review by qualified clinical statisticians before any real-world study decisions.

---

*Built as a HackRU project concept. Current deliverables are the specification, architecture, and implementation plan—not a claim of a validated or production-ready clinical application.*
