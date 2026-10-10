"""One-process synchronous worker. Demo adapters are explicit, never a live fallback."""

import argparse
from collections import deque
import hashlib
import importlib
import json
import logging
import os
import time
from typing import Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from app.api.models import Change, Fact, Finding, Source
from app.persistence.repository import RepositoryUnavailable
from app.persistence.seed import DEMO_STUDY_ID
from app.persistence.storage import PrivateStorage, configured_storage
from app.persistence.worker import Context, LeaseLost, PostgresWorkerStore, Results

logger = logging.getLogger(__name__)


class Pipeline(Protocol):
    def extract(self, content: bytes, context: Context) -> list[Fact]: ...
    def compare(self, facts: list[Fact], context: Context) -> list[Change]: ...
    def assess(self, changes: list[Change], facts: list[Fact], context: Context) -> list[Finding]: ...


class ProcessingError(Exception):
    """Only predefined codes, never adapter messages, are exposed by the worker."""


class Worker:
    def __init__(self, store: PostgresWorkerStore, storage: PrivateStorage, pipeline: Pipeline):
        self.store, self.storage, self.pipeline = store, storage, pipeline

    def run_once(self) -> bool:
        claim = self.store.claim()
        if claim is None:
            return False
        stage = 'loading'
        try:
            context = self.store.context(claim)
            if not context.version.storage_path or not context.version.content_hash:
                raise ProcessingError('missing_source')
            content = self.storage.read(context.version.storage_path)
            if hashlib.sha256(content).hexdigest() != context.version.content_hash:
                raise ProcessingError('source_hash_mismatch')
            stage = 'extracting'
            self.store.heartbeat(claim, stage)
            facts = [Fact.model_validate(f) for f in self.pipeline.extract(content, context)]
            stage = 'comparing'
            self.store.heartbeat(claim, stage)
            changes = [Change.model_validate(c) for c in self.pipeline.compare(facts, context)]
            stage = 'assessing'
            self.store.heartbeat(claim, stage)
            findings = [Finding.model_validate(f) for f in self.pipeline.assess(changes, facts, context)]
            stage = 'persisting'
            self.store.heartbeat(claim, stage)
            self.store.complete(claim, context, Results(facts, changes, findings))
            logger.info('Job %s succeeded on attempt %s', claim.job_id, claim.attempt)
        except LeaseLost:
            logger.warning('Job %s lost its lease; results discarded', claim.job_id)
        except Exception as exc:
            known_codes = {'missing_source', 'source_hash_mismatch', 'demo_study_only', 'invalid_demo_json'}
            code = str(exc) if isinstance(exc, ProcessingError) and str(exc) in known_codes else 'processing_error'
            # Do not print exception text: adapters may include source documents or credentials.
            logger.warning('Job %s failed at %s (%s)', claim.job_id, stage, code)
            try:
                self.store.fail(claim, f'{stage}: {code}')
            except LeaseLost:
                pass  # A newer attempt (or an uncertain successful commit) already owns the outcome.
        return True


def stable_id(version_id: UUID, kind: str, key: str) -> UUID:
    return uuid5(NAMESPACE_URL, f'trialsync/demo/{version_id}/{kind}/{key}')


