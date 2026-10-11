# BetterBaseline — Devpost replacement copy

Prepared from the team's supplied Devpost story. Paste the sections below into
Devpost; this file does not update the published submission.

**Suggested tagline:** Make fragile trial assumptions visible before enrollment begins.

## Inspiration

A conversation with Henry Wei from Regeneron changed the question we were trying
to answer. We had started with TrialSync, a tool for tracking dependencies in
clinical trials. His feedback drew our attention to an earlier risk: the
assumptions used to design the trial itself.

One example made that risk concrete. Regeneron and Sanofi's AERIFY program studied
itepekimab for COPD. AERIFY-1 met its primary endpoint; AERIFY-2 did not at 52 weeks.
The sponsors reported fewer exacerbations than anticipated, reducing statistical
power in both trials. ([Sponsor announcement](https://investor.regeneron.com/news-releases/news-release-details/itepekimab-met-primary-endpoint-one-two-chronic-obstructive/))

That led us to ask: **if fewer events occur than a trial expects, how much ability
to detect an assumed treatment benefit does it lose?** We built BetterBaseline to
make that sensitivity visible while the design can still change.

## What it does

BetterBaseline is an interactive planning prototype for two-arm trials with a
binary outcome. Researchers enter a control event risk, assumed treatment effect,
target power, and dropout. They calculate a sample size, freeze enrollment, and
stress-test what happens when those assumptions change.

Power curves and an assumption-sensitivity heatmap show where the fixed design
falls below its target. Seeded Monte Carlo simulations provide a reproducible
simulation check, with simulation error reported separately from uncertainty in
the assumptions. Exports preserve inputs, methods, and provenance for review.

Our default **synthetic** example starts with 20% control risk, an assumed relative
risk of 0.75, and 903 participants per arm with no dropout. Lowering control risk
to 10%, while keeping enrollment and relative risk fixed, lowers approximate
conditional power from 80% to 47%.

**How could this help with an AERIFY-like problem?** The workflow could expose
sensitivity to fewer events during planning, prompting a team to examine more
conservative assumptions or enrollment margins with a statistician. Our current
binary model does not analyze AERIFY's recurrent COPD exacerbations. The demo is
not a reconstruction of its power, and it cannot establish that another design
would have changed AERIFY-2's result.

Power is the probability of detecting the assumed difference under the specified
model and test. It is not the probability that a drug works.

## How we built it

We used Next.js, React, TypeScript, and CSS modules for the frontend, with Python,
FastAPI, NumPy, SciPy, and statsmodels powering the statistical backend. Typed API
contracts connect the workspace to analytic calculations and seeded simulations.
The interface labels demo fixtures separately from live backend calculations and
keeps planned assumptions separate from stress scenarios.

## Challenges we ran into

We pivoted from TrialSync midway through the hackathon after industry feedback.
That left us learning clinical trial statistics while building the product.

The hardest challenge was showing a meaningful result without overstating it.
Enrollment must stay fixed during a stress test. Simulation precision must not be
confused with certainty about clinical assumptions. And a real-world example with
a recurrent-event endpoint cannot simply be entered into a binary-outcome model.

## Accomplishments that we're proud of

We turned an unfamiliar statistical problem into a functional planning workspace
with reproducible simulations and visual explanations. The default example lets
someone see how a seemingly adequate design becomes fragile when its assumptions
shift, while preserving the distinction between historical context and synthetic
calculations.

## What we learned

Choosing the right problem matters as much as building the solution. Feedback
from someone working in the field helped us move from tracking a trial's workflow
to examining its design assumptions.

We also learned that an 80% power calculation is conditional on a model and its
inputs. Exploring plausible alternatives makes that dependence easier to
understand and discuss.

## What's next for BetterBaseline

Our next steps are independent statistical validation, usability testing with
research teams, and models for recurrent events and survival outcomes. To analyze
historical trials, we would need curated protocols and verified original planning
assumptions alongside ClinicalTrials.gov metadata. We also want to support shared
scenario review and comparison across a research team.

## Built With

FastAPI, Next.js, NumPy, Python, React, SciPy, statsmodels, TypeScript, CSS modules.

## Try it out

[BetterBaseline demo](https://better-baseline.vercel.app/) ·
[Source code](https://github.com/shivenp14/BetterBaseline)

The demo URL is supplied by the team; its deployment contents are not established
by this narrative update.
