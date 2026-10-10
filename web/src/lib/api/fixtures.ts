import type { Artifact, Change, Dependency, Fact, Finding, Graph, Study } from "./types";
export const studyId = "00000000-0000-4000-8000-000000000001";
const id = (n: number) =>
  `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`;
export const studies: Study[] = [
  {
    id: studyId,
    name: "MERIDIAN · Synthetic study",
    description:
      "A synthetic trial workspace tracing an endpoint timing change from week 24 to week 36.",
  },
];
export const artifacts: Artifact[] = [
  { id: id(10), name: "Study protocol", kind: "Protocol", versions: [1, 2] },
  {
    id: id(11),
    name: "Statistical analysis plan",
    kind: "Analysis plan",
    versions: [1],
  },
  {
    id: id(12),
    name: "Schedule of assessments",
    kind: "Visit schedule",
    versions: [1],
  },
  {
    id: id(13),
    name: "Historical study report",
    kind: "Historical report",
    versions: [1],
  },
].map((artifact, index) => ({
  ...artifact,
  study_id: studyId,
  versions: artifact.versions.map((number) => ({
    id: id(100 + index * 10 + number),
    artifact_id: artifact.id,
    study_id: studyId,
    version_number: number,
    previous_version_id:
      number === 1 ? null : id(100 + index * 10 + number - 1),
    filename: `${artifact.kind.toLowerCase().replaceAll(" ", "-")}-v${number}.pdf`,
    status: "ready" as const,
  })),
}));
const source = (fragment: number, locator: string, quote: string) => ({
  fragment_id: id(fragment),
  locator,
  quote,
});
export const facts: Fact[] = [
  {
    id: id(201), artifact_id: id(10), version_id: id(102),
    logical_key: "primary_endpoint_timing", label: "Primary endpoint",
    value: 36, unit: "weeks", source: source(601, "Protocol v2 · §4.1", "The primary endpoint will be assessed at week 36."),
  },
  {
    id: id(202), artifact_id: id(11), version_id: id(111),
    logical_key: "primary_endpoint_timing", label: "Primary endpoint analysis",
    value: 24, unit: "weeks", source: source(602, "Analysis plan v1 · §5.2", "Analyze the primary endpoint at week 24."),
  },
  {
    id: id(203), artifact_id: id(12), version_id: id(121),
    logical_key: "primary_endpoint_timing", label: "Primary endpoint visit",
    value: 24, unit: "weeks", source: source(603, "Visit schedule v1 · Table 2", "Primary endpoint assessment: week 24."),
  },
  {
    id: id(204), artifact_id: id(13), version_id: id(131),
    logical_key: "primary_endpoint_timing", label: "Endpoint in historical report",
    value: 24, unit: "weeks", source: source(604, "Historical report v1 · §2.1", "The primary endpoint was assessed at week 24."),
  },
  {
    id: id(205), artifact_id: id(10), version_id: id(101),
    logical_key: "primary_endpoint_timing", label: "Primary endpoint · prior version",
    value: 24, unit: "weeks", source: source(605, "Protocol v1 · §4.1", "The primary endpoint will be assessed at week 24."),
  },
];
export const dependencies: Dependency[] = [
  { id: id(301), from_fact_id: id(201), to_fact_id: id(202), relationship: "requires", tracking: "current", status: "confirmed", evidence: [source(610, "Dependency evidence", "The analysis plan follows the protocol endpoint.")] },
  { id: id(302), from_fact_id: id(201), to_fact_id: id(203), relationship: "requires", tracking: "current", status: "proposed", evidence: [source(611, "Dependency evidence", "The visit schedule follows the protocol endpoint.")] },
  { id: id(303), from_fact_id: id(205), to_fact_id: id(204), relationship: "describes", tracking: "pinned", status: "confirmed", evidence: [source(612, "Historical linkage", "This report preserves the original week 24 context.")] },
];
export const graph: Graph = { facts, dependencies };
export const changes: Change[] = [
  {
    id: id(500), artifact_id: id(10), logical_key: "primary_endpoint_timing",
    before_fact_id: id(205), after_fact_id: id(201), before_value: 24,
    after_value: 36, kind: "modified",
  },
];
export const findings: Finding[] = [
  {
    artifact: 11,
    fact: 202,
    edge: 301,
    explanation:
      "The analysis plan still specifies week 24. Review it against the protocol’s week 36 endpoint.",
  },
  {
    artifact: 12,
    fact: 203,
    edge: 302,
    explanation:
      "The assessment schedule still lists the endpoint at week 24. Review the visit timing for week 36.",
  },
].map((item, index) => ({
  id: id(400 + index),
  study_id: studyId,
  change_id: id(500),
  affected_fact_id: id(item.fact),
  affected_artifact_id: id(item.artifact),
  path_edge_ids: [id(item.edge)],
  action: "review_document",
  explanation: item.explanation,
  sources: [
    {
      fragment_id: id(600),
      locator: "Protocol v2, section 4.1",
      quote: "The primary endpoint will be assessed at week 36.",
    },
  ],
  status: "open",
  owner_id: null,
  resolution: null,
}));
