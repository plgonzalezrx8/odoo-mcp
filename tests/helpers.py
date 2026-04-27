from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any


class RecordingOdooClient:
    def __init__(self, response: Any | None = None) -> None:
        self.response = response if response is not None else []
        self.calls: list[dict[str, Any]] = []

    async def call(
        self,
        model: str,
        method: str,
        *,
        ids: list[int] | None = None,
        context: dict[str, Any] | None = None,
        **params: Any,
    ) -> Any:
        self.calls.append(
            {
                "model": model,
                "method": method,
                "ids": ids,
                "context": context,
                "params": params,
            }
        )
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


ToolInvoker = Callable[..., Awaitable[Any]]
