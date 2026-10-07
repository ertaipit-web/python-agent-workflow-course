from __future__ import annotations

import io
import json
import time
from collections.abc import Iterator
from http.client import HTTPConnection
from pathlib import Path
from typing import Self
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pytest

from integration_lab.client import IssueApiClient
from integration_lab.errors import (
    AuthenticationError,
    NotFoundError,
    PermissionDeniedError,
    ServerError,
    TransportTimeoutError,
    WriteOutcomeUnknownError,
)
from integration_lab.issue_api import SCOPE_READ, SCOPE_WRITE, FaultPlan, IssueApi, Token

OWNER = "course"
REPOSITORY = "taskboard"
READ_TOKEN = Token(name="read-only", scopes=frozenset({SCOPE_READ}))
WRITE_TOKEN = Token(name="read-write", scopes=frozenset({SCOPE_READ, SCOPE_WRITE}))


@pytest.fixture
def api(tmp_path: Path) -> Iterator[IssueApi]:
    instance = IssueApi(
        database=tmp_path / "issues.db",
        tokens=(READ_TOKEN, WRITE_TOKEN),
    )
    instance.store.create_issue(OWNER, REPOSITORY, title="Filter ignores case", body="", labels=("bug",))
    instance.store.create_issue(OWNER, REPOSITORY, title="Document statuses", body="", labels=("docs",))
    instance.store.create_issue(OWNER, REPOSITORY, title="Old issue", body="", labels=())
    instance.store.set_state(OWNER, REPOSITORY, 3, "closed")
    instance.start()
    try:
        yield instance
    finally:
        instance.close()


@pytest.fixture
def client(api: IssueApi) -> Iterator[IssueApiClient]:
    instance = IssueApiClient(api.base_url, "read-write", timeout=2.0)
    try:
        yield instance
    finally:
        del instance


def _wait_for_issues(api: IssueApi, expected: int, *, timeout: float = 3.0) -> int:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if api.store.count() == expected:
            return expected
        time.sleep(0.02)
    return api.store.count()


def raw_request(
    api: IssueApi,
    method: str,
    path: str,
    *,
    token: str | None = "read-write",
    body: dict[str, object] | None = None,
) -> tuple[int, dict[str, object]]:
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    request = Request(f"{api.base_url}{path}", data=payload, method=method)
    if token is not None:
        request.add_header("Authorization", f"Bearer {token}")
    if payload is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urlopen(request, timeout=2) as response:
            return response.status, json.loads(response.read() or b"{}")
    except HTTPError as error:
        return error.code, json.loads(error.read() or b"{}")


def test_client_validates_its_configuration(api: IssueApi) -> None:
    with pytest.raises(ValueError, match="http or https"):
        IssueApiClient("localhost:8765", "token")
    with pytest.raises(ValueError, match="token must not be empty"):
        IssueApiClient(api.base_url, " ")
    with pytest.raises(ValueError, match="timeout must be positive"):
        IssueApiClient(api.base_url, "read-write", timeout=0)
    with pytest.raises(ValueError, match="max_attempts"):
        IssueApiClient(api.base_url, "read-write", max_attempts=0)


def test_client_validates_arguments_before_any_request(api: IssueApi) -> None:
    instance = IssueApiClient(api.base_url, "read-write")

    with pytest.raises(ValueError, match="limit must be between"):
        instance.list_issues(OWNER, REPOSITORY, limit=0)
    with pytest.raises(ValueError, match="state must be"):
        instance.list_issues(OWNER, REPOSITORY, state="deleted")
    with pytest.raises(ValueError, match="number must be positive"):
        instance.get_issue(OWNER, REPOSITORY, 0)
    with pytest.raises(ValueError, match="title must not be empty"):
        instance.create_issue(OWNER, REPOSITORY, title="   ")
    with pytest.raises(ValueError, match="title must be at most"):
        instance.create_issue(OWNER, REPOSITORY, title="x" * 201)

    assert instance.call_count == 0


