"""Shared JSON and Odoo type aliases."""

from __future__ import annotations

from typing import Any, TypeAlias

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]
OdooDomain: TypeAlias = list[Any]
