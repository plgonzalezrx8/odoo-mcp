"""Shared JSON and Odoo type aliases."""

from __future__ import annotations

from typing import Any

type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]
type OdooDomain = list[Any]
