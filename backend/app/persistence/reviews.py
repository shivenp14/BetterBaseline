"""PostgreSQL review mixin; each mutation, projection and audit commits together."""

from contextlib import contextmanager
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.api.models import ArtifactVersion, Dependency, Finding
from app.api.review_policy import InvalidReview, ReviewConflict, validate_confirmation
from app.persistence.repository import RecordNotFound, RepositoryUnavailable, StoredDependency


class PostgresReviews:
    @contextmanager
    def _review_transaction(self, study_id, actor):
        try:
            with psycopg.connect(self._database_url, row_factory=dict_row,
                                 connect_timeout=5, prepare_threshold=None) as connection:
                member = connection.execute('SELECT user_id FROM public.memberships WHERE study_id=%s AND user_id=%s FOR SHARE',
                                            (study_id, actor)).fetchone()
                if member is None:
                    raise InvalidReview('Acting reviewer must be a study member')
                # Lock order matches worker persistence: artifacts, then dependencies/findings.
                rows = connection.execute('SELECT id, approved_version_id FROM public.artifacts WHERE study_id=%s ORDER BY id FOR UPDATE',
                                          (study_id,)).fetchall()
                yield connection, {r['id']: r['approved_version_id'] for r in rows}
        except psycopg.Error:
            raise RepositoryUnavailable from None

    def get_dependency(self, dependency_id):
        with self._read() as connection:
            row = connection.execute('SELECT * FROM public.dependencies WHERE id=%s', (dependency_id,)).fetchone()
            if row is None:
                raise RecordNotFound
            study_id = row.pop('study_id')
            return StoredDependency(Dependency.model_validate(row), study_id)

    def get_finding(self, finding_id):
        with self._read() as connection:
            row = connection.execute('SELECT * FROM public.findings WHERE id=%s', (finding_id,)).fetchone()
            if row is None:
                raise RecordNotFound
            return Finding.model_validate(row)

    def _audit_review(self, connection, study_id, actor, action, entity_id):
        connection.execute('INSERT INTO public.audit_events(id,study_id,actor_id,action,entity_id) VALUES (%s,%s,%s,%s,%s)',
                           (uuid4(), study_id, actor, action, entity_id))

    def confirm_dependency(self, dependency_id, actor):
        stored = self.get_dependency(dependency_id)
        with self._review_transaction(stored.study_id, actor) as (connection, approved):
            row = connection.execute('SELECT * FROM public.dependencies WHERE id=%s FOR UPDATE', (dependency_id,)).fetchone()
            study_id = row.pop('study_id')
            edge = Dependency.model_validate(row)
            validate_confirmation(edge, self._graph(connection, study_id), approved)
            if edge.status == 'confirmed':
                return edge
            edge.status = 'confirmed'
            connection.execute("UPDATE public.dependencies SET status='confirmed' WHERE id=%s", (dependency_id,))
            self._audit_review(connection, study_id, actor, 'dependency.confirmed', dependency_id)
            return edge

    def _approve_review_version(self, connection, version_id, study_id, actor, approved, policy):
        row = connection.execute('''SELECT id, artifact_id, study_id, version_number, previous_version_id,
            filename, status FROM public.artifact_versions WHERE id=%s''', (version_id,)).fetchone()
        if row is None:
            raise InvalidReview('Replacement version does not exist')
        version = ArtifactVersion.model_validate(row)
        if version.study_id != study_id or version.status != 'ready':
            raise InvalidReview('Replacement must be a ready version in this study')
        job = connection.execute('SELECT status FROM public.jobs WHERE version_id=%s', (version_id,)).fetchone()
        if job is not None and job['status'] != 'succeeded':
            raise InvalidReview('Replacement processing must have succeeded')
        if approved.get(version.artifact_id) == version.id:
            return version
        current = approved.get(version.artifact_id)
        if current:
            number = connection.execute('SELECT version_number FROM public.artifact_versions WHERE id=%s', (current,)).fetchone()
            if version.version_number <= number['version_number']:
                raise ReviewConflict('Approval cannot roll back an artifact to an older snapshot')
        graph = self._graph(connection, study_id)
        projections = policy.projection(graph, approved, version)
        for edge in projections:
            if edge.status != 'confirmed' or edge.tracking != 'current':
                raise InvalidReview('Projection must retain confirmed current links')
            connection.execute('''INSERT INTO public.dependencies
                (id,study_id,from_fact_id,to_fact_id,relationship,tracking,status,evidence)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)''',
                (edge.id, study_id, edge.from_fact_id, edge.to_fact_id, edge.relationship, edge.tracking,
                 edge.status, Jsonb([source.model_dump(mode='json') for source in edge.evidence])))
        connection.execute('UPDATE public.artifacts SET approved_version_id=%s WHERE id=%s', (version_id, version.artifact_id))
        approved[version.artifact_id] = version_id
        self._audit_review(connection, study_id, actor, 'version.approved', version_id)
        return version

    def approve_version(self, version_id, actor, policy):
        stored = self.get_version(version_id)
        with self._review_transaction(stored.version.study_id, actor) as (connection, approved):
            return self._approve_review_version(connection, version_id, stored.version.study_id, actor, approved, policy)

    def update_finding(self, finding_id, patch, actor, policy):
        stored = self.get_finding(finding_id)
        with self._review_transaction(stored.study_id, actor) as (connection, approved):
            row = connection.execute('SELECT * FROM public.findings WHERE id=%s FOR UPDATE', (finding_id,)).fetchone()
            current = Finding.model_validate(row)
            updated = policy.finding(current, patch)
            if updated.owner_id is not None:
                member = connection.execute('SELECT user_id FROM public.memberships WHERE study_id=%s AND user_id=%s FOR SHARE',
                                            (current.study_id, updated.owner_id)).fetchone()
                if member is None:
                    raise InvalidReview('Finding owner must be a study member')
            if updated == current:
                return updated
            resolution = updated.resolution
            if resolution is not None and resolution.decision == 'updated':
                try:
                    replacement = self.get_version(resolution.replacement_version_id).version
                except RecordNotFound:
                    raise InvalidReview('Replacement version does not exist') from None
                affected = connection.execute('''SELECT v.version_number FROM public.facts f
                    JOIN public.artifact_versions v ON v.id=f.version_id WHERE f.id=%s''', (current.affected_fact_id,)).fetchone()
                if replacement.artifact_id != current.affected_artifact_id or replacement.version_number <= affected['version_number']:
                    raise InvalidReview('Replacement must be a newer version of the affected artifact')
                self._approve_review_version(connection, replacement.id, current.study_id, actor, approved, policy)
            connection.execute('UPDATE public.findings SET status=%s,owner_id=%s,resolution=%s WHERE id=%s',
                (updated.status, updated.owner_id, Jsonb(resolution.model_dump(mode='json')) if resolution else None, finding_id))
            self._audit_review(connection, current.study_id, actor, 'finding.updated', finding_id)
            return updated
