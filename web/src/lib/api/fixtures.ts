import type { Artifact, Finding, Study } from "./types";
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
export const findings: Finding[] = [
  {
    artifact: 11,
    fact: 201,
    edge: 301,
    explanation:
      "The analysis plan still specifies week 24. Review it against the protocol’s week 36 endpoint.",
  },
  {
    artifact: 12,
    fact: 202,
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
