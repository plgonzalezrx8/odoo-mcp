from __future__ import annotations

from odoo_mcp.prompts import register_prompts


class FakeMCP:
    def __init__(self) -> None:
        self.prompts: dict[str, object] = {}

    def prompt(self, *, name: str, description: str | None = None):
        def decorator(func):
            self.prompts[name] = func
            func.description = description
            return func

        return decorator


def test_registers_safe_odoo_and_crm_prompts() -> None:
    mcp = FakeMCP()

    register_prompts(mcp)

    assert set(mcp.prompts) == {
        "odoo_safe_operation",
        "odoo_crm_pipeline_review",
        "odoo_record_change_plan",
    }


def test_safe_operation_prompt_includes_guardrails_and_context() -> None:
    mcp = FakeMCP()
    register_prompts(mcp)

    prompt = mcp.prompts["odoo_safe_operation"](
        goal="Clean duplicate contacts",
        model="res.partner",
        risk_level="high",
    )

    assert "Clean duplicate contacts" in prompt
    assert "res.partner" in prompt
    assert "read first" in prompt.lower()
    assert "confirm" in prompt.lower()
    assert "high" in prompt.lower()


def test_crm_prompt_is_specific_to_pipeline_work() -> None:
    mcp = FakeMCP()
    register_prompts(mcp)

    prompt = mcp.prompts["odoo_crm_pipeline_review"](team="Inside Sales", period="this month")

    assert "Inside Sales" in prompt
    assert "this month" in prompt
    assert "crm.lead" in prompt
    assert "pipeline" in prompt.lower()
    assert "next actions" in prompt.lower()


def test_record_change_plan_prompt_demands_dry_run() -> None:
    mcp = FakeMCP()
    register_prompts(mcp)

    prompt = mcp.prompts["odoo_record_change_plan"](
        model="crm.lead",
        change="Set stale opportunities to lost",
        sample_size=10,
    )

    assert "crm.lead" in prompt
    assert "Set stale opportunities to lost" in prompt
    assert "dry run" in prompt.lower()
    assert "10" in prompt
