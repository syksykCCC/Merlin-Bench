"""Committed, domain-separated, replayable protocol randomness."""

from __future__ import annotations

import hashlib
import hmac

from aipbench.core.errors import AIPBenchError

PRG_DOMAIN = b"aipbench/committed-prg/v1"
COMMITMENT_DOMAIN = b"aipbench/coin-commitment/v1"


def seed_commitment(*, seed: bytes, run_id: str, task_digest: str) -> str:
    material = b"\x00".join(
        (COMMITMENT_DOMAIN, seed, run_id.encode("utf-8"), task_digest.encode("ascii"))
    )
    return f"sha256:{hashlib.sha256(material).hexdigest()}"


class CommittedPRG:
    """Deterministic PRF stream with per-session tag uniqueness enforcement."""

    def __init__(self, *, seed: bytes, run_id: str, task_digest: str) -> None:
        if len(seed) < 32:
            raise ValueError("coin seed must contain at least 256 bits")
        self.seed = seed
        self.run_id = run_id
        self.task_digest = task_digest
        self.commitment = seed_commitment(seed=seed, run_id=run_id, task_digest=task_digest)
        self._used_tags: set[str] = set()

    @property
    def used_tags(self) -> frozenset[str]:
        return frozenset(self._used_tags)

    def _claim_tag(self, tag: str) -> None:
        if not tag or tag.strip() != tag:
            raise AIPBenchError(
                "INVALID_RANDOMNESS_TAG", "randomness tag is empty or non-canonical"
            )
        if tag in self._used_tags:
            raise AIPBenchError("DUPLICATE_RANDOMNESS_TAG", f"duplicate randomness tag: {tag}")
        self._used_tags.add(tag)

    def _block(self, *, tag: str, event_hash: str, counter: int) -> bytes:
        message = b"\x00".join(
            (
                PRG_DOMAIN,
                self.run_id.encode("utf-8"),
                self.task_digest.encode("ascii"),
                event_hash.encode("ascii"),
                tag.encode("utf-8"),
                counter.to_bytes(8, "big"),
            )
        )
        return hmac.new(self.seed, message, hashlib.sha256).digest()

    def random_bytes(self, *, tag: str, length: int, event_hash: str) -> bytes:
        if length < 0:
            raise ValueError("length must be non-negative")
        self._claim_tag(tag)
        blocks = bytearray()
        counter = 0
        while len(blocks) < length:
            blocks.extend(self._block(tag=tag, event_hash=event_hash, counter=counter))
            counter += 1
        return bytes(blocks[:length])

    def random_int(
        self,
        *,
        tag: str,
        lower_inclusive: int,
        upper_exclusive: int,
        event_hash: str,
    ) -> int:
        span = upper_exclusive - lower_inclusive
        if span <= 0:
            raise ValueError("random integer range must be non-empty")
        self._claim_tag(tag)
        byte_length = max(1, (span.bit_length() + 7) // 8)
        sample_space = 1 << (8 * byte_length)
        cutoff = sample_space - (sample_space % span)
        blocks_per_sample = (byte_length + 31) // 32
        attempt = 0
        while True:
            sample = b"".join(
                self._block(
                    tag=tag,
                    event_hash=event_hash,
                    counter=(attempt * blocks_per_sample) + block_index,
                )
                for block_index in range(blocks_per_sample)
            )
            candidate = int.from_bytes(sample[:byte_length], "big")
            attempt += 1
            if candidate < cutoff:
                return lower_inclusive + (candidate % span)
