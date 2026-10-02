"""Shared test helpers: file writers and valid record builders."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_CONFIG_DIR = PROJECT_ROOT / "config"
SAMPLE_DATA_DIR = PROJECT_ROOT / "data"


def write_json(path: Path, payload: Any) -> Path:
    """Write ``payload`` as JSON to ``path``, creating parent folders."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def write_text(path: Path, text: str) -> Path:
    """Write raw ``text`` to ``path``, creating parent folders."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def release_record(**overrides: Any) -> dict[str, Any]:
    """Build a valid release record, with optional field overrides."""
    record = {
        "release_id": "REL-2030.01",
        "name": "Test Release",
        "version": "2030.1.0",
        "target_date": "2030-01-15T02:00:00Z",
        "status": "IN_TESTING",
        "release_manager": "Test Manager",
        "applications": [
            {"app_id": "APP-ONE", "name": "App One", "version": "1.0.0", "owner_team": "Team A"},
            {"app_id": "APP-TWO", "name": "App Two", "version": "2.0.0", "owner_team": "Team B"},
        ],
    }
    return record | overrides


def defect_record(**overrides: Any) -> dict[str, Any]:
    """Build a valid open defect record, with optional field overrides."""
    record = {
        "defect_id": "DEF-1",
        "release_id": "REL-2030.01",
        "application_id": "APP-ONE",
        "title": "Something is broken",
        "severity": "HIGH",
        "status": "OPEN",
        "created_at": "2030-01-02T10:00:00Z",
    }
    return record | overrides


def pipeline_record(**overrides: Any) -> dict[str, Any]:
    """Build a valid successful pipeline run, with optional field overrides."""
    record = {
        "pipeline_id": "PL-1",
        "release_id": "REL-2030.01",
        "application_id": "APP-ONE",
        "name": "app-one-release",
        "status": "SUCCESS",
        "build_number": 1,
        "started_at": "2030-01-05T10:00:00Z",
        "finished_at": "2030-01-05T10:30:00Z",
    }
    return record | overrides


def regression_record(**overrides: Any) -> dict[str, Any]:
    """Build a valid regression suite result, with optional field overrides."""
    record = {
        "suite_id": "RS-1",
        "release_id": "REL-2030.01",
        "application_id": "APP-ONE",
        "suite_name": "Suite",
        "total_tests": 100,
        "passed": 95,
        "failed": 3,
        "skipped": 2,
        "coverage_percent": 90.0,
        "executed_at": "2030-01-06T10:00:00Z",
    }
    return record | overrides


def approval_record(**overrides: Any) -> dict[str, Any]:
    """Build a valid approved sign-off, with optional field overrides."""
    record = {
        "approval_id": "APR-1",
        "release_id": "REL-2030.01",
        "role": "QA_LEAD",
        "approver": "QA Person",
        "status": "APPROVED",
        "requested_at": "2030-01-07T09:00:00Z",
        "decided_at": "2030-01-08T09:00:00Z",
    }
    return record | overrides


def freeze_record(**overrides: Any) -> dict[str, Any]:
    """Build a valid freeze window, with optional field overrides."""
    record = {
        "freeze_id": "FRZ-1",
        "name": "Test Freeze",
        "start": "2030-01-10T00:00:00Z",
        "end": "2030-01-20T00:00:00Z",
    }
    return record | overrides


def history_record(**overrides: Any) -> dict[str, Any]:
    """Build a valid historical release, with optional field overrides."""
    record = {
        "release_id": "REL-2029.12",
        "version": "2029.12.0",
        "released_at": "2029-12-15T02:00:00Z",
        "outcome": "SUCCESS",
    }
    return record | overrides


def write_minimal_data_dir(root: Path) -> Path:
    """Create a small but complete, valid data directory under ``root``."""
    write_json(root / "releases" / "release.json", release_record())
    write_json(root / "defects" / "defects.json", [defect_record()])
    write_json(root / "pipelines" / "pipelines.json", [pipeline_record()])
    write_json(root / "testing" / "regression.json", [regression_record()])
    write_json(root / "approvals" / "approvals.json", [approval_record()])
    write_json(root / "freeze" / "freeze.json", [freeze_record()])
    write_json(root / "history" / "history.json", [history_record()])
    return root
