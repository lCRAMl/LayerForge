from fractions import Fraction

import pytest

from layerpattern.domain.linear import D, KB, KL, LinearForm
from layerpattern.domain.rational import (
    NotRepresentable, decimal_text, is_representable, parse_decimal, real_literal
)


@pytest.mark.parametrize("value, text", [
    (Fraction(1, 4), "0.25"),
    (Fraction(-1, 2), "-0.5"),
    (Fraction(1), "1.0"),
    (Fraction(0), "0.0"),
    (Fraction(-0), "0.0"),
    (Fraction(1, 16), "0.0625"),
    (Fraction(-37, 16), "-2.3125"),
    (Fraction(12), "12.0"),
])
def test_real_literals_are_exact_and_clean(value, text):
    assert real_literal(value) == text
    assert parse_decimal(text) == value


def test_float_artefacts_never_appear():
    # 0.1 + 0.15 in binary floating point would print 0.25000000000000006.
    value = Fraction(1, 10) * 0 + Fraction(1, 8) + Fraction(1, 8)
    assert real_literal(value) == "0.25"
    assert "0000" not in real_literal(Fraction(3, 16))


@pytest.mark.parametrize("value", [Fraction(1, 3), Fraction(1, 32), Fraction(3, 10)])
def test_policy_rejects_other_denominators(value):
    assert not is_representable(value)
    with pytest.raises(NotRepresentable):
        real_literal(value)


def test_parse_rejects_garbage_and_tiny_fractions():
    with pytest.raises(NotRepresentable):
        parse_decimal("abc")
    with pytest.raises(NotRepresentable):
        parse_decimal("0.03125")      # 1/32


def test_decimal_text_without_forced_point():
    assert decimal_text(Fraction(2)) == "2"
    assert decimal_text(Fraction(3, 2)) == "1.5"


def test_linear_form_arithmetic_and_value():
    f = KL * Fraction(1, 2) + KB - D * 2
    assert f == LinearForm.of(Fraction(1, 2), 1, -2)
    assert f.value(600, 400, 20) == 300 + 400 - 40
    assert -f + f == LinearForm()
    assert (KL + KB).half() == LinearForm.of(Fraction(1, 2), Fraction(1, 2), 0)


def test_formula_text_matches_spec_example():
    f = LinearForm.of(Fraction(-1, 4), Fraction(3, 4), Fraction(-1, 2))
    assert f.text() == "-0.25*KL + 0.75*KB - 0.5*D"
    assert (KL + D).text() == "KL + D"
    assert LinearForm().text() == "0"
    assert (-KB).text("·") == "-KB"


def test_complexity_prefers_small_coefficients():
    simple = KL + D
    complicated = KB * Fraction(3, 2) + D * Fraction(1, 2)
    assert simple.complexity() < complicated.complexity()
