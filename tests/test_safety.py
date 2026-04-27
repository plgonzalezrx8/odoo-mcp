from __future__ import annotations

import pytest

from odoo_mcp.exceptions import OdooSafetyError
from odoo_mcp.safety import assert_method_allowed, assert_write_allowed, is_mutating_method


@pytest.mark.parametrize(
    "method",
    ["search", "search_read", "read", "fields_get", "name_search", "search_count"],
)
def test_read_methods_are_not_mutating(method: str) -> None:
    assert is_mutating_method(method) is False
    assert_method_allowed(method, confirm=False)


@pytest.mark.parametrize(
    "method",
    ["create", "write", "unlink", "action_confirm", "button_validate"],
)
def test_mutating_methods_require_confirmation(method: str) -> None:
    assert is_mutating_method(method) is True

    with pytest.raises(OdooSafetyError) as exc_info:
        assert_method_allowed(method, confirm=False)

    assert "confirm=True" in str(exc_info.value)


@pytest.mark.parametrize(
    "method",
    ["call", "call_kw", "execute", "execute_kw", "run"],
)
def test_dangerous_generic_methods_are_blocked_even_with_confirmation(method: str) -> None:
    with pytest.raises(OdooSafetyError) as exc_info:
        assert_method_allowed(method, confirm=True)

    assert "blocked" in str(exc_info.value)


def test_allowlisted_generic_method_still_requires_confirmation() -> None:
    with pytest.raises(OdooSafetyError):
        assert_method_allowed("call_kw", confirm=False, allowed_generic_methods={"call_kw"})

    assert_method_allowed("call_kw", confirm=True, allowed_generic_methods={"call_kw"})


def test_write_guard_requires_confirmation() -> None:
    with pytest.raises(OdooSafetyError):
        assert_write_allowed(confirm=False, operation="bulk update")

    assert_write_allowed(confirm=True, operation="bulk update")
