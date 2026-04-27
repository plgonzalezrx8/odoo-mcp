"""Prompt registration helpers for safe Odoo work."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol


class SupportsPromptRegistration(Protocol):
    def prompt(
        self, *, name: str, description: str | None = None
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]: ...


def register_prompts(mcp: SupportsPromptRegistration) -> None:
    """Register operator prompts for safe Odoo and CRM workflows."""

    @mcp.prompt(
        name="odoo_safe_operation",
        description="Plan safe Odoo work with read-first validation and explicit confirmation.",
    )
    def odoo_safe_operation(goal: str, model: str, risk_level: str = "medium") -> str:
        return "\n".join(
            [
                f"Goal: {goal}",
                f"Primary Odoo model: {model}",
                f"Risk level: {risk_level}",
                "",
                "Work read first. Inspect relevant records, fields, access assumptions, "
                "and current user context before proposing changes.",
                "For any write, unlink, action, or method call, explain the exact target "
                "domain or ids, the fields that will change, and the expected business effect.",
                "Ask for confirmation before destructive or broad changes. Prefer small batches "
                "and verify after each batch.",
                "Return a concise plan, the MCP tools/resources you will use, and the rollback "
                "or mitigation path when available.",
            ]
        )

    @mcp.prompt(
        name="odoo_crm_pipeline_review",
        description="Review CRM pipeline health and recommend safe next actions.",
    )
    def odoo_crm_pipeline_review(team: str = "all teams", period: str = "current period") -> str:
        return "\n".join(
            [
                f"Review the CRM pipeline for {team} during {period}.",
                "Use crm.lead as the primary model and start from odoo://crm/pipeline/summary.",
                "Segment open opportunities by stage, expected revenue, probability, owner, "
                "stale activity, and next activity date where available.",
                "Identify risks and next actions without modifying records unless the operator "
                "explicitly approves a change plan.",
                "When recommending updates, include the exact search domain, sample records, "
                "and validation checks.",
            ]
        )

    @mcp.prompt(
        name="odoo_record_change_plan",
        description="Prepare a dry-run plan before changing Odoo records.",
    )
    def odoo_record_change_plan(model: str, change: str, sample_size: int = 20) -> str:
        return "\n".join(
            [
                f"Prepare a dry run for this Odoo record change: {change}",
                f"Target model: {model}",
                f"Sample size: {sample_size}",
                "",
                "First list the domain, fields to read, and safety constraints. Then fetch a "
                "representative sample and summarize what would change.",
                "Do not call create, write, unlink, action, or arbitrary methods during the "
                "dry run.",
                "Before execution, require confirmation that includes the model, domain or ids, "
                "values, count, and verification query.",
            ]
        )
