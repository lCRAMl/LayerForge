"""Exact coefficient policy (decision D9).

Coefficients are `Fraction`s whose denominator is a power of two not larger than
`MAX_DENOMINATOR`. Such values have a finite decimal expansion (at most four places
for 1/16) and are exactly representable as IEEE single precision, so neither the
Excel sheet nor the PLC REAL ever sees a rounding artefact.

Inside the tool every coefficient is produced by exact arithmetic (sums of package
half-sizes, D, and one halving for the bounding-box centre), so the policy is only
*checked* there. Rationalisation of foreign numbers happens at import boundaries.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from fractions import Fraction

MAX_DENOMINATOR = 16


class NotRepresentable(ValueError):
    """A value violates the coefficient policy."""


def is_representable(value: Fraction) -> bool:
    den = value.denominator
    return den <= MAX_DENOMINATOR and den & (den - 1) == 0


def check(value: Fraction) -> Fraction:
    if not is_representable(value):
        raise NotRepresentable(f"{value} is not a multiple of 1/{MAX_DENOMINATOR} "
                               "with a power-of-two denominator")
    return value


def decimal_text(value: Fraction, *, force_point: bool = False) -> str:
    """Exact decimal notation, shortest form: 1/4 -> '0.25', 2 -> '2' ('2.0' with force_point)."""
    check(value)
    places = value.denominator.bit_length() - 1          # denominator == 2**places
    scaled = abs(value.numerator) * 5 ** places          # == abs(value) * 10**places
    digits = str(scaled).rjust(places + 1, "0")
    whole, frac = (digits[:-places], digits[-places:]) if places else (digits, "")
    frac = frac.rstrip("0")
    if not frac and force_point:
        frac = "0"
    text = f"{whole}.{frac}" if frac else whole
    # Never "-0.0": zero has no sign in the export.
    return f"-{text}" if value < 0 else text


def real_literal(value: Fraction) -> str:
    """Siemens REAL start value: always with a decimal point ('1.0', '-0.5', '0.0625')."""
    return decimal_text(value, force_point=True)


def parse_decimal(text: str) -> Fraction:
    """Inverse of `decimal_text`/`real_literal`; rejects values outside the policy."""
    try:
        value = Fraction(Decimal(text.strip()))
    except (InvalidOperation, ValueError) as exc:
        raise NotRepresentable(f"not a number: {text!r}") from exc
    return check(value)
