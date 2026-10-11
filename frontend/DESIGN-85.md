# Issue #85 design agreement

The user requested implementation from the supplied `mockups/` on 2026-10-11.
`mockups/DARK_INSTRUMENT_HANDOFF.md` and its desktop/mobile PNGs are the approved
presentation direction. This record precedes styling implementation.

- Dark instrument: slate canvas #101A20, working surface #17262E, mint action
  #A8E6C5, primary text #EAF2F2, muted text #A1B3BE and rules #34464F.
- Continuous flat surfaces, square controls, restrained rules; functional sans
  typography with monospace numerical readings and identifiers.
- Desktop: planning inputs and enrollment summary, stress controls and comparison,
  paired curve and sensitivity panels, selected-scenario simulation, export and
  provenance/disclosures. Around 375px, stack sections and contain wide tables
  within labeled scroll regions; no page-wide horizontal scrolling.
- Preserve LIVE/DEMO labeling and explicit loading, stale, invalid and failure
  text. Amber and coral supplement text; status never depends only on color.
- Preserve labels, semantic selectors, keyboard controls, visible focus and
  numerical chart alternatives. Scientific disclosures remain available.
- Mockup bindings and schematic marks are specifications, not runtime values.
  All displayed results continue to come from the existing functional workflow.

Functional inventory: preset selector; planning RR/ARR inputs and validation;
calculation/loading/error; design summary and frozen enrollment; stress risk and
dropout controls; analytic request status and comparison; power curve and table;
heatmap, invalid cells and CSV; selected-scenario Monte Carlo controls/results;
current/stale simulation; provenance-preserving scenario export; detached JSON
validation; field provenance; method disclosures and synthetic-data warnings.

Statistical formulas, request semantics, frozen enrollment, result matching,
simulation selection and exported data are outside the styling change.

Validation evidence and before/after screenshots will be recorded under
`frontend/verification/issue-85/` and summarized in the pull request.
