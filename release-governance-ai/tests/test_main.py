"""End-to-end tests for the command-line program (main.py) and logging."""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pytest

import main
from src.logger import LOG_FILE_NAME, setup_logging
from tests.helpers import SAMPLE_CONFIG_DIR, SAMPLE_DATA_DIR, write_text


def run_main(
    tmp_path: Path,
    *extra: str,
    config_dir: Path = SAMPLE_CONFIG_DIR,
    data_dir: Path = SAMPLE_DATA_DIR,
) -> int:
    """Run the program with logs written under ``tmp_path``."""
    args = [
        "--config-dir", str(config_dir),
        "--data-dir", str(data_dir),
        "--log-dir", str(tmp_path / "logs"),
        *extra,
    ]
    return main.main(args)


def test_prints_summary_for_sample_data(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A normal run succeeds and prints the summary to stdout."""
    assert run_main(tmp_path) == main.EXIT_OK
    out = capsys.readouterr().out
    assert "AI Release Governance Assistant" in out
    assert "Approvals           : 3 of 4" in out
    assert "Data Issues         : 0" in out


def test_specific_release(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """--release-id selects another release."""
    assert run_main(tmp_path, "--release-id", "REL-2026.11") == main.EXIT_OK
    out = capsys.readouterr().out
    assert "REL-2026.11" in out and "Applications        : 2" in out


def test_unknown_release(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """An unknown release ID exits with code 1 and prints no summary."""
    assert run_main(tmp_path, "--release-id", "REL-1999.01") == main.EXIT_RELEASE_NOT_FOUND
    assert capsys.readouterr().out == ""


def test_invalid_config(tmp_path: Path, config_dir: Path) -> None:
    """Broken configuration exits with code 2 instead of crashing."""
    write_text(config_dir / "weights.yaml", "weights: {defects: 2}\n")
    assert run_main(tmp_path, config_dir=config_dir) == main.EXIT_CONFIG_ERROR


def test_missing_config(tmp_path: Path) -> None:
    """Missing configuration exits with code 2 instead of crashing."""
    assert run_main(tmp_path, config_dir=tmp_path / "nowhere") == main.EXIT_CONFIG_ERROR


def test_bad_data_still_produces_summary(tmp_path: Path, data_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Malformed data files are reported but don't stop the run."""
    write_text(data_dir / "defects" / "broken.json", "{not json")
    assert run_main(tmp_path, data_dir=data_dir) == main.EXIT_OK
    assert "Data Issues         : 1" in capsys.readouterr().out


def test_writes_log_file_with_timestamp_level_and_module(tmp_path: Path) -> None:
    """The log file records each line with timestamp, level, and module name."""
    run_main(tmp_path)
    log_text = (tmp_path / "logs" / LOG_FILE_NAME).read_text(encoding="utf-8")
    assert "| INFO     | src.data_loader | Loaded defects: 16 record(s)" in log_text
    # Imported as a module here, so the logger is "main" rather than "__main__".
    first = log_text.splitlines()[0]
    assert re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \| INFO     \| main \| Starting", first), first


def test_quiet_mode_hides_info_on_console(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """--quiet keeps INFO lines out of the console but not the log file."""
    run_main(tmp_path, "--quiet")
    assert "| INFO" not in capsys.readouterr().err
    assert "| INFO" in (tmp_path / "logs" / LOG_FILE_NAME).read_text(encoding="utf-8")


def test_setup_logging_is_idempotent(tmp_path: Path) -> None:
    """Calling setup twice doesn't duplicate handlers."""
    setup_logging(tmp_path)
    setup_logging(tmp_path)
    ours = [h for h in logging.getLogger().handlers if getattr(h, "_release_governance_handler", False)]
    assert len(ours) == 2  # one console + one file
