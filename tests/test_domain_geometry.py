from dataclasses import replace
from fractions import Fraction

from helpers import D, H, KB, KL, eu13, form, grid, pattern, pkg

from layerforge.domain import validation as v
from layerforge.domain.export_model import fingerprint, package_rows
from layerforge.domain.geometry import (
    extent, normalized, overhang, relative_centers, validity_conditions
)
from layerforge.domain.model import DEFAULT_MAX_PACKAGES, Dimensions


def rows(packages, dims=None):
    return package_rows(pattern(packages, dims=dims))


def check(packages, dims=None, max_packages=DEFAULT_MAX_PACKAGES):
    return v.check_pattern(pattern(packages, dims=dims), max_packages)


def test_single_package_is_centred_at_zero():
    for x, y in [(form(), form()), (KL * 7, KB * -3 + D)]:
        ((o, kx, ky),) = rows([pkg(x, y)])
        assert kx.is_zero() and ky.is_zero() and o == 0
    assert check([pkg(KL, KB)]).valid


def test_two_lying_packages_side_by_side():
    (_, x1, y1), (_, x2, y2) = rows(grid(2, 1))
    assert x1 == form(-H, 0, -H) and x2 == form(H, 0, H)
    assert y1.is_zero() and y2.is_zero()
    assert check(grid(2, 1)).valid


def test_two_standing_packages_side_by_side():
    (o1, x1, _), (o2, x2, _) = rows(grid(2, 1, orientation=90))
    assert o1 == o2 == 90
    assert x1 == form(0, -H, -H) and x2 == form(0, H, H)


def test_two_lying_packages_stacked():
    (_, x1, y1), (_, _, y2) = rows(grid(1, 2))
    assert x1.is_zero()
    assert y1 == form(0, -H, -H) and y2 == form(0, H, H)


def test_mixed_orientations_eu13_by_hand():
    # Bounding box: width KL + D + KB, height 2KB + D (valid while 2KB + D >= KL).
    # Centre: ((KL + D + KB)/2, KB + D/2).
    (oa, xa, ya), (ob, xb, yb), (oc, xc, yc) = rows(eu13())
    assert (oa, ob, oc) == (0, 0, 90)
    assert xa == xb == form(0, -H, -H)
    assert ya == form(0, -H, -H) and yb == form(0, H, H)
    assert xc == form(H, 0, H)
    assert yc == form(-H, 1, H)
    assert check(eu13()).valid


def test_eu13_validity_condition_and_regime_flip():
    conditions = validity_conditions(eu13(), Dimensions())
    assert [c.text() for c in conditions] == ["2·KB + D ≥ KL"]

    # With KL = 900 the standing package defines the height: the centre moves and
    # every Y coefficient changes, so a verification of the old data is stale.
    base = pattern(eu13())
    verified = replace(base, verified=fingerprint(base))
    flipped = replace(verified, dims=Dimensions(kl=900))
    assert fingerprint(flipped) != verified.verified
    report = v.check_pattern(flipped, DEFAULT_MAX_PACKAGES)
    assert report.has(v.VERIFICATION_STALE) and report.valid


def test_conditions_that_always_hold_are_dropped():
    # A lying and a standing package side by side: height = KL because KL >= KB always.
    lying = pkg(KL * H, KB * H)
    standing = pkg(KL + D + KB * H, KL * H, 90)
    assert validity_conditions((lying, standing), Dimensions()) == []


def test_asymmetric_l_shape():
    packages = grid(2, 2, skip={(1, 1)})
    assert check(packages).valid
    (_, x0, y0), _, _ = rows(packages)
    assert x0 == form(-H, 0, -H) and y0 == form(0, -H, -H)


def test_quarter_coefficients_from_half_offset_brick():
    # Upper package centred on the right edge of the lower one (brick bond).
    lower = pkg(KL * H, KB * H)
    upper = pkg(KL, KB * Fraction(3, 2) + D)
    (_, x_low, _), (_, x_up, _) = rows((lower, upper))
    assert x_low == form(Fraction(-1, 4))
    assert x_up == form(Fraction(1, 4))
    assert check((lower, upper)).valid


def test_u_shape_is_valid():
    assert check(grid(3, 3, skip={(1, 1), (1, 2)})).valid


def test_ring_with_hole_is_valid():
    report = check(grid(3, 3, skip={(1, 1)}))
    assert report.valid
    centers = relative_centers(grid(3, 3, skip={(1, 1)}), Dimensions())
    assert len(centers) == 8


def test_overlap_is_blocking():
    a = pkg(KL * H, KB * H)
    b = pkg(KL, KB * H)
    report = check((a, b))
    assert report.has(v.OVERLAP) and not report.valid


def test_isolated_package_is_blocking():
    packages = grid(2, 1) + (pkg(KL * 5, KB * 5),)
    report = check(packages)
    assert report.has(v.DISCONNECTED)
    assert report.blockers[0].packages == (2,)


def test_diagonal_contact_does_not_connect():
    a = pkg(KL * H, KB * H)
    b = pkg(KL * Fraction(3, 2) + D, KB * Fraction(3, 2) + D)
    assert check((a, b)).has(v.DISCONNECTED)


def test_touching_without_gap_violates_clearance():
    a = pkg(KL * H, KB * H)
    b = pkg(KL * Fraction(3, 2), KB * H)          # right edge to left edge, no D
    report = check((a, b))
    assert report.has(v.CLEARANCE) and not report.has(v.OVERLAP)
    # With D = 0 the same arrangement is a proper neighbour relation.
    assert check((a, b), Dimensions(d=0)).valid


def test_package_count_boundary():
    assert check(grid(8, 8)).valid
    assert check(grid(8, 8) + (pkg(KL * H, KB * 8 + D * 8 + KB * H),)).has(v.TOO_MANY)
    assert check(grid(8, 8), max_packages=63).has(v.TOO_MANY)


def test_empty_pattern_and_invalid_dimensions():
    assert check(()).has(v.EMPTY)
    report = check(grid(2, 1), Dimensions(kl=300, kb=400))
    assert report.has(v.INVALID_DIMENSIONS) and not report.valid


def test_square_package_is_a_note_only():
    report = check(grid(2, 1), Dimensions(kl=400, kb=400))
    assert report.has(v.SQUARE_PACKAGE) and report.valid


def test_normalized_moves_origin_to_lower_left():
    packages = normalized([pkg(KL * 3, KB * -2)], Dimensions())
    box = extent(packages, Dimensions())
    assert box.left.is_zero() and box.bottom.is_zero()


def test_overhang():
    assert overhang(grid(2, 2), Dimensions()) == (Fraction(10), Fraction(10))
    assert overhang(grid(1, 1), Dimensions()) == (0, 0)
