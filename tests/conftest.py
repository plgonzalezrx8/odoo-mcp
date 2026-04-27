from __future__ import annotations

import os
from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def clean_odoo_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for key in list(os.environ):
        if key.startswith(("ODOO_", "MCP_", "JWT_")):
            monkeypatch.delenv(key, raising=False)
    yield