class DemoPipeline:
    """Strict JSON fixture ingestion and deterministic comparison/traversal stubs."""

    def extract(self, content, context):
        version = context.version.version
        if version.study_id != DEMO_STUDY_ID:
            raise ProcessingError('demo_study_only')
        try:
            document = json.loads(content)
            if set(document) != {'facts'} or not isinstance(document['facts'], list):
                raise ValueError
            facts = []
            for item in document['facts']:
                if set(item) != {'logical_key', 'label', 'value', 'unit', 'locator', 'quote'}:
                    raise ValueError
                key = item['logical_key']
                if not isinstance(key, str) or not key.strip():
                    raise ValueError
                facts.append(Fact(id=stable_id(version.id, 'fact', key), artifact_id=version.artifact_id,
                    version_id=version.id, logical_key=key, label=item['label'], value=item['value'], unit=item['unit'],
                    source=Source(fragment_id=stable_id(version.id, 'fragment', key),
                                  locator=item['locator'], quote=item['quote'])))
            if len({f.logical_key for f in facts}) != len(facts):
                raise ValueError
            return facts
        except (ValueError, TypeError, KeyError):
            raise ProcessingError('invalid_demo_json') from None

    def compare(self, facts, context):
        old = {f.logical_key: f for f in context.previous_facts}
        new = {f.logical_key: f for f in facts}
        changes = []
        for key in sorted(old.keys() | new.keys()):
            before, after = old.get(key), new.get(key)
            if before and after and type(before.value) is type(after.value) and before.value == after.value and before.unit == after.unit:
                continue
            kind = 'added' if before is None else 'removed' if after is None else 'modified'
            changes.append(Change(id=stable_id(context.version.version.id, 'change', key),
                artifact_id=context.version.version.artifact_id, logical_key=key,
                before_fact_id=before.id if before else None, after_fact_id=after.id if after else None,
                before_value=before.value if before else None, after_value=after.value if after else None, kind=kind))
        return changes

    def assess(self, changes, facts, context):
        lookup = {f.id: f for f in context.graph.facts + facts}
        outgoing = {}
        for edge in sorted(context.graph.dependencies, key=lambda e: str(e.id)):
            if edge.status == 'confirmed' and edge.tracking == 'current':
                outgoing.setdefault(edge.from_fact_id, []).append(edge)
        findings = []
        for change in changes:
            root = change.before_fact_id if change.kind != 'added' else change.after_fact_id
            queue = deque([(root, [])])
            visited = {root}
            targets = [(root, [])] if change.kind == 'added' else []
            while queue:
                current, path = queue.popleft()
                for edge in outgoing.get(current, []):
                    if edge.to_fact_id not in visited:
                        visited.add(edge.to_fact_id)
                        next_path = path + [edge.id]
                        queue.append((edge.to_fact_id, next_path))
                        targets.append((edge.to_fact_id, next_path))
            for fact_id, path in targets:
                fact = lookup[fact_id]
                action = {'analysis': 'rerun_analysis', 'support': 'review_support'}.get(
                    context.artifact_kinds.get(fact.artifact_id), 'review_document')
                findings.append(Finding(id=stable_id(context.version.version.id, 'finding', f'{change.id}/{fact_id}'),
                    study_id=context.version.version.study_id, change_id=change.id, affected_fact_id=fact_id,
                    affected_artifact_id=fact.artifact_id, path_edge_ids=path, action=action,
                    explanation=f'Synthetic fixture: {change.logical_key} changed from {change.before_value!r} to '
                        f'{change.after_value!r}; review {fact.label} via {len(path)} confirmed current edge(s).',
                    sources=[lookup[root].source, fact.source] if root != fact_id else [fact.source],
                    status='open', owner_id=None, resolution=None))
        return findings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--adapter', required=True, help='demo, or module:factory returning a Pipeline')
    parser.add_argument('--once', action='store_true', help='Claim at most one available job')
    parser.add_argument('--poll-seconds', type=float, default=1)
    parser.add_argument('--lease-seconds', type=int, default=120)
    parser.add_argument('--max-attempts', type=int, default=3)
    parser.add_argument('--retry-seconds', type=int, default=5)
    args = parser.parse_args()
    if args.poll_seconds <= 0:
        parser.error('--poll-seconds must be positive')
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        parser.error('DATABASE_URL is required; in-memory API data cannot be shared with a worker')
    if args.adapter == 'demo':
        pipeline = DemoPipeline()
    else:
        module, factory = args.adapter.split(':', 1)
        pipeline = getattr(importlib.import_module(module), factory)()
    worker = Worker(PostgresWorkerStore(database_url, args.lease_seconds, args.max_attempts, args.retry_seconds),
                    configured_storage(), pipeline)
    logging.basicConfig(level=logging.INFO)
    try:
        while True:
            try:
                worked = worker.run_once()
            except RepositoryUnavailable:
                logger.error('Worker database unavailable; outstanding leases will recover')
                if args.once:
                    raise SystemExit(1) from None
                worked = False
            if args.once:
                return
            if not worked:
                time.sleep(args.poll_seconds)
    except KeyboardInterrupt:
        return


if __name__ == '__main__':
    main()
