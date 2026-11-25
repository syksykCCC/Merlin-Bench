#!/usr/bin/env python3
"""Generic Agent-side client for the public Merlin-Bench Participant API.

The helper intentionally contains no task solver or reference prover.  It reads
the endpoint and bearer token from the paired ``AIP_ENDPOINT`` and
``AIP_SESSION_TOKEN`` variables, or falls back to ``.aipbench-connection.json``
next to this file, and offers generic inspect, event, and artifact-upload operations.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ClientError(RuntimeError):
    """A user-facing configuration, transport, or response error."""


class AgentClient:
    """Minimal standard-library client; safe to copy into an Agent workspace."""

    def __init__(self, *, endpoint: str, session_token: str, timeout_seconds: float) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.session_token = session_token
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_environment(
        cls,
        *,
        timeout_seconds: float,
        connection_file: Path | None = None,
    ) -> AgentClient:
        """Load connection data, preferring environment variables over a local file."""

        if timeout_seconds <= 0:
            raise ClientError("--timeout must be greater than zero")
        endpoint = os.environ.get("AIP_ENDPOINT", "").strip()
        token = os.environ.get("AIP_SESSION_TOKEN", "").strip()
        if bool(endpoint) != bool(token):
            raise ClientError(
                "AIP_ENDPOINT and AIP_SESSION_TOKEN must either both be set or both be unset"
            )
        configured_path = os.environ.get("AIP_CONNECTION_FILE", "").strip()
        config_path = connection_file or (
            Path(configured_path)
            if configured_path
            else Path(__file__).resolve().with_name(".aipbench-connection.json")
        )
        if not endpoint and config_path.is_file():
            try:
                decoded = json.loads(config_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ClientError(f"cannot read connection file {config_path}: {exc}") from exc
            if not isinstance(decoded, dict):
                raise ClientError(f"connection file {config_path} must contain one JSON object")
            file_endpoint = decoded.get("endpoint")
            if isinstance(file_endpoint, str):
                endpoint = file_endpoint.strip()
            file_token = decoded.get("session_token")
            if isinstance(file_token, str):
                token = file_token.strip()
        missing = [
            name
            for name, value in (
                ("AIP_ENDPOINT", endpoint),
                ("AIP_SESSION_TOKEN", token),
            )
            if not value
        ]
        if missing:
            raise ClientError(
                f"missing connection value(s): {', '.join(missing)}; set the environment "
                f"variables or create {config_path}"
            )
        return cls(
            endpoint=endpoint,
            session_token=token,
            timeout_seconds=timeout_seconds,
        )

    def request_json(
        self,
        method: str,
        path: str,
        *,
        json_body: Mapping[str, Any] | None = None,
        raw_body: bytes | None = None,
        media_type: str | None = None,
    ) -> dict[str, Any]:
        if json_body is not None and raw_body is not None:
            raise ValueError("a request cannot have both JSON and raw bodies")

        body = raw_body
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.session_token}",
        }
        if json_body is not None:
            body = json.dumps(dict(json_body), ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            )
            headers["Content-Type"] = "application/json"
        elif raw_body is not None:
            headers["Content-Type"] = media_type or "application/octet-stream"

        request = Request(
            f"{self.endpoint}/{path.lstrip('/')}",
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                response_body = response.read()
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise ClientError(
                f"Arthur returned HTTP {exc.code} for {method} {path}: {detail}"
            ) from None
        except URLError as exc:
            raise ClientError(f"cannot reach Arthur at {self.endpoint}: {exc.reason}") from None

        try:
            decoded = json.loads(response_body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ClientError(f"Arthur returned invalid JSON for {method} {path}: {exc}") from exc
        if not isinstance(decoded, dict):
            raise ClientError(f"Arthur returned a non-object JSON value for {method} {path}")
        return decoded

    def get(self, resource: str) -> dict[str, Any]:
        return self.request_json("GET", f"/v1/{resource}")

    def submit_event(
        self,
        *,
        sequence: int,
        kind: str,
        payload: Mapping[str, Any],
        artifact_refs: Sequence[str],
    ) -> dict[str, Any]:
        session = self.get("session")
        session_id = session.get("session_id")
        if not isinstance(session_id, str):
            raise ClientError("Arthur's session response has no string session_id")
        return self.request_json(
            "POST",
            "/v1/events",
            json_body={
                "api_version": "aip/1",
                "session_id": session_id,
                "sequence": sequence,
                "kind": kind,
                "payload": dict(payload),
                "artifact_refs": list(artifact_refs),
            },
        )

    def upload_artifact(self, *, path: Path, media_type: str | None) -> dict[str, Any]:
        if not path.is_file():
            raise ClientError(f"artifact is not a regular file: {path}")
        detected_type = media_type or mimetypes.guess_type(path.name)[0]
        return self.request_json(
            "POST",
            "/v1/artifacts",
            raw_body=path.read_bytes(),
            media_type=detected_type or "application/octet-stream",
        )


def _print_json(value: Mapping[str, Any]) -> None:
    print(json.dumps(dict(value), ensure_ascii=False, indent=2, sort_keys=True))


def _parse_payload(*, inline: str | None, payload_file: Path | None) -> dict[str, Any]:
    source = "--payload"
    text = inline
    if payload_file is not None:
        source = str(payload_file)
        try:
            text = payload_file.read_text(encoding="utf-8")
        except OSError as exc:
            raise ClientError(f"cannot read payload file {payload_file}: {exc}") from exc
    if text is None:
        text = "{}"
    try:
        decoded = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ClientError(f"{source} is not valid JSON: {exc}") from exc
    if not isinstance(decoded, dict):
        raise ClientError(f"{source} must contain one JSON object")
    return decoded


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect and call the public Merlin-Bench Participant API. "
            "Connection data comes from AIP_ENDPOINT/AIP_SESSION_TOKEN or "
            ".aipbench-connection.json. This helper does not solve a task."
        ),
        epilog=(
            "Typical flow: `info`, create a task-specific payload after reading protocol.json, "
            "then use `event --sequence N --kind KIND --payload-file payload.json`."
        ),
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="HTTP timeout in seconds (default: 30)",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser(
        "info",
        help="read and print session, protocol, public instance, and status",
    )

    get_parser = commands.add_parser("get", help="read one public API resource")
    get_parser.add_argument(
        "resource",
        choices=("session", "protocol", "instance", "status"),
    )

    event_parser = commands.add_parser("event", help="submit one generic participant event")
    event_parser.add_argument("--sequence", type=int, required=True)
    event_parser.add_argument("--kind", required=True)
    payload_source = event_parser.add_mutually_exclusive_group()
    payload_source.add_argument(
        "--payload",
        help="inline JSON object; --payload-file is usually easier in a shell",
    )
    payload_source.add_argument("--payload-file", type=Path, help="UTF-8 JSON object file")
    event_parser.add_argument(
        "--artifact-ref",
        action="append",
        default=[],
        help="sha256 artifact ID; may be repeated",
    )

    upload_parser = commands.add_parser(
        "upload", help="upload one file to the content-addressed artifact API"
    )
    upload_parser.add_argument("path", type=Path)
    upload_parser.add_argument(
        "--media-type",
        help="Content-Type; guessed from the filename when omitted",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments:
        parser.print_help()
        return 0
    args = parser.parse_args(arguments)

    try:
        client = AgentClient.from_environment(timeout_seconds=args.timeout)
        if args.command == "info":
            for resource in ("session", "protocol", "instance", "status"):
                print(f"## {resource}")
                _print_json(client.get(resource))
            return 0
        if args.command == "get":
            _print_json(client.get(args.resource))
            return 0
        if args.command == "event":
            payload = _parse_payload(
                inline=args.payload,
                payload_file=args.payload_file,
            )
            _print_json(
                client.submit_event(
                    sequence=args.sequence,
                    kind=args.kind,
                    payload=payload,
                    artifact_refs=args.artifact_ref,
                )
            )
            return 0
        if args.command == "upload":
            _print_json(client.upload_artifact(path=args.path, media_type=args.media_type))
            return 0
        parser.error(f"unknown command: {args.command}")
    except ClientError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
