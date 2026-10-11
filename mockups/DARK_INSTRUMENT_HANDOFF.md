# Better Baseline — Dark instrument mockups

Design document: `../untitled.pen`.
Functional source: the supplied `FRONTEND_MOCKUP_BRIEF.md` (issue #85).

## Scope

Sixteen coverage states of the Trial Planning Workspace at `/`, each with a desktop and approximately 375px narrow-screen counterpart. Expanded details are sections of the same workspace, not new routes. Earlier mockups and style explorations remain intact.

## Visual direction

Approved reference: **Style 04 · Dark instrument** (`AUQEY`).

- Slate canvas `#101A20`; secondary working surface `#17262E`.
- Mint action/selection `#A8E6C5`; pale primary text `#EAF2F2`.
- Muted labels `#A1B3BE`; thin rules `#34464F`.
- Explicit amber stale/warning and coral invalid/error labels.
- Inter for functional text; IBM Plex Mono for numerical readings and identifiers.
- Flat, continuous working surfaces with square controls. Avoid decorative card grids.

## Canvas organization

New mockups have a `Dark` or `Dark instrument` prefix. Four adjacent workstreams organize the canvas: planning/recovery, analytic stress testing, selected-scenario simulation, and provenance/implementation guidance. Desktop frames have aligned narrow-screen companions.

Read-first frames:
- `Nz398`: state coverage and implementation contract.
- `Q2U920`: 375px interaction contract.

| State | Coverage | Desktop frame | Narrow frame |
|---|---|---|---|
| 01 | Initial LIVE, calculation needed | TYjBn | DMrIl |
| 02 | Manual planning edit, alternate ARR | gJz7S | XMUbk |
| 03 | Invalid ARR and field feedback | qEyok | NEolC |
| 04 | Calculation in progress | MQifF | enTvt |
| 05 | Calculated design and enrollment lock | wNBZE | yHIz1 |
| 06 | Stress comparison, analytic curve and grid | K9I8t | H2mlS3 |
| 07 | Stress change, stale/loading dependencies | A91flR | RQgJy |
| 08 | Valid selection, simulation ready | oeJgm | jGm5t |
| 09 | Invalid/null scenario, actions blocked | hl3Iv | dzS22 |
| 10 | Simulation running and failure/retry | L8l2V | zptrl |
| 11 | Complete current simulation, export eligibility | bHVvJ | OcKZj |
| 12 | Stale simulation and export blocking | Mgm7y | wrlDq |
| 13 | Unavailable backend, preserved inputs | XVBZg | MpIls |
| 14 | DEMO, explicitly illustrative output | Ao3BR | RmGN2 |
| 15 | Detached JSON validation, valid/invalid feedback | H0txg | EeSpk |
| 16 | Mixed field provenance, methods and disclosures | q4mxCU | VrT7S |

## Numerical honesty

`‹Service-returned bindings›` are layout specifications, not computed measurements. Hand-authored fixtures and schematic chart marks must retain their illustrative labels. No live Monte Carlo outcomes are fabricated by these mockups. A LIVE execution-mode label alone does not make a fixture a current live result.

## Implementation invariants

1. Planning risk, dropout, alpha and power use percentages; ARR uses percentage points; RR is a ratio. Stress numeric inputs use explicitly labeled fractions.
2. A successful design calculation establishes the enrollment lock. Editing planning inputs makes existing results stale; stress changes never resize enrollment.
3. Enrollment before losses, required evaluable counts, floored expected retention and sampled actual retention are distinct outputs.
4. Curve values use the selected dropout exactly. The original-plan point must not be mislabeled when the selected dropout differs from planned dropout.
5. Grid rows are dropout; columns are baseline risk. Null is never zero. Invalid cells are not selectable; boundaries and curve traces do not bridge invalid regions.
6. Simulation applies to one selected valid scenario. Separate two-sided and favorable-direction significance fractions, with separate MCSE values in percentage points.
7. Complete scenario JSON requires current matching design, curve/grid, simulation, assumptions, seed and replicates. Grid CSV is independent.
8. JSON reopening validates a detached artifact. It does not restore inputs or replay calculations.
9. DEMO cannot run live Monte Carlo or produce a complete current scenario export. The execution mode has no user-facing toggle.
10. Accessible implementations need labeled controls, keyboard selection, numerical chart alternatives, visible focus, adequate targets, first-invalid-field focus and explicit text/status announcements.

The mockups specify presentation and interactions. They are not a runtime acceptance test, a statistical validation, or a clinical/regulatory certification.
