from __future__ import annotations

from pathlib import Path

from src.rule_engine import RuleEngine, RuleLoader, evaluate_rules
from src.rule_models import RuleDefinition
from src.rule_result import RuleResult


def test_rule_loader_reads_governance_rules() -> None:
    """The config file loads as governance rule definitions."""
    rules = RuleLoader(Path("config/rules.yaml")).load()
    names = {rule.name for rule in rules}
    assert {"Critical Defects", "Regression Coverage", "Security Approval", "Production Freeze", "High Defects"}.issubset(names)


def test_rule_evaluator_blocks_critical_defects() -> None:
    """Open critical defects are a blocking failure."""
    engine = RuleEngine(Path("config/rules.yaml"))
    decision = engine.evaluate(
        {
            "open_critical_defects": 2,
            "regression_coverage": 95.0,
            "security_approval_pending": False,
            "freeze_active": False,
            "open_high_defects": 2,
        }
    )
    assert decision.overall_recommendation == "BLOCK"
    assert any(result.rule_name == "Critical Defects" and result.status == "FAIL" for result in decision.rule_results)


def test_rule_evaluator_blocks_regression_coverage_gap() -> None:
    """Coverage below threshold blocks the release."""
    engine = RuleEngine(Path("config/rules.yaml"))
    decision = engine.evaluate(
        {
            "open_critical_defects": 0,
            "regression_coverage": 85.0,
            "security_approval_pending": False,
            "freeze_active": False,
            "open_high_defects": 2,
        }
    )
    assert decision.overall_recommendation == "BLOCK"
    assert any(result.rule_name == "Regression Coverage" and result.status == "FAIL" for result in decision.rule_results)


def test_rule_evaluator_escalates_when_security_is_pending() -> None:
    """Pending security approval escalates without blocking."""
    engine = RuleEngine(Path("config/rules.yaml"))
    decision = engine.evaluate(
        {
            "open_critical_defects": 0,
            "regression_coverage": 95.0,
            "security_approval_pending": True,
            "freeze_active": False,
            "open_high_defects": 2,
        }
    )
    assert decision.overall_recommendation == "ESCALATE"
    assert any(result.rule_name == "Security Approval" and result.status == "FAIL" for result in decision.rule_results)


def test_rule_evaluator_returns_conditional_approval_for_high_defects() -> None:
    """High defect count can lead to conditional approval."""
    engine = RuleEngine(Path("config/rules.yaml"))
    decision = engine.evaluate(
        {
            "open_critical_defects": 0,
            "regression_coverage": 95.0,
            "security_approval_pending": False,
            "freeze_active": False,
            "open_high_defects": 6,
        }
    )
    assert decision.overall_recommendation == "CONDITIONAL APPROVAL"
    assert any(result.rule_name == "High Defects" and result.status == "WARNING" for result in decision.rule_results)


def test_rule_evaluator_proceeds_when_mandatory_rules_pass() -> None:
    """A clean release proceeds without exemptions."""
    engine = RuleEngine(Path("config/rules.yaml"))
    decision = engine.evaluate(
        {
            "open_critical_defects": 0,
            "regression_coverage": 96.0,
            "security_approval_pending": False,
            "freeze_active": False,
            "open_high_defects": 2,
        }
    )
    assert decision.overall_recommendation == "PROCEED"
    assert all(result.status == "PASS" for result in decision.rule_results)


def test_evaluate_rules_utility_function() -> None:
    """The utility helper returns the same structured results."""
    result = evaluate_rules(
        {
            "open_critical_defects": 0,
            "regression_coverage": 92.0,
            "security_approval_pending": False,
            "freeze_active": False,
            "open_high_defects": 4,
        },
        Path("config/rules.yaml"),
    )
    assert isinstance(result, RuleResult)
    assert result.overall_recommendation in {"PROCEED", "CONDITIONAL APPROVAL", "BLOCK", "ESCALATE"}


def test_rule_definition_supports_yaml_descriptions() -> None:
    """Rule definitions can carry descriptive metadata."""
    rule = RuleDefinition(name="Critical Defects", field="open_critical_defects", operator="gt", value=0, recommendation="Close critical defects")
    assert rule.name == "Critical Defects"
    assert rule.field == "open_critical_defects"
    assert rule.operator == "gt"
