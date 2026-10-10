// Shared field names and enums follow issue #1. IDs are UUID strings.
export type JsonScalar = string | number | boolean | null;
export interface Source {
  fragment_id: string;
  locator: string;
  quote: string;
}
export interface ArtifactVersion {
  id: string;
  artifact_id: string;
  study_id: string;
  version_number: number;
  previous_version_id: string | null;
  filename: string;
  status: "uploaded" | "processing" | "ready" | "failed";
}
// Study and Artifact summary fields are provisional: #1 does not define them.
export interface Study {
  id: string;
  name: string;
  description?: string;
}
export interface Artifact {
  id: string;
  study_id: string;
  name: string;
  kind: string;
  versions: ArtifactVersion[];
}
export interface Fact {
  id: string;
  artifact_id: string;
  version_id: string;
  logical_key: string;
  label: string;
  value: JsonScalar;
  unit: string | null;
  source: Source;
}
export interface Dependency {
  id: string;
  from_fact_id: string;
  to_fact_id: string;
  relationship:
    "defines" | "describes" | "calculated_from" | "requires" | "covered_by";
  tracking: "current" | "pinned";
  status: "proposed" | "confirmed";
  evidence: Source[];
}
export interface Change {
  id: string;
  artifact_id: string;
  logical_key: string;
  before_fact_id: string | null;
  after_fact_id: string | null;
  before_value: JsonScalar;
  after_value: JsonScalar;
  kind: "added" | "removed" | "modified";
}
export interface Finding {
  id: string;
  study_id: string;
  change_id: string;
  affected_fact_id: string;
  affected_artifact_id: string;
  path_edge_ids: string[];
  action: "review_document" | "rerun_analysis" | "review_support";
  explanation: string;
  sources: Source[];
  status: "open" | "in_review" | "resolved" | "dismissed";
  owner_id: string | null;
  resolution: {
    decision: "updated" | "reanalysis_requested" | "no_change";
    note: string;
    replacement_version_id: string | null;
  } | null;
}
export interface Job {
  id: string;
  version_id: string;
  status: "queued" | "running" | "succeeded" | "failed";
  stage: string;
  error: string | null;
}
export interface Graph {
  facts: Fact[];
  dependencies: Dependency[];
}
export interface ListResponse<T> {
  items: T[];
}
export interface StudyApi {
  listStudies(): Promise<ListResponse<Study>>;
  listArtifacts(studyId: string): Promise<ListResponse<Artifact>>;
  listFindings(studyId: string): Promise<ListResponse<Finding>>;
}
