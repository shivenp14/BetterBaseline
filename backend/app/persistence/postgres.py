"""Direct PostgreSQL read adapter; compatible with Supabase Postgres."""

from contextlib import contextmanager
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from app.api.models import Artifact, ArtifactVersion, AuditEvent, Dependency, Fact, Finding, Graph, Job, Study, UploadReceipt
from app.persistence.repository import RecordNotFound, RepositoryUnavailable, StoredJob, StoredVersion, StudyNotFound, UploadOutcomeUnknown


class PostgresRepository:
    def __init__(self, database_url: str):
        self._database_url = database_url

    @contextmanager
    def _read(self, study_id: UUID | None = None):
        try:
            with psycopg.connect(self._database_url, row_factory=dict_row,
                                 connect_timeout=5, prepare_threshold=None) as connection:
                connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                connection.execute("SET LOCAL TIME ZONE 'UTC'")
                if study_id is not None:
                    found = connection.execute("SELECT id FROM public.studies WHERE id = %s", (study_id,)).fetchone()
                    if found is None:
                        raise StudyNotFound
                yield connection
        except psycopg.Error:
            # SQL errors can contain connection details; keep them off the wire.
            raise RepositoryUnavailable from None

    def list_studies(self) -> list[Study]:
        with self._read() as connection:
            rows = connection.execute("SELECT id, name FROM public.studies ORDER BY id").fetchall()
            return [Study.model_validate(row) for row in rows]

    def list_artifacts(self, study_id: UUID) -> list[Artifact]:
        with self._read(study_id) as connection:
            artifacts = connection.execute(
                "SELECT id, study_id, name, kind FROM public.artifacts WHERE study_id = %s ORDER BY id",
                (study_id,),
            ).fetchall()
            versions = connection.execute(
                """SELECT id, artifact_id, study_id, version_number, previous_version_id, filename, status
                   FROM public.artifact_versions WHERE study_id = %s ORDER BY artifact_id, version_number""",
                (study_id,),
            ).fetchall()
            by_artifact = {row["id"]: [] for row in artifacts}
            for row in versions:
                by_artifact[row["artifact_id"]].append(ArtifactVersion.model_validate(row))
            return [Artifact.model_validate({**row, "versions": by_artifact[row["id"]]}) for row in artifacts]

    def get_graph(self, study_id: UUID) -> Graph:
        with self._read(study_id) as connection:
            return self._graph(connection, study_id)

    def _graph(self, connection, study_id):
        facts = connection.execute(
            """SELECT f.id, f.artifact_id, f.version_id, f.logical_key, f.label, f.value, f.unit,
                      jsonb_build_object('fragment_id', s.id, 'locator', s.locator, 'quote', s.quote) AS source
               FROM public.facts f JOIN public.source_fragments s ON s.id = f.fragment_id
               WHERE f.study_id = %s ORDER BY f.id""", (study_id,),
        ).fetchall()
        dependencies = connection.execute(
            """SELECT id, from_fact_id, to_fact_id, relationship, tracking, status, evidence
               FROM public.dependencies WHERE study_id = %s ORDER BY id""", (study_id,),
        ).fetchall()
        return Graph(facts=[Fact.model_validate(row) for row in facts],
                     dependencies=[Dependency.model_validate(row) for row in dependencies])

    def list_findings(self, study_id: UUID) -> list[Finding]:
        with self._read(study_id) as connection:
            rows = connection.execute(
                """SELECT id, study_id, change_id, affected_fact_id, affected_artifact_id, path_edge_ids,
                          action, explanation, sources, status, owner_id, resolution
                   FROM public.findings WHERE study_id = %s ORDER BY id""", (study_id,),
            ).fetchall()
            return [Finding.model_validate(row) for row in rows]

    def list_audit(self, study_id: UUID) -> list[AuditEvent]:
        with self._read(study_id) as connection:
            rows = connection.execute(
                """SELECT id, study_id, actor_id, action, entity_id, created_at
                   FROM public.audit_events WHERE study_id = %s ORDER BY created_at, id""", (study_id,),
            ).fetchall()
            return [AuditEvent.model_validate(row) for row in rows]

    def get_artifact(self, artifact_id: UUID) -> Artifact:
        with self._read() as connection:
            row = connection.execute("SELECT study_id FROM public.artifacts WHERE id = %s", (artifact_id,)).fetchone()
            if row is None:
                raise RecordNotFound
        return next(item for item in self.list_artifacts(row["study_id"]) if item.id == artifact_id)

    def get_job(self, job_id: UUID) -> StoredJob:
        with self._read() as connection:
            row = connection.execute("SELECT id, version_id, study_id, status, stage, error FROM public.jobs WHERE id = %s",
                                     (job_id,)).fetchone()
            if row is None:
                raise RecordNotFound
            study_id = row.pop("study_id")
            return StoredJob(Job.model_validate(row), study_id)

    def get_version(self, version_id: UUID) -> StoredVersion:
        with self._read() as connection:
            row = connection.execute("""SELECT id, artifact_id, study_id, version_number, previous_version_id,
                filename, status, storage_path, content_hash FROM public.artifact_versions WHERE id = %s""",
                (version_id,)).fetchone()
            if row is None:
                raise RecordNotFound
            path, digest = row.pop("storage_path"), row.pop("content_hash")
            return StoredVersion(ArtifactVersion.model_validate(row), path, digest)

    def create_version_job(self, artifact_id, version_id, job_id, filename, storage_path, content_hash):
        connection = None
        committing = False
        try:
            connection = psycopg.connect(self._database_url, row_factory=dict_row, connect_timeout=5, prepare_threshold=None)
            row = connection.execute("SELECT study_id FROM public.artifacts WHERE id = %s FOR UPDATE", (artifact_id,)).fetchone()
            if row is None:
                raise RecordNotFound
            previous = connection.execute("""SELECT id, version_number FROM public.artifact_versions
                WHERE artifact_id = %s ORDER BY version_number DESC LIMIT 1""", (artifact_id,)).fetchone()
            version = ArtifactVersion(id=version_id, artifact_id=artifact_id, study_id=row["study_id"],
                version_number=previous["version_number"] + 1 if previous else 1,
                previous_version_id=previous["id"] if previous else None, filename=filename, status="uploaded")
            job = Job(id=job_id, version_id=version_id, status="queued", stage="queued", error=None)
            connection.execute("""INSERT INTO public.artifact_versions
                (id, artifact_id, study_id, version_number, previous_version_id, filename, status, storage_path, content_hash)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (version.id, artifact_id, version.study_id, version.version_number, version.previous_version_id,
                 filename, version.status, storage_path, content_hash))
            connection.execute("""INSERT INTO public.jobs (id, study_id, version_id, status, stage)
                VALUES (%s, %s, %s, 'queued', 'queued')""", (job_id, version.study_id, version_id))
            committing = True
            connection.commit()
            return UploadReceipt(version=version, job=job)
        except psycopg.Error:
            if committing:
                raise UploadOutcomeUnknown from None
            raise RepositoryUnavailable from None
        finally:
            if connection is not None:
                connection.close()
