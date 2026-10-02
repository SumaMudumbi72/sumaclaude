"""Tests for cross-dataset integrity checks (src/validator.py)."""

from __future__ import annotations

from pathlib import Path

from src.data_loader import ReleaseDataLoader, ReleaseDataset
from src.validator import DataIntegrityValidator, IssueLevel, ValidationIssue
from tests.helpers import (
    SAMPLE_DATA_DIR,
    approval_record,
    defect_record,
    history_record,
    pipeline_record,
    write_json,
)


def validate(data_dir: Path) -> list[ValidationIssue]:
    """Load ``data_dir`` and run the default integrity checks."""
    return DataIntegrityValidator().validate(ReleaseDataLoader(data_dir).load_all())


def test_sample_data_has_no_integrity_issues() -> None:
    """The shipped sample data is internally consistent."""
    assert validate(SAMPLE_DATA_DIR) == []


def test_minimal_data_has_no_integrity_issues(data_dir: Path) -> None:
    """The minimal test data set is internally consistent."""
    assert validate(data_dir) == []


def test_duplicate_ids(data_dir: Path) -> None:
    """The same ID used twice in a dataset is an error."""
    write_json(data_dir / "defects" / "defects.json", [defect_record(), defect_record()])
    issues = validate(data_dir)
    assert len(issues) == 1
    assert issues[0].level is IssueLevel.ERROR
    assert (issues[0].dataset, issues[0].record_id) == ("defects", "DEF-1")
    assert "2 times" in issues[0].message


def test_duplicate_ids_across_files(data_dir: Path) -> None:
    """Duplicates are found even when split across files."""
    write_json(data_dir / "approvals" / "more.json", [approval_record()])
    assert [i.record_id for i in validate(data_dir)] == ["APR-1"]


def test_unknown_release_reference(data_dir: Path) -> None:
    """Records must refer to a release that exists."""
    write_json(data_dir / "pipelines" / "pipelines.json", [pipeline_record(release_id="REL-2099.01")])
    issues = validate(data_dir)
    assert len(issues) == 1 and "unknown release REL-2099.01" in issues[0].message


def test_application_not_in_release(data_dir: Path) -> None:
    """Records must refer to an application that is part of their release."""
    write_json(data_dir / "defects" / "defects.json", [defect_record(application_id="APP-GHOST")])
    issues = validate(data_dir)
    assert len(issues) == 1
    assert "APP-GHOST is not part of REL-2030.01" in issues[0].message


def test_history_after_active_release_is_warning(data_dir: Path) -> None:
    """A 'past' release dated after the next planned release is suspicious."""
    write_json(data_dir / "history" / "history.json", [history_record(released_at="2030-06-01T00:00:00Z")])
    issues = validate(data_dir)
    assert len(issues) == 1 and issues[0].level is IssueLevel.WARNING


def test_custom_checks_can_be_plugged_in() -> None:
    """New checks can be added without modifying the validator."""
    def always_warn(dataset: ReleaseDataset) -> list[ValidationIssue]:
        return [ValidationIssue(IssueLevel.WARNING, "custom", "X", "hello")]

    issues = DataIntegrityValidator(checks=(always_warn,)).validate(ReleaseDataset())
    assert [str(i) for i in issues] == ["[WARNING] custom X: hello"]
