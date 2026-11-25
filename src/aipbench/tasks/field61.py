"""Canonical arithmetic helpers for the Tier-2 ``field61/hex-v1`` codec.

The JSON representation is deliberately a string: ``2**61 - 1`` exceeds the
JavaScript safe-integer range.  Coefficient vectors are always stored in
increasing-power order.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Final

MODULUS: Final = (1 << 61) - 1
HEX_WIDTH: Final = 16
CODEC_NAME: Final = "field61/hex-v1"


def encode_field(value: int) -> str:
    """Encode one canonical field element."""

    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < MODULUS:
        raise ValueError("field element must be an integer in [0, 2^61-1)")
    return f"{value:0{HEX_WIDTH}x}"


def decode_field(value: object) -> int:
    """Strictly decode one ``field61/hex-v1`` value."""

    if not isinstance(value, str) or len(value) != HEX_WIDTH:
        raise ValueError("field element must be a 16-character lowercase hex string")
    if any(character not in "0123456789abcdef" for character in value):
        raise ValueError("field element is not canonical lowercase hexadecimal")
    decoded = int(value, 16)
    if decoded >= MODULUS:
        raise ValueError("field element is outside the canonical residue range")
    return decoded


def add_polynomials(left: Sequence[int], right: Sequence[int]) -> list[int]:
    """Return ``left + right`` modulo the field prime."""

    size = max(len(left), len(right))
    result = [0] * size
    for index in range(size):
        result[index] = (
            (left[index] if index < len(left) else 0) + (right[index] if index < len(right) else 0)
        ) % MODULUS
    return trim_polynomial(result)


def scale_polynomial(polynomial: Sequence[int], scalar: int) -> list[int]:
    """Multiply all coefficients by ``scalar`` modulo the field prime."""

    return trim_polynomial([(coefficient * scalar) % MODULUS for coefficient in polynomial])


def multiply_polynomials(left: Sequence[int], right: Sequence[int]) -> list[int]:
    """Return the coefficient convolution modulo the field prime."""

    if not left or not right:
        return [0]
    result = [0] * (len(left) + len(right) - 1)
    for left_index, left_coefficient in enumerate(left):
        if left_coefficient == 0:
            continue
        for right_index, right_coefficient in enumerate(right):
            result[left_index + right_index] = (
                result[left_index + right_index] + left_coefficient * right_coefficient
            ) % MODULUS
    return trim_polynomial(result)


def trim_polynomial(polynomial: Iterable[int]) -> list[int]:
    """Remove non-semantic high zeroes while retaining one zero coefficient."""

    result = [coefficient % MODULUS for coefficient in polynomial]
    while len(result) > 1 and result[-1] == 0:
        result.pop()
    return result or [0]


def evaluate_polynomial(coefficients: Sequence[int], point: int) -> int:
    """Evaluate an increasing-power coefficient vector by Horner's rule."""

    result = 0
    for coefficient in reversed(coefficients):
        result = (result * point + coefficient) % MODULUS
    return result


def interpolate_consecutive(values: Sequence[int]) -> list[int]:
    """Interpolate at points ``0, 1, ..., len(values)-1``.

    The routine uses explicit Lagrange basis polynomials.  Tier-2 degree caps
    are small, so this quadratic implementation is preferable to a less
    transparent fast interpolation routine.
    """

    if not values:
        raise ValueError("at least one interpolation value is required")
    result = [0]
    for index, raw_value in enumerate(values):
        numerator = [1]
        denominator = 1
        for other in range(len(values)):
            if other == index:
                continue
            numerator = multiply_polynomials(numerator, [(-other) % MODULUS, 1])
            denominator = (denominator * (index - other)) % MODULUS
        scale = (raw_value % MODULUS) * pow(denominator, MODULUS - 2, MODULUS)
        result = add_polynomials(result, scale_polynomial(numerator, scale % MODULUS))
    return trim_polynomial(result)


__all__ = [
    "CODEC_NAME",
    "HEX_WIDTH",
    "MODULUS",
    "add_polynomials",
    "decode_field",
    "encode_field",
    "evaluate_polynomial",
    "interpolate_consecutive",
    "multiply_polynomials",
    "scale_polynomial",
    "trim_polynomial",
]
