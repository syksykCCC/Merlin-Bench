"""C08: a hidden-structure binary syndrome-decoding certificate.

The public relation checks a packed binary vector of prescribed weight against
a dense binary parity system.  Maintainer-only code recognizes a frozen,
permuted and row-mixed primitive BCH family and decodes from public data.  No
family identifier, canonical ordering, row transform, or decoding hint enters
the public instance or participant specification.
"""

from __future__ import annotations

import hashlib
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

CASE_ID: Final = "c08"
TITLE: Final = "Anonymous binary syndrome certificate"
DEFAULT_PARAMETERS: Final[Mapping[str, Any]] = {
    "num_items": 511,
    "target_weight": 28,
    "word_bits": 32,
}

_FIELD_DEGREE: Final = 9
_FIELD_SIZE: Final = 1 << _FIELD_DEGREE
_CODE_LENGTH: Final = _FIELD_SIZE - 1
_TARGET_WEIGHT: Final = 28
_MAX_SYNDROME_INDEX: Final = 2 * _TARGET_WEIGHT
_SYNDROME_COUNT: Final = _TARGET_WEIGHT
_SYNDROME_BITS: Final = _FIELD_DEGREE * _SYNDROME_COUNT
_WORD_BITS: Final = 32
_SYNDROME_WORDS: Final = (_SYNDROME_BITS + _WORD_BITS - 1) // _WORD_BITS
_ITEM_BLOCK: Final = 32
_ITEM_BLOCKS: Final = (_CODE_LENGTH + _ITEM_BLOCK - 1) // _ITEM_BLOCK
_PRIMITIVE_POLYNOMIAL: Final = (1 << 9) | (1 << 4) | 1
_FAMILY_DOMAIN: Final = b"aipbench/t3-mcm/c08/hidden-bch/v1\x00"


def _gf_multiply(left: int, right: int) -> int:
    result = 0
    value = left
    multiplier = right
    while multiplier:
        if multiplier & 1:
            result ^= value
        multiplier >>= 1
        value <<= 1
        if value & _FIELD_SIZE:
            value ^= _PRIMITIVE_POLYNOMIAL
    return result


@lru_cache(maxsize=1)
def _gf_tables() -> tuple[tuple[int, ...], tuple[int, ...]]:
    exponent = [0] * (2 * _CODE_LENGTH)
    logarithm = [-1] * _FIELD_SIZE
    value = 1
    for index in range(_CODE_LENGTH):
        if logarithm[value] != -1:
            raise AssertionError("the frozen polynomial is not primitive")
        exponent[index] = value
        logarithm[value] = index
        value = _gf_multiply(value, 2)
    if value != 1 or any(entry < 0 for entry in logarithm[1:]):
        raise AssertionError("the frozen polynomial does not generate GF(2^9)^*")
    for index in range(_CODE_LENGTH, 2 * _CODE_LENGTH):
        exponent[index] = exponent[index - _CODE_LENGTH]
    return tuple(exponent), tuple(logarithm)


def _gf_mul(left: int, right: int) -> int:
    if left == 0 or right == 0:
        return 0
    exponent, logarithm = _gf_tables()
    return exponent[(logarithm[left] + logarithm[right]) % _CODE_LENGTH]


def _gf_div(left: int, right: int) -> int:
    if right == 0:
        raise ZeroDivisionError("finite-field division by zero")
    if left == 0:
        return 0
    exponent, logarithm = _gf_tables()
    return exponent[(logarithm[left] - logarithm[right]) % _CODE_LENGTH]


def _raw_column(position: int) -> int:
    exponent, _ = _gf_tables()
    packed = 0
    for packed_index, syndrome_index in enumerate(range(1, _MAX_SYNDROME_INDEX + 1, 2)):
        value = exponent[(syndrome_index * position) % _CODE_LENGTH]
        packed |= value << (_FIELD_DEGREE * packed_index)
    return packed


def _domain_integer(label: bytes, index: int) -> int:
    return int.from_bytes(
        hashlib.sha256(_FAMILY_DOMAIN + label + index.to_bytes(8, "big")).digest(),
        "big",
    )


@lru_cache(maxsize=1)
def _row_operations() -> tuple[tuple[int, int, int], ...]:
    operations: list[tuple[int, int, int]] = []
    for index in range(12 * _SYNDROME_BITS):
        left = _domain_integer(b"row-left", index) % _SYNDROME_BITS
        right = _domain_integer(b"row-right", index) % (_SYNDROME_BITS - 1)
        if right >= left:
            right += 1
        # Roughly one operation in eight is a swap; the rest are reversible
        # row additions.  Both operations are their own inverse over GF(2).
        kind = int(_domain_integer(b"row-kind", index) % 8 == 0)
        operations.append((kind, left, right))
    return tuple(operations)


