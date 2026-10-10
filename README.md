# Clinical Trial Dependency Manager

A proposed platform for tracing dependencies across clinical-trial data, documents, and decisions, identifying the consequences of changes, and coordinating their resolution.

**Project status:** concept and interactive explainers. The application, ingestion pipeline, and dependency engine described below are planned functionality.

## The problem

Clinical trials depend on information distributed across protocols, datasets, statistical analysis plans, laboratory records, participant materials, registries, and operational systems. These sources are maintained by different people and updated at different times.

A change in one source can affect many other artifacts. A corrected dataset may require an analysis to be rerun. An amended endpoint may affect the statistical plan and assessment schedule. A revised visit schedule may require participant materials and support arrangements to be reviewed.

Teams need to understand where information came from, what relies on it, which version applies, and who is responsible for acting when it changes. Finding those relationships manually adds coordination work and creates opportunities for inconsistencies and missed updates.

## Our idea

Represent the clinical trial as a **versioned dependency graph** connecting source information, derived artifacts, document claims, decisions, and responsible owners.

When a source changes, the system follows relevant relationships to identify affected artifacts. It explains why each artifact needs recalculation, revision, or review, then creates actionable tasks that owners can resolve with supporting evidence.

The central workflow is:

1. Import and version trial information.
2. Extract and confirm dependencies.
3. Detect a meaningful change between versions.
4. Identify and explain its downstream consequences.
5. Assign review and resolution tasks.
6. Record approved updates and preserve the history.

The intended result is less manual dependency hunting, clearer ownership, and a traceable process for resolving changes.

## Who it helps

- **Clinical study teams:** understand the consequences of amendments and operational changes.
- **Data managers and statisticians:** trace analyses and reported numbers back to the dataset versions and transformations that produced them.
- **Medical writers and document owners:** find claims that need revision and inspect the evidence behind proposed updates.
- **Research coordinators:** track operational consequences and outstanding actions.
- **Reviewers:** see what changed, why an update was proposed, and how the issue was resolved.

## What makes a dependency useful

A graph connection must describe the relationship between two specific pieces of information. Similar wording alone is a candidate connection that needs confirmation.

Examples of relationship types include:

- **Calculated from:** a result depends on particular input values and a transformation.
- **Describes:** a document passage describes a study requirement or result.
- **Assumes:** a decision depends on a stated assumption remaining applicable.
- **Must reflect the current version of:** an active artifact must remain consistent with its approved source.
- **Requires:** a procedure depends on a resource, prerequisite, or operational capability.
- **Covered by:** a participant need or study activity depends on a support commitment.

Each dependency should retain:

- The source and destination identifiers and versions.
- The exact field, row, calculation, or document passage involved.
- The relationship type and its source evidence.
- The transformation or reasoning connecting the records.
- The applicable population and time period.
- Confidence and human confirmation status.
- The responsible owner and review status.

**Version context matters.** A historical report can correctly describe an earlier dataset. A live dashboard may need the latest approved dataset. Those relationships produce different consequences when a new version arrives. A source change creates an impact finding; the finding's rules and context determine what action is appropriate.

## How the system would work

### 1. Ingest and version information

Import a focused set of documents and structured data. Preserve each source snapshot with an identifier, version, owner, timestamp, and approval status. Proposed amendments remain distinguishable from approved requirements.

### 2. Build and confirm the graph

AI proposes structured facts and dependencies from source passages, fields, and metadata. Structured bindings and recorded analysis inputs provide explicit connections where available. Reviewers inspect uncertain matches and confirm important relationships.

### 3. Detect changes

Compare versions to identify changed values, added or removed records, altered requirements, or changed support commitments. Semantic comparison helps distinguish a wording edit from a substantive change, while preserving the original passages for review.

### 4. Evaluate downstream impact

Traverse potentially affected relationships and apply rules appropriate to each relationship type. Determine whether an artifact needs recalculation, a claim needs checking, a document needs revision, or a required resource needs confirmation.

Findings include the triggering change, the dependency path, the evidence, the action required, and the responsible owner. Missing information remains visible as an unresolved question.

### 5. Coordinate resolution

Create review tasks and, where supported, draft revisions or request recalculation. Owners inspect proposed changes, record decisions, and link the resulting artifact or confirmation. Close findings when their required resolution evidence has been reviewed.

### 6. Preserve the history

Retain source versions, graph changes, findings, reviewer decisions, and resulting artifacts. Users should be able to reconstruct which information supported a decision at a particular point in the trial.

## Example: a corrected dataset

A laboratory export is corrected after an analysis and report section have been produced.

The graph connects the corrected records to the analysis inputs, the derived results, and the report claims supported by those results. The system flags the analysis for recalculation and the dependent claims for review. It also shows the data manager, statistician, and document owner their respective tasks.

