"""Factual summary of a release's loaded data.

These are plain counts and aggregates, with no readiness judgement. That
reasoning belongs to a later phase.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from src.data_loader import ReleaseSnapshot
from src.models import (
    Approval,
    ApprovalStatus,
    Defect,
    FreezeWindow,
    Pipeline,
    PipelineStatus,
    RegressionResult,
    Release,
    Severity,
)

TITLE = "AI Release Governance Assistant"
RULE = "=" * 37
NO_DATA = "NO DATA"

# Worst-first ranking used when combining several pipeline results.
_PIPELINE_SEVERITY = {
    PipelineStatus.SUCCESS: 0,
    PipelineStatus.RUNNING: 1,
    PipelineStatus.UNSTABLE: 2,
    PipelineStatus.CANCELLED: 3,
    PipelineStatus.FAILED: 4,
}


@dataclass(frozen=True)
class ReleaseSummary:
    """Headline numbers for one release."""

    release_id: str
    release_name: str
    version: str
    application_count: int
    open_critical_defects: int
    open_high_defects: int
    pipeline_status: str
    regression_coverage: float | None
    approvals_granted: int
    approvals_required: int
    active_freezes: list[str]
    historical_releases: int
    data_issues: int

    @property
    def freeze_active(self) -> bool:
        """Whether any freeze window covers the release's target date."""
        return bool(self.active_freezes)


def count_open_defects(defects: Iterable[Defect], severity: Severity) -> int:
    """Count unresolved defects of the given severity."""
    return sum(1 for d in defects if d.severity is severity and d.is_open)


def latest_pipeline_runs(pipelines: Iterable[Pipeline]) -> list[Pipeline]:
    """Keep only the most recent run (highest build number) per application."""
    latest: dict[str, Pipeline] = {}
    for run in pipelines:
        current = latest.get(run.application_id)
        if current is None or run.build_number > current.build_number:
            latest[run.application_id] = run
    return list(latest.values())


def overall_pipeline_status(pipelines: Iterable[Pipeline]) -> str:
    """Combine the latest run of each application into one status.

    The worst status wins, so one failed application makes the release
    ``FAILED``. Returns ``NO DATA`` when there are no runs.
    """
    runs = latest_pipeline_runs(pipelines)
    if not runs:
        return NO_DATA
    return str(max((run.status for run in runs), key=_PIPELINE_SEVERITY.__getitem__))


def weighted_coverage(results: Iterable[RegressionResult]) -> float | None:
    """Average suite coverage, weighted by each suite's number of tests.

    Returns ``None`` when there are no tests.
    """
    results = list(results)
    total_tests = sum(r.total_tests for r in results)
    if not total_tests:
        return None
    return sum(r.coverage_percent * r.total_tests for r in results) / total_tests


def count_approvals(approvals: Iterable[Approval]) -> tuple[int, int]:
    """Return ``(granted, required)`` counting only required approvals."""
    required = [a for a in approvals if a.required]
    granted = sum(1 for a in required if a.status is ApprovalStatus.APPROVED)
    return granted, len(required)


def active_freezes(release: Release, windows: Iterable[FreezeWindow]) -> list[str]:
    """Names of freeze windows covering the release's target date and environment."""
    return [w.name for w in windows if w.covers(release.target_date, release.environment)]


def build_summary(snapshot: ReleaseSnapshot, data_issues: int = 0) -> ReleaseSummary:
    """Compute the headline numbers for a release.

    Args:
        snapshot: The release and its related data.
        data_issues: Number of loading and integrity issues found.

    Returns:
        The summary.
    """
    release = snapshot.release
    granted, required = count_approvals(snapshot.approvals)
    return ReleaseSummary(
        release_id=release.release_id,
        release_name=release.name,
        version=release.version,
        application_count=len(release.applications),
        open_critical_defects=count_open_defects(snapshot.defects, Severity.CRITICAL),
        open_high_defects=count_open_defects(snapshot.defects, Severity.HIGH),
        pipeline_status=overall_pipeline_status(snapshot.pipelines),
        regression_coverage=weighted_coverage(snapshot.regression_results),
        approvals_granted=granted,
        approvals_required=required,
        active_freezes=active_freezes(release, snapshot.freeze_windows),
        historical_releases=len(snapshot.history),
        data_issues=data_issues,
    )


def format_summary(summary: ReleaseSummary) -> str:
    """Render the summary as the console report.

    Args:
        summary: The numbers to show.

    Returns:
        A multi-line string ready to print.
    """
    coverage = NO_DATA if summary.regression_coverage is None else f"{summary.regression_coverage:.0f}%"
    freeze = f"Yes ({', '.join(summary.active_freezes)})" if summary.freeze_active else "No"
    rows = [
        ("Applications", str(summary.application_count)),
        ("Critical Defects", str(summary.open_critical_defects)),
        ("High Defects", str(summary.open_high_defects)),
        ("Pipeline Status", summary.pipeline_status),
        ("Regression Coverage", coverage),
        ("Approvals", f"{summary.approvals_granted} of {summary.approvals_required}"),
        ("Freeze Active", freeze),
        ("Historical Releases", str(summary.historical_releases)),
        ("Data Issues", str(summary.data_issues)),
    ]
    width = max(len(label) for label, _ in rows)
    lines = [
        RULE, "", TITLE, "", RULE, "",
        f"Release Loaded : {summary.release_id} ({summary.release_name}, v{summary.version})",
        "",
        *(f"{label:<{width}} : {value}" for label, value in rows),
        "", RULE,
    ]
    return "\n".join(lines)
