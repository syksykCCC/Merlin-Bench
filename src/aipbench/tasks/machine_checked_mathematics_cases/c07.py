"""C07: an anonymous modular subset certificate.

Arthur's public relation is only a modular dot product against packed bits.
The frozen generator uses a disguised superincreasing family so that the
maintainer can recover the unique bits from public data without retaining a
private witness.  The family constants and recovery route are deliberately
absent from the public problem and participant specification.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence
from functools import lru_cache
from typing import Any, Final

from aipbench.tasks.machine_checked_mathematics_cases.common import (
    DeterministicStream,
    LeanCaseBlueprint,
    challenge_source,
    integer_parameter,
    lean_nat_list,
)

CASE_ID: Final = "c07"
TITLE: Final = "Anonymous modular subset certificate"
DEFAULT_PARAMETERS: Final[Mapping[str, Any]] = {"num_items": 256, "word_bits": 32}

_MAX_ITEMS: Final = 256
_BLOCK_SIZE: Final = 16
_FAMILY_DOMAIN: Final = b"aipbench/t3-mcm/c07/hidden-superincreasing/v1\x00"


def _domain_integer(label: bytes, index: int = 0) -> int:
    return int.from_bytes(
        hashlib.sha256(_FAMILY_DOMAIN + label + index.to_bytes(4, "big")).digest(), "big"
    )


@lru_cache(maxsize=1)
def _family_material() -> tuple[tuple[int, ...], int, int, int]:
    """Return the frozen hidden weights, modulus, multiplier, and its inverse."""

    hidden: list[int] = []
    running_sum = 0
    for index in range(_MAX_ITEMS):
        # Bounded nonzero perturbations avoid a visibly canonical power-of-two
        # sequence while retaining the greedy uniqueness invariant.
        weight = running_sum + 1 + _domain_integer(b"increment", index) % 1024
        hidden.append(weight)
        running_sum += weight

    modulus = running_sum + 1 + _domain_integer(b"modulus-gap") % (1 << 20)
    multiplier = 2 + _domain_integer(b"multiplier") % (modulus - 3)
    while math.gcd(multiplier, modulus) != 1:
        multiplier += 1
        if multiplier == modulus:
            multiplier = 2
    inverse = pow(multiplier, -1, modulus)
    return tuple(hidden), modulus, multiplier, inverse


def _pack_bits(bits: Sequence[int], word_bits: int) -> tuple[int, ...]:
    return tuple(
        sum(
            int(bits[index]) << (index - offset)
            for index in range(offset, min(offset + word_bits, len(bits)))
        )
        for offset in range(0, len(bits), word_bits)
    )


def _unpack_bits(words: Sequence[int], count: int, word_bits: int) -> tuple[int, ...]:
    return tuple(
        (int(words[index // word_bits]) >> (index % word_bits)) & 1 for index in range(count)
    )


def render_solution(certificate: Sequence[int]) -> str:
    # length, word bounds, residue bounds, one premise per block, and the
    # final residue equation are deliberately separated to bound elaboration.
    proofs = " ".join("(by decide)" for _ in range(20))
    return f"""import Challenge

namespace AMBenchSolution

theorem proof : Challenge.Target := by
  let certificate : List Nat := {lean_nat_list(certificate)}
  exact Challenge.submit certificate {proofs}

end AMBenchSolution
"""


def solve(problem: Mapping[str, Any]) -> tuple[int, ...]:
    count = int(problem["num_items"])
    word_bits = int(problem["word_bits"])
    modulus = int(problem["modulus"])
    target = int(problem["target"])
    public_weights = tuple(int(value) for value in problem["weights"])
    if not (8 <= count <= _MAX_ITEMS) or len(public_weights) != count:
        raise ValueError("unsupported public item profile")
    if not (4 <= word_bits <= 64) or not (0 <= target < modulus):
        raise ValueError("unsupported public certificate codec")

    hidden, expected_modulus, multiplier, inverse = _family_material()
    if modulus != expected_modulus:
        raise ValueError("public modulus is outside the frozen c07 family")
    residue_to_hidden = {multiplier * hidden[index] % modulus: index for index in range(count)}
    if len(residue_to_hidden) != count or set(public_weights) != set(residue_to_hidden):
        raise ValueError("public weights are outside the frozen c07 family")

    remaining = inverse * target % modulus
    hidden_bits = [0] * count
    for index in range(count - 1, -1, -1):
        if hidden[index] <= remaining:
            hidden_bits[index] = 1
            remaining -= hidden[index]
    if remaining != 0:
        raise ValueError("public target has no frozen-family representation")

    public_bits = tuple(hidden_bits[residue_to_hidden[value]] for value in public_weights)
    bit_words = _pack_bits(public_bits, word_bits)
    recovered = _unpack_bits(bit_words, count, word_bits)
    block_residues = tuple(
        sum(
            public_weights[index] * recovered[index]
            for index in range(offset, min(offset + _BLOCK_SIZE, count))
        )
        % modulus
        for offset in range(0, count, _BLOCK_SIZE)
    )
    certificate = (*bit_words, *block_residues)
    residue = (
        sum(value * bit for value, bit in zip(public_weights, recovered, strict=True)) % modulus
    )
    if residue != target:
        raise AssertionError("recovered modular subset does not verify")
    return certificate


def build(stream: DeterministicStream, parameters: Mapping[str, Any]) -> LeanCaseBlueprint:
    count = integer_parameter(parameters, "num_items", minimum=8, maximum=_MAX_ITEMS)
    word_bits = integer_parameter(parameters, "word_bits", minimum=4, maximum=64)
    if count != _MAX_ITEMS or word_bits != 32:
        raise ValueError("c07 uses one frozen 256-item, 32-bit-word profile")
    hidden, modulus, multiplier, _ = _family_material()

    chosen = list(range(count))
    stream.shuffle(chosen)
    chosen = chosen[: count // 2]
    hidden_bits = [0] * count
    for index in chosen:
        hidden_bits[index] = 1

    public_order = list(range(count))
    stream.shuffle(public_order)
    public_weights = [multiplier * hidden[index] % modulus for index in public_order]
    public_bits = [hidden_bits[index] for index in public_order]
    target = (
        sum(weight * bit for weight, bit in zip(public_weights, public_bits, strict=True)) % modulus
    )
    problem = {
        "num_items": count,
        "word_bits": word_bits,
        "modulus": modulus,
        "weights": public_weights,
        "target": target,
    }
    certificate = solve(problem)

    certificate_words = (count + word_bits - 1) // word_bits
    num_blocks = (count + _BLOCK_SIZE - 1) // _BLOCK_SIZE
    declarations = f"""set_option maxRecDepth 100000