Once the analysis is rerun, the reviewer can determine whether the report needs revision or whether the correction leaves its claims unchanged. The original dataset, analysis, and report remain linked to their historical versions.

## Example: a protocol amendment

A proposed amendment changes an endpoint's assessment time from week 24 to week 36.

Confirmed relationships may connect that requirement to the statistical analysis plan, assessment schedule, data-collection specifications, registry fields, and participant materials. The system identifies which specific sections depend on the timepoint and routes them to their owners.

The output is an impact review with evidence and accountable actions. Updated artifacts become linked to the new approved version as their reviews are completed.

## Why this fits the Regeneron challenge

The project addresses coordination and consistency bottlenecks in clinical development. It would help real users manage trial amendments, data corrections, analyses, and reporting with clearer evidence and less manual work.

Regeneron's materials on data fragmentation, reusable content, and digital data flow inform the concept. Our emphasis is on tracing typed dependencies across data, documents, and decisions and carrying each identified consequence through review and resolution.

## Our main Social Good argument

Clinical trials are part of the process of developing medicines that can benefit society. Avoidable administrative delays and inconsistencies consume time and resources that research teams could use to advance that work.

By reducing dependency-management effort and helping teams catch consequential inconsistencies, this project aims to help important trials progress more efficiently. Over time, that efficiency could support greater research capacity and more frequent trials.

For a prototype, the directly demonstrable outcomes are time saved in identifying affected artifacts, relevant dependencies found, inconsistencies caught, and tasks resolved. Increased trial throughput and earlier access to beneficial medicines are longer-term goals that would require evidence from real use.

## Extension: participant impact and equitable access

The same graph can extend to participant needs and community support commitments. This adds a concrete way to examine whether trial changes introduce unequal participation burdens.

For example, an added visit may require an extra transport voucher, additional childcare, or accessible transport on a new weekday. The trial documents may be updated while the original support agreements still cover only the previous schedule.

This extension connects:

- Study requirements, including visit duration, location, and attendance needs.
- Voluntarily declared participant needs.
- Support commitments, including covered trips, limits, availability, capacity, and expiration dates.
- Related participant materials and responsible coordinators.

Explicit rules can identify a coverage gap or an availability question and assign it for resolution. A provider confirmation or reviewed funding commitment supplies evidence that the issue has been addressed.

The community benefits are fairer access, less unexpected burden, and accountability for promised support. This is an additional capability extending the dependency-management core. Broader demographic coverage also depends on recruitment, eligibility, and other factors.

## AI and human responsibilities

AI would assist with extracting information, proposing relationships, comparing document meaning, explaining dependency paths, and drafting updates.

Explicit rules and recorded transformations would perform calculations and constraint checks. Authorized people would confirm dependencies, assess scientific or operational implications, approve changes, and verify support commitments. Findings must distinguish confirmed evidence from inferred relationships.

## Initial prototype scope

Start with one synthetic trial and a small collection of linked artifacts:

- A protocol and one amendment.
- A statistical analysis plan and participant-information document.
- A structured dataset and a corrected version.
- A derived analysis summary containing traceable claims.
- A small set of fictional participant profiles and support agreements for the access extension.

Demonstrate both a dataset correction and a protocol amendment. For each change, show the affected records, the reasons they are affected, assigned review tasks, and the recorded resolution.

A minimal implementation can store nodes, edges, versions, and findings in ordinary database tables. The planned components are source ingestion, fact extraction, a dependency store, change comparison, impact rules, a review workflow, and an interface for exploring evidence paths. Technology choices remain open.

## Existing explainers

These standalone HTML files illustrate the concept and can be opened in a browser:

- [Clinical dependency explorer](docs/clinical-dependencies.html): examples of dependency types and the consequences of source changes.
- [Project and Social Good walkthrough](docs/trial-dependencies-social-good.html): the interactive amendment example, implementation explanation, and participant-access extension.
- [Trial change example](docs/trial-change-example.html): a focused amendment dependency illustration.
- [Participant access impact](docs/participant-access-impact.html): illustrative differences in burden across fictional profiles.

The examples use invented changes, profiles, costs, and policies. They illustrate the proposed behavior; the full application is still to be implemented.

## Project materials

- `docs/`: interactive concept explainers.
- `regeneron-info/`: supplied Regeneron challenge materials, starter sheets, and background reading.
- `README.md`: the defined project concept, intended behavior, and initial scope.

## Project pitch

> We help clinical-trial teams trace dependencies across fragmented data, documents, and decisions, identify the consequences of changes, and coordinate their resolution. By reducing avoidable delays and inconsistencies, we help important research progress more efficiently. An additional participant-impact layer helps teams preserve access as trials evolve.