def test_client_lists_and_filters_issues(client: IssueApiClient) -> None:
    issues = client.list_issues(OWNER, REPOSITORY, state="open")
    closed = client.list_issues(OWNER, REPOSITORY, state="closed")
    every = client.list_issues(OWNER, REPOSITORY, state="all", limit=3)

    assert [issue["title"] for issue in issues] == ["Filter ignores case", "Document statuses"]
    assert [issue["title"] for issue in closed] == ["Old issue"]
    assert len(every) == 3
    assert every[0]["url"] == f"/repos/{OWNER}/{REPOSITORY}/issues/1"
    assert every[0]["labels"] == ["bug"]


def test_client_creates_an_issue_with_a_stable_shape(client: IssueApiClient, api: IssueApi) -> None:
    created = client.create_issue(
        OWNER, REPOSITORY, title="Triage", body="details", labels=["bug", "triage"]
    )

    assert created["number"] == 4
    assert created["state"] == "open"
    assert created["labels"] == ["bug", "triage"]
    assert client.get_issue(OWNER, REPOSITORY, 4)["title"] == "Triage"
    assert api.store.count() == 4


def test_client_maps_missing_issue_to_a_typed_error(client: IssueApiClient) -> None:
    with pytest.raises(NotFoundError):
        client.get_issue(OWNER, REPOSITORY, 999)


def test_client_maps_missing_scope_to_a_permission_error(api: IssueApi) -> None:
    read_only = IssueApiClient(api.base_url, "read-only")

    with pytest.raises(PermissionDeniedError, match="issues:write"):
        read_only.create_issue(OWNER, REPOSITORY, title="Not allowed")


def test_client_rejects_an_unknown_token(api: IssueApi) -> None:
    with pytest.raises(AuthenticationError, match="not known"):
        IssueApiClient(api.base_url, "made-up").list_issues(OWNER, REPOSITORY)


def test_service_requires_a_bearer_token(api: IssueApi) -> None:
    status, payload = raw_request(api, "GET", f"/repos/{OWNER}/{REPOSITORY}/issues", token=None)

    assert status == 401
    assert payload["error"] == {
        "code": "authentication_required",
        "message": "Provide an Authorization: Bearer header",
    }


def test_service_answers_an_unknown_route_with_a_typed_error(api: IssueApi) -> None:
    status, payload = raw_request(api, "GET", "/repos/course/taskboard/wiki")

    assert status == 404
    assert payload["error"]["code"] == "not_found"


def test_service_rejects_an_invalid_title_with_a_predictable_error(api: IssueApi) -> None:
    status, payload = raw_request(
        api, "POST", f"/repos/{OWNER}/{REPOSITORY}/issues", body={"title": "   "}
    )

    assert status == 422
    assert payload["error"] == {"code": "invalid_title", "message": "title is required"}


def test_service_rejects_a_malformed_body(api: IssueApi) -> None:
    payload = json.dumps({"title": "x", "labels": "bug"}).encode("utf-8")
    request = Request(
        f"{api.base_url}/repos/{OWNER}/{REPOSITORY}/issues",
        data=payload,
        method="POST",
        headers={"Authorization": "Bearer read-write", "Content-Type": "application/json"},
    )

    with pytest.raises(HTTPError) as error:
        urlopen(request, timeout=2)

    assert error.value.code == 422
    assert json.loads(error.value.read())["error"]["code"] == "invalid_labels"


def test_service_rejects_a_non_numeric_content_length(api: IssueApi) -> None:
    status, payload = _raw_request_with_content_length(
        api, "abc", f"/repos/{OWNER}/{REPOSITORY}/issues"
    )

    assert status == 400
    assert payload["error"]["code"] == "invalid_content_length"


