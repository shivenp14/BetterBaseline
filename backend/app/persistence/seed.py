"""Insert the one API-owned synthetic fixture atomically, without resetting reviews."""

import json
import os
from importlib.resources import files
from uuid import UUID

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from app.persistence.memory import StudyFixture

DEMO_STUDY_ID = UUID("30f04fb1-10cd-5674-88a0-2a6b4962a848")


def seed_demo(database_url: str) -> UUID:
    raw = json.loads(files("app.persistence").joinpath("fixtures.json").read_text())
    if len(raw) != 1:
        raise ValueError("Expected exactly one synthetic study")
    fixture = StudyFixture.model_validate(raw[0])
    if fixture.study.id != DEMO_STUDY_ID:
        raise ValueError("Seed is restricted to the known synthetic study")

    with psycopg.connect(database_url, connect_timeout=5, prepare_threshold=None) as connection:
        # Serialize concurrent demo seeds. No DELETE/UPDATE of existing records.
        connection.execute("SELECT pg_advisory_xact_lock(1413592595, 14)")

        def insert(table, record):
            query = sql.SQL("INSERT INTO public.{} ({}) VALUES ({}) ON CONFLICT DO NOTHING RETURNING id").format(
                sql.Identifier(table),
                sql.SQL(", ").join(map(sql.Identifier, record)),
                sql.SQL(", ").join(sql.Placeholder() for _ in record),
            )
            return connection.execute(query, list(record.values())).fetchone()

        study_id = fixture.study.id
        insert("studies", fixture.study.model_dump())
        actor_id = fixture.audit[0].actor_id
        connection.execute(
            """INSERT INTO public.memberships (study_id, user_id, role) VALUES (%s, %s, 'owner')
               ON CONFLICT DO NOTHING""", (study_id, actor_id),
        )
        for artifact in fixture.artifacts:
            created = insert("artifacts", artifact.model_dump(exclude={"versions"}))
            for version in sorted(artifact.versions, key=lambda item: item.version_number):
                insert("artifact_versions", version.model_dump())
            if created:
                baseline_version = min(artifact.versions, key=lambda item: item.version_number).id
                connection.execute("UPDATE public.artifacts SET approved_version_id = %s WHERE id = %s",
                                   (baseline_version, artifact.id))
        for fact in fixture.graph.facts:
            insert("source_fragments", dict(id=fact.source.fragment_id, study_id=study_id,
                artifact_id=fact.artifact_id, version_id=fact.version_id,
                locator=fact.source.locator, quote=fact.source.quote))
            record = fact.model_dump(exclude={"source"})
            record.update(study_id=study_id, fragment_id=fact.source.fragment_id, value=Jsonb(fact.value))
            insert("facts", record)
        for dependency in fixture.graph.dependencies:
            record = dependency.model_dump()
            record.update(study_id=study_id, evidence=Jsonb([source.model_dump(mode="json") for source in dependency.evidence]))
            insert("dependencies", record)
        for change in fixture.changes:
            record = change.model_dump()
            record.update(study_id=study_id, before_value=Jsonb(change.before_value), after_value=Jsonb(change.after_value))
            insert("changes", record)
        for finding in fixture.findings:
            record = finding.model_dump()
            record["sources"] = Jsonb([source.model_dump(mode="json") for source in finding.sources])
            record["resolution"] = Jsonb(finding.resolution.model_dump(mode="json")) if finding.resolution else None
            insert("findings", record)
        for event in fixture.audit:
            insert("audit_events", event.model_dump())
    return study_id


def main():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required (backend-only PostgreSQL connection string)")
    try:
        study_id = seed_demo(database_url)
    except psycopg.Error:
        raise SystemExit("Demo seed failed; check database connectivity and the baseline migration") from None
    print(f"Synthetic study seeded: {study_id}")


if __name__ == "__main__":
    main()