def _apply_row_operations(value: int, *, inverse: bool = False) -> int:
    operations: Sequence[tuple[int, int, int]] = _row_operations()
    if inverse:
        operations = tuple(reversed(operations))
    result = value
    for kind, left, right in operations:
        left_bit = (result >> left) & 1
        right_bit = (result >> right) & 1
        if kind == 1:
            if left_bit != right_bit:
                result ^= (1 << left) | (1 << right)
        elif right_bit:
            result ^= 1 << left
    return result


@lru_cache(maxsize=1)
def _public_order() -> tuple[int, ...]:
    return tuple(
        sorted(
            range(_CODE_LENGTH),
            key=lambda index: (
                hashlib.sha256(
                    _FAMILY_DOMAIN + b"column-order" + index.to_bytes(4, "big")
                ).digest(),
                index,
            ),
        )
    )


def _pack_chunks(value: int, count: int, word_bits: int = _WORD_BITS) -> tuple[int, ...]:
    mask = (1 << word_bits) - 1
    return tuple((value >> (word_bits * index)) & mask for index in range(count))


def _unpack_chunks(words: Sequence[int], word_bits: int = _WORD_BITS) -> int:
    return sum(int(word) << (word_bits * index) for index, word in enumerate(words))


@lru_cache(maxsize=1)
def _family_columns() -> tuple[tuple[int, ...], tuple[int, ...]]:
    canonical = tuple(_raw_column(position) for position in range(_CODE_LENGTH))
    transformed = tuple(_apply_row_operations(column) for column in canonical)
    public = tuple(transformed[position] for position in _public_order())
    return canonical, public


def _berlekamp_massey(syndromes: Sequence[int]) -> tuple[int, ...]:
    length = len(syndromes)
    locator = [1] + [0] * length
    previous = [1] + [0] * length
    degree = 0
    shift = 1
    previous_discrepancy = 1
    for index in range(length):
        discrepancy = syndromes[index]
        for offset in range(1, degree + 1):
            discrepancy ^= _gf_mul(locator[offset], syndromes[index - offset])
        if discrepancy == 0:
            shift += 1
            continue
        snapshot = locator.copy()
        scale = _gf_div(discrepancy, previous_discrepancy)
        for offset in range(length + 1 - shift):
            locator[offset + shift] ^= _gf_mul(scale, previous[offset])
        if 2 * degree <= index:
            degree = index + 1 - degree
            previous = snapshot
            previous_discrepancy = discrepancy
            shift = 1
        else:
            shift += 1
    return tuple(locator[: degree + 1])


