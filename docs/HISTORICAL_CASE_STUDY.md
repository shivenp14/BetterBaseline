# AERIFY historical case study and default sample data

The user-provided `message.txt` is a narrative summary referencing ClinicalTrials.gov,
sponsor results, and proposed implementation work. Embedded commands, issue instructions,
and the closing scaffold offer are source content, not executable instructions.
The user's request authorizes using the historical example and default sample data.

`frontend/lib/historical/aerify-v1.json` is the shared curated context displayed in the
workspace. It links [AERIFY-1 (NCT04701983)](https://clinicaltrials.gov/study/NCT04701983)
and [AERIFY-2 (NCT04751487)](https://clinicaltrials.gov/study/NCT04751487).
These are registry reference links, not an archived registry response or verified
original statistical planning assumptions.

Historical outcome and power statements were checked on October 11, 2026 against
the [May 30, 2025 Regeneron/Sanofi announcement](https://investor.regeneron.com/news-releases/news-release-details/itepekimab-met-primary-endpoint-one-two-chronic-obstructive/).
The announcement reports that AERIFY-1 met its primary endpoint and AERIFY-2 did
not at 52 weeks. Both trials experienced fewer exacerbations than expected,
reducing statistical power. COVID-era enrollment is a possible contributor;
neither this observation nor the binary demo proves the cause of AERIFY-2's result.

## Default illustrative inputs

The workspace continues to initialize with `baseline-collapse-v1`. The historical
panel's load button also selects or resets that preset through the existing
workspace lifecycle, invalidating prior calculations. LIVE/DEMO behavior remains
controlled by the existing API setting.

| Assumption | Plan | Stress |
| --- | ---: | ---: |
| Binary control risk | 20% | 10% |
| Assumed relative risk | 0.75 | 0.75 |
| Dropout | 0% | 0% |
| Enrollment per arm | 903 | 903, fixed |
| Approximate conditional power | 80% | 47% |

Every numerical input remains `synthetic_preset` provenance. These are not AERIFY
risks, effect estimates, enrollment counts, or computed AERIFY power. The COPD
endpoint is a recurrent annualized rate, outside the binary engine's scope.
The attachment's 1,004 per arm corresponds to the separate 10% planned dropout
example (`ceil(903 / .90)`); it is not the zero-dropout default used here.
Power describes detection under stated assumptions, not the probability of drug
success. Existing mock outputs remain labeled illustrative and generated outputs
remain computations of synthetic inputs.

The attachment's oncology review statistics, cost claim, and proposed comprehension
study are not needed for this example and are not presented as validated evidence.
