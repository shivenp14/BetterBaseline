# Presenting BetterBaseline through the AERIFY example

## The central message

**Make fragile trial assumptions visible before enrollment begins.**

Start with the team's conversation with Henry Wei from Regeneron and the pivot
from TrialSync. Then use AERIFY as the concrete motivation, the synthetic binary
example as the demonstration, and earlier design review as the practical value.
The [Devpost replacement story](DEVPOST_STORY.md) follows this sequence.

## A 90-second walkthrough

1. **0–20 seconds — motivate the question.** “AERIFY-2 missed its primary endpoint.
   The sponsors reported fewer exacerbations than expected and reduced power in
   both AERIFY trials. That made us ask: how sensitive is a trial to the event
   rate assumed when it was designed?” Open the historical panel and show its
   source links. Attribute the report to the sponsors.
2. **20–40 seconds — establish the example.** Load `baseline-collapse-v1`.
   Say “This is a synthetic binary-outcome example, not AERIFY data.” Set stressed
   control risk to 20% and dropout to 0%, then Calculate & Lock Design. Identify
   the enrollment counts as 903 per arm and the planned power as approximately 80%.
3. **40–60 seconds — reveal the sensitivity.** Lower stressed control risk to
   10%; keep dropout at 0% and enrollment fixed. Wait for the current evaluation.
   “The assumed relative risk is still 0.75, but fewer events make the absolute
   difference smaller. Approximate power falls to 47%.” Point to the unchanged
   enrollment and the power curve or heatmap, once current.
4. **60–80 seconds — connect it to a decision.** “Seeing this before recruitment
   gives a team a reason to examine lower event-risk assumptions and enrollment
   margins. It makes the tradeoff visible for discussion with a statistician.”
5. **80–90 seconds — state the boundary and next step.** “AERIFY needs a
   recurrent-event model and verified planning inputs. This prototype demonstrates
   the planning question; endpoint-specific models and independent validation are
   our next steps.”

Use LIVE mode with a working backend for fresh numerical results. In DEMO mode,
identify outputs as fixtures/client calculations. Run a seeded simulation only
when live execution is available; Monte Carlo error describes simulation
precision, not uncertainty about clinical assumptions. Do not describe stale
results as newly calculated. Changing enrollment is a separate new planning
exercise, not part of the frozen-design stress test.

## Consistent wording across surfaces

| Surface | Recommended message |
| --- | --- |
| Devpost tagline / opening slide | Make fragile trial assumptions visible before enrollment begins. |
| README / demo introduction | What if fewer patients experience the event than your trial was designed to expect? |
| Historical panel | AERIFY-2 missed its primary endpoint; sponsors reported fewer events and reduced power in both trials. |
| Chart / screenshot caption | Synthetic binary example: 20% → 10% control risk; RR 0.75; N=903/arm fixed; no dropout; approximate power 80% → 47%. |
| Closing slide | Earlier visibility into assumption sensitivity can inform design review. |

## Claims to keep precise

| Avoid | Use |
| --- | --- |
| “We could have saved the failed trial.” | “The workflow could make sensitivity to fewer events visible during planning.” |
| “COVID caused the failure.” | “Sponsors described pandemic-era enrollment as a possible contributor to lower event rates.” |
| “AERIFY's power fell from 80% to 47%.” | “Our synthetic binary example shows an approximate 80% → 47% drop.” |
| “The drug worked, but statistics hid it.” | “Our tool cannot establish treatment efficacy or why AERIFY-2 missed its endpoint.” |
| “We use real trial data to calculate the right sample size.” | “Registry metadata provides context; calculations use explicitly supplied assumptions.” |
| “More simulation runs remove trial uncertainty.” | “More runs reduce Monte Carlo sampling error.” |
| “We optimize adaptive designs.” | “Adaptive designs are outside the current MVP.” |

Call AERIFY-2 a trial that **missed its primary endpoint**. The practical value is
an inspectable design risk, not a demonstrated rescue, guaranteed success, or
quantified cost saving. See [the evidence note](HISTORICAL_CASE_STUDY.md).
