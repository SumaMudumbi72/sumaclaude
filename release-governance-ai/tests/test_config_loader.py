"""Tests for configuration loading (src/config_loader.py)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.config_loader import ConfigLoader, load_yaml_mapping
from src.exceptions import ConfigurationError, MissingFileError
from src.models import ApprovalRole, PipelineStatus, RulesConfig, WeightsConfig
from tests.helpers import SAMPLE_CONFIG_DIR, write_text


class TestSampleConfiguration:
    """The shipped config files load into typed objects."""

    def test_loads_both_files_as_typed_models(self) -> None:
        """Loads both files as typed models."""
        config = ConfigLoader(SAMPLE_CONFIG_DIR).load()
        assert isinstance(config.rules, RulesConfig)
        assert isinstance(config.weights, WeightsConfig)

    def test_rules_values_are_parsed_to_python_types(self) -> None:
        """Rule values are parsed into Python and enum types."""
        rules = ConfigLoader(SAMPLE_CONFIG_DIR).load_rules()
        assert rules.readiness.max_open_critical_defects == 0
        assert rules.readiness.required_pipeline_status is PipelineStatus.SUCCESS
        assert ApprovalRole.CHANGE_ADVISORY_BOARD in rules.readiness.required_approval_roles
        assert rules.history.lookback_releases == 12

    def test_weights_add_up_to_one(self) -> None:
        """Weights add up to one."""
        weights = ConfigLoader(SAMPLE_CONFIG_DIR).load_weights()
        assert sum(weights.weights.model_dump().values()) == pytest.approx(1.0)
        assert weights.thresholds.go > weights.thresholds.conditional_go


class TestMissingFiles:
    """Missing configuration raises MissingFileError."""

    def test_missing_rules_file(self, config_dir: Path) -> None:
        """Missing rules file."""
        (config_dir / "rules.yaml").unlink()
        with pytest.raises(MissingFileError, match="rules.yaml"):
            ConfigLoader(config_dir).load()

    def test_missing_weights_file(self, config_dir: Path) -> None:
        """Missing weights file."""
        (config_dir / "weights.yaml").unlink()
        with pytest.raises(MissingFileError, match="weights.yaml"):
            ConfigLoader(config_dir).load()

    def test_missing_directory(self, tmp_path: Path) -> None:
        """A missing config directory raises MissingFileError."""
        with pytest.raises(MissingFileError):
            ConfigLoader(tmp_path / "does-not-exist").load()


class TestInvalidConfiguration:
    """Malformed or invalid configuration raises ConfigurationError."""

    def test_invalid_yaml_syntax(self, config_dir: Path) -> None:
        """A YAML syntax error raises ConfigurationError."""
        write_text(config_dir / "rules.yaml", "readiness: [unclosed\n")
        with pytest.raises(ConfigurationError, match="Invalid YAML"):
            ConfigLoader(config_dir).load_rules()

    @pytest.mark.parametrize("content", ["", "- just\n- a list\n", "plain string\n"])
    def test_top_level_must_be_a_mapping(self, config_dir: Path, content: str) -> None:
        """Top level must be a mapping."""
        write_text(config_dir / "rules.yaml", content)
        with pytest.raises(ConfigurationError, match="mapping"):
            ConfigLoader(config_dir).load_rules()

    def test_unknown_key_is_rejected(self, config_dir: Path) -> None:
        """Unknown key is rejected."""
        write_text(config_dir / "rules.yaml", "readiness:\n  max_open_critcal_defects: 1\n")
        with pytest.raises(ConfigurationError, match="max_open_critcal_defects"):
            ConfigLoader(config_dir).load_rules()

    def test_wrong_type_is_rejected(self, config_dir: Path) -> None:
        """Wrong type is rejected."""
        write_text(config_dir / "rules.yaml", "readiness:\n  max_open_high_defects: lots\n")
        with pytest.raises(ConfigurationError, match="max_open_high_defects"):
            ConfigLoader(config_dir).load_rules()

    def test_invalid_enum_is_rejected(self, config_dir: Path) -> None:
        """Invalid enum is rejected."""
        write_text(config_dir / "rules.yaml", "readiness:\n  required_approval_roles: [JANITOR]\n")
        with pytest.raises(ConfigurationError, match="required_approval_roles"):
            ConfigLoader(config_dir).load_rules()

    def test_out_of_range_percentage_is_rejected(self, config_dir: Path) -> None:
        """Out of range percentage is rejected."""
        write_text(config_dir / "rules.yaml", "readiness:\n  min_regression_coverage: 120\n")
        with pytest.raises(ConfigurationError, match="min_regression_coverage"):
            ConfigLoader(config_dir).load_rules()

    def test_weights_must_sum_to_one(self, config_dir: Path) -> None:
        """Weights must sum to one."""
        write_text(
            config_dir / "weights.yaml",
            "weights: {defects: 0.5, testing: 0.5, pipeline: 0.5, approvals: 0, freeze: 0, history: 0}\n",
        )
        with pytest.raises(ConfigurationError, match="add up to 1.0"):
            ConfigLoader(config_dir).load_weights()

    def test_thresholds_must_be_ordered(self, config_dir: Path) -> None:
        """Thresholds must be ordered."""
        write_text(
            config_dir / "weights.yaml",
            "weights: {defects: 1, testing: 0, pipeline: 0, approvals: 0, freeze: 0, history: 0}\n"
            "thresholds: {go: 50, conditional_go: 70}\n",
        )
        with pytest.raises(ConfigurationError, match="go threshold"):
            ConfigLoader(config_dir).load_weights()


def test_defaults_fill_omitted_rules(config_dir: Path) -> None:
    """Sections left out of rules.yaml fall back to defaults."""
    write_text(config_dir / "rules.yaml", "version: '2.0'\n")
    rules = ConfigLoader(config_dir).load_rules()
    assert rules.version == "2.0"
    assert rules.readiness.max_open_high_defects == 3
    assert rules.readiness.block_during_freeze is True


def test_load_yaml_mapping_returns_dict(config_dir: Path) -> None:
    """The low-level reader returns the raw mapping."""
    data = load_yaml_mapping(config_dir / "weights.yaml")
    assert data["weights"]["defects"] == 0.30
