"""Durable leased queue and fenced, atomic candidate-result writes."""

from contextlib import contextmanager
from dataclasses import dataclass
from uuid import UUID, uuid4

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.api.models import Change, Dependency, Fact, Finding, Graph
from app.persistence.postgres import PostgresRepository
from app.persistence.repository import RepositoryUnavailable, StoredVersion


class LeaseLost(Exception):
    pass


@dataclass(frozen=True)
class Claim:
    job_id: UUID
    version_id: UUID
    study_id: UUID
    token: str
    attempt: int


@dataclass
class Context:
    version: StoredVersion
    previous_facts: list[Fact]
    graph: Graph
    artifact_kinds: dict[UUID, str]
    approved_versions: dict[UUID, UUID | None]


@dataclass
class Results:
    facts: list[Fact]
    changes: list[Change]
    findings: list[Finding]


class PostgresWorkerStore:
    def __init__(self, database_url: str, lease_seconds: int = 120, max_attempts: int = 3,
                 retry_seconds: int = 5):
        if lease_seconds < 1 or max_attempts < 1 or retry_seconds < 0:
            raise ValueError("Invalid worker lease/retry configuration")
        self.database_url = database_url
        self.lease_seconds = lease_seconds
        self.max_attempts = max_attempts
        self.retry_seconds = retry_seconds
        self.reads = PostgresRepository(database_url)

    @contextmanager
    def _transaction(self):
        try:
            with psycopg.connect(self.database_url, row_factory=dict_row,
                                 connect_timeout=5, prepare_threshold=None) as connection:
                yield connection
        except psycopg.Error:
            raise RepositoryUnavailable from None

    def claim(self) -> Claim | None:
        token = str(uuid4())
        with self._transaction() as connection:
            # A crashed final attempt is terminal; recovery itself never adds results.
            expired = connection.execute("""UPDATE public.jobs SET status='failed', stage='failed',
                error='lease_expired: retry budget exhausted', lease_expires_at=NULL, claimed_by=NULL,
                next_retry_at=NULL, updated_at=clock_timestamp()
                WHERE status='running' AND lease_expires_at <= clock_timestamp() AND attempts >= %s
                RETURNING version_id""", (self.max_attempts,)).fetchall()
            for row in expired:
                connection.execute("UPDATE public.artifact_versions SET status='failed' WHERE id=%s", (row['version_id'],))
            row = connection.execute("""WITH candidate AS (
                SELECT id FROM public.jobs WHERE attempts < %s AND
                  ((status='queued' AND (next_retry_at IS NULL OR next_retry_at <= clock_timestamp())) OR
                   (status='running' AND lease_expires_at <= clock_timestamp()))
                ORDER BY created_at, id FOR UPDATE SKIP LOCKED LIMIT 1
            ) UPDATE public.jobs j SET status='running', stage='loading', error=NULL,
                attempts=j.attempts+1, claimed_by=%s,
                lease_expires_at=clock_timestamp() + %s * interval '1 second',
                next_retry_at=NULL, updated_at=clock_timestamp()
            FROM candidate WHERE j.id=candidate.id RETURNING j.id,j.version_id,j.study_id,j.attempts""",
                (self.max_attempts, token, self.lease_seconds)).fetchone()
            if row is None:
                return None
            connection.execute("UPDATE public.artifact_versions SET status='processing' WHERE id=%s", (row['version_id'],))
            return Claim(row['id'], row['version_id'], row['study_id'], token, row['attempts'])

    def _owned(self, connection, claim):
        row = connection.execute("""SELECT id FROM public.jobs WHERE id=%s AND status='running'
            AND claimed_by=%s AND attempts=%s AND lease_expires_at > clock_timestamp() FOR UPDATE""",
            (claim.job_id, claim.token, claim.attempt)).fetchone()
        if row is None:
            raise LeaseLost

    def heartbeat(self, claim: Claim, stage: str):
        with self._transaction() as connection:
            self._owned(connection, claim)
            connection.execute("""UPDATE public.jobs SET stage=%s,
                lease_expires_at=clock_timestamp() + %s * interval '1 second', updated_at=clock_timestamp()
                WHERE id=%s""", (stage, self.lease_seconds, claim.job_id))

    def context(self, claim: Claim) -> Context:
        version = self.reads.get_version(claim.version_id)
        if version.version.study_id != claim.study_id:
            raise ValueError("Job study mismatch")
        with self.reads._read(claim.study_id) as connection:
            # Only approved snapshots drive impact. Historical 'current' edges are excluded.
            rows = connection.execute("SELECT id, kind, approved_version_id FROM public.artifacts WHERE study_id=%s",
                                      (claim.study_id,)).fetchall()
            approved = {r['approved_version_id'] for r in rows if r['approved_version_id']}
            graph = self.reads._graph(connection, claim.study_id)
            facts = [fact for fact in graph.facts if fact.version_id in approved]
            ids = {fact.id for fact in facts}
            graph = Graph(facts=facts, dependencies=[edge for edge in graph.dependencies
                if edge.from_fact_id in ids and edge.to_fact_id in ids])
            previous = [fact for fact in facts if fact.artifact_id == version.version.artifact_id]
            return Context(version, previous, graph, {r['id']: r['kind'] for r in rows},
                           {r['id']: r['approved_version_id'] for r in rows})

    def complete(self, claim: Claim, context: Context, results: Results):
        validate_results(claim, context, results)
        with self._transaction() as connection:
            self._owned(connection, claim)
            rows = connection.execute("SELECT id, approved_version_id FROM public.artifacts WHERE study_id=%s ORDER BY id FOR SHARE",
                                      (claim.study_id,)).fetchall()
            if {r['id']: r['approved_version_id'] for r in rows} != context.approved_versions:
                raise ValueError('Approved snapshots changed during processing; retry')
            rows = connection.execute("""SELECT id, from_fact_id, to_fact_id, relationship,
                tracking, status, evidence FROM public.dependencies WHERE study_id=%s ORDER BY id FOR SHARE""",
                (claim.study_id,)).fetchall()
            active_ids = {fact.id for fact in context.graph.facts}
            active_edges = {r['id']: Dependency.model_validate(r) for r in rows
                            if r['from_fact_id'] in active_ids and r['to_fact_id'] in active_ids}
            if active_edges != {edge.id: edge for edge in context.graph.dependencies}:
                raise ValueError('Approved graph changed during processing; retry')
            def insert(table, record):
                query = sql.SQL("INSERT INTO public.{} ({}) VALUES ({})").format(sql.Identifier(table),
                    sql.SQL(',').join(map(sql.Identifier, record)),
                    sql.SQL(',').join(sql.Placeholder() for _ in record))
                connection.execute(query, list(record.values()))
            fragments = {}
            for fact in results.facts:
                fragments[fact.source.fragment_id] = fact.source
            for source in fragments.values():
                insert('source_fragments', dict(id=source.fragment_id, study_id=claim.study_id,
                    artifact_id=context.version.version.artifact_id, version_id=claim.version_id,
                    locator=source.locator, quote=source.quote))
            for fact in results.facts:
                record = fact.model_dump(exclude={'source'})
                record.update(study_id=claim.study_id, fragment_id=fact.source.fragment_id, value=Jsonb(fact.value))
                insert('facts', record)
            for change in results.changes:
                record = change.model_dump()
                record.update(study_id=claim.study_id, candidate_version_id=claim.version_id,
                              before_value=Jsonb(change.before_value), after_value=Jsonb(change.after_value))
                insert('changes', record)
            for finding in results.findings:
                record = finding.model_dump()
                record['sources'] = Jsonb([s.model_dump(mode='json') for s in finding.sources])
                record['resolution'] = None
                insert('findings', record)
            # Check time again after writes: expired attempts roll back the entire result set.
            self._owned(connection, claim)
            connection.execute("UPDATE public.artifact_versions SET status='ready' WHERE id=%s", (claim.version_id,))
            connection.execute("""UPDATE public.jobs SET status='succeeded', stage='complete', error=NULL,
                claimed_by=NULL, lease_expires_at=NULL, next_retry_at=NULL, updated_at=clock_timestamp()
                WHERE id=%s""", (claim.job_id,))

    def fail(self, claim: Claim, error: str):
        with self._transaction() as connection:
            self._owned(connection, claim)
            retry = claim.attempt < self.max_attempts
            connection.execute("""UPDATE public.jobs SET status=%s, stage=%s, error=%s,
                claimed_by=NULL, lease_expires_at=NULL,
                next_retry_at=CASE WHEN %s THEN clock_timestamp() + %s * interval '1 second' ELSE NULL END,
                updated_at=clock_timestamp() WHERE id=%s""",
                ('queued' if retry else 'failed', 'retry_wait' if retry else 'failed', error,
                 retry, self.retry_seconds * claim.attempt, claim.job_id))
            connection.execute("UPDATE public.artifact_versions SET status=%s WHERE id=%s",
                               ('uploaded' if retry else 'failed', claim.version_id))


