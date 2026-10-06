"""Rule evaluation result objects and console rendering."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RuleResult:
    """Single-rule evaluation output or aggregate governance evaluation result."""

    rule_name: str = ""
    status: str = ""
    evidence: str = ""
    recommendation: str = ""
    outcome: str = ""
    rule_results: list["RuleResult"] = field(default_factory=list)
    overall_recommendation: str = ""
    reasons: list[str] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        """Backward-compatible alias for the rule name."""
        return self.rule_name

    @property
    def decision(self) -> str:
        """Backward-compatible alias for the overall decision."""
        return self.overall_recommendation

    @property
    def is_pass(self) -> bool:
        """Whether this rule passed."""
        return self.status == "PASS"


RuleEvaluation = RuleResult


class RuleSummaryGenerator:
    """Render a governance evaluation as a console report."""

    @staticmethod
    def generate(evaluation: RuleEvaluation) -> str:
        """Return a printable summary matching the release governance format."""
        lines: list[str] = [
            "=========================================",
            "Release Governance Result",
            "=========================================",
            "",
        ]

        for result in evaluation.rule_results:
            lines.append(f"{result.rule_name:<24} {result.status}")

        lines.extend(
            [
                "",
                "-----------------------------------------",
                "",
                "Overall Decision",
                "",
                evaluation.overall_recommendation,
                "",
                "-----------------------------------------",
                "",
                "Reason",
                *[f"• {reason}" for reason in evaluation.reasons],
                "",
                "Next Actions",
                *[f"{index}. {action}" for index, action in enumerate(evaluation.next_actions, start=1)],
            ]
        )
        return "\n".join(lines) + "\n\n========================================="


def format_rule_summary(evaluation: RuleEvaluation) -> str:
    """Compatibility wrapper for rendering a rule evaluation summary."""
    return RuleSummaryGenerator.generate(evaluation)


RuleDecision = RuleEvaluation

__all__ = [
    "RuleDecision",
    "RuleEvaluation",
    "RuleResult",
    "RuleSummaryGenerator",
    "format_rule_summary",
]
