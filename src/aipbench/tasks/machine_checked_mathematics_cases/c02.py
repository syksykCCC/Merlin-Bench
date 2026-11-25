"""C02: shuffled Chinese-remainder reconstruction with quotient witnesses."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any, Final

from aipbench.tasks.machine_checked_mathematics_cases.common import (
    DeterministicStream,
    LeanCaseBlueprint,
    challenge_source,
    integer_parameter,
    lean_nat_list,
)

CASE_ID: Final = "c02"
TITLE: Final = "Shuffled CRT reconstruction certificate"
DEFAULT_PARAMETERS: Final[Mapping[str, Any]] = {
    "num_congruences": 12,
    "prime_floor": 1_000_000,
    "prime_window": 200_000,
}


def _is_prime(value: int) -> bool:
    if value < 2:
        return False
    if value % 2 == 0:
        return value == 2
    divisor = 3
    while divisor * divisor <= value:
        if value % divisor == 0:
            return False
        divisor += 2
    return True


def _next_prime(value: int) -> int:
    candidate = max(2, value)
    while not _is_prime(candidate):
        candidate += 1
    return candidate


def _integer_sequence(problem: Mapping[str, Any], name: str) -> tuple[int, ...]:
    raw = problem[name]
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise ValueError(f"CRT {name} must be a sequence")
    values: list[int] = []
    for item in raw:
        if isinstance(item, bool) or not isinstance(item, int):
            raise ValueError(f"CRT {name} must contain integers")
        values.append(item)
    return tuple(values)


def solve(problem: Mapping[str, Any]) -> tuple[int, ...]:
    moduli = _integer_sequence(problem, "moduli")
    residues = _integer_sequence(problem, "residues")
    if len(moduli) < 2 or len(moduli) != len(residues):
        raise ValueError("CRT moduli and residues must have one common nontrivial length")
    for index, (modulus, residue) in enumerate(zip(moduli, residues, strict=True)):
        if modulus <= 1 or residue < 0 or residue >= modulus:
            raise ValueError("CRT moduli and residues are out of range")
        if any(math.gcd(modulus, previous) != 1 for previous in moduli[:index]):
            raise ValueError("CRT moduli must be pairwise coprime")

    combined_modulus = 1
    solution = 0
    for modulus, residue in zip(moduli, residues, strict=True):
        correction = ((residue - solution) * pow(combined_modulus, -1, modulus)) % modulus
        solution += combined_modulus * correction
        combined_modulus *= modulus
    published_product = problem["modulus_product"]
    if (
        isinstance(published_product, bool)
        or not isinstance(published_product, int)
        or published_product != combined_modulus
    ):
        raise ValueError("CRT modulus product is inconsistent")
    quotients = tuple(
        (solution - residue) // modulus for modulus, residue in zip(moduli, residues, strict=True)
    )
    return solution, *quotients


def build(stream: DeterministicStream, parameters: Mapping[str, Any]) -> LeanCaseBlueprint:
    num_congruences = integer_parameter(parameters, "num_congruences", minimum=2, maximum=16)
    prime_floor = integer_parameter(parameters, "prime_floor", minimum=3, maximum=10_000_000)
    prime_window = integer_parameter(parameters, "prime_window", minimum=8, maximum=1_000_000)
    cursor = prime_floor + stream.randbelow(prime_window)
    moduli: list[int] = []
    stride = max(2, prime_window // num_congruences)
    for _ in range(num_congruences):
        modulus = _next_prime(cursor)
        moduli.append(modulus)
        cursor = modulus + 1 + stream.randbelow(stride)

    modulus_product = math.prod(moduli)
    lower = modulus_product // 3
    upper = (2 * modulus_product) // 3
    planted_solution = stream.randint(lower, upper)
    residues = [planted_solution % modulus for modulus in moduli]
    congruences = list(zip(moduli, residues, strict=True))
    stream.shuffle(congruences)
    moduli = [modulus for modulus, _ in congruences]
    residues = [residue for _, residue in congruences]
    problem = {
        "moduli": moduli,
        "residues": residues,
        "modulus_product": modulus_product,
    }
    certificate = solve(problem)
    if certificate[0] != planted_solution:
        raise AssertionError("public CRT solver did not recover the planted solution")

    declarations = f"""def moduli : List Nat := {lean_nat_list(moduli)}
def residues : List Nat := {lean_nat_list(residues)}
def modulusProduct : Nat := {modulus_product}

def congruencesHold (x : Nat) (quotients : List Nat) : Bool :=
  ((moduli.zip residues).zip quotients).all (fun equation =>
    x == equation.1.2 + equation.2 * equation.1.1)

abbrev ProductEncoded : Prop :=
  moduli.foldl (fun product modulus => product * modulus) 1 = modulusProduct"""
    predicate = """abbrev valid : List Nat -> Prop
  | x :: quotients =>
      0 < x ∧
      x < modulusProduct ∧
      quotients.length = moduli.length ∧
      congruencesHold x quotients = true
  | [] => False"""
    source = challenge_source(
        declarations=declarations,
        predicate=predicate,
        claim="ProductEncoded",
    )
    source = source.replace(
        "\nend Challenge\n",
        """

theorem submit (certificate : List Nat) (hValid : valid certificate) : Target := by
  exact Exists.intro certificate (And.intro hValid (by decide))

end Challenge
""",
    )
    return LeanCaseBlueprint(
        title=TITLE,
        problem=problem,
        challenge_source=source,
        reference_certificate=certificate,
        public_features={
            "congruences": num_congruences,
            "solution_bits": planted_solution.bit_length(),
        },
        metadata={
            "criterion": "normalized_crt_with_exact_quotients",
            "modulus_product_bits": modulus_product.bit_length(),
            "solution_digits": len(str(planted_solution)),
        },
    )


__all__ = ["CASE_ID", "DEFAULT_PARAMETERS", "TITLE", "build", "solve"]
