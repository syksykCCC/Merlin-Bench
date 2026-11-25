"""C06: a structured hidden-factor cube-root certificate.

The public relation is deliberately ordinary: exhibit a non-trivial
factorisation of a composite modulus together with a modular cube root.  The
maintainer reference remains public-only, but uses the frozen generation
family to recover the latent integer from the size of the modulus.  None of
that family information is included in the participant specification or the
public instance.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any, Final

from aipbench.tasks.machine_checked_mathematics_cases.common import (
    DeterministicStream,
    LeanCaseBlueprint,
    certificate_predicate,
    challenge_source,
    integer_parameter,
)

CASE_ID: Final = "c06"
TITLE: Final = "Composite cube-root certificate"
DEFAULT_PARAMETERS: Final[Mapping[str, Any]] = {"latent_bits": 128}

# These constants are maintainer-only family data.  They never enter the
# generated public problem or Challenge.lean.
_QUADRATIC_COEFFICIENT: Final = 997
_ASYMPTOTIC_ROOT_OFFSET: Final = _QUADRATIC_COEFFICIENT // 6
_RECOVERY_RADIUS: Final = 6
_MR_BASES: Final[tuple[int, ...]] = (
    2,
    3,
    5,
    7,
    11,
    13,
    17,
    19,
    23,
    29,
    31,
    37,
    41,
    43,
    47,
    53,
    59,
    61,
    67,
    71,
    73,
    79,
    83,
    89,
)


def _is_strong_probable_prime(value: int) -> bool:
    """Deterministic-for-generation multi-base Miller--Rabin screen."""

    if value < 2:
        return False
    for prime in _MR_BASES:
        if value % prime == 0:
            return value == prime
    odd_part = value - 1
    powers_of_two = 0
    while odd_part % 2 == 0:
        powers_of_two += 1
        odd_part //= 2
    for base in _MR_BASES:
        if base >= value:
            continue
        residue = pow(base, odd_part, value)
        if residue in (1, value - 1):
            continue
        for _ in range(powers_of_two - 1):
            residue = residue * residue % value
            if residue == value - 1:
                break
        else:
            return False
    return True


def _next_cube_permutation_prime(lower_bound: int) -> int:
    """Return the first screened prime above the bound with p = 2 (mod 3)."""

    candidate = max(5, lower_bound | 1)
    while candidate % 3 != 2:
        candidate += 2
    while not _is_strong_probable_prime(candidate):
        candidate += 6
    return candidate


def _family_factors(latent: int) -> tuple[int, int]:
    first = _next_cube_permutation_prime(latent**3 + 17 * latent + 29)
    second = _next_cube_permutation_prime(
        latent**3 + _QUADRATIC_COEFFICIENT * latent**2 + 19 * latent + 43
    )
    if first == second:
        raise AssertionError("the two structured factors must be distinct")
    return first, second


def _family_message(first: int, second: int, modulus: int) -> int:
    width = (modulus.bit_length() + 7) // 8
    first_bytes = first.to_bytes((first.bit_length() + 7) // 8, "big")
    second_bytes = second.to_bytes((second.bit_length() + 7) // 8, "big")
    material = bytearray()
    counter = 0
    while len(material) < width + 16:
        material.extend(
            hashlib.sha256(
                b"aipbench/t3-mcm/c06/family-message/v1\x00"
                + len(first_bytes).to_bytes(2, "big")
                + first_bytes
                + len(second_bytes).to_bytes(2, "big")
                + second_bytes
                + counter.to_bytes(4, "big")
            ).digest()
        )
        counter += 1
    lower = modulus // 3
    return lower + int.from_bytes(material, "big") % (modulus - lower)


def _integer_nth_root(value: int, degree: int) -> int:
    if value < 0 or degree < 1:
        raise ValueError("invalid integer-root input")
    if value < 2:
        return value
    lower = 1 << ((value.bit_length() - 1) // degree)
    upper = 1 << ((value.bit_length() + degree - 1) // degree + 1)
    while lower + 1 < upper:
        middle = (lower + upper) // 2
        if middle**degree <= value:
            lower = middle
        else:
            upper = middle
    return lower


def _recover_family(modulus: int) -> tuple[int, int, int]:
    approximate = _integer_nth_root(modulus, 6)
    # For the frozen 128-bit profile, expanding the sixth root of the product
    # gives latent + floor(997 / 6), with the remaining terms below one.  Tiny
    # oracle profiles are intentionally allowed a wider bounded scan.
    if modulus.bit_length() < 256:
        centre = approximate
        radius = 384
    else:
        centre = approximate - _ASYMPTOTIC_ROOT_OFFSET
        radius = _RECOVERY_RADIUS
    lower = max(2, centre - radius)
    upper = centre + radius
    for latent in range(lower, upper + 1):
        first, second = _family_factors(latent)
        if first * second == modulus:
            return latent, first, second
    # The bounded scan is the calibrated fast path.  This monotone fallback
    # preserves public-only solvability even after an unusually large
    # screened-prime gap invalidates the asymptotic constant-width estimate.
    lower = 2
    upper = approximate
    while lower <= upper:
        latent = (lower + upper) // 2
        first, second = _family_factors(latent)
        product = first * second
        if product == modulus:
            return latent, first, second
        if product < modulus:
            lower = latent + 1
        else:
            upper = latent - 1
    raise ValueError("public modulus is outside the frozen c06 family")


def _recover_factors(modulus: int) -> tuple[int, int]:
    _, first, second = _recover_family(modulus)
    return first, second


def solve(problem: Mapping[str, Any]) -> tuple[int, ...]:
    modulus = int(problem["modulus"])
    ciphertext = int(problem["ciphertext"])
    exponent = int(problem["exponent"])
    if exponent != 3 or not (0 <= ciphertext < modulus):
        raise ValueError("unsupported public cube-root instance")
    _, first, second = _recover_family(modulus)
    message = _family_message(first, second, modulus)
    if pow(message, exponent, modulus) != ciphertext:
        raise ValueError("recovered modular root does not verify")
    return first, second, message


def build(stream: DeterministicStream, parameters: Mapping[str, Any]) -> LeanCaseBlueprint:
    latent_bits = integer_parameter(parameters, "latent_bits", minimum=3, maximum=192)
    latent = (1 << (latent_bits - 1)) + stream.randbelow(1 << (latent_bits - 1))
    first, second = _family_factors(latent)
    modulus = first * second
    message = _family_message(first, second, modulus)
    exponent = 3
    ciphertext = pow(message, exponent, modulus)
    problem = {
        "modulus": modulus,
        "ciphertext": ciphertext,
        "exponent": exponent,
    }
    certificate = solve(problem)
    if certificate != (first, second, message):
        raise AssertionError("public-only recovery differs from the generated witness")

    predicate = certificate_predicate(
        ["firstFactor", "secondFactor", "root"],
        [
            "1 < firstFactor",
            "1 < secondFactor",
            "firstFactor < modulus",
            "secondFactor < modulus",
            "firstFactor * secondFactor = modulus",
            "root < modulus",
            "AMBenchPrelude.powMod root exponent modulus = ciphertext",
        ],
    )
    declarations = f"""def modulus : Nat := {modulus}
def ciphertext : Nat := {ciphertext}
def exponent : Nat := {exponent}

abbrev WellFormedInstance : Prop :=
  1 < modulus ∧ ciphertext < modulus ∧ exponent = 3"""
    return LeanCaseBlueprint(
        title=TITLE,
        problem=problem,
        challenge_source=challenge_source(
            declarations=declarations,
            predicate=predicate,
            claim="WellFormedInstance",
        ),
        reference_certificate=certificate,
        public_features={"certificate_entries": 3, "exponent": exponent},
        metadata={
            "criterion": "nontrivial_factorization_and_modular_cube_root",
            "modulus_bits": modulus.bit_length(),
        },
    )


__all__ = [
    "CASE_ID",
    "DEFAULT_PARAMETERS",
    "TITLE",
    "_family_factors",
    "_family_message",
    "_integer_nth_root",
    "_recover_factors",
    "build",
    "solve",
]
