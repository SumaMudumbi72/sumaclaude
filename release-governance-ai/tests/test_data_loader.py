"""Tests for JSON loading (src/data_loader.py).

Covers sample data, payload shapes, missing files, invalid JSON, and invalid
schema. The loader must never raise from its ``load_*`` methods.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from src.data_loader import JsonDataLoader, ReleaseDataLoader
from src.exceptions import DataValidationError, InvalidJsonError, MissingFileError, ReleaseNotFoundError
from src.models import Defect, Release, Severity
from tests.helpers import (
    SAMPLE_DATA_DIR,
    defect_record,
    release_record,
    write_json,
    write_text,
)


@pytest.fixture
def loader() -> JsonDataLoader:
    """Provide a fresh JSON loader."""
    return JsonDataLoader()


class TestSampleData:
    """The shipped sample data loads completely and cleanly."""

    def test_every_dataset_loads_without_issues(self) -> None:
        """Every dataset loads without issues."""
        dataset = ReleaseDataLoader(SAMPLE_DATA_DIR).load_all()
        assert dataset.issues == []
        assert len(dataset.releases) == 2
        assert len(dataset.defects) == 16
        assert len(dataset.pipelines) == 6
        assert len(dataset.regression_results) == 6
        assert len(dataset.approvals) == 4
        assert len(dataset.freeze_windows) == 3
        assert len(dataset.history) == 18

    def test_records_are_typed_models(self) -> None:
        """Records are typed models."""
        dataset = ReleaseDataLoader(SAMPLE_DATA_DIR).load_all()
        assert all(isinstance(r, Release) for r in dataset.releases)
        assert all(isinstance(d.severity, Severity) for d in dataset.defects)


class TestJsonLoading:
    """Valid JSON files in their supported shapes."""

    def test_single_object_file(self, loader: JsonDataLoader, tmp_path: Path) -> None:
        """A file holding one JSON object yields one record."""
        path = write_json(tmp_path / "one.json", defect_record())
        result = loader.load_file(path, Defect)
        assert result.ok and result.files_read == 1
        assert [d.defect_id for d in result.records] == ["DEF-1"]

    def test_array_file(self, loader: JsonDataLoader, tmp_path: Path) -> None:
        """A file holding a JSON array yields one record per item."""
        path = write_json(tmp_path / "many.json", [defect_record(defect_id=f"DEF-{i}") for i in range(3)])
        result = loader.load_file(path, Defect)
        assert result.ok
        assert [d.defect_id for d in result.records] == ["DEF-0", "DEF-1", "DEF-2"]

    def test_empty_array_is_valid(self, loader: JsonDataLoader, tmp_path: Path) -> None:
        """Empty array is valid."""
        result = loader.load_file(write_json(tmp_path / "empty.json", []), Defect)
        assert result.ok and result.records == []

    def test_directory_merges_files_in_name_order(self, loader: JsonDataLoader, tmp_path: Path) -> None:
        """Directory merges files in name order."""
        write_json(tmp_path / "b.json", [defect_record(defect_id="DEF-2")])
        write_json(tmp_path / "a.json", [defect_record(defect_id="DEF-1")])
        write_text(tmp_path / "notes.txt", "not json, ignored")
        result = loader.load_directory(tmp_path, Defect)
        assert result.ok and result.files_read == 2
        assert [d.defect_id for d in result.records] == ["DEF-1", "DEF-2"]

    def test_unknown_fields_are_ignored(self, loader: JsonDataLoader, tmp_path: Path) -> None:
        """Unknown fields are ignored."""
        path = write_json(tmp_path / "extra.json", defect_record(jira_key="ABC-123"))
        result = loader.load_file(path, Defect)
        assert result.ok and len(result.records) == 1


class TestMissingFiles:
    """Missing files and folders become issues, never exceptions."""

    def test_missing_file(self, loader: JsonDataLoader, tmp_path: Path) -> None:
        """A missing file becomes an issue, not an exception."""
        result = loader.load_file(tmp_path / "nope.json", Defect)
        assert result.records == [] and result.files_read == 0
        assert "not found" in result.issues[0].message

    def test_missing_directory(self, loader: JsonDataLoader, tmp_path: Path) -> None:
        """A missing directory becomes an issue, not an exception."""
        result = loader.load_directory(tmp_path / "missing", Defect)
        assert result.records == []
        assert "not found" in result.issues[0].message

    def test_empty_directory(self, loader: JsonDataLoader, tmp_path: Path) -> None:
        """A directory with no JSON files is reported."""
        result = loader.load_directory(tmp_path, Defect)
        assert "no JSON files" in result.issues[0].message

    def test_missing_dataset_folder_does_not_stop_others(self, data_dir: Path) -> None:
        """Missing dataset folder does not stop others."""
        for path in (data_dir / "defects").iterdir():
            path.unlink()
        (data_dir / "defects").rmdir()
        dataset = ReleaseDataLoader(data_dir).load_all()
        assert dataset.defects == []
        assert len(dataset.releases) == 1 and len(dataset.pipelines) == 1
        assert len(dataset.issues) == 1

    def test_read_json_raises_missing_file_error(self, loader: JsonDataLoader, tmp_path: Path) -> None:
        """The strict reader raises MissingFileError."""
        with pytest.raises(MissingFileError):
            loader.read_json(tmp_path / "nope.json")


class TestInvalidJson:
    """Malformed JSON is reported and skipped."""

    @pytest.mark.parametrize(
        "content",
        ['{"defect_id": "DEF-1",', "[1, 2,]", "not json at all", ""],
        ids=["truncated", "trailing-comma", "plain-text", "empty-file"],
    )
    def test_malformed_file_becomes_issue(self, loader: JsonDataLoader, tmp_path: Path, content: str) -> None:
        """Malformed file becomes issue."""
        result = loader.load_file(write_text(tmp_path / "bad.json", content), Defect)
        assert result.records == []
        assert "Invalid JSON" in result.issues[0].message

    def test_issue_includes_line_and_column(self, loader: JsonDataLoader, tmp_path: Path) -> None:
        """Issue includes line and column."""
        content = '{\n  "a": 1,\n  "b": oops\n}'
        result = loader.load_file(write_text(tmp_path / "bad.json", content), Defect)
        assert "line 3, column 8" in result.issues[0].message

    def test_non_utf8_file(self, loader: JsonDataLoader, tmp_path: Path) -> None:
        """A file that is not UTF-8 is reported, not crashed on."""
        path = tmp_path / "latin1.json"
        path.write_bytes('{"title": "café"}'.encode("latin-1"))
        result = loader.load_file(path, Defect)
        assert "UTF-8" in result.issues[0].message

    def test_bad_file_does_not_block_good_files(self, loader: JsonDataLoader, tmp_path: Path) -> None:
        """Bad file does not block good files."""
        write_text(tmp_path / "a-bad.json", "{oops")
        write_json(tmp_path / "b-good.json", [defect_record()])
        result = loader.load_directory(tmp_path, Defect)
        assert len(result.records) == 1 and len(result.issues) == 1

    @pytest.mark.parametrize("payload", ['"a string"', "42", "null", "true"])
    def test_unsupported_top_level_value(self, loader: JsonDataLoader, tmp_path: Path, payload: str) -> None:
        """Unsupported top level value."""
        result = loader.load_file(write_text(tmp_path / "scalar.json", payload), Defect)
        assert "top level" in result.issues[0].message

    def test_read_json_raises_invalid_json_error(self, loader: JsonDataLoader, tmp_path: Path) -> None:
        """The strict reader raises InvalidJsonError with the position."""
        with pytest.raises(InvalidJsonError, match="line 1"):
            loader.read_json(write_text(tmp_path / "bad.json", "{oops"))

    def test_errors_are_logged(self, loader: JsonDataLoader, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """Errors are logged."""
        with caplog.at_level(logging.ERROR):
            loader.load_file(write_text(tmp_path / "bad.json", "{oops"), Defect)
        assert any("Invalid JSON" in r.message and r.levelno == logging.ERROR for r in caplog.records)


class TestInvalidSchema:
    """Records that fail validation are skipped; valid siblings are kept."""

    def test_invalid_record_skipped_valid_kept(self, loader: JsonDataLoader, tmp_path: Path) -> None:
        """An invalid record is skipped while valid ones in the file are kept."""
        records = [
            defect_record(defect_id="DEF-1"),
            defect_record(defect_id="DEF-2", severity="APOCALYPTIC"),
            defect_record(defect_id="DEF-3"),
        ]
        result = loader.load_file(write_json(tmp_path / "defects.json", records), Defect)
        assert [d.defect_id for d in result.records] == ["DEF-1", "DEF-3"]
        assert len(result.issues) == 1
        assert result.issues[0].source == "defects.json[1]"
        assert "severity" in result.issues[0].message

    @pytest.mark.parametrize(
        ("record", "field_name"),
        [
            (defect_record(title=None), "title"),
            ({k: v for k, v in defect_record().items() if k != "severity"}, "severity"),
            (defect_record(created_at="yesterday"), "created_at"),
            (defect_record(release_id="release-ten"), "release_id"),
        ],
        ids=["null-required", "missing-required", "bad-datetime", "bad-id-format"],
    )
    def test_schema_errors_name_the_field(
        self, loader: JsonDataLoader, tmp_path: Path, record: dict, field_name: str
    ) -> None:
        """Schema errors name the field."""
        result = loader.load_file(write_json(tmp_path / "d.json", [record]), Defect)
        assert result.records == []
        assert field_name in result.issues[0].message

    def test_non_object_item(self, loader: JsonDataLoader, tmp_path: Path) -> None:
        """Array items that are not objects are reported and skipped."""
        result = loader.load_file(write_json(tmp_path / "d.json", [defect_record(), "oops", 7]), Defect)
        assert len(result.records) == 1 and len(result.issues) == 2
        assert "expected a JSON object" in result.issues[0].message

    def test_validate_record_raises_data_validation_error(self, loader: JsonDataLoader) -> None:
        """The strict validator raises DataValidationError with details."""
        with pytest.raises(DataValidationError) as excinfo:
            loader.validate_record(defect_record(severity="NOPE"), Defect, "inline")
        assert excinfo.value.source == "inline"
        assert any("severity" in error for error in excinfo.value.errors)


class TestReleaseSelection:
    """Choosing a release from the loaded dataset."""

    def test_snapshot_filters_by_release(self, data_dir: Path) -> None:
        """A snapshot only includes records for the selected release."""
        other = defect_record(defect_id="DEF-99", release_id="REL-2031.01")
        write_json(data_dir / "defects" / "other.json", [other])
        snapshot = ReleaseDataLoader(data_dir).load_all().snapshot("REL-2030.01")
        assert [d.defect_id for d in snapshot.defects] == ["DEF-1"]

    def test_unknown_release_raises(self, data_dir: Path) -> None:
        """Unknown release raises."""
        dataset = ReleaseDataLoader(data_dir).load_all()
        with pytest.raises(ReleaseNotFoundError, match="REL-1999.01"):
            dataset.snapshot("REL-1999.01")

    def test_no_releases_raises(self, data_dir: Path) -> None:
        """No releases raises."""
        (data_dir / "releases" / "release.json").unlink()
        dataset = ReleaseDataLoader(data_dir).load_all()
        with pytest.raises(ReleaseNotFoundError, match="No releases"):
            dataset.default_release()

    def test_default_is_earliest_active_release(self, data_dir: Path) -> None:
        """The default release is the active one with the earliest target date."""
        later = release_record(release_id="REL-2030.02", target_date="2030-02-15T02:00:00Z")
        done = release_record(release_id="REL-2029.12", target_date="2029-12-15T02:00:00Z", status="DEPLOYED")
        write_json(data_dir / "releases" / "later.json", later)
        write_json(data_dir / "releases" / "done.json", done)
        assert ReleaseDataLoader(data_dir).load_all().default_release().release_id == "REL-2030.01"

    def test_default_falls_back_to_latest_when_none_active(self, data_dir: Path) -> None:
        """With no active releases, the most recent one is the default."""
        older = release_record(release_id="REL-2029.12", target_date="2029-12-15T02:00:00Z", status="DEPLOYED")
        write_json(data_dir / "releases" / "release.json", release_record(status="DEPLOYED"))
        write_json(data_dir / "releases" / "older.json", older)
        assert ReleaseDataLoader(data_dir).load_all().default_release().release_id == "REL-2030.01"
