"""Tests for the release summary (src/summary.py)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.data_loader import ReleaseDataLoader
from src.models import Pipeline, RegressionResult
from src.summary import (
    NO_DATA,
    build_summary,
    format_summary,
    overall_pipeline_status,
    weighted_coverage,
)
from tests.helpers import SAMPLE_DATA_DIR, freeze_record, pipeline_record, regression_record, write_json


def test_sample_release_summary() -> None:
    """The sample data produces the expected headline numbers."""
    snapshot = ReleaseDataLoader(SAMPLE_DATA_DIR).load_all().snapshot()
    summary = build_summary(snapshot)
    assert summary.release_id == "REL-2026.10"
    assert summary.application_count == 5
    assert summary.open_critical_defects == 2
    assert summary.open_high_defects == 4
    assert summary.pipeline_status == "SUCCESS"
    assert round(summary.regression_coverage or 0) == 94
    assert (summary.approvals_granted, summary.approvals_required) == (3, 4)
    assert summary.freeze_active is False
    assert summary.historical_releases == 18


def test_formatted_summary_contains_every_line() -> None:
    """The console report shows each headline figure."""
    snapshot = ReleaseDataLoader(SAMPLE_DATA_DIR).load_all().snapshot()
    report = format_summary(build_summary(snapshot))
    for expected in [
        "AI Release Governance Assistant",
        "Release Loaded : REL-2026.10",
        "Applications        : 5",
        "Critical Defects    : 2",
        "High Defects        : 4",
        "Pipeline Status     : SUCCESS",
        "Regression Coverage : 94%",
        "Approvals           : 3 of 4",
        "Freeze Active       : No",
        "Historical Releases : 18",
    ]:
        assert expected in report


def _pipelines(*records: dict) -> list[Pipeline]:
    """Validate raw pipeline records into models."""
    return [Pipeline.model_validate(r) for r in records]


class TestPipelineStatus:
    """Combining pipeline runs into one status."""

    def test_latest_build_wins_per_application(self) -> None:
        """Latest build wins per application."""
        runs = _pipelines(
            pipeline_record(pipeline_id="a", build_number=1, status="FAILED"),
            pipeline_record(pipeline_id="b", build_number=2, status="SUCCESS"),
        )
        assert overall_pipeline_status(runs) == "SUCCESS"

    def test_worst_application_wins(self) -> None:
        """Worst application wins."""
        runs = _pipelines(
            pipeline_record(pipeline_id="a", application_id="APP-ONE", status="SUCCESS"),
            pipeline_record(pipeline_id="b", application_id="APP-TWO", status="FAILED"),
        )
        assert overall_pipeline_status(runs) == "FAILED"

    def test_running_is_reported(self) -> None:
        """Running is reported."""
        runs = _pipelines(pipeline_record(status="RUNNING", finished_at=None))
        assert overall_pipeline_status(runs) == "RUNNING"

    def test_no_runs(self) -> None:
        """With no pipeline runs the status is NO DATA."""
        assert overall_pipeline_status([]) == NO_DATA


class TestCoverage:
    """Weighted regression coverage."""

    def test_weighted_by_test_count(self) -> None:
        """Suites with more tests count for more in the average."""
        results = [
            RegressionResult.model_validate(regression_record(suite_id="a", coverage_percent=100.0)),
            RegressionResult.model_validate(
                regression_record(suite_id="b", total_tests=300, passed=300, failed=0, skipped=0, coverage_percent=80.0)
            ),
        ]
        assert weighted_coverage(results) == pytest.approx(85.0)

    def test_no_tests(self) -> None:
        """With no test results coverage is None."""
        assert weighted_coverage([]) is None


def test_freeze_on_target_date_is_reported(data_dir: Path) -> None:
    """A freeze covering the target date shows as active, by name."""
    write_json(data_dir / "freeze" / "freeze.json", [freeze_record(name="Year End", start="2030-01-01T00:00:00Z")])
    summary = build_summary(ReleaseDataLoader(data_dir).load_all().snapshot())
    assert summary.active_freezes == ["Year End"]
    assert "Freeze Active       : Yes (Year End)" in format_summary(summary)


def test_release_without_data_shows_no_data(data_dir: Path) -> None:
    """A release with no related records still produces a summary."""
    for folder in ("pipelines", "testing"):
        write_json(data_dir / folder / next((data_dir / folder).iterdir()).name, [])
    report = format_summary(build_summary(ReleaseDataLoader(data_dir).load_all().snapshot()))
    assert "Pipeline Status     : NO DATA" in report
    assert "Regression Coverage : NO DATA" in report
