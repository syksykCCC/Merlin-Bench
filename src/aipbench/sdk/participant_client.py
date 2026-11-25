"""Small synchronous HTTP client implementing the participant client protocol."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx


class HttpParticipantClient:
    def __init__(
        self,
        *,
        endpoint: str,
        session_token: str,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._client = httpx.Client(
            base_url=endpoint.rstrip("/"),
            headers={"Authorization": f"Bearer {session_token}"},
            timeout=timeout_seconds,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> HttpParticipantClient:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _json(self, response: httpx.Response) -> Mapping[str, Any]:
        response.raise_for_status()
        value = response.json()
        if not isinstance(value, dict):
            raise TypeError("Arthur returned a non-object response")
        return value

    def get_session(self) -> Mapping[str, Any]:
        return self._json(self._client.get("/v1/session"))

    def get_protocol(self) -> Mapping[str, Any]:
        return self._json(self._client.get("/v1/protocol"))

    def get_instance(self) -> Mapping[str, Any]:
        return self._json(self._client.get("/v1/instance"))

    def get_status(self) -> Mapping[str, Any]:
        return self._json(self._client.get("/v1/status"))

    def upload_artifact(self, *, content: bytes, media_type: str) -> Mapping[str, Any]:
        return self._json(
            self._client.post(
                "/v1/artifacts", content=content, headers={"Content-Type": media_type}
            )
        )

    def submit_event(
        self,
        *,
        sequence: int,
        kind: str,
        payload: Mapping[str, Any],
        artifact_refs: tuple[str, ...] = (),
    ) -> Mapping[str, Any]:
        session_id = str(self.get_session()["session_id"])
        return self._json(
            self._client.post(
                "/v1/events",
                json={
                    "api_version": "aip/1",
                    "artifact_refs": list(artifact_refs),
                    "kind": kind,
                    "payload": dict(payload),
                    "sequence": sequence,
                    "session_id": session_id,
                },
            )
        )


__all__ = ["HttpParticipantClient"]
