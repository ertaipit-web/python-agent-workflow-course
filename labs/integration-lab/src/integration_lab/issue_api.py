from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

SCOPE_READ = "issues:read"
SCOPE_WRITE = "issues:write"

_ISSUES_PATH = re.compile(r"^/repos/(?P<owner>[^/]+)/(?P<repository>[^/]+)/issues$")
_ISSUE_PATH = re.compile(r"^/repos/(?P<owner>[^/]+)/(?P<repository>[^/]+)/issues/(?P<number>\d{1,9})$")
_REPOSITORY_PATH = re.compile(r"^/repos/(?P<owner>[^/]+)/(?P<repository>[^/]+)$")
_MAX_BODY_CHARACTERS = 8_000
_MAX_TITLE_CHARACTERS = 200


@dataclass(frozen=True)
class Token:
    name: str
    scopes: frozenset[str]


@dataclass(frozen=True)
class FaultPlan:
    fail_reads: int = 0
    fail_writes: int = 0
    read_delay_seconds: float = 0.0
    write_delay_seconds: float = 0.0


@dataclass
class IssueStore:
    database: str | Path = ":memory:"
    _connection: sqlite3.Connection = field(init=False, repr=False)
    _lock: threading.Lock = field(init=False, repr=False)
    _closed: bool = field(init=False, default=False, repr=False)

    def __post_init__(self) -> None:
        self._connection = sqlite3.connect(self.database, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS issues (
                number INTEGER PRIMARY KEY AUTOINCREMENT,
                owner TEXT NOT NULL,
                repository TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                state TEXT NOT NULL,
                labels TEXT NOT NULL
            )
            """
        )
        self._connection.commit()
        self._lock = threading.Lock()

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._connection.close()
            self._closed = True

    def list_issues(
        self, owner: str, repository: str, *, state: str | None = "open", limit: int = 20
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM issues WHERE owner = ? AND repository = ?"
        parameters: list[Any] = [owner, repository]
        if state is not None:
            query += " AND state = ?"
            parameters.append(state)
        query += " ORDER BY number LIMIT ?"
        parameters.append(limit)
        with self._lock:
            rows = self._connection.execute(query, parameters).fetchall()
        return [_to_issue(dict(row)) for row in rows]

    def get_issue(self, owner: str, repository: str, number: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM issues WHERE owner = ? AND repository = ? AND number = ?",
                (owner, repository, number),
            ).fetchone()
        return _to_issue(dict(row)) if row is not None else None

    def create_issue(
        self, owner: str, repository: str, *, title: str, body: str, labels: tuple[str, ...]
    ) -> dict[str, Any]:
        with self._lock:
            cursor = self._connection.execute(
                "INSERT INTO issues (owner, repository, title, body, state, labels)"
                " VALUES (?, ?, ?, ?, 'open', ?)",
                (owner, repository, title, body, json.dumps(list(labels))),
            )
            self._connection.commit()
            number = int(cursor.lastrowid or 0)
        return {
            "number": number,
            "owner": owner,
            "repository": repository,
            "title": title,
            "body": body,
            "state": "open",
            "labels": list(labels),
            "url": f"/repos/{owner}/{repository}/issues/{number}",
        }

    def set_state(
        self, owner: str, repository: str, number: int, state: str
    ) -> dict[str, Any] | None:
        with self._lock:
            cursor = self._connection.execute(
                "UPDATE issues SET state = ? WHERE owner = ? AND repository = ? AND number = ?",
                (state, owner, repository, number),
            )
            self._connection.commit()
        if cursor.rowcount == 0:
            return None
        return self.get_issue(owner, repository, number)

    def delete_repository(self, owner: str, repository: str) -> int:
        with self._lock:
            cursor = self._connection.execute(
                "DELETE FROM issues WHERE owner = ? AND repository = ?", (owner, repository)
            )
            self._connection.commit()
            return int(cursor.rowcount)

    def count(self) -> int:
        with self._lock:
            row = self._connection.execute("SELECT COUNT(*) AS total FROM issues").fetchone()
        return int(row["total"])


def _to_issue(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "number": int(row["number"]),
        "owner": row["owner"],
        "repository": row["repository"],
        "title": row["title"],
        "body": row["body"],
        "state": row["state"],
        "labels": json.loads(row["labels"]),
        "url": f"/repos/{row['owner']}/{row['repository']}/issues/{row['number']}",
    }


class IssueApi:
    def __init__(
        self,
        *,
        database: str | Path = ":memory:",
        tokens: tuple[Token, ...] = (),
        faults: FaultPlan = FaultPlan(),
    ) -> None:
        self.store = IssueStore(database)
        self.faults = faults
        self._tokens = {token.name: token for token in tokens}
        self._server: _Server | None = None
        self._thread: threading.Thread | None = None
        self._remaining_read_failures = faults.fail_reads
        self._remaining_write_failures = faults.fail_writes
        self._counter_lock = threading.Lock()

    @property
    def base_url(self) -> str:
        if self._server is None:
            raise RuntimeError("The API is not running")
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def scopes_of(self, token: str) -> frozenset[str]:
        try:
            return self._tokens[token].scopes
        except KeyError:
            raise KeyError(f"Unknown token: {token}") from None

    def start(self, host: str = "127.0.0.1", port: int = 0) -> str:
        if self._server is not None:
            raise RuntimeError("The API is already running")
        server = _Server((host, port), self)
        self._server = server
        self._thread = threading.Thread(
            target=lambda: server.serve_forever(poll_interval=0.01),
            name="issue-api",
            daemon=True,
        )
        self._thread.start()
        return self.base_url

    def stop(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._server = None
        self._thread = None

    def close(self) -> None:
        self.stop()
        self.store.close()

    def _consume_failure(self, *, write: bool) -> bool:
        with self._counter_lock:
            remaining = self._remaining_write_failures if write else self._remaining_read_failures
            if remaining <= 0:
                return False
            if write:
                self._remaining_write_failures -= 1
            else:
                self._remaining_read_failures -= 1
            return True

    def _wait(self, *, write: bool) -> None:
        delay = self.faults.write_delay_seconds if write else self.faults.read_delay_seconds
        if delay > 0:
            time.sleep(delay)


class _Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], api: IssueApi) -> None:
        super().__init__(address, _Handler)
        self.api = api


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "CourseIssueApi/1.0"

    @property
    def api(self) -> IssueApi:
        server = self.server
        if not isinstance(server, _Server):
            raise RuntimeError("The issue API must be served by its own HTTP server")
        return server.api

    def log_message(self, format: str, *arguments: Any) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        issues_match = _ISSUES_PATH.match(path)
        if issues_match is not None:
            self._read(issues_match, self._list_issues)
            return
        issue_match = _ISSUE_PATH.match(path)
        if issue_match is not None:
            self._read(issue_match, self._get_issue)
            return
        self._fail(404, "not_found", f"No route for GET {path}")

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        match = _ISSUES_PATH.match(path)
        if match is None:
            self._fail(404, "not_found", f"No route for POST {path}")
            return
        payload = self._read_payload()
        if payload is None:
            return
        self._write(SCOPE_WRITE, match, lambda found: self._create_issue(found, payload))

    def do_PATCH(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        match = _ISSUE_PATH.match(path)
        if match is None:
            self._fail(404, "not_found", f"No route for PATCH {path}")
            return
        payload = self._read_payload()
        if payload is None:
            return
        self._write(SCOPE_WRITE, match, lambda found: self._close_issue(found, payload))

    def do_DELETE(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        match = _REPOSITORY_PATH.match(path)
        if match is None:
            self._fail(404, "not_found", f"No route for DELETE {path}")
            return
        self._write(SCOPE_WRITE, match, self._delete_repository)

    def _read(self, match: re.Match[str], action: Any) -> None:
        if self._denied(SCOPE_READ):
            return
        self.api._wait(write=False)
        if self.api._consume_failure(write=False):
            self._fail(503, "service_unavailable", "The issue service is temporarily unavailable")
            return
        status, payload = action(match)
        self._send_json(status, payload)

    def _write(self, scope: str, match: re.Match[str], action: Any) -> None:
        if self._denied(scope):
            return
        self.api._wait(write=False)
        if self.api._consume_failure(write=True):
            self._fail(503, "service_unavailable", "The issue service is temporarily unavailable")
            return
        self.api._wait(write=True)
        status, payload = action(match)
        self._send_json(status, payload)

    def _denied(self, scope: str) -> bool:
        header = self.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            self._fail(401, "authentication_required", "Provide an Authorization: Bearer header")
            return True
        token = self.api._tokens.get(header.removeprefix("Bearer ").strip())
        if token is None:
            self._fail(401, "invalid_token", "The token is not known to this service")
            return True
        if scope not in token.scopes:
            self._fail(403, "insufficient_scope", f"This action requires the {scope} scope")
            return True
        return False

    def _list_issues(self, match: re.Match[str]) -> tuple[int, dict[str, Any]]:
        parameters = parse_qs(urlparse(self.path).query)
        state = parameters.get("state", ["open"])[0]
        issues = self.api.store.list_issues(
            match.group("owner"),
            match.group("repository"),
            state=None if state == "all" else state,
            limit=_bounded_int(parameters.get("limit", ["20"])[0]),
        )
        return 200, {"total_count": len(issues), "issues": issues}

    def _get_issue(self, match: re.Match[str]) -> tuple[int, dict[str, Any]]:
        issue = self.api.store.get_issue(
            match.group("owner"), match.group("repository"), int(match.group("number"))
        )
        if issue is None:
            return 404, {"error": {"code": "not_found", "message": "No such issue"}}
        return 200, issue

    def _create_issue(
        self, match: re.Match[str], payload: dict[str, Any]
    ) -> tuple[int, dict[str, Any]]:
        title = payload.get("title")
        if not isinstance(title, str) or not title.strip():
            return 422, {"error": {"code": "invalid_title", "message": "title is required"}}
        if len(title) > _MAX_TITLE_CHARACTERS:
            return 422, {
                "error": {"code": "title_too_long", "message": "title is too long"}
            }
        labels = payload.get("labels", [])
        if not isinstance(labels, list) or not all(isinstance(label, str) for label in labels):
            return 422, {"error": {"code": "invalid_labels", "message": "labels must be strings"}}
        body = payload.get("body", "")
        if not isinstance(body, str):
            return 422, {"error": {"code": "invalid_body", "message": "body must be a string"}}
        issue = self.api.store.create_issue(
            match.group("owner"),
            match.group("repository"),
            title=title.strip(),
            body=body,
            labels=tuple(labels),
        )
        return 201, issue

    def _close_issue(self, match: re.Match[str], payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        state = payload.get("state")
        if state not in {"open", "closed"}:
            return 422, {"error": {"code": "invalid_state", "message": "state must be open or closed"}}
        issue = self.api.store.set_state(
            match.group("owner"), match.group("repository"), int(match.group("number")), state
        )
        if issue is None:
            return 404, {"error": {"code": "not_found", "message": "No such issue"}}
        return 200, issue

    def _delete_repository(self, match: re.Match[str]) -> tuple[int, dict[str, Any]]:
        return 200, {"deleted_issues": self.api.store.delete_repository(
            match.group("owner"), match.group("repository")
        )}

    def _read_payload(self) -> dict[str, Any] | None:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._fail(400, "invalid_content_length", "Content-Length must be an integer")
            return None
        if length < 0 or length > _MAX_BODY_CHARACTERS:
            self._fail(413, "payload_too_large", "The request body is too large")
            return None
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            self._fail(400, "invalid_json", "The request body is not valid JSON")
            return None
        if not isinstance(payload, dict):
            self._fail(400, "invalid_json", "The request body must be a JSON object")
            return None
        return payload

    def _fail(self, status: int, code: str, message: str) -> None:
        self._send_json(status, {"error": {"code": code, "message": message}})

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            self.close_connection = True


def _bounded_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError:
        return 20
    return parsed if 1 <= parsed <= 100 else 20