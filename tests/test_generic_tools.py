from __future__ import annotations

import pytest

from odoo_mcp.tools.generic import register_generic_tools


class FakeMCP:
    def __init__(self) -> None:
        self.tools: dict[str, object] = {}

    def tool(self, *, name: str, description: str | None = None):
        def decorator(func):
            self.tools[name] = func
            func.description = description
            return func

        return decorator


class FakeSafety:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def ensure_model_allowed(self, model: str) -> None:
        self.calls.append(("ensure_model_allowed", (model,)))

    def ensure_read_allowed(self, model: str, fields: list[str] | None = None) -> None:
        self.calls.append(("ensure_read_allowed", (model, fields)))

    def ensure_write_allowed(self, model: str, values: dict[str, object]) -> None:
        self.calls.append(("ensure_write_allowed", (model, values)))

    def ensure_unlink_allowed(self, model: str, ids: list[int]) -> None:
        self.calls.append(("ensure_unlink_allowed", (model, ids)))

    def ensure_action_allowed(self, action: str, model: str | None = None) -> None:
        self.calls.append(("ensure_action_allowed", (action, model)))

    def ensure_method_allowed(self, model: str, method: str) -> None:
        self.calls.append(("ensure_method_allowed", (model, method)))


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    async def search_read(self, model, domain, fields, limit, offset, order, context=None):
        self.calls.append(
            ("search_read", (model, domain, fields, limit, offset, order), {"context": context})
        )
        return [{"id": 7, "name": "Acme"}]

    async def read(self, model, ids, fields=None, context=None):
        self.calls.append(("read", (model, ids, fields), {"context": context}))
        return [{"id": ids[0], "name": "Acme"}]

    async def create(self, model, values, context=None):
        self.calls.append(("create", (model, values), {"context": context}))
        return 42

    async def write(self, model, ids, values, context=None):
        self.calls.append(("write", (model, ids, values), {"context": context}))
        return True

    async def unlink(self, model, ids, context=None):
        self.calls.append(("unlink", (model, ids), {"context": context}))
        return True

    async def action(self, action, *, model=None, record_ids=None, context=None):
        self.calls.append(
            ("action", (action,), {"model": model, "record_ids": record_ids, "context": context})
        )
        return {"type": "ir.actions.act_window", "name": action}

    async def call_method(self, model, method, args=None, kwargs=None, context=None):
        self.calls.append(
            ("call_method", (model, method), {"args": args, "kwargs": kwargs, "context": context})
        )
        return {"ok": True}

    async def current_user(self, context=None):
        self.calls.append(("current_user", (), {"context": context}))
        return {"id": 2, "name": "Demo"}

    async def model_fields(self, model, attributes=None, context=None):
        self.calls.append(("model_fields", (model, attributes), {"context": context}))
        return {"name": {"type": "char", "string": "Name"}}

    async def list_models(self, *, search=None, limit=200, context=None):
        self.calls.append(
            ("list_models", (), {"search": search, "limit": limit, "context": context})
        )
        return [{"model": "res.partner", "name": "Contact"}]


def test_registers_expected_generic_tools() -> None:
    mcp = FakeMCP()

    register_generic_tools(mcp, client=FakeClient(), safety=FakeSafety())

    assert set(mcp.tools) == {
        "odoo_search_read",
        "odoo_read",
        "odoo_create",
        "odoo_write",
        "odoo_unlink",
        "odoo_action",
        "odoo_call_method",
        "odoo_current_user",
        "odoo_model_fields",
        "odoo_list_models",
    }


@pytest.mark.asyncio
async def test_search_read_normalizes_defaults_and_checks_safety() -> None:
    mcp = FakeMCP()
    client = FakeClient()
    safety = FakeSafety()
    register_generic_tools(mcp, client=client, safety=safety)

    result = await mcp.tools["odoo_search_read"](
        "res.partner", fields=["name"], context={"lang": "en_US"}
    )

    assert result == [{"id": 7, "name": "Acme"}]
    assert safety.calls == [
        ("ensure_model_allowed", ("res.partner",)),
        ("ensure_read_allowed", ("res.partner", ["name"])),
    ]
    assert client.calls == [
        (
            "search_read",
            ("res.partner", [], ["name"], 80, 0, None),
            {"context": {"lang": "en_US"}},
        )
    ]


@pytest.mark.asyncio
async def test_write_create_unlink_and_method_tools_delegate_with_safety() -> None:
    mcp = FakeMCP()
    client = FakeClient()
    safety = FakeSafety()
    register_generic_tools(mcp, client=client, safety=safety)

    assert await mcp.tools["odoo_create"]("res.partner", {"name": "Acme"}) == 42
    assert await mcp.tools["odoo_write"]("res.partner", [42], {"phone": "555"}) is True
    assert await mcp.tools["odoo_unlink"]("res.partner", [42]) is True
    assert await mcp.tools["odoo_call_method"]("res.partner", "name_get", args=[[42]]) == {
        "ok": True
    }

    assert safety.calls == [
        ("ensure_model_allowed", ("res.partner",)),
        ("ensure_write_allowed", ("res.partner", {"name": "Acme"})),
        ("ensure_model_allowed", ("res.partner",)),
        ("ensure_write_allowed", ("res.partner", {"phone": "555"})),
        ("ensure_model_allowed", ("res.partner",)),
        ("ensure_unlink_allowed", ("res.partner", [42])),
        ("ensure_model_allowed", ("res.partner",)),
        ("ensure_method_allowed", ("res.partner", "name_get")),
    ]


@pytest.mark.asyncio
async def test_action_current_user_fields_and_models_delegate() -> None:
    mcp = FakeMCP()
    client = FakeClient()
    safety = FakeSafety()
    register_generic_tools(mcp, client=client, safety=safety)

    assert await mcp.tools["odoo_action"]("crm.crm_lead_action_pipeline", model="crm.lead") == {
        "type": "ir.actions.act_window",
        "name": "crm.crm_lead_action_pipeline",
    }
    assert await mcp.tools["odoo_current_user"]() == {"id": 2, "name": "Demo"}
    assert await mcp.tools["odoo_model_fields"]("res.partner") == {
        "name": {"type": "char", "string": "Name"}
    }
    assert await mcp.tools["odoo_list_models"](search="partner", limit=5) == [
        {"model": "res.partner", "name": "Contact"}
    ]

    assert ("ensure_action_allowed", ("crm.crm_lead_action_pipeline", "crm.lead")) in safety.calls
    assert ("ensure_read_allowed", ("res.partner", None)) in safety.calls
