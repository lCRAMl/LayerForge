"""Linear forms in the three symbolic lengths KL, KB and D.

Every coordinate of the tool is such a form: ``l*KL + b*KB + d*D`` with exact
`Fraction` coefficients. Millimetres only appear when a form is evaluated for the
example values of a pattern.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from .rational import decimal_text

SYMBOLS = ("KL", "KB", "D")


def _frac(value) -> Fraction:
    return value if isinstance(value, Fraction) else Fraction(value)


@dataclass(frozen=True, slots=True)
class LinearForm:
    l: Fraction = Fraction(0)  # noqa: E741 - the symbol is called KL
    b: Fraction = Fraction(0)
    d: Fraction = Fraction(0)

    @staticmethod
    def of(l=0, b=0, d=0) -> LinearForm:  # noqa: E741
        return LinearForm(_frac(l), _frac(b), _frac(d))

    # --- arithmetic -------------------------------------------------------

    def __add__(self, other: LinearForm) -> LinearForm:
        return LinearForm(self.l + other.l, self.b + other.b, self.d + other.d)

    def __sub__(self, other: LinearForm) -> LinearForm:
        return LinearForm(self.l - other.l, self.b - other.b, self.d - other.d)

    def __neg__(self) -> LinearForm:
        return LinearForm(-self.l, -self.b, -self.d)

    def __mul__(self, factor) -> LinearForm:
        k = _frac(factor)
        return LinearForm(self.l * k, self.b * k, self.d * k)

    __rmul__ = __mul__

    def half(self) -> LinearForm:
        return self * Fraction(1, 2)

    # --- evaluation -------------------------------------------------------

    def value(self, kl: int, kb: int, d: int) -> Fraction:
        return self.l * kl + self.b * kb + self.d * d

    def coefficients(self) -> tuple[Fraction, Fraction, Fraction]:
        return (self.l, self.b, self.d)

    def is_zero(self) -> bool:
        return not (self.l or self.b or self.d)

    def complexity(self) -> tuple:
        """Sort key for "simplest relation": small coefficients, small denominators."""
        coeffs = self.coefficients()
        return (sum(abs(c) for c in coeffs), max(c.denominator for c in coeffs),
                tuple(abs(c) for c in coeffs))

    # --- text -------------------------------------------------------------

    def text(self, times: str = "*", zero: str = "0") -> str:
        """Readable sum, e.g. '-0.25*KL + 0.75*KB - 0.5*D'; coefficient 1 is omitted."""
        parts: list[str] = []
        for coeff, symbol in zip(self.coefficients(), SYMBOLS):
            if not coeff:
                continue
            magnitude = abs(coeff)
            term = symbol if magnitude == 1 else f"{decimal_text(magnitude)}{times}{symbol}"
            if not parts:
                parts.append(f"-{term}" if coeff < 0 else term)
            else:
                parts.append(f"{'-' if coeff < 0 else '+'} {term}")
        return " ".join(parts) if parts else zero

    def __str__(self) -> str:
        return self.text("·")


ZERO = LinearForm()
KL = LinearForm.of(l=1)
KB = LinearForm.of(b=1)
D = LinearForm.of(d=1)