def validate_results(claim: Claim, context: Context, results: Results):
    version = context.version.version
    new = {fact.id: fact for fact in results.facts}
    old = {fact.id: fact for fact in context.previous_facts}
    targets = {fact.id: fact for fact in context.graph.facts} | new
    changes = {change.id: change for change in results.changes}
    edges = {edge.id: edge for edge in context.graph.dependencies
             if edge.status == 'confirmed' and edge.tracking == 'current'}
    if len(new) != len(results.facts) or len(changes) != len(results.changes):
        raise ValueError('Duplicate result IDs')
    if len({f.logical_key for f in new.values()}) != len(new):
        raise ValueError('Duplicate logical keys')
    fragments = {}
    for fact in new.values():
        if fact.version_id != claim.version_id or fact.artifact_id != version.artifact_id:
            raise ValueError('Candidate fact scope mismatch')
        previous = fragments.setdefault(fact.source.fragment_id, fact.source)
        if previous != fact.source:
            raise ValueError('Conflicting source fragment')
    for change in changes.values():
        if change.artifact_id != version.artifact_id:
            raise ValueError('Change artifact mismatch')
        before = old.get(change.before_fact_id)
        after = new.get(change.after_fact_id)
        valid = {'added': before is None and change.before_fact_id is None and after is not None,
                 'removed': before is not None and after is None and change.after_fact_id is None,
                 'modified': before is not None and after is not None}[change.kind]
        if not valid or any(f.logical_key != change.logical_key for f in (before, after) if f):
            raise ValueError('Change snapshot mismatch')
        if change.before_value != (before.value if before else None) or change.after_value != (after.value if after else None):
            raise ValueError('Change value mismatch')
    seen = set()
    for finding in results.findings:
        target = targets.get(finding.affected_fact_id)
        change = changes.get(finding.change_id)
        if (finding.study_id != claim.study_id or target is None or change is None or
            target.artifact_id != finding.affected_artifact_id or finding.status != 'open' or
            finding.owner_id is not None or finding.resolution is not None):
            raise ValueError('Finding scope/review mismatch')
        pair = (finding.change_id, finding.affected_fact_id)
        if pair in seen:
            raise ValueError('Duplicate finding')
        seen.add(pair)
        cursor = change.before_fact_id if change.kind != 'added' else change.after_fact_id
        for edge_id in finding.path_edge_ids:
            edge = edges.get(edge_id)
            if edge is None or edge.from_fact_id != cursor:
                raise ValueError('Invalid impact path')
            cursor = edge.to_fact_id
        if cursor != target.id:
            raise ValueError('Invalid impact target')
