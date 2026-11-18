"""Fit to pallet: round KL/KB that keep the drawing and fit the pallet best."""

import pytest
from helpers import D, H, KB, KL, grid, pattern

from layerpattern.domain import validation as v
from layerpattern.domain.cancel import Cancelled
from layerpattern.domain.fitting import applicable_hints, fit_to_pallet, roundness
from layerpattern.domain.linear import LinearForm
from layerpattern.domain.model import DEFAULT_MAX_PACKAGES, Dimensions, Package
from layerpattern.domain.reconstruct import flip_y, reconstruct

HINT_3KL_4KB = LinearForm.of(3, -4)


def vmf15():
    """Pallet-formats.pdf, VMF 12 bottles: three rows of four standing cases on top of
    one row of three lying cases; both blocks are flush on the right in the drawing."""
    lying = [Package(KL * H + (KL + D) * c, KB * H, 0) for c in range(3)]
    standing = [Package(KB * H + (KB + D) * c, KB + D + KL * H + (KL + D) * r, 90)
                for r in range(3) for c in range(4)]
    return tuple(lying + standing)


def test_roundness_levels():
    assert [roundness(v) for v in (300, 250, 320, 305)] == [3, 2, 1, 0]


def test_vmf_keeps_the_drawing_and_fills_the_pallet():
    (best, *_rest) = fit_to_pallet(vmf15(), (HINT_3KL_4KB,), 1000, 1200, 0)
    assert (best.kl, best.kb) == (320, 240)
    assert (best.width, best.height) == (960, 1200)
    assert best.drawing_kept and best.overhang_x == best.overhang_y == 0


def test_without_the_hint_the_blocks_would_not_be_flush():
    (best, *_rest) = fit_to_pallet(vmf15(), (), 1000, 1200, 0)
    assert (best.kl, best.kb) != (320, 240)


def test_regular_grid_on_euro_pallet():
    (best, *_rest) = fit_to_pallet(grid(3, 2), (), 1200, 800, 0)
    assert (best.kl, best.kb) == (400, 400)


def test_rounder_value_wins_only_within_the_tolerance():
    # Three lying cases on a 1000 x 300 pallet: KB = 300; KL 330 leaves 10 mm, 300 leaves 100 mm.
    tight = fit_to_pallet(grid(3, 1), (), 1000, 300, 0, band=25)[0]
    loose = fit_to_pallet(grid(3, 1), (), 1000, 300, 0, band=100)[0]
    assert tight.kl == 330
    assert loose.kl == 300 and roundness(loose.kl) > roundness(tight.kl)


def test_overhang_is_allowed_but_counted():
    results = fit_to_pallet(grid(3, 2), (), 1200, 800, 20)
    assert results[0].overhang_x == 0                      # 380 x 380 fits inside
    assert any(r.overhang_x > 0 for r in results[1:])      # 390 x 390 overhangs, offered as alternative


def test_every_suggestion_is_a_valid_pattern():
    for r in fit_to_pallet(vmf15(), (HINT_3KL_4KB,), 1000, 1200, 20):
        dims = Dimensions(r.kl, r.kb, 20, 1000, 1200)
        assert v.check_pattern(pattern(vmf15(), dims=dims), DEFAULT_MAX_PACKAGES).valid
        assert r.kl % 10 == 0 and r.kb % 10 == 0 and r.kl >= r.kb


def test_unreachable_drawing_falls_back_and_says_so():
    # 2*KL = KB is an edge difference of this pattern, but contradicts KL >= KB.
    impossible = LinearForm.of(2, -1)
    assert applicable_hints(vmf15(), (impossible,)) == [(2, -1)]
    results = fit_to_pallet(vmf15(), (impossible,), 1000, 1200, 0)
    assert results and not results[0].drawing_kept


def test_hints_of_removed_edges_are_ignored():
    assert applicable_hints(vmf15(), (HINT_3KL_4KB,)) == [(3, -4)]
    assert applicable_hints(grid(3, 2), (HINT_3KL_4KB,)) == []


def test_cancel():
    with pytest.raises(Cancelled):
        fit_to_pallet(grid(3, 2), (), 1200, 800, 0, cancel=lambda: True)


def test_reconstruction_reads_the_proportion_from_the_drawing():
    # Pixel coordinates of the VMF pattern in the user's screenshot (Y down).
    cells = [(x0, y0, x1, y1) for x0, x1 in ((55, 172), (172, 289), (289, 405), (405, 521))
             for y0, y1 in ((49, 183), (183, 312), (312, 441))]
    cells += [(x0, 441, x1, 541) for x0, x1 in ((55, 210), (210, 366), (366, 521))]
    rec = reconstruct(flip_y(cells, 600.0), Dimensions())
    assert HINT_3KL_4KB in rec.hints
    (best, *_rest) = fit_to_pallet(rec.packages, rec.hints, 1000, 1200, 0)
    assert (best.kl, best.kb) == (320, 240)
