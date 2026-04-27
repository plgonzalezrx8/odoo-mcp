"""Local safety policy for Odoo model method calls."""

from __future__ import annotations

from collections.abc import Collection

from odoo_mcp.exceptions import OdooSafetyError

READ_METHODS = frozenset(
    {
        "check_access_rights",
        "check_access_rule",
        "default_get",
        "fields_get",
        "name_get",
        "name_search",
        "onchange",
        "read",
        "read_group",
        "search",
        "search_count",
        "search_read",
        "web_read",
        "web_search_read",
    }
)
MUTATING_METHODS = frozenset(
    {
        "copy",
        "create",
        "flush",
        "load",
        "message_post",
        "toggle_active",
        "unlink",
        "write",
    }
)
MUTATING_PREFIXES = (
    "action_",
    "button_",
    "confirm_",
    "do_",
    "mark_",
    "post_",
    "send_",
    "set_",
    "toggle_",
    "validate_",
)
DANGEROUS_GENERIC_METHODS = frozenset({"call", "call_kw", "execute", "execute_kw", "run"})


def normalize_method_name(method: str) -> str:
    return method.strip()


def is_dangerous_generic_method(method: str) -> bool:
    return normalize_method_name(method).lower() in DANGEROUS_GENERIC_METHODS


def is_mutating_method(method: str) -> bool:
    normalized = normalize_method_name(method).lower()
    if normalized in READ_METHODS:
        return False
    if normalized in DANGEROUS_GENERIC_METHODS:
        return True
    return normalized in MUTATING_METHODS or normalized.startswith(MUTATING_PREFIXES)


def assert_method_allowed(
    method: str,
    *,
    confirm: bool,
    allowed_generic_methods: Collection[str] = frozenset(),
) -> None:
    """Raise if a method violates local safety policy."""

    normalized = normalize_method_name(method).lower()
    allowed_generic = {item.lower() for item in allowed_generic_methods}

    if normalized in DANGEROUS_GENERIC_METHODS and normalized not in allowed_generic:
        raise OdooSafetyError(
            f"Odoo method {method!r} is blocked by local safety policy; "
            "allowlist it only when the exact target behavior is known."
        )

    if is_mutating_method(normalized) and not confirm:
        raise OdooSafetyError(f"Odoo method {method!r} mutates data and requires confirm=True.")


def assert_write_allowed(*, confirm: bool, operation: str = "write") -> None:
    """Raise unless an explicit write confirmation was supplied."""

    if not confirm:
        raise OdooSafetyError(f"Odoo {operation} mutates data and requires confirm=True.")
