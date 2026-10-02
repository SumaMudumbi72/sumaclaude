"""Loading of JSON datasets into validated models.

:class:`JsonDataLoader` reads JSON files and validates each record against a
pydantic model. Its ``load_*`` methods never raise: problems such as missing
files, malformed JSON, or invalid records are logged and collected as
:class:`LoadIssue` entries, and every valid record is still returned.

:class:`ReleaseDataLoader` uses it to load all datasets under ``data/`` into
a :class:`ReleaseDataset`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from src.exceptions import (
    DataValidationError,
    InvalidJsonError,
    MissingFileError,
    ReleaseGovernanceError,
    ReleaseNotFoundError,
)
from src.logger import get_logger
from src.models import (
    Approval,
    Defect,
    FreezeWindow,
    GovernanceModel,
    HistoricalRelease,
    Pipeline,
    RegressionResult,
    Release,
    format_validation_errors,
)

logger = get_logger(__name__)


# --------------------------------------------------------------------------
# Generic JSON loading
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class LoadIssue:
    """A problem found while loading data. Loading continues past it."""

    source: str
    message: str

    def __str__(self) -> str:
        """Return ``source: message``."""
        return f"{self.source}: {self.message}"


@dataclass
class LoadResult[T: BaseModel]:
    """Records loaded from one or more files, plus any problems found."""

    records: list[T] = field(default_factory=list)
    issues: list[LoadIssue] = field(default_factory=list)
    files_read: int = 0

    @property
    def ok(self) -> bool:
        """Whether loading finished without any issues."""
        return not self.issues

    def merge(self, other: LoadResult[T]) -> None:
        """Add the records, issues, and file count from ``other`` to this result."""
        self.records.extend(other.records)
        self.issues.extend(other.issues)
        self.files_read += other.files_read


class JsonDataLoader:
    """Reads JSON files and validates their records against pydantic models.

    A file may contain a single JSON object (one record) or an array of
    objects (many records).
    """

    def read_json(self, path: Path) -> Any:
        """Parse a JSON file.

        Args:
            path: The file to read.

        Returns:
            The parsed JSON value.

        Raises:
            MissingFileError: The file does not exist.
            InvalidJsonError: The file isn't valid UTF-8 JSON.
        """
        if not path.is_file():
            raise MissingFileError(path, "Data file")
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise InvalidJsonError(path, f"{exc.msg} (line {exc.lineno}, column {exc.colno})") from exc
        except UnicodeDecodeError as exc:
            raise InvalidJsonError(path, "file is not UTF-8 encoded") from exc

    def validate_record[T: BaseModel](self, data: Any, model: type[T], source: str) -> T:
        """Validate one record against ``model``.

        Args:
            data: The parsed JSON value for the record.
            model: The pydantic model to validate against.
            source: Where the record came from, used in error messages.

        Returns:
            The validated model instance.

        Raises:
            DataValidationError: The record doesn't match the model.
        """
        if not isinstance(data, dict):
            raise DataValidationError(source, [f"expected a JSON object, got {type(data).__name__}"])
        try:
            return model.model_validate(data)
        except ValidationError as exc:
            raise DataValidationError(source, format_validation_errors(exc)) from exc

    def load_file[T: BaseModel](self, path: Path, model: type[T]) -> LoadResult[T]:
        """Load and validate every record in one file. Never raises.

        Args:
            path: The JSON file to load.
            model: The pydantic model each record must match.

        Returns:
            The valid records, plus an issue for each problem found.
        """
        # Issue messages omit the path because the issue's source already shows it.
        result: LoadResult[T] = LoadResult()
        try:
            payload = self.read_json(path)
        except MissingFileError:
            return _with_issue(result, str(path), "file not found", warning=True)
        except InvalidJsonError as exc:
            return _with_issue(result, str(path), f"Invalid JSON: {exc.detail}")
        except OSError as exc:
            return _with_issue(result, str(path), f"cannot read file: {exc.strerror or exc}")

        result.files_read = 1
        items = _as_record_list(payload)
        if items is None:
            return _with_issue(result, str(path), "top level must be a JSON object or array")

        for index, item in enumerate(items):
            source = f"{path.name}[{index}]" if isinstance(payload, list) else path.name
            try:
                result.records.append(self.validate_record(item, model, source))
            except DataValidationError as exc:
                _with_issue(result, source, "; ".join(exc.errors))
        return result

    def load_directory[T: BaseModel](self, directory: Path, model: type[T]) -> LoadResult[T]:
        """Load every ``*.json`` file in ``directory`` (not recursive). Never raises.

        Args:
            directory: The folder to scan.
            model: The pydantic model each record must match.

        Returns:
            The valid records from all files, plus all issues found.
        """
        result: LoadResult[T] = LoadResult()
        if not directory.is_dir():
            return _with_issue(result, str(directory), "directory not found", warning=True)

        files = sorted(directory.glob("*.json"))
        if not files:
            return _with_issue(result, str(directory), "no JSON files found", warning=True)
        for path in files:
            result.merge(self.load_file(path, model))
        return result


def _as_record_list(payload: Any) -> list[Any] | None:
    """Normalize a JSON payload into a list of records, or ``None`` if unsupported."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        return [payload]
    return None


