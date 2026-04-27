from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from odoo_mcp.exceptions import OdooSafetyError
from odoo_mcp.tools.crm import register_crm_tools


class FakeMCP:
    def __init__(self) -> None:
        self.tools: dict[str, Callable[..., Any]] = {}

    def tool(
        self, *, name: str, description: str
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        assert description

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self.tools[name] = func
            return func

        return decorator


class FakeOdooClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    async def call(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append(("call", args, kwargs))
        method = args[1]
        if method == "search_read":
            return [{"id": 7, "name": "Important opportunity"}]
        if method == "create":
            return 42
        if method == "write":
            return True
        if method == "read_group":
            return [{"stage_id": [1, "New"], "__count": 3}]
        return {"ok": True}


@pytest.fixture
def registered() -> tuple[FakeMCP, FakeOdooClient]:
    mcp = FakeMCP()
    client = FakeOdooClient()
    register_crm_tools(mcp, client)
    return mcp, client


def test_registers_comprehensive_core_crm_tools(registered: tuple[FakeMCP, FakeOdooClient]) -> None:
    mcp, _client = registered

    assert {
        "crm_list_leads",
        "crm_get_lead",
        "crm_create_lead",
        "crm_update_lead",
        "crm_list_pipeline_stages",
        "crm_move_lead_to_stage",
        "crm_mark_won",
        "crm_mark_lost",
        "crm_restore_lead",
        "crm_convert_lead_to_opportunity",
        "crm_merge_opportunities",
        "crm_schedule_activity",
        "crm_mark_activity_done",
        "crm_list_activities",
        "crm_list_teams",
        "crm_update_lead_score",
        "crm_pipeline_report",
        "crm_activity_report",
    }.issubset(mcp.tools)


@pytest.mark.asyncio
async def test_lead_search_uses_search_read_with_expected_domain_and_fields(
    registered: tuple[FakeMCP, FakeOdooClient],
) -> None:
    mcp, client = registered

    result = await mcp.tools["crm_list_leads"](
        kind="opportunity",
        team_id=3,
        salesperson_id=8,
        stage_id=5,
        active=True,
        search="Important",
        limit=10,
        offset=2,
    )

    assert result == [{"id": 7, "name": "Important opportunity"}]
    assert client.calls == [
        (
            "call",
            ("crm.lead", "search_read"),
            {
                "ids": None,
                "confirm": False,
                "domain": [
                    ("type", "=", "opportunity"),
                    ("team_id", "=", 3),
                    ("user_id", "=", 8),
                    ("stage_id", "=", 5),
                    ("active", "=", True),
                    "|",
                    ("name", "ilike", "Important"),
                    ("partner_name", "ilike", "Important"),
                ],
                "fields": [
                    "id",
                    "name",
                    "type",
                    "partner_id",
                    "partner_name",
                    "email_from",
                    "phone",
                    "stage_id",
                    "team_id",
                    "user_id",
                    "priority",
                    "probability",
                    "planned_revenue",
                    "expected_revenue",
                    "date_deadline",
                    "activity_state",
                    "active",
                ],
                "limit": 10,
                "offset": 2,
                "order": "priority desc, create_date desc",
            },
        )
    ]


@pytest.mark.asyncio
async def test_create_update_and_lifecycle_mutations_require_confirm(
    registered: tuple[FakeMCP, FakeOdooClient],
) -> None:
    mcp, client = registered

    with pytest.raises(OdooSafetyError):
        await mcp.tools["crm_create_lead"](name="Nope")
    with pytest.raises(OdooSafetyError):
        await mcp.tools["crm_update_lead"](lead_id=7, values={"name": "Updated"})
    with pytest.raises(OdooSafetyError):
        await mcp.tools["crm_mark_won"](lead_id=7)

    assert client.calls == []


@pytest.mark.asyncio
async def test_confirmed_create_and_update_use_json2_single_calls(
    registered: tuple[FakeMCP, FakeOdooClient],
) -> None:
    mcp, client = registered

    created = await mcp.tools["crm_create_lead"](
        name="New deal",
        kind="opportunity",
        partner_id=11,
        planned_revenue=9000.0,
        confirm=True,
    )
    updated = await mcp.tools["crm_update_lead"](
        lead_id=42, values={"probability": 80}, confirm=True
    )

    assert created == {"id": 42}
    assert updated == {"updated": True, "id": 42}
    assert client.calls == [
        (
            "call",
            ("crm.lead", "create"),
            {
                "ids": None,
                "confirm": True,
                "values": {
                    "name": "New deal",
                    "type": "opportunity",
                    "partner_id": 11,
                    "planned_revenue": 9000.0,
                }
            },
        ),
        (
            "call",
            ("crm.lead", "write"),
            {"ids": [42], "confirm": True, "values": {"probability": 80}},
        ),
    ]


@pytest.mark.asyncio
async def test_won_lost_conversion_merge_and_activity_use_model_methods(
    registered: tuple[FakeMCP, FakeOdooClient],
) -> None:
    mcp, client = registered

    await mcp.tools["crm_mark_won"](lead_id=7, confirm=True)
    await mcp.tools["crm_mark_lost"](lead_id=7, lost_reason_id=2, confirm=True)
    await mcp.tools["crm_restore_lead"](lead_id=7, confirm=True)
    await mcp.tools["crm_convert_lead_to_opportunity"](lead_id=7, partner_id=9, confirm=True)
    await mcp.tools["crm_merge_opportunities"](
        lead_ids=[7, 8], user_id=4, team_id=3, confirm=True
    )
    await mcp.tools["crm_schedule_activity"](
        lead_id=7,
        activity_type_id=1,
        summary="Follow up",
        date_deadline="2026-05-01",
        user_id=4,
        confirm=True,
    )
    await mcp.tools["crm_mark_activity_done"](activity_id=13, feedback="Done", confirm=True)

    assert client.calls == [
        ("call", ("crm.lead", "action_set_won"), {"ids": [7], "confirm": True}),
        (
            "call",
            ("crm.lead", "action_set_lost"),
            {"ids": [7], "confirm": True, "lost_reason_id": 2},
        ),
        ("call", ("crm.lead", "action_set_active"), {"ids": [7], "confirm": True}),
        (
            "call",
            ("crm.lead", "convert_opportunity"),
            {"ids": [7], "confirm": True, "partner_id": 9},
        ),
        (
            "call",
            ("crm.lead", "merge_opportunity"),
            {"ids": [7, 8], "confirm": True, "user_id": 4, "team_id": 3},
        ),
        (
            "call",
            ("mail.activity", "create"),
            {
                "ids": None,
                "confirm": True,
                "values": {
                    "res_model": "crm.lead",
                    "res_id": 7,
                    "activity_type_id": 1,
                    "summary": "Follow up",
                    "date_deadline": "2026-05-01",
                    "user_id": 4,
                }
            },
        ),
        (
            "call",
            ("mail.activity", "action_feedback"),
            {"ids": [13], "confirm": True, "feedback": "Done"},
        ),
    ]


@pytest.mark.asyncio
async def test_reports_use_read_group() -> None:
    mcp = FakeMCP()
    client = FakeOdooClient()
    register_crm_tools(mcp, client)

    pipeline = await mcp.tools["crm_pipeline_report"](groupby=["stage_id", "user_id"], active=True)
    activity = await mcp.tools["crm_activity_report"](team_id=3)

    assert pipeline == [{"stage_id": [1, "New"], "__count": 3}]
    assert activity == [{"stage_id": [1, "New"], "__count": 3}]
    assert client.calls == [
        (
            "call",
            ("crm.lead", "read_group"),
            {
                "ids": None,
                "confirm": False,
                "domain": [("type", "=", "opportunity"), ("active", "=", True)],
                "fields": ["planned_revenue:sum", "expected_revenue:sum", "probability:avg"],
                "groupby": ["stage_id", "user_id"],
                "limit": 80,
                "offset": 0,
            },
        ),
        (
            "call",
            ("mail.activity", "read_group"),
            {
                "ids": None,
                "confirm": False,
                "domain": [("res_model", "=", "crm.lead"), ("team_id", "=", 3)],
                "fields": ["id:count"],
                "groupby": ["activity_type_id", "state", "user_id"],
                "limit": 80,
                "offset": 0,
            },
        ),
    ]


def test_optional_feature_gated_tools_are_registered_only_when_enabled() -> None:
    base_mcp = FakeMCP()
    register_crm_tools(base_mcp, FakeOdooClient())

    enabled_mcp = FakeMCP()
    register_crm_tools(
        enabled_mcp,
        FakeOdooClient(),
        optional_features={"crm_iap_enrich", "crm_recurring_revenue"},
    )

    assert "crm_enrich_lead" not in base_mcp.tools
    assert "crm_recurring_revenue_report" not in base_mcp.tools
    assert "crm_enrich_lead" in enabled_mcp.tools
    assert "crm_recurring_revenue_report" in enabled_mcp.tools