def _decode_raw_syndrome(raw_syndrome: int, expected_weight: int) -> tuple[int, ...]:
    odd_syndromes = tuple(
        (raw_syndrome >> (_FIELD_DEGREE * index)) & (_FIELD_SIZE - 1)
        for index in range(_SYNDROME_COUNT)
    )
    indexed: dict[int, int] = {2 * index + 1: value for index, value in enumerate(odd_syndromes)}
    for syndrome_index in range(2, _MAX_SYNDROME_INDEX + 1, 2):
        half = indexed[syndrome_index // 2]
        indexed[syndrome_index] = _gf_mul(half, half)
    syndromes = tuple(indexed[index] for index in range(1, _MAX_SYNDROME_INDEX + 1))
    locator = _berlekamp_massey(syndromes)
    if len(locator) - 1 != expected_weight:
        raise ValueError("public syndrome has the wrong locator degree")
    exponent, _ = _gf_tables()
    positions: list[int] = []
    for position in range(_CODE_LENGTH):
        root = exponent[(-position) % _CODE_LENGTH]
        power = 1
        value = 0
        for coefficient in locator:
            value ^= _gf_mul(coefficient, power)
            power = _gf_mul(power, root)
        if value == 0:
            positions.append(position)
    if len(positions) != expected_weight:
        raise ValueError("public syndrome does not have the expected number of roots")
    replay = 0
    for position in positions:
        replay ^= _raw_column(position)
    if replay != raw_syndrome:
        raise ValueError("decoded error positions do not replay the public syndrome")
    return tuple(positions)


def _certificate_from_public_bits(
    public_bits: Sequence[int], public_columns: Sequence[int]
) -> tuple[int, ...]:
    del public_columns
    bit_words = tuple(
        sum(
            int(public_bits[index]) << (index - offset)
            for index in range(offset, min(offset + _WORD_BITS, len(public_bits)))
        )
        for offset in range(0, len(public_bits), _WORD_BITS)
    )
    word_weights = tuple(int(word).bit_count() for word in bit_words)
    return (*bit_words, *word_weights)


def _certificate_bits(certificate: Sequence[int], count: int) -> tuple[int, ...]:
    return tuple(
        (int(certificate[index // _WORD_BITS]) >> (index % _WORD_BITS)) & 1
        for index in range(count)
    )


def solve(problem: Mapping[str, Any]) -> tuple[int, ...]:
    count = int(problem["num_items"])
    target_weight = int(problem["target_weight"])
    word_bits = int(problem["word_bits"])
    raw_columns = problem["columns"]
    raw_syndrome_words = problem["syndrome"]
    if (count, target_weight, word_bits) != (_CODE_LENGTH, _TARGET_WEIGHT, _WORD_BITS):
        raise ValueError("unsupported c08 public profile")
    if len(raw_columns) != count or len(raw_syndrome_words) != _SYNDROME_WORDS:
        raise ValueError("malformed c08 public matrix shape")
    public_columns = tuple(
        _unpack_chunks(tuple(int(word) for word in column)) for column in raw_columns
    )
    _, expected_columns = _family_columns()
    if public_columns != expected_columns:
        raise ValueError("public matrix is outside the frozen c08 family")
    public_syndrome = _unpack_chunks(tuple(int(word) for word in raw_syndrome_words))
    if public_syndrome >= 1 << _SYNDROME_BITS:
        raise ValueError("public syndrome exceeds its declared width")
    raw_syndrome = _apply_row_operations(public_syndrome, inverse=True)
    canonical_errors = set(_decode_raw_syndrome(raw_syndrome, target_weight))
    public_bits = tuple(
        int(canonical_position in canonical_errors) for canonical_position in _public_order()
    )
    certificate = _certificate_from_public_bits(public_bits, public_columns)
    replay = 0
    for bit, column in zip(public_bits, public_columns, strict=True):
        if bit:
            replay ^= column
    if sum(public_bits) != target_weight or replay != public_syndrome:
        raise AssertionError("decoded public error vector does not verify")
    return certificate


def render_solution(certificate: Sequence[int]) -> str:
    # Length, two bounds, sixteen bounded popcounts, their total, and one
    # bounded computation for each of the sixteen public syndrome chunks.
    proofs = " ".join("(by decide)" for _ in range(272))
    return f"""import Challenge

namespace AMBenchSolution

theorem proof : Challenge.Target := by
  let certificate : List Nat := {lean_nat_list(certificate)}
  exact Challenge.submit certificate {proofs}

end AMBenchSolution
"""


def _lean_matrix(rows: Sequence[Sequence[int]]) -> str:
    return "[\n    " + ",\n    ".join(lean_nat_list(row) for row in rows) + "\n  ]"


def build(stream: DeterministicStream, parameters: Mapping[str, Any]) -> LeanCaseBlueprint:
    count = integer_parameter(parameters, "num_items", minimum=8, maximum=_CODE_LENGTH)
    target_weight = integer_parameter(
        parameters, "target_weight", minimum=1, maximum=_TARGET_WEIGHT
    )
    word_bits = integer_parameter(parameters, "word_bits", minimum=4, maximum=64)
    if (count, target_weight, word_bits) != (_CODE_LENGTH, _TARGET_WEIGHT, _WORD_BITS):
        raise ValueError("c08 uses one frozen 511-item, weight-28 profile")

    _, public_columns = _family_columns()
    canonical_errors = list(range(_CODE_LENGTH))
    stream.shuffle(canonical_errors)
    canonical_error_set = set(canonical_errors[:target_weight])
    raw_syndrome = 0
    for position in canonical_error_set:
        raw_syndrome ^= _raw_column(position)
    public_syndrome = _apply_row_operations(raw_syndrome)
    column_chunks = tuple(_pack_chunks(column, _SYNDROME_WORDS) for column in public_columns)
    problem = {
        "num_items": count,
        "target_weight": target_weight,
        "word_bits": word_bits,
        "columns": [list(column) for column in column_chunks],
        "syndrome": list(_pack_chunks(public_syndrome, _SYNDROME_WORDS)),
    }
    certificate = solve(problem)

    bit_words = (count + word_bits - 1) // word_bits
    certificate_entries = 2 * bit_words
    last_word_bits = count - word_bits * (bit_words - 1)
    row_supports = tuple(
        tuple(item for item, column in enumerate(public_columns) if (column >> row) & 1)
        for row in range(_SYNDROME_BITS)
    )
    row_definition_parts: list[str] = []
    for row, support in enumerate(row_supports):
        support_groups = tuple(
            support[offset : offset + 32] for offset in range(0, len(support), 32)
        )
        row_definition_parts.append(
            f"""def rowSupport{row} : List (List Nat) := {_lean_matrix(support_groups)}
def rowHolds{row} (certificate : List Nat) : Bool :=
  rowParity certificate rowSupport{row} == {(public_syndrome >> row) & 1}"""
        )
    row_declarations = "\n\n".join(row_definition_parts)
    declarations = f"""set_option maxRecDepth 100000
set_option maxHeartbeats 10000000

def numItems : Nat := {count}
def targetWeight : Nat := {target_weight}
def wordBits : Nat := {word_bits}
def bitWords : Nat := {bit_words}
def lastWordBits : Nat := {last_word_bits}
def itemBlock : Nat := {_ITEM_BLOCK}
def itemBlocks : Nat := {_ITEM_BLOCKS}
def syndromeWords : Nat := {_SYNDROME_WORDS}
def syndromeBits : Nat := {_SYNDROME_BITS}
def certificateEntries : Nat := {certificate_entries}

def selectedBit (certificate : List Nat) (index : Nat) : Nat :=
  ((certificate.getD (index / wordBits) 0) / (2 ^ (index % wordBits))) % 2

def bitCount (word : Nat) : Nat :=
  (List.range wordBits).foldl (fun total offset =>
    total + (word / (2 ^ offset)) % 2) 0

def certificateWeight (certificate : List Nat) : Nat :=
  (List.range bitWords).foldl (fun total word =>
    total + certificate.getD (bitWords + word) (wordBits + 1)) 0

def wordWeightHolds (certificate : List Nat) (word : Nat) : Bool :=
  bitCount (certificate.getD word 0) == certificate.getD (bitWords + word) (wordBits + 1)

def supportParity (certificate support : List Nat) : Nat :=
  support.foldl (fun total item => (total + selectedBit certificate item) % 2) 0

def rowParity (certificate : List Nat) (groups : List (List Nat)) : Nat :=
  groups.foldl (fun total support =>
    (total + supportParity certificate support) % 2) 0

def bitWordsValid (certificate : List Nat) : Bool :=
  (List.range bitWords).all (fun word =>
    certificate.getD word 0 <
      2 ^ (if word + 1 == bitWords then lastWordBits else wordBits))

def weightWordsValid (certificate : List Nat) : Bool :=
  (List.range bitWords).all (fun word =>
    certificate.getD (bitWords + word) (wordBits + 1) <= wordBits)

{row_declarations}

abbrev ProfileEncoded : Prop :=
  syndromeBits = {_SYNDROME_BITS} ∧ numItems = {_CODE_LENGTH}"""
    weight_terms = " ∧\n  ".join(
        f"wordWeightHolds certificate {word} = true" for word in range(bit_words)
    )
    chunk_terms = " ∧\n  ".join(
        f"rowHolds{index} certificate = true" for index in range(_SYNDROME_BITS)
    )
    predicate = f"""abbrev valid (certificate : List Nat) : Prop :=
  certificate.length = certificateEntries ∧
  bitWordsValid certificate = true ∧
  weightWordsValid certificate = true ∧
  {weight_terms} ∧
  certificateWeight certificate = targetWeight ∧
  {chunk_terms}"""
    source = challenge_source(
        declarations=declarations,
        predicate=predicate,
        claim="ProfileEncoded",
    )
    chunk_arguments = "\n    ".join(
        f"(hSyndrome{index} : rowHolds{index} certificate = true)"
        for index in range(_SYNDROME_BITS)
    )
    weight_arguments = "\n    ".join(
        f"(hWeight{word} : wordWeightHolds certificate {word} = true)" for word in range(bit_words)
    )
    weight_names = ", ".join(f"hWeight{word}" for word in range(bit_words))
    chunk_names = ", ".join(f"hSyndrome{index}" for index in range(_SYNDROME_BITS))
    source = source.replace(
        "\nend Challenge\n",
        f"""

theorem submit (certificate : List Nat)
    (hLength : certificate.length = certificateEntries)
    (hBitWords : bitWordsValid certificate = true)
    (hWeightWords : weightWordsValid certificate = true)
    {weight_arguments}
    (hTotalWeight : certificateWeight certificate = targetWeight)
    {chunk_arguments} : Target := by
  exact Exists.intro certificate
    (And.intro
      ⟨hLength, hBitWords, hWeightWords, {weight_names}, hTotalWeight, {chunk_names}⟩
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
            "certificate_entries": certificate_entries,
            "certificate_codec": "packed_binary_vector_and_block_syndromes",
        },
        metadata={
            "criterion": "fixed_weight_binary_syndrome",
            "public_equations": _SYNDROME_BITS,
        },
    )


__all__ = [
    "CASE_ID",
    "DEFAULT_PARAMETERS",
    "TITLE",
    "_certificate_bits",
    "_certificate_from_public_bits",
    "_decode_raw_syndrome",
    "_family_columns",
    "_pack_chunks",
    "_public_order",
    "_unpack_chunks",
    "build",
    "render_solution",
    "solve",
]
