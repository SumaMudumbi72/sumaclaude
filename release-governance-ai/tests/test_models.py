"""Tests for record-level validation rules (src/models.py)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from src.models import (
    Approval,
    Defect,
    DefectStatus,
    Environment,
    FreezeWindow,
    HistoricalRelease,
    Pipeline,
    RegressionResult,
    Release,
    ReleaseStatus,
)
from tests.helpers import (
    approval_record,
    defect_record,
    freeze_record,
    history_record,
    pipeline_record,
    regression_record,
    release_record,
)


def assert_invalid(model: type[BaseModel], data: dict[str, Any], expected: str) -> None:
    """Assert that ``data`` fails validation with a message containing ``expected``."""
    with pytest.raises(ValidationError) as excinfo:
        model.model_validate(data)
    assert expected in str(excinfo.value)


class TestRelease:
    """Release and Application validation."""

    def test_valid_release_and_defaults(self) -> None:
        """A valid release loads, with defaults filled in."""
        release = Release.model_validate(release_record())
        assert release.environment is Environment.PRODUCTION
        assert release.application_ids == {"APP-ONE", "APP-TWO"}
        assert release.applications[0].components == []

    def test_requires_at_least_one_application(self) -> None:
        """Requires at least one application."""
        assert_invalid(Release, release_record(applications=[]), "at least 1 item")

    def test_rejects_duplicate_application_ids(self) -> None:
        """A release cannot list the same application twice."""
        app = release_record()["applications"][0]
        assert_invalid(Release, release_record(applications=[app, app]), "duplicate application IDs: APP-ONE")

    @pytest.mark.parametrize("version", ["1.0", "v1.0.0", "1.0.0.0", "latest"])
    def test_rejects_bad_version(self, version: str) -> None:
        """Versions must look like MAJOR.MINOR.PATCH."""
        assert_invalid(Release, release_record(version=version), "version")

    def test_rejects_timestamp_without_timezone(self) -> None:
        """Rejects timestamp without timezone."""
        assert_invalid(Release, release_record(target_date="2030-01-15T02:00:00"), "timezone")

    def test_is_immutable(self) -> None:
        """Loaded records cannot be modified."""
        release = Release.model_validate(release_record())
        with pytest.raises(ValidationError):
            release.name = "changed"  # type: ignore[misc]

    def test_terminal_statuses(self) -> None:
        """Deployed, rolled-back and cancelled releases are terminal."""
        assert ReleaseStatus.DEPLOYED.is_terminal
        assert not ReleaseStatus.AWAITING_APPROVAL.is_terminal


class TestDefect:
    """Defect validation and helpers."""

    def test_defaults(self) -> None:
        """Optional defect fields get their defaults."""
        defect = Defect.model_validate(defect_record())
        assert defect.is_blocking is False and defect.assignee is None and defect.is_open

    @pytest.mark.parametrize(
        ("status", "is_open"),
        [("OPEN", True), ("IN_PROGRESS", True), ("REOPENED", True), ("DEFERRED", False)],
    )
    def test_open_statuses(self, status: str, is_open: bool) -> None:
        """Only OPEN, IN_PROGRESS and REOPENED defects count as open."""
        assert Defect.model_validate(defect_record(status=status)).is_open is is_open

    def test_resolved_requires_resolved_at(self) -> None:
        """Resolved defects must have a resolved_at time."""
        assert_invalid(Defect, defect_record(status="RESOLVED"), "resolved_at is required")

    def test_resolved_at_not_before_created_at(self) -> None:
        """A defect cannot be resolved before it was created."""
        record = defect_record(status="CLOSED", resolved_at="2030-01-01T00:00:00Z")
        assert_invalid(Defect, record, "resolved_at must not be earlier than created_at")

    def test_rejects_unknown_status(self) -> None:
        """Rejects unknown status."""
        assert_invalid(Defect, defect_record(status="WONT_FIX"), "status")

    def test_strips_whitespace(self) -> None:
        """Strips whitespace."""
        assert Defect.model_validate(defect_record(title="  padded  ")).title == "padded"

    def test_status_enum_value(self) -> None:
        """Status strings are parsed into the DefectStatus enum."""
        assert Defect.model_validate(defect_record()).status is DefectStatus.OPEN


class TestPipeline:
    """Pipeline validation."""

    def test_running_pipeline_needs_no_finish_time(self) -> None:
        """Running pipeline needs no finish time."""
        record = pipeline_record(status="RUNNING", finished_at=None)
        assert Pipeline.model_validate(record).finished_at is None

    def test_finished_pipeline_needs_finish_time(self) -> None:
        """Finished pipeline needs finish time."""
        assert_invalid(Pipeline, pipeline_record(finished_at=None), "finished_at is required")

    def test_finish_not_before_start(self) -> None:
        """Finish not before start."""
        assert_invalid(Pipeline, pipeline_record(finished_at="2030-01-05T09:00:00Z"), "must not be earlier")

    @pytest.mark.parametrize("sha", ["xyz1234", "abc", "ABCDEF1234"])
    def test_rejects_bad_commit_sha(self, sha: str) -> None:
        """Commit SHAs must be 7-40 lowercase hex characters."""
        assert_invalid(Pipeline, pipeline_record(commit_sha=sha), "commit_sha")

    def test_rejects_zero_build_number(self) -> None:
        """Rejects zero build number."""
        assert_invalid(Pipeline, pipeline_record(build_number=0), "build_number")

    def test_rejects_negative_stage_duration(self) -> None:
        """Rejects negative stage duration."""
        stage = {"name": "build", "status": "SUCCESS", "duration_seconds": -1}
        assert_invalid(Pipeline, pipeline_record(stages=[stage]), "duration_seconds")


class TestRegressionResult:
    """Regression result validation."""

    def test_pass_rate(self) -> None:
        """Pass rate is passed tests as a percentage of all tests."""
        assert RegressionResult.model_validate(regression_record()).pass_rate == pytest.approx(95.0)

    def test_empty_suite_pass_rate_is_zero(self) -> None:
        """Empty suite pass rate is zero."""
        record = regression_record(total_tests=0, passed=0, failed=0, skipped=0)
        assert RegressionResult.model_validate(record).pass_rate == 0.0

    def test_counts_must_add_up(self) -> None:
        """Counts must add up."""
        assert_invalid(RegressionResult, regression_record(passed=90), "must equal total_tests (100)")

    @pytest.mark.parametrize("coverage", [-1, 100.5])
    def test_coverage_range(self, coverage: float) -> None:
        """Coverage must be between 0 and 100."""
        assert_invalid(RegressionResult, regression_record(coverage_percent=coverage), "coverage_percent")

    def test_rejects_negative_counts(self) -> None:
        """Rejects negative counts."""
        assert_invalid(RegressionResult, regression_record(failed=-3, passed=101), "failed")


class TestApproval:
    """Approval validation."""

    def test_pending_needs_no_decision(self) -> None:
        """Pending needs no decision."""
        approval = Approval.model_validate(approval_record(status="PENDING", decided_at=None))
        assert approval.required is True

    @pytest.mark.parametrize("status", ["APPROVED", "REJECTED"])
    def test_decision_requires_decided_at(self, status: str) -> None:
        """Decision requires decided at."""
        assert_invalid(Approval, approval_record(status=status, decided_at=None), "decided_at is required")

    def test_decision_not_before_request(self) -> None:
        """Decision not before request."""
        assert_invalid(Approval, approval_record(decided_at="2030-01-01T00:00:00Z"), "must not be earlier")

    def test_rejects_unknown_role(self) -> None:
        """Rejects unknown role."""
        assert_invalid(Approval, approval_record(role="INTERN"), "role")


class TestFreezeWindow:
    """Freeze window validation and coverage checks."""

    def test_end_after_start(self) -> None:
        """A freeze window must end after it starts."""
        assert_invalid(FreezeWindow, freeze_record(end="2030-01-10T00:00:00Z"), "end must be later than start")

    def test_defaults_to_production(self) -> None:
        """Defaults to production."""
        assert FreezeWindow.model_validate(freeze_record()).environments == [Environment.PRODUCTION]

    @pytest.mark.parametrize(
        ("moment", "environment", "expected"),
        [
            (datetime(2030, 1, 15, tzinfo=UTC), Environment.PRODUCTION, True),
            (datetime(2030, 1, 10, tzinfo=UTC), Environment.PRODUCTION, True),   # start is inclusive
            (datetime(2030, 1, 20, tzinfo=UTC), Environment.PRODUCTION, True),   # end is inclusive
            (datetime(2030, 1, 21, tzinfo=UTC), Environment.PRODUCTION, False),
            (datetime(2030, 1, 15, tzinfo=UTC), Environment.STAGING, False),
        ],
    )
    def test_covers(self, moment: datetime, environment: Environment, expected: bool) -> None:
        """A window covers moments inside it, inclusive, for affected environments only."""
        window = FreezeWindow.model_validate(freeze_record())
        assert window.covers(moment, environment) is expected

    def test_empty_environments_means_all(self) -> None:
        """Empty environments means all."""
        window = FreezeWindow.model_validate(freeze_record(environments=[]))
        assert window.covers(datetime(2030, 1, 15, tzinfo=UTC), Environment.QA)


class TestHistoricalRelease:
    """Historical release validation."""

    def test_rollback_flag_must_match_outcome(self) -> None:
        """Rollback flag must match outcome."""
        assert_invalid(HistoricalRelease, history_record(outcome="ROLLED_BACK"), "rollback_performed")
        assert_invalid(HistoricalRelease, history_record(rollback_performed=True), "rollback_performed")

    def test_critical_cannot_exceed_total(self) -> None:
        """Critical cannot exceed total."""
        record = history_record(post_release_defects=1, critical_post_release_defects=2)
        assert_invalid(HistoricalRelease, record, "cannot exceed")

    def test_hotfix_release_id_allowed(self) -> None:
        """Hotfix release id allowed."""
        record = history_record(release_id="REL-2029.12.1", version="2029.12.1")
        assert HistoricalRelease.model_validate(record).release_id == "REL-2029.12.1"
