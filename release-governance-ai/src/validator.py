"""Cross-dataset integrity checks.

Each record is already validated on its own by its pydantic model when it is
loaded. This module checks the relationships *between* records: unique IDs
and references to releases and applications that actually exist.

It reports data problems only. Judging whether a release is ready to ship is
left to later phases.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum

from src.data_loader import ReleaseDataset
from src.logger import get_logger
from src.models import GovernanceModel

logger = get_logger(__name__)


class IssueLevel(StrEnum):
    """How serious an integrity issue is."""

    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass(frozen=True)
class ValidationIssue:
    """A relationship problem between records."""

    level: IssueLevel
    dataset: str
    record_id: str
    message: str

    def __str__(self) -> str:
        """Return a one-line description."""
        return f"[{self.level}] {self.dataset} {self.record_id}: {self.message}"


# A check inspects the whole dataset and yields any issues it finds.
IntegrityCheck = Callable[[ReleaseDataset], Iterable[ValidationIssue]]


def check_unique_ids(dataset: ReleaseDataset) -> Iterable[ValidationIssue]:
    """Report IDs that appear more than once within a dataset."""
    id_fields: list[tuple[str, Sequence[GovernanceModel], str]] = [
        ("releases", dataset.releases, "release_id"),
        ("defects", dataset.defects, "defect_id"),
        ("pipelines", dataset.pipelines, "pipeline_id"),
        ("regression_results", dataset.regression_results, "suite_id"),
        ("approvals", dataset.approvals, "approval_id"),
        ("freeze_windows", dataset.freeze_windows, "freeze_id"),
        ("history", dataset.history, "release_id"),
    ]
    for name, records, id_field in id_fields:
        counts = Counter(getattr(record, id_field) for record in records)
        for record_id, count in counts.items():
            if count > 1:
                yield ValidationIssue(IssueLevel.ERROR, name, record_id, f"ID appears {count} times")


def check_release_references(dataset: ReleaseDataset) -> Iterable[ValidationIssue]:
    """Report records that point at a release or application that doesn't exist."""
    apps_by_release = {r.release_id: r.application_ids for r in dataset.releases}
    linked: list[tuple[str, str, str, str | None]] = [
        *(("defects", d.defect_id, d.release_id, d.application_id) for d in dataset.defects),
        *(("pipelines", p.pipeline_id, p.release_id, p.application_id) for p in dataset.pipelines),
        *(("regression_results", r.suite_id, r.release_id, r.application_id) for r in dataset.regression_results),
        *(("approvals", a.approval_id, a.release_id, None) for a in dataset.approvals),
    ]
    for name, record_id, release_id, app_id in linked:
        if release_id not in apps_by_release:
            yield ValidationIssue(IssueLevel.ERROR, name, record_id, f"unknown release {release_id}")
        elif app_id is not None and app_id not in apps_by_release[release_id]:
            yield ValidationIssue(
                IssueLevel.ERROR, name, record_id, f"application {app_id} is not part of {release_id}"
            )


def check_history_dates(dataset: ReleaseDataset) -> Iterable[ValidationIssue]:
    """Warn about historical releases dated after an active release's target date."""
    active_dates = [r.target_date for r in dataset.releases if not r.status.is_terminal]
    if not active_dates:
        return
    earliest_active = min(active_dates)
    for past in dataset.history:
        if past.released_at > earliest_active:
            yield ValidationIssue(
                IssueLevel.WARNING, "history", past.release_id,
                "released_at is later than the next planned release",
            )


DEFAULT_CHECKS: tuple[IntegrityCheck, ...] = (
    check_unique_ids,
    check_release_references,
    check_history_dates,
)


class DataIntegrityValidator:
    """Runs a configurable set of integrity checks over a loaded dataset."""

    def __init__(self, checks: tuple[IntegrityCheck, ...] = DEFAULT_CHECKS) -> None:
        """Create a validator.

        Args:
            checks: The checks to run; new checks can be added without
                changing this class.
        """
        self.checks = checks

    def validate(self, dataset: ReleaseDataset) -> list[ValidationIssue]:
        """Run every check and log what it finds.

        Args:
            dataset: The loaded data.

        Returns:
            All issues found, in check order.
        """
        issues = [issue for check in self.checks for issue in check(dataset)]
        for issue in issues:
            log = logger.error if issue.level is IssueLevel.ERROR else logger.warning
            log("%s", issue)
        logger.info("Integrity validation finished with %d issue(s)", len(issues))
        return issues