def numItems : Nat := {count}
def wordBits : Nat := {word_bits}
def bitWordCount : Nat := {certificate_words}
def blockSize : Nat := {_BLOCK_SIZE}
def numBlocks : Nat := {num_blocks}
def certificateEntries : Nat := bitWordCount + numBlocks
def modulus : Nat := {modulus}
def target : Nat := {target}
def weights : List Nat := {lean_nat_list(public_weights)}

def selectedBit (certificate : List Nat) (index : Nat) : Nat :=
  ((certificate.getD (index / wordBits) 0) / (2 ^ (index % wordBits))) % 2

def dotPrefix (certificate : List Nat) (index : Nat) : Nat -> List Nat -> Nat
  | 0, _ => 0
  | _, [] => 0
  | remaining + 1, weight :: rest =>
      (weight * selectedBit certificate index +
        dotPrefix certificate (index + 1) remaining rest) % modulus

def claimedBlock (certificate : List Nat) (block : Nat) : Nat :=
  certificate.getD (bitWordCount + block) modulus

def computedBlock (certificate : List Nat) (block : Nat) : Nat :=
  dotPrefix certificate (block * blockSize) blockSize (weights.drop (block * blockSize))

def blockHolds (certificate : List Nat) (block : Nat) : Bool :=
  computedBlock certificate block == claimedBlock certificate block

def wordsValid (certificate : List Nat) : Bool :=
  (List.range bitWordCount).all (fun word =>
    certificate.getD word 0 < 2 ^ wordBits)

def residuesValid (certificate : List Nat) : Bool :=
  (List.range numBlocks).all (fun block =>
    claimedBlock certificate block < modulus)

def totalHolds (certificate : List Nat) : Bool :=
  (List.range numBlocks).foldl (fun total block =>
    (total + claimedBlock certificate block) % modulus) 0 == target

abbrev WellFormedInstance : Prop :=
  weights.length = numItems ∧ 1 < modulus ∧ target < modulus"""
    block_terms = " ∧\n  ".join(
        f"blockHolds certificate {index} = true" for index in range(num_blocks)
    )
    predicate = f"""abbrev valid (certificate : List Nat) : Prop :=
  certificate.length = certificateEntries ∧
  wordsValid certificate = true ∧
  residuesValid certificate = true ∧
  {block_terms} ∧
  totalHolds certificate = true"""
    source = challenge_source(
        declarations=declarations,
        predicate=predicate,
        claim="WellFormedInstance",
    )
    block_arguments = "\n    ".join(
        f"(hBlock{index} : blockHolds certificate {index} = true)" for index in range(num_blocks)
    )
    block_names = ", ".join(f"hBlock{index}" for index in range(num_blocks))
    source = source.replace(
        "\nend Challenge\n",
        f"""

theorem submit (certificate : List Nat)
    (hLength : certificate.length = certificateEntries)
    (hWords : wordsValid certificate = true)
    (hResidues : residuesValid certificate = true)
    {block_arguments}
    (hTotal : totalHolds certificate = true) : Target := by
  exact Exists.intro certificate
    (And.intro
      ⟨hLength, hWords, hResidues, {block_names}, hTotal⟩
      (by decide))

end Challenge
""",
    )
    return LeanCaseBlueprint(
        title=TITLE,
        problem=problem,
        challenge_source=source,
        reference_certificate=certificate,
        public_features={
            "certificate_entries": certificate_words + num_blocks,
            "certificate_codec": "packed_binary_words",
        },
        metadata={
            "criterion": "exact_modular_subset_residue",
            "modulus_bits": modulus.bit_length(),
        },
    )


__all__ = [
    "CASE_ID",
    "DEFAULT_PARAMETERS",
    "TITLE",
    "_family_material",
    "_pack_bits",
    "_unpack_bits",
    "build",
    "render_solution",
    "solve",
]
