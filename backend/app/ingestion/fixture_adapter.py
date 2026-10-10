"""Deterministic fixture adapter for TrialSync local synthetic demo.

Loads synthetic demo documents, contract-shaped baseline facts, confirmed
dependencies, and expected revision impact findings without external LLM calls.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID


def _find_repo_root() -> Path:
    """Traverse upwards from this module to locate the TrialSync repository root."""
    current = Path(__file__).resolve().parent
    for parent in [current] + list(current.parents):
        if (parent / "demo" / "fixtures" / "fixtures.json").is_file():
            return parent
        if (parent / "TrialSync" / "demo" / "fixtures" / "fixtures.json").is_file():
            return parent / "TrialSync"
    # Fallback to relative path from backend/app/ingestion
    return Path(__file__).resolve().parents[3]


def get_fixtures_dir() -> Path:
    """Return the path to demo/fixtures directory."""
    return _find_repo_root() / "demo" / "fixtures"


def get_sources_dir() -> Path:
    """Return the path to demo/sources directory."""
    return _find_repo_root() / "demo" / "sources"


def load_demo_fixtures() -> list[dict[str, Any]]:
    """Load the canonical demo fixtures dataset."""
    fixture_path = get_fixtures_dir() / "fixtures.json"
    if not fixture_path.is_file():
        # Fallback to persistence fixtures if present in backend
        alt_path = _find_repo_root() / "backend" / "app" / "persistence" / "fixtures.json"
        if alt_path.is_file():
            fixture_path = alt_path
        else:
            raise FileNotFoundError(f"Fixture file not found at {fixture_path}")

    with open(fixture_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_source_text(filename: str) -> str:
    """Load raw synthetic source text for an artifact version."""
    source_path = get_sources_dir() / filename
    if not source_path.is_file():
        raise FileNotFoundError(f"Source file '{filename}' not found at {source_path}")
    return source_path.read_text(encoding="utf-8")


def get_baseline_graph() -> dict[str, Any]:
    """Return the un-amended baseline state (Study, baseline artifacts, v1 facts, confirmed edges)."""
    baseline_path = get_fixtures_dir() / "baseline_graph.json"
    if baseline_path.is_file():
        with open(baseline_path, "r", encoding="utf-8") as f:
            return json.load(f)

    # Fallback: compute dynamically from fixtures.json
    fixtures = load_demo_fixtures()[0]
    baseline_artifacts = []
    for art in fixtures.get("artifacts", []):
        art_copy = dict(art)
        art_copy["versions"] = [v for v in art["versions"] if v.get("version_number") == 1]
        baseline_artifacts.append(art_copy)

    baseline_facts = [
        f for f in fixtures.get("graph", {}).get("facts", []) if f.get("value") == 24
    ]
    dependencies = fixtures.get("graph", {}).get("dependencies", [])

    return {
        "study": fixtures["study"],
        "artifacts": baseline_artifacts,
        "graph": {
            "facts": baseline_facts,
            "dependencies": dependencies,
        },
    }


def get_revision_delta() -> dict[str, Any]:
    """Return the amendment delta (v2 versions, v2 facts, change record, and expected findings)."""
    revision_path = get_fixtures_dir() / "revision_delta.json"
    if revision_path.is_file():
        with open(revision_path, "r", encoding="utf-8") as f:
            return json.load(f)

    fixtures = load_demo_fixtures()[0]
    v2_versions = [
        v
        for art in fixtures.get("artifacts", [])
        for v in art["versions"]
        if v.get("version_number") == 2
    ]
    v2_facts = [
        f for f in fixtures.get("graph", {}).get("facts", []) if f.get("value") == 36
    ]

    return {
        "study_id": fixtures["study"]["id"],
        "amended_versions": v2_versions,
        "new_facts": v2_facts,
        "changes": fixtures.get("changes", []),
        "findings": fixtures.get("findings", []),
    }


def extract_version_fixture(filename_or_id: str | UUID) -> list[dict[str, Any]]:
    """Extract deterministic facts for a specific document version or filename.

    Allows ingestion workflows to run in offline/synthetic mode without live LLMs.
    """
    target = str(filename_or_id).strip()
    fixtures = load_demo_fixtures()[0]

    # Resolve version_id if filename was provided
    target_version_id = None
    for art in fixtures.get("artifacts", []):
        for v in art.get("versions", []):
            if v.get("filename") == target or str(v.get("id")) == target:
                target_version_id = str(v.get("id"))
                break
        if target_version_id:
            break

    if target_version_id is None:
        target_version_id = target

    matching_facts = [
        fact
        for fact in fixtures.get("graph", {}).get("facts", [])
        if str(fact.get("version_id")) == target_version_id
    ]

    return matching_facts


def verify_evidence_integrity() -> list[dict[str, Any]]:
    """Verify that all source quotes and locators cited in fixtures exist verbatim in source text."""
    fixtures = load_demo_fixtures()[0]
    version_to_file: dict[str, str] = {}
    for art in fixtures.get("artifacts", []):
        for v in art.get("versions", []):
            version_to_file[str(v.get("id"))] = v.get("filename", "")

    results: list[dict[str, Any]] = []
    for fact in fixtures.get("graph", {}).get("facts", []):
        version_id = str(fact.get("version_id"))
        filename = version_to_file.get(version_id)
        if not filename:
            results.append({
                "fact_id": fact.get("id"),
                "status": "missing_artifact_version",
                "valid": False,
            })
            continue

        source_text = load_source_text(filename)
        quote = fact.get("source", {}).get("quote", "")
        locator = fact.get("source", {}).get("locator", "")

        quote_match = quote in source_text
        locator_match = locator in source_text

        results.append({
            "fact_id": fact.get("id"),
            "filename": filename,
            "logical_key": fact.get("logical_key"),
            "quote": quote,
            "locator": locator,
            "quote_match": quote_match,
            "locator_match": locator_match,
            "valid": quote_match and locator_match,
        })

    return results
