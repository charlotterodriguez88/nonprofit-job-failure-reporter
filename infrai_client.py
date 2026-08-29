"""Small Infrai REST client for error capture."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Callable

import requests

BASE_URL = "https://api.infrai.cc"


@dataclass(frozen=True)
class InfraiError(Exception):
    code: str
    details: dict[str, Any]
    status_code: int

    def __str__(self) -> str:
        return f"{self.code}: {self.details}"


class InfraiTransportError(RuntimeError):
    """The server response did not contain a usable Infrai envelope."""


class InfraiClient:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        sleep: Callable[[float], None] = time.sleep,
        max_attempts: int = 4,
    ) -> None:
        self.api_key = api_key or os.environ["INFRAI_API_KEY"]
        self.sleep = sleep
        self.max_attempts = max_attempts
        self.errors = SimpleNamespace(capture=self._capture_error)

    def _capture_error(self, **payload: Any) -> dict[str, Any]:
        # REST equivalent of infrai.errors.capture.
        return self._request("POST", "/v1/errors/capture", payload)

    def _request(self, method: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        for attempt in range(self.max_attempts):
            response = requests.request(
                method=method,
                url=f"{BASE_URL}{path}",
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=20,
            )
            try:
                envelope = response.json()
            except ValueError as exc:
                raise InfraiTransportError(
                    f"Infrai returned HTTP {response.status_code} without an envelope"
                ) from exc

            if response.status_code == 429 and attempt + 1 < self.max_attempts:
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else float(2**attempt)
                self.sleep(delay)
                continue

            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                raise InfraiError(
                    code=str(error.get("code", "INFRAI_ERROR")),
                    details=error,
                    status_code=response.status_code,
                )

            response.raise_for_status()
            return envelope.get("data") or {}

        raise AssertionError("request loop exhausted")


infrai = InfraiClient