def test_service_rejects_a_negative_content_length(api: IssueApi) -> None:
    status, payload = _raw_request_with_content_length(
        api, "-5", f"/repos/{OWNER}/{REPOSITORY}/issues"
    )

    assert status == 413
    assert payload["error"]["code"] == "payload_too_large"


def test_service_rejects_an_out_of_range_issue_number(api: IssueApi) -> None:
    status, payload = raw_request(
        api, "GET", f"/repos/{OWNER}/{REPOSITORY}/issues/{'9' * 40}"
    )

    assert status == 404
    assert payload["error"]["code"] == "not_found"


def _raw_request_with_content_length(
    api: IssueApi, content_length: str, path: str
) -> tuple[int, dict[str, object]]:
    connection = HTTPConnection(*api.base_url.removeprefix("http://").split(":"))
    connection.putrequest("POST", path, skip_accept_encoding=True)
    connection.putheader("Authorization", "Bearer read-write")
    connection.putheader("Content-Length", content_length)
    connection.endheaders()
    response = connection.getresponse()
    payload = json.loads(response.read() or b"{}")
    connection.close()
    return response.status, payload


def test_api_can_be_restarted_after_stop(api: IssueApi) -> None:
    api.stop()
    base_url = api.start(port=0)

    client = IssueApiClient(base_url, "read-write", timeout=2.0)

    assert [issue["title"] for issue in client.list_issues(OWNER, REPOSITORY)] == [
        "Filter ignores case",
        "Document statuses",
    ]
    assert client.create_issue(OWNER, REPOSITORY, title="After restart")["number"] == 4


def test_write_is_not_retried_after_a_connection_reset(api: IssueApi, monkeypatch) -> None:
    def broken_urlopen(request: Request, timeout: float) -> None:
        raise URLError(ConnectionResetError("peer closed the connection"))

    monkeypatch.setattr("integration_lab.client.urlopen", broken_urlopen)
    client = IssueApiClient(api.base_url, "read-write", timeout=2.0, max_attempts=3)

    with pytest.raises(WriteOutcomeUnknownError):
        client.create_issue(OWNER, REPOSITORY, title="Must not be sent twice")

    assert client.call_count == 1
    assert api.store.count() == 3


def test_read_is_retried_after_a_connection_reset(api: IssueApi, monkeypatch) -> None:
    attempts: list[str] = []

    class Response:
        def read(self) -> bytes:
            return b'{"total_count": 2, "issues": []}'

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *arguments: object) -> None:
            return None

    def flaky_urlopen(request: Request, timeout: float) -> Response:
        attempts.append(request.get_method())
        if len(attempts) == 1:
            raise URLError(ConnectionResetError("peer closed the connection"))
        return Response()

    monkeypatch.setattr("integration_lab.client.urlopen", flaky_urlopen)
    client = IssueApiClient(api.base_url, "read-write", timeout=2.0, max_attempts=2)

    assert client.list_issues(OWNER, REPOSITORY) == []
    assert attempts == ["GET", "GET"]


def test_idempotent_read_retries_429_and_eventually_succeeds(monkeypatch) -> None:
    attempts = 0

    class Response:
        def read(self) -> bytes:
            return b'{"issues": []}'

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *arguments: object) -> None:
            return None

    def flaky_urlopen(request: Request, timeout: float) -> Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise HTTPError(
                request.full_url,
                429,
                "rate limited",
                {},
                io.BytesIO(b'{"error":{"code":"rate_limited","message":"try later"}}'),
            )
        return Response()

    monkeypatch.setattr("integration_lab.client.urlopen", flaky_urlopen)
    client = IssueApiClient("http://example.com", "read-write", max_retries=1, backoff_base=0.01)

    assert client.list_issues("owner", "repo") == []
    assert attempts == 2