def _with_issue[T: BaseModel](
    result: LoadResult[T], source: str, message: str, *, warning: bool = False
) -> LoadResult[T]:
    """Log a problem, record it on ``result``, and return ``result``."""
    log = logger.warning if warning else logger.error
    log("%s: %s", source, message)
    result.issues.append(LoadIssue(source=source, message=message))
    return result


# --------------------------------------------------------------------------
# Release datasets
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class DatasetSpec:
    """Where a dataset lives under ``data/`` and which model its records use."""

    attribute: str
    folder: str
    model: type[GovernanceModel]


# Adding a dataset only requires a new entry here and a field on ReleaseDataset.
DATASET_SPECS: tuple[DatasetSpec, ...] = (
    DatasetSpec("releases", "releases", Release),
    DatasetSpec("defects", "defects", Defect),
    DatasetSpec("pipelines", "pipelines", Pipeline),
    DatasetSpec("regression_results", "testing", RegressionResult),
    DatasetSpec("approvals", "approvals", Approval),
    DatasetSpec("freeze_windows", "freeze", FreezeWindow),
    DatasetSpec("history", "history", HistoricalRelease),
)


@dataclass(frozen=True)
class ReleaseSnapshot:
    """All data relevant to a single release, ready for analysis."""

    release: Release
    defects: list[Defect]
    pipelines: list[Pipeline]
    regression_results: list[RegressionResult]
    approvals: list[Approval]
    freeze_windows: list[FreezeWindow]
    history: list[HistoricalRelease]


@dataclass
class ReleaseDataset:
    """Every loaded dataset, plus the issues found while loading."""

    releases: list[Release] = field(default_factory=list)
    defects: list[Defect] = field(default_factory=list)
    pipelines: list[Pipeline] = field(default_factory=list)
    regression_results: list[RegressionResult] = field(default_factory=list)
    approvals: list[Approval] = field(default_factory=list)
    freeze_windows: list[FreezeWindow] = field(default_factory=list)
    history: list[HistoricalRelease] = field(default_factory=list)
    issues: list[LoadIssue] = field(default_factory=list)

    def get_release(self, release_id: str) -> Release:
        """Return the release with ``release_id``.

        Raises:
            ReleaseNotFoundError: No release has that ID.
        """
        for release in self.releases:
            if release.release_id == release_id:
                return release
        raise ReleaseNotFoundError(release_id)

    def default_release(self) -> Release:
        """Pick the release to analyze when none is specified.

        Returns the active (not deployed, rolled back, or cancelled) release
        with the earliest target date, or the most recent release if none
        are active.

        Raises:
            ReleaseNotFoundError: There are no releases at all.
        """
        active = [r for r in self.releases if not r.status.is_terminal]
        if active:
            return min(active, key=lambda r: r.target_date)
        if self.releases:
            return max(self.releases, key=lambda r: r.target_date)
        raise ReleaseNotFoundError(None)

    def snapshot(self, release_id: str | None = None) -> ReleaseSnapshot:
        """Collect the data for one release.

        Args:
            release_id: The release to select, or ``None`` for :meth:`default_release`.

        Raises:
            ReleaseNotFoundError: The release doesn't exist.
        """
        release = self.get_release(release_id) if release_id else self.default_release()
        rid = release.release_id
        return ReleaseSnapshot(
            release=release,
            defects=[d for d in self.defects if d.release_id == rid],
            pipelines=[p for p in self.pipelines if p.release_id == rid],
            regression_results=[r for r in self.regression_results if r.release_id == rid],
            approvals=[a for a in self.approvals if a.release_id == rid],
            freeze_windows=list(self.freeze_windows),
            history=sorted(self.history, key=lambda h: h.released_at),
        )


class ReleaseDataLoader:
    """Loads every release-governance dataset from a data directory."""

    def __init__(
        self,
        data_dir: Path,
        json_loader: JsonDataLoader | None = None,
        specs: tuple[DatasetSpec, ...] = DATASET_SPECS,
    ) -> None:
        """Create a loader for ``data_dir``.

        Args:
            data_dir: Root folder containing one subfolder per dataset.
            json_loader: Loader to use; injectable for testing.
            specs: Which datasets to load and where they live.
        """
        self.data_dir = data_dir
        self.json_loader = json_loader or JsonDataLoader()
        self.specs = specs

    def load_all(self) -> ReleaseDataset:
        """Load every dataset. Never raises.

        Returns:
            All valid records, plus every issue found.
        """
        dataset = ReleaseDataset()
        for spec in self.specs:
            result = self._load_dataset(spec)
            setattr(dataset, spec.attribute, result.records)
            dataset.issues.extend(result.issues)
        log = logger.warning if dataset.issues else logger.info
        log("Data loading finished with %d issue(s)", len(dataset.issues))
        return dataset

    def _load_dataset(self, spec: DatasetSpec) -> LoadResult[GovernanceModel]:
        """Load one dataset, guarding against unexpected errors."""
        directory = self.data_dir / spec.folder
        try:
            result = self.json_loader.load_directory(directory, spec.model)
        except ReleaseGovernanceError as exc:  # Defensive: load_directory shouldn't raise.
            result = _with_issue(LoadResult(), str(directory), str(exc))
        logger.info(
            "Loaded %s: %d record(s) from %d file(s)",
            spec.attribute.replace("_", " "), len(result.records), result.files_read,
        )
        return result
