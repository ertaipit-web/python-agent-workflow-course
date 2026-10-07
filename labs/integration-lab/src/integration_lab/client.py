from __future__ import annotations

import json
import random
import socket
import time
from collections.abc import Sequence
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from integration_lab.errors import (
    AuthenticationError,
    NotFoundError,
    PermissionDeniedError,
    ServerError,
    TransportTimeoutError,
    ValidationRejectedError,
    WriteOutcomeUnknownError,
)

DEFAULT_TIMEOUT_SECONDS = 2.0
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BACKOFF_BASE_SECONDS = 0.5
DEFAULT_BACKOFF_MAX_SECONDS = 4.0
MAX_TITLE_CHARACTERS = 200


class IssueApiClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        backoff_base: float = DEFAULT_BACKOFF_BASE_SECONDS,
        backoff_max: float = DEFAULT_BACKOFF_MAX_SECONDS,
    ) -> None:
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("base_url must be an http or https URL")
        if not token.strip():
            raise ValueError("token must not be empty")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if backoff_base <= 0:
            raise ValueError("backoff_base must be positive")
        if backoff_max < backoff_base:
            raise ValueError("backoff_max must be >= backoff_base")
        self.base_url = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout
        self._max_attempts = max_attempts
        self._backoff_base = backoff_base
        self._backoff_max = backoff_max
        self.call_count = 0

    def list_issues(
        self, owner: str, repository: str, *, state: str = "open", limit: int = 10
    ) -> list[dict[str, Any]]:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if state not in {"open", "closed", "all"}:
            raise ValueError("state must be open, closed or all")
        payload = self._request(
            "GET",
            f"/repos/{owner}/{repository}/issues?state={state}&limit={limit}",
            idempotent=True,
        )
        return list(payload.get("issues", []))

    def get_issue(self, owner: str, repository: str, number: int) -> dict[str, Any]:
        if number < 1:
            raise ValueError("number must be positive")
        return self._request(
            "GET", f"/repos/{owner}/{repository}/issues/{number}", idempotent=True
        )

    def create_issue(
        self,
        owner: str,
        repository: str,
        *,
        title: str,
        body: str = "",
        labels: Sequence[str] = (),
    ) -> dict[str, Any]:
        title = title.strip()
        if not title:
            raise ValueError("title must not be empty")
        if len(title) > MAX_TITLE_CHARACTERS:
            raise ValueError(f"title must be at most {MAX_TITLE_CHARACTERS} characters")
        return self._request(
            "POST",
            f"/repos/{owner}/{repository}/issues",
            payload={"title": title, "body": body, "labels": list(labels)},
            idempotent=False,
        )

    def close_issue(self, owner: str, repository: str, number: int) -> dict[str, Any]:
        if number < 1:
            raise ValueError("number must be positive")
        return self._request(
            "PATCH",
            f"/repos/{owner}/{repository}/issues/{number}",
            payload={"state": "closed"},
            idempotent=False,
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        idempotent: bool,
    ) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        for attempt in range(1, self._max_attempts + 1):
            request = Request(f"{self.base_url}{path}", data=body, method=method)
            request.add_header("Authorization", f"Bearer {self._token}")
            request.add_header("Accept", "application/json")
            if body is not None:
                request.add_header("Content-Type", "application/json")
            self.call_count += 1
            try:
                with urlopen(request, timeout=self._timeout) as response:
                    return json.loads(response.read() or b"{}")
            except HTTPError as error:
                mapped = _map_http_error(error, attempts=attempt)
                if isinstance(mapped, ServerError) and idempotent and attempt < self._max_attempts:
                    time.sleep(self._backoff(attempt))
                    continue
                raise mapped from None
            except TimeoutError as error:
                if not idempotent:
                    raise WriteOutcomeUnknownError(
                        f"{method} {path} timed out after the request was sent"
                    ) from error
                if attempt == self._max_attempts:
                    raise TransportTimeoutError(f"{method} {path} timed out") from error
                time.sleep(self._backoff(attempt))
            except URLError as error:
                if isinstance(error.reason, (TimeoutError, socket.timeout)):
                    if not idempotent:
                        raise WriteOutcomeUnknownError(
                            f"{method} {path} timed out after the request was sent"
                        ) from error
                    if attempt == self._max_attempts:
                        raise TransportTimeoutError(f"{method} {path} timed out") from error
                    time.sleep(self._backoff(attempt))
                elif not idempotent:
                    raise WriteOutcomeUnknownError(
                        f"{method} {path} lost the connection after the request was sent"
                    ) from error
                elif attempt < self._max_attempts:
                    time.sleep(self._backoff(attempt))
                else:
                    raise ServerError(f"{method} {path} failed: {error.reason}", attempts=attempt)
        raise ServerError(f"{method} {path} failed", attempts=self._max_attempts)

    def _backoff(self, attempt: int) -> float:
        """Exponential backoff with bounded jitter, capped at backoff_max.

        delay = min(backoff_base * 2^(attempt-1), backoff_max)
        jittered = delay * uniform(0.5, 1.0)

        The jitter prevents synchronized retries when multiple clients hit
        the same rate limit. Bounded so tests can assert a range, not an exact value.
        """
        delay = min(self._backoff_base * (2 ** (attempt - 1)), self._backoff_max)
        return delay * random.uniform(0.5, 1.0)


def _map_http_error(error: HTTPError, *, attempts: int) -> Exception:
    status = error.code
    code, message = _error_details(error)
    if status == 401:
        return AuthenticationError(message or "authentication failed")
    if status == 403:
        return PermissionDeniedError(message or "the token lacks the required scope")
    if status == 404:
        return NotFoundError(message or "resource not found")
    if status in {400, 409, 413, 422}:
        return ValidationRejectedError(message or f"the service rejected the request ({code})")
    if status >= 500:
        return ServerError(message or f"the service failed with status {status}", attempts=attempts)
    return ValidationRejectedError(message or f"unexpected status {status}")


def _error_details(error: HTTPError) -> tuple[str, str]:
    try:
        payload = json.loads(error.read() or b"{}")
    except json.JSONDecodeError:
        return "", ""
    if not isinstance(payload, dict):
        return "", ""
    detail = payload.get("error", {})
    if not isinstance(detail, dict):
        return "", ""
    return str(detail.get("code", "")), str(detail.get("message", ""))