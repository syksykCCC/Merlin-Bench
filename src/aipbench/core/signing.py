"""Ed25519 result signing helpers."""

from __future__ import annotations

import base64

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)


class ResultSigner:
    def __init__(self, private_key: Ed25519PrivateKey) -> None:
        self._private_key = private_key

    @classmethod
    def generate(cls) -> ResultSigner:
        return cls(Ed25519PrivateKey.generate())

    @classmethod
    def from_private_base64(cls, encoded: str) -> ResultSigner:
        raw = base64.b64decode(encoded, validate=True)
        return cls(Ed25519PrivateKey.from_private_bytes(raw))

    @property
    def private_base64(self) -> str:
        raw = self._private_key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
        return base64.b64encode(raw).decode("ascii")

    @property
    def public_base64(self) -> str:
        raw = self._private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        return base64.b64encode(raw).decode("ascii")

    def sign(self, data: bytes) -> str:
        return base64.b64encode(self._private_key.sign(data)).decode("ascii")


def verify_signature(*, public_key_base64: str, data: bytes, signature_base64: str) -> bool:
    try:
        public_raw = base64.b64decode(public_key_base64, validate=True)
        signature = base64.b64decode(signature_base64, validate=True)
        Ed25519PublicKey.from_public_bytes(public_raw).verify(signature, data)
    except (ValueError, InvalidSignature):
        return False
    return True
