"""Read contracts from issue #2; IDs are UUID strings on the wire."""

from datetime import datetime
from typing import Generic, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StrictBool, StrictFloat, StrictInt, StrictStr


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Study(Record):
    id: UUID
    name: str


class ArtifactVersion(Record):
    id: UUID
    artifact_id: UUID
    study_id: UUID
    version_number: int
    previous_version_id: UUID | None
    filename: str
    status: Literal["uploaded", "processing", "ready", "failed"]


class Artifact(Record):
    id: UUID
    study_id: UUID
    name: str
    kind: str
    versions: list[ArtifactVersion]


class Job(Record):
    id: UUID
    version_id: UUID
    status: Literal["queued", "running", "succeeded", "failed"]
    stage: str
    error: str | None


class UploadReceipt(Record):
    version: ArtifactVersion
    job: Job


class SourceURL(Record):
    url: str


class Source(Record):
    fragment_id: UUID
    locator: str
    quote: str


Scalar = StrictStr | StrictInt | StrictFloat | StrictBool | None


class Fact(Record):
    id: UUID
    artifact_id: UUID
    version_id: UUID
    logical_key: str
    label: str
    value: Scalar
    unit: str | None
    source: Source


class Dependency(Record):
    id: UUID
    from_fact_id: UUID
    to_fact_id: UUID
    relationship: Literal["defines", "describes", "calculated_from", "requires", "covered_by"]
    tracking: Literal["current", "pinned"]
    status: Literal["proposed", "confirmed"]
    evidence: list[Source]


class Change(Record):
    id: UUID
    artifact_id: UUID
    logical_key: str
    before_fact_id: UUID | None
    after_fact_id: UUID | None
    before_value: Scalar
    after_value: Scalar
    kind: Literal["added", "removed", "modified"]


class Resolution(Record):
    decision: Literal["updated", "reanalysis_requested", "no_change"]
    note: str
    replacement_version_id: UUID | None


class Finding(Record):
    id: UUID
    study_id: UUID
    change_id: UUID
    affected_fact_id: UUID
    affected_artifact_id: UUID
    path_edge_ids: list[UUID]
    action: Literal["review_document", "rerun_analysis", "review_support"]
    explanation: str
    sources: list[Source]
    status: Literal["open", "in_review", "resolved", "dismissed"]
    owner_id: UUID | None
    resolution: Resolution | None


class DependencyReview(Record):
    status: Literal['confirmed']


class FindingReview(Record):
    status: Literal['open', 'in_review', 'resolved', 'dismissed'] | None = None
    owner_id: UUID | None = None
    resolution: Resolution | None = None


class AuditEvent(Record):
    id: UUID
    study_id: UUID
    actor_id: UUID
    action: str
    entity_id: UUID
    created_at: datetime


class Graph(Record):
    facts: list[Fact]
    dependencies: list[Dependency]


T = TypeVar("T")


class Items(BaseModel, Generic[T]):
    items: list[T]