def test_idempotent_read_stops_after_429_retry_budget(monkeypatch) -> None:
    def rate_limited_urlopen(request: Request, timeout: float) -> None:
        raise HTTPError(
            request.full_url,
            429,
            "rate limited",
            {},
            io.BytesIO(b'{"error":{"code":"rate_limited","message":"try later"}}'),
        )

    monkeypatch.setattr("integration_lab.client.urlopen", rate_limited_urlopen)
    client = IssueApiClient("http://example.com", "read-write", max_retries=1, backoff_base=0.01)

    with pytest.raises(ServerError) as error:
        client.list_issues("owner", "repo")

    assert error.value.attempts == 2


def test_write_429_does_not_retry(monkeypatch) -> None:
    attempts = 0

    def rate_limited_urlopen(request: Request, timeout: float) -> None:
        nonlocal attempts
        attempts += 1
        raise HTTPError(
            request.full_url,
            429,
            "rate limited",
            {},
            io.BytesIO(b'{"error":{"code":"rate_limited","message":"try later"}}'),
        )

    monkeypatch.setattr("integration_lab.client.urlopen", rate_limited_urlopen)
    client = IssueApiClient("http://example.com", "read-write", max_retries=3, backoff_base=0.01)

    with pytest.raises(ServerError):
        client.create_issue("owner", "repo", title="test")

    assert attempts == 1


def test_client_retries_a_failing_read_only_once(tmp_path: Path) -> None:
    api = IssueApi(
        database=tmp_path / "flaky.db",
        tokens=(WRITE_TOKEN,),
        faults=FaultPlan(fail_reads=1),
    )
    api.store.create_issue(OWNER, REPOSITORY, title="Retry me", body="", labels=())
    api.start()
    try:
        client = IssueApiClient(api.base_url, "read-write", timeout=2.0, max_attempts=2)
        issues = client.list_issues(OWNER, REPOSITORY)
        assert [issue["title"] for issue in issues] == ["Retry me"]
        assert client.call_count == 2
    finally:
        api.stop()


def test_client_gives_up_after_the_retry_budget(tmp_path: Path) -> None:
    api = IssueApi(
        database=tmp_path / "down.db",
        tokens=(WRITE_TOKEN,),
        faults=FaultPlan(fail_reads=5),
    )
    api.start()
    try:
        client = IssueApiClient(api.base_url, "read-write", timeout=2.0, max_attempts=2)
        with pytest.raises(ServerError) as error:
            client.list_issues(OWNER, REPOSITORY)
        assert error.value.attempts == 2
        assert client.call_count == 2
    finally:
        api.stop()


def test_client_reports_a_read_timeout(tmp_path: Path) -> None:
    api = IssueApi(
        database=tmp_path / "slow.db",
        tokens=(WRITE_TOKEN,),
        faults=FaultPlan(read_delay_seconds=0.4),
    )
    api.start()
    try:
        client = IssueApiClient(api.base_url, "read-write", timeout=0.1, max_attempts=1)
        with pytest.raises(TransportTimeoutError):
            client.list_issues(OWNER, REPOSITORY)
    finally:
        api.stop()


def test_write_timeout_is_reported_as_an_unknown_outcome(tmp_path: Path) -> None:
    api = IssueApi(
        database=tmp_path / "slow-write.db",
        tokens=(WRITE_TOKEN,),
        faults=FaultPlan(write_delay_seconds=0.4),
    )
    api.start()
    try:
        client = IssueApiClient(api.base_url, "read-write", timeout=0.1, max_attempts=3)
        with pytest.raises(WriteOutcomeUnknownError) as error:
            client.create_issue(OWNER, REPOSITORY, title="Timed out")
        assert error.value.effect_may_have_applied is True
        assert client.call_count == 1

        assert _wait_for_issues(api, 1) == 1

        retry = IssueApiClient(api.base_url, "read-write", timeout=2.0)
        duplicate = retry.create_issue(OWNER, REPOSITORY, title="Timed out")

        assert duplicate["number"] == 2
        assert [issue["title"] for issue in retry.list_issues(OWNER, REPOSITORY)] == [
            "Timed out",
            "Timed out",
        ]
    finally:
        api.stop()
