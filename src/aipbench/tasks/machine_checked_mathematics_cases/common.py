"""Shared deterministic builders for T3.1 Lean challenges.

The released profile intentionally targets Lean's core library.  Each challenge
asks for an existential certificate and makes the certificate predicate fully
transparent, so an honest participant may compute data in any language while
the final proposition is checked by the Lean kernel.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

PRELUDE_SOURCE: Final = """import Init

namespace AMBenchPrelude

def powMod (base exponent modulus : Nat) : Nat :=
  match exponent with
  | 0 => 1 % modulus
  | n + 1 => (powMod base n modulus * (base % modulus)) % modulus

def evalPolyMod (coefficients : List Nat) (x modulus : Nat) : Nat :=
  match coefficients with
  | [] => 0
  | coefficient :: rest =>
      (coefficient + x * evalPolyMod rest x modulus) % modulus

def absDiff (a b : Nat) : Nat :=
  if a <= b then b - a else a - b

end AMBenchPrelude
"""


class DeterministicStream:
    """Domain-separated SHA-256 stream used only during instance generation."""

    _DOMAIN: Final = b"aipbench/t3-machine-checked-mathematics/generator/v1\x00"

    def __init__(self, seed: bytes) -> None:
        self._seed = bytes(seed)
        self._counter = 0
        self._buffer = bytearray()

    def _refill(self) -> None:
        self._buffer.extend(
            hashlib.sha256(
                self._DOMAIN
                + len(self._seed).to_bytes(8, "big")
                + self._seed
                + self._counter.to_bytes(16, "big")
            ).digest()
        )
        self._counter += 1

    def take(self, length: int) -> bytes:
        if length < 0:
            raise ValueError("length must be non-negative")
        while len(self._buffer) < length:
            self._refill()
        value = bytes(self._buffer[:length])
        del self._buffer[:length]
        return value

    def randbelow(self, upper_exclusive: int) -> int:
        if upper_exclusive <= 0:
            raise ValueError("upper_exclusive must be positive")
        width = max(1, (upper_exclusive.bit_length() + 7) // 8)
        sample_space = 1 << (8 * width)
        limit = sample_space - sample_space % upper_exclusive
        while True:
            value = int.from_bytes(self.take(width), "big")
            if value < limit:
                return value % upper_exclusive

    def randint(self, lower_inclusive: int, upper_inclusive: int) -> int:
        if upper_inclusive < lower_inclusive:
            raise ValueError("invalid inclusive range")
        return lower_inclusive + self.randbelow(upper_inclusive - lower_inclusive + 1)

    def shuffle(self, values: list[Any]) -> None:
        for index in range(len(values) - 1, 0, -1):
            other = self.randbelow(index + 1)
            values[index], values[other] = values[other], values[index]


def integer_parameter(
    parameters: Mapping[str, Any], name: str, *, minimum: int = 0, maximum: int = 10_000
) -> int:
    value = parameters.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum or value > maximum:
        raise ValueError(f"case parameter {name!r} must be an integer in [{minimum}, {maximum}]")
    return value


def lean_nat_list(values: Sequence[int]) -> str:
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in values):
        raise ValueError("Lean Nat lists require non-negative integers")
    return "[" + ", ".join(str(value) for value in values) + "]"


def lean_pair_list(values: Sequence[tuple[int, int]]) -> str:
    return "[" + ", ".join(f"({left}, {right})" for left, right in values) + "]"


def conjunction(terms: Sequence[str]) -> str:
    if not terms:
        return "True"
    return " ∧\n      ".join(terms)


def certificate_predicate(variable_names: Sequence[str], terms: Sequence[str]) -> str:
    pattern = ", ".join(variable_names)
    body = conjunction(terms)
    return f"""abbrev valid : List Nat -> Prop
  | [{pattern}] =>
      {body}
  | _ => False"""


def challenge_source(*, declarations: str, predicate: str, claim: str) -> str:
    return f"""import AMBenchPrelude

namespace Challenge

{declarations.rstrip()}

{predicate.rstrip()}

abbrev MathematicalClaim : Prop :=
  {claim}

def Target : Prop :=
  exists certificate : List Nat, valid certificate ∧ MathematicalClaim

end Challenge
"""


def solution_source(certificate: Sequence[int]) -> str:
    return f"""import Challenge

namespace AMBenchSolution

theorem proof : Challenge.Target := by
  refine Exists.intro {lean_nat_list(certificate)} ?_
  unfold Challenge.valid Challenge.MathematicalClaim
  decide

end AMBenchSolution
"""


@dataclass(frozen=True)
class LeanCaseBlueprint:
    title: str
    problem: Mapping[str, Any]
    challenge_source: str
    reference_certificate: tuple[int, ...]
    public_features: Mapping[str, int | str]
    metadata: Mapping[str, Any] = field(default_factory=dict)


CaseBuilder = Callable[[DeterministicStream, Mapping[str, Any]], LeanCaseBlueprint]
PublicSolver = Callable[[Mapping[str, Any]], tuple[int, ...]]
SolutionRenderer = Callable[[Sequence[int]], str]


@dataclass(frozen=True)
class CaseDefinition:
    case_id: str
    title: str
    parameters: Mapping[str, Any]
    builder: CaseBuilder
    solver: PublicSolver
    solution_renderer: SolutionRenderer = solution_source


def distinct_prime_factors(value: int) -> tuple[int, ...]:
    if value < 1:
        raise ValueError("prime factorization expects a positive integer")
    factors: list[int] = []
    divisor = 2
    remainder = value
    while divisor * divisor <= remainder:
        if remainder % divisor == 0:
            factors.append(divisor)
            while remainder % divisor == 0:
                remainder //= divisor
        divisor += 1
    if remainder > 1:
        factors.append(remainder)
    return tuple(factors)


def pow_mod(base: int, exponent: int, modulus: int) -> int:
    return pow(base, exponent, modulus)


def eval_poly_mod(coefficients: Sequence[int], x: int, modulus: int) -> int:
    result = 0
    for coefficient in reversed(coefficients):
        result = (result * x + coefficient) % modulus
    return result


__all__ = [
    "CaseDefinition",
    "DeterministicStream",
    "LeanCaseBlueprint",
    "PRELUDE_SOURCE",
    "PublicSolver",
    "SolutionRenderer",
    "certificate_predicate",
    "challenge_source",
    "conjunction",
    "distinct_prime_factors",
    "eval_poly_mod",
    "integer_parameter",
    "lean_nat_list",
    "lean_pair_list",
    "pow_mod",
    "solution_source",
]
