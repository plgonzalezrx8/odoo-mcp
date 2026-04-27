"""CRM FastMCP tool registrations for Odoo 19 JSON-2."""
# mypy: disable-error-code="no-any-return"

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable, Sequence
from typing import Any, Protocol

from odoo_mcp.exceptions import OdooSafetyError
from odoo_mcp.types import OdooDomain

CRM_LEAD_FIELDS = [
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
]

CRM_STAGE_FIELDS = ["id", "name", "sequence", "team_id", "fold", "is_won", "requirements"]
CRM_TEAM_FIELDS = ["id", "name", "active", "user_id", "member_ids", "alias_name", "use_leads"]
CRM_ACTIVITY_FIELDS = [
    "id",
    "res_model",
    "res_id",
    "activity_type_id",
    "summary",
    "date_deadline",
    "user_id",
    "state",
    "note",
]


class FastMCPLike(Protocol):
    def tool(
        self, *, name: str, description: str
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Register a callable as an MCP tool."""


class OdooClientLike(Protocol):
    def call(
        self,
        model: str,
        method: str,
        *,
        ids: list[int] | None = None,
        confirm: bool = False,
        **named_args: Any,
    ) -> Any:
        """Run an Odoo 19 JSON-2 model method call."""


def _confirm_mutation(confirm: bool) -> None:
    if not confirm:
        raise OdooSafetyError("CRM mutation requires confirm=True.")


def _ids(ids: int | Sequence[int]) -> list[int]:
    if isinstance(ids, int):
        return [ids]
    return list(ids)


def _compact(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


async def _json2_call(
    client: Any,
    model: str,
    method: str,
    *,
    ids: Sequence[int] | None = None,
    confirm: bool = False,
    **named_args: Any,
) -> Any:
    if hasattr(client, "call"):
        return await _maybe_await(
            client.call(
                model,
                method,
                ids=list(ids) if ids is not None else None,
                confirm=confirm,
                **_compact(named_args),
            )
        )

    if method == "search_read":
        return await _maybe_await(
            client.search_read(
                model,
                domain=named_args.get("domain"),
                fields=named_args.get("fields"),
                limit=named_args.get("limit"),
                offset=named_args.get("offset", 0),
                order=named_args.get("order"),
            )
        )
    if method == "create":
        return await _maybe_await(client.create(model, named_args["values"]))
    if method == "write":
        return await _maybe_await(client.write(model, list(ids or []), named_args["values"]))
    if method == "read_group":
        return await _maybe_await(
            client.read_group(
                model,
                domain=named_args.get("domain"),
                fields=named_args.get("fields"),
                groupby=named_args.get("groupby"),
                limit=named_args.get("limit"),
                offset=named_args.get("offset", 0),
                orderby=named_args.get("orderby"),
            )
        )
    return await _maybe_await(
        client.call_method(model, method, ids=list(ids or []), kwargs=named_args)
    )


def _append_if(domain: OdooDomain, field: str, value: Any) -> None:
    if value is not None:
        domain.append((field, "=", value))


def _lead_domain(
    *,
    kind: str | None = None,
    team_id: int | None = None,
    salesperson_id: int | None = None,
    stage_id: int | None = None,
    partner_id: int | None = None,
    active: bool | None = None,
    search: str | None = None,
) -> OdooDomain:
    domain: OdooDomain = []
    if kind and kind != "all":
        domain.append(("type", "=", kind))
    _append_if(domain, "team_id", team_id)
    _append_if(domain, "user_id", salesperson_id)
    _append_if(domain, "stage_id", stage_id)
    _append_if(domain, "partner_id", partner_id)
    _append_if(domain, "active", active)
    if search:
        domain.extend(["|", ("name", "ilike", search), ("partner_name", "ilike", search)])
    return domain


def _activity_domain(
    *,
    lead_id: int | None = None,
    user_id: int | None = None,
    team_id: int | None = None,
    state: str | None = None,
) -> OdooDomain:
    domain: OdooDomain = [("res_model", "=", "crm.lead")]
    _append_if(domain, "res_id", lead_id)
    _append_if(domain, "user_id", user_id)
    _append_if(domain, "team_id", team_id)
    _append_if(domain, "state", state)
    return domain


def _register(
    mcp: FastMCPLike,
    name: str,
    description: str,
    func: Callable[..., Any],
) -> None:
    mcp.tool(name=name, description=description)(func)


def register_crm_tools(
    mcp: FastMCPLike,
    client: OdooClientLike,
    *,
    optional_features: Iterable[str] | None = None,
) -> None:
    """Register CRM tools backed by a single injected Odoo JSON-2 client."""

    enabled_features = set(optional_features or ())

    async def crm_list_leads(
        *,
        kind: str | None = "all",
        team_id: int | None = None,
        salesperson_id: int | None = None,
        stage_id: int | None = None,
        partner_id: int | None = None,
        active: bool | None = True,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
        order: str = "priority desc, create_date desc",
    ) -> list[dict[str, Any]]:
        return await _json2_call(
            client,
            "crm.lead",
            "search_read",
            domain=_lead_domain(
                kind=kind,
                team_id=team_id,
                salesperson_id=salesperson_id,
                stage_id=stage_id,
                partner_id=partner_id,
                active=active,
                search=search,
            ),
            fields=CRM_LEAD_FIELDS,
            limit=limit,
            offset=offset,
            order=order,
        )

    async def crm_get_lead(lead_id: int) -> dict[str, Any] | None:
        rows = await _json2_call(
            client,
            "crm.lead",
            "search_read",
            domain=[("id", "=", lead_id)],
            fields=[
                *CRM_LEAD_FIELDS,
                "contact_name",
                "description",
                "campaign_id",
                "medium_id",
                "source_id",
                "lost_reason_id",
                "date_closed",
                "create_date",
                "write_date",
            ],
            limit=1,
            offset=0,
            order=None,
        )
        return rows[0] if rows else None

    async def crm_create_lead(
        *,
        name: str,
        kind: str = "lead",
        email_from: str | None = None,
        phone: str | None = None,
        partner_id: int | None = None,
        partner_name: str | None = None,
        contact_name: str | None = None,
        team_id: int | None = None,
        salesperson_id: int | None = None,
        stage_id: int | None = None,
        priority: str | None = None,
        probability: float | None = None,
        planned_revenue: float | None = None,
        date_deadline: str | None = None,
        description: str | None = None,
        confirm: bool = False,
    ) -> dict[str, int]:
        _confirm_mutation(confirm)
        lead_id = await _json2_call(
            client,
            "crm.lead",
            "create",
            values=_compact(
                {
                    "name": name,
                    "type": kind,
                    "email_from": email_from,
                    "phone": phone,
                    "partner_id": partner_id,
                    "partner_name": partner_name,
                    "contact_name": contact_name,
                    "team_id": team_id,
                    "user_id": salesperson_id,
                    "stage_id": stage_id,
                    "priority": priority,
                    "probability": probability,
                    "planned_revenue": planned_revenue,
                    "date_deadline": date_deadline,
                    "description": description,
                }
            ),
            confirm=True,
        )
        return {"id": lead_id}

    async def crm_update_lead(
        *, lead_id: int, values: dict[str, Any], confirm: bool = False
    ) -> dict[str, Any]:
        _confirm_mutation(confirm)
        await _json2_call(client, "crm.lead", "write", ids=[lead_id], values=values, confirm=True)
        return {"updated": True, "id": lead_id}

    async def crm_list_pipeline_stages(
        *, team_id: int | None = None, include_folded: bool = True
    ) -> list[dict[str, Any]]:
        domain: OdooDomain = []
        _append_if(domain, "team_id", team_id)
        if not include_folded:
            domain.append(("fold", "=", False))
        return await _json2_call(
            client,
            "crm.stage",
            "search_read",
            domain=domain,
            fields=CRM_STAGE_FIELDS,
            limit=100,
            offset=0,
            order="sequence asc, id asc",
        )

    async def crm_move_lead_to_stage(
        *, lead_id: int, stage_id: int, confirm: bool = False
    ) -> dict[str, Any]:
        _confirm_mutation(confirm)
        await _json2_call(
            client,
            "crm.lead",
            "write",
            ids=[lead_id],
            values={"stage_id": stage_id},
            confirm=True,
        )
        return {"updated": True, "id": lead_id, "stage_id": stage_id}

    async def crm_mark_won(*, lead_id: int, confirm: bool = False) -> Any:
        _confirm_mutation(confirm)
        return await _json2_call(client, "crm.lead", "action_set_won", ids=[lead_id], confirm=True)

    async def crm_mark_lost(
        *, lead_id: int, lost_reason_id: int | None = None, confirm: bool = False
    ) -> Any:
        _confirm_mutation(confirm)
        return await _json2_call(
            client,
            "crm.lead",
            "action_set_lost",
            ids=[lead_id],
            confirm=True,
            **_compact({"lost_reason_id": lost_reason_id}),
        )

    async def crm_restore_lead(*, lead_id: int, confirm: bool = False) -> Any:
        _confirm_mutation(confirm)
        return await _json2_call(
            client, "crm.lead", "action_set_active", ids=[lead_id], confirm=True
        )

    async def crm_convert_lead_to_opportunity(
        *,
        lead_id: int,
        partner_id: int | None = None,
        user_id: int | None = None,
        team_id: int | None = None,
        confirm: bool = False,
    ) -> Any:
        _confirm_mutation(confirm)
        return await _json2_call(
            client,
            "crm.lead",
            "convert_opportunity",
            ids=[lead_id],
            confirm=True,
            **_compact({"partner_id": partner_id, "user_id": user_id, "team_id": team_id}),
        )

    async def crm_merge_opportunities(
        *,
        lead_ids: Sequence[int],
        user_id: int | None = None,
        team_id: int | None = None,
        confirm: bool = False,
    ) -> Any:
        _confirm_mutation(confirm)
        return await _json2_call(
            client,
            "crm.lead",
            "merge_opportunity",
            ids=_ids(lead_ids),
            confirm=True,
            **_compact({"user_id": user_id, "team_id": team_id}),
        )

    async def crm_assign_lead(
        *, lead_id: int, user_id: int, team_id: int | None = None, confirm: bool = False
    ) -> dict[str, Any]:
        _confirm_mutation(confirm)
        values = _compact({"user_id": user_id, "team_id": team_id})
        await _json2_call(client, "crm.lead", "write", ids=[lead_id], values=values, confirm=True)
        return {"updated": True, "id": lead_id}

    async def crm_schedule_activity(
        *,
        lead_id: int,
        activity_type_id: int,
        summary: str,
        date_deadline: str,
        user_id: int | None = None,
        note: str | None = None,
        confirm: bool = False,
    ) -> dict[str, int]:
        _confirm_mutation(confirm)
        activity_id = await _json2_call(
            client,
            "mail.activity",
            "create",
            values=_compact(
                {
                    "res_model": "crm.lead",
                    "res_id": lead_id,
                    "activity_type_id": activity_type_id,
                    "summary": summary,
                    "date_deadline": date_deadline,
                    "user_id": user_id,
                    "note": note,
                }
            ),
            confirm=True,
        )
        return {"id": activity_id}

    async def crm_mark_activity_done(
        *, activity_id: int, feedback: str | None = None, confirm: bool = False
    ) -> Any:
        _confirm_mutation(confirm)
        return await _json2_call(
            client,
            "mail.activity",
            "action_feedback",
            ids=[activity_id],
            confirm=True,
            **_compact({"feedback": feedback}),
        )

    async def crm_list_activities(
        *,
        lead_id: int | None = None,
        user_id: int | None = None,
        team_id: int | None = None,
        state: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        return await _json2_call(
            client,
            "mail.activity",
            "search_read",
            domain=_activity_domain(lead_id=lead_id, user_id=user_id, team_id=team_id, state=state),
            fields=CRM_ACTIVITY_FIELDS,
            limit=limit,
            offset=offset,
            order="date_deadline asc, id asc",
        )

    async def crm_list_activity_types() -> list[dict[str, Any]]:
        return await _json2_call(
            client,
            "mail.activity.type",
            "search_read",
            domain=[("res_model", "in", ["crm.lead", False])],
            fields=["id", "name", "category", "delay_count", "delay_unit"],
            limit=100,
            offset=0,
            order="sequence asc, id asc",
        )

    async def crm_list_teams(*, active: bool | None = True) -> list[dict[str, Any]]:
        domain: OdooDomain = []
        _append_if(domain, "active", active)
        return await _json2_call(
            client,
            "crm.team",
            "search_read",
            domain=domain,
            fields=CRM_TEAM_FIELDS,
            limit=100,
            offset=0,
            order="name asc",
        )

    async def crm_update_lead_score(
        *, lead_id: int, probability: float, confirm: bool = False
    ) -> dict[str, Any]:
        _confirm_mutation(confirm)
        await _json2_call(
            client,
            "crm.lead",
            "write",
            ids=[lead_id],
            values={"probability": probability},
            confirm=True,
        )
        return {"updated": True, "id": lead_id, "probability": probability}

    async def crm_list_lost_reasons(*, active: bool | None = True) -> list[dict[str, Any]]:
        domain: OdooDomain = []
        _append_if(domain, "active", active)
        return await _json2_call(
            client,
            "crm.lost.reason",
            "search_read",
            domain=domain,
            fields=["id", "name", "active"],
            limit=100,
            offset=0,
            order="name asc",
        )

    async def crm_pipeline_report(
        *,
        groupby: Sequence[str] | None = None,
        team_id: int | None = None,
        salesperson_id: int | None = None,
        active: bool | None = True,
        limit: int = 80,
        offset: int = 0,
        orderby: str | None = None,
    ) -> list[dict[str, Any]]:
        return await _json2_call(
            client,
            "crm.lead",
            "read_group",
            domain=_lead_domain(
                kind="opportunity",
                team_id=team_id,
                salesperson_id=salesperson_id,
                active=active,
            ),
            fields=["planned_revenue:sum", "expected_revenue:sum", "probability:avg"],
            groupby=list(groupby or ["stage_id"]),
            limit=limit,
            offset=offset,
            orderby=orderby,
        )

    async def crm_activity_report(
        *,
        team_id: int | None = None,
        user_id: int | None = None,
        state: str | None = None,
        groupby: Sequence[str] | None = None,
        limit: int = 80,
        offset: int = 0,
        orderby: str | None = None,
    ) -> list[dict[str, Any]]:
        return await _json2_call(
            client,
            "mail.activity",
            "read_group",
            domain=_activity_domain(team_id=team_id, user_id=user_id, state=state),
            fields=["id:count"],
            groupby=list(groupby or ["activity_type_id", "state", "user_id"]),
            limit=limit,
            offset=offset,
            orderby=orderby,
        )

    _register(mcp, "crm_list_leads", "List CRM leads and opportunities.", crm_list_leads)
    _register(mcp, "crm_get_lead", "Get a single CRM lead or opportunity.", crm_get_lead)
    _register(mcp, "crm_create_lead", "Create a CRM lead or opportunity.", crm_create_lead)
    _register(mcp, "crm_update_lead", "Update CRM lead fields.", crm_update_lead)
    _register(
        mcp, "crm_list_pipeline_stages", "List CRM pipeline stages.", crm_list_pipeline_stages
    )
    _register(
        mcp, "crm_move_lead_to_stage", "Move a lead to a pipeline stage.", crm_move_lead_to_stage
    )
    _register(mcp, "crm_mark_won", "Mark an opportunity won.", crm_mark_won)
    _register(mcp, "crm_mark_lost", "Mark an opportunity lost.", crm_mark_lost)
    _register(mcp, "crm_restore_lead", "Restore an archived or lost lead.", crm_restore_lead)
    _register(
        mcp,
        "crm_convert_lead_to_opportunity",
        "Convert a lead into an opportunity.",
        crm_convert_lead_to_opportunity,
    )
    _register(mcp, "crm_merge_opportunities", "Merge CRM opportunities.", crm_merge_opportunities)
    _register(mcp, "crm_assign_lead", "Assign a CRM lead to a salesperson.", crm_assign_lead)
    _register(mcp, "crm_schedule_activity", "Schedule a CRM activity.", crm_schedule_activity)
    _register(mcp, "crm_mark_activity_done", "Mark a CRM activity done.", crm_mark_activity_done)
    _register(mcp, "crm_list_activities", "List CRM activities.", crm_list_activities)
    _register(mcp, "crm_list_activity_types", "List CRM activity types.", crm_list_activity_types)
    _register(mcp, "crm_list_teams", "List CRM sales teams.", crm_list_teams)
    _register(
        mcp, "crm_update_lead_score", "Update a lead probability score.", crm_update_lead_score
    )
    _register(mcp, "crm_list_lost_reasons", "List CRM lost reasons.", crm_list_lost_reasons)
    _register(mcp, "crm_pipeline_report", "Summarize CRM pipeline metrics.", crm_pipeline_report)
    _register(mcp, "crm_activity_report", "Summarize CRM activity metrics.", crm_activity_report)

    if "crm_iap_enrich" in enabled_features:

        async def crm_enrich_lead(*, lead_id: int, confirm: bool = False) -> Any:
            _confirm_mutation(confirm)
            return await _json2_call(client, "crm.lead", "iap_enrich", ids=[lead_id], confirm=True)

        _register(mcp, "crm_enrich_lead", "Enrich a lead through Odoo CRM IAP.", crm_enrich_lead)

    if "crm_predictive_lead_scoring" in enabled_features:

        async def crm_list_scoring_rules() -> list[dict[str, Any]]:
            return await _json2_call(
                client,
                "crm.lead.scoring.frequency",
                "search_read",
                domain=[],
                fields=["id", "variable", "value", "won_count", "lost_count", "team_id"],
                limit=200,
                offset=0,
                order="variable asc, value asc",
            )

        _register(
            mcp,
            "crm_list_scoring_rules",
            "List predictive lead scoring frequency rules.",
            crm_list_scoring_rules,
        )

    if "crm_recurring_revenue" in enabled_features:

        async def crm_recurring_revenue_report(
            *,
            team_id: int | None = None,
            salesperson_id: int | None = None,
            active: bool | None = True,
            limit: int = 80,
            offset: int = 0,
        ) -> list[dict[str, Any]]:
            return await _json2_call(
                client,
                "crm.lead",
                "read_group",
                domain=_lead_domain(
                    kind="opportunity",
                    team_id=team_id,
                    salesperson_id=salesperson_id,
                    active=active,
                ),
                fields=["recurring_revenue:sum", "recurring_revenue_monthly:sum"],
                groupby=["recurring_plan"],
                limit=limit,
                offset=offset,
                orderby=None,
            )

        _register(
            mcp,
            "crm_recurring_revenue_report",
            "Summarize optional recurring revenue CRM metrics.",
            crm_recurring_revenue_report,
        )
