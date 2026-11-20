from dataclasses import replace
from fractions import Fraction

from helpers import D, H, KB, KL, eu13, form, grid, pattern, pkg

from layerforge.domain import validation as v
from layerforge.domain.export_model import fingerprint, package_rows
from layerforge.domain.geometry import (
    corner_relative, extent, normalized, overhang, validity_conditions
)
from layerforge.domain.model import DEFAULT_MAX_PACKAGES, Dimensions


def rows(packages, dims=None):
    """(orientation, x, y) from the lower-left corner, in the order of `packages`."""
    dims = dims or Dimensions()
    return [(p.orientation, x, y) for p, (x, y) in zip(packages, corner_relative(packages, dims))]


def check(packages, dims=None, max_packages=DEFAULT_MAX_PACKAGES):
    return v.check_pattern(pattern(packages, dims=dims), max_packages)


def test_single_package_sits_half_its_size_from_the_corner():
    for x, y in [(form(), form()), (KL * 7, KB * -3 + D)]:
        ((o, kx, ky),) = rows([pkg(x, y)])
        assert kx == form(H) and ky == form(0, H) and o == 0
    ((o, kx, ky),) = rows([pkg(KL, KB, 90)])
    assert kx == form(0, H) and ky == form(H) and o == 90
    assert check([pkg(KL, KB)]).valid


def test_corner_positions_are_never_negative():
    # The positions are, single coefficients are not: the standing EU13 package sits
    # at Y = 2KB + D - KL/2.
    dims = Dimensions()
    for packages in (grid(3, 2), eu13(), grid(3, 3, skip={(1, 1)})):
        for _o, x, y in rows(packages):
            assert x.value(dims.kl, dims.kb, dims.d) > 0 and y.value(dims.kl, dims.kb, dims.d) > 0


def test_two_lying_packages_side_by_side():
    (_, x1, y1), (_, x2, y2) = rows(grid(2, 1))
    assert x1 == form(H) and x2 == form(3 * H, 0, 1)
    assert y1 == y2 == form(0, H)
    assert check(grid(2, 1)).valid


def test_two_standing_packages_side_by_side():
    (o1, x1, _), (o2, x2, _) = rows(grid(2, 1, orientation=90))
    assert o1 == o2 == 90
    assert x1 == form(0, H) and x2 == form(0, 3 * H, 1)


def test_two_lying_packages_stacked():
    (_, x1, y1), (_, _, y2) = rows(grid(1, 2))
    assert x1 == form(H)
    assert y1 == form(0, H) and y2 == form(0, 3 * H, 1)


def test_mixed_orientations_eu13_by_hand():
    # Lower-left corner: left edge of the lying packages, bottom edge of the lower one
    # (valid while 2KB + D >= KL, i.e. the standing package does not reach lower).
    (oa, xa, ya), (ob, xb, yb), (oc, xc, yc) = rows(eu13())
    assert (oa, ob, oc) == (0, 0, 90)
    assert xa == xb == form(H)
    assert ya == form(0, H) and yb == form(0, 3 * H, 1)
    assert xc == form(1, H, 1)
    assert yc == form(-H, 2, 1)
    assert check(eu13()).valid


def test_export_rows_are_in_the_automatic_order():
    # Rows bottom-up, each row left to right: lower lying, standing, upper lying.
    a, b, c = eu13()
    assert package_rows(pattern((b, c, a))) == rows((a, c, b))


def test_eu13_validity_condition_and_regime_flip():
    conditions = validity_conditions(eu13(), Dimensions())
    assert [c.text() for c in conditions] == ["2·KB + D ≥ KL"]

    # With KL = 900 the standing package reaches lower than the lying ones: the
    # reference corner moves and every Y coefficient changes, so a verification of
    # the old data is stale.
    base = pattern(eu13())
    verified = replace(base, verified=fingerprint(base))
    flipped = replace(verified, dims=Dimensions(kl=900))
    assert fingerprint(flipped) != verified.verified
    report = v.check_pattern(flipped, DEFAULT_MAX_PACKAGES)
    assert report.has(v.VERIFICATION_STALE) and report.valid


def test_right_and_top_edges_give_no_condition():
    # The standing package may or may not be the highest (2KB + D vs KL), but only
    # the lower-left corner is the reference, so nothing has to hold.
    a = pkg(KL * H, KB * H)
    b = pkg(KL * H, KB * Fraction(3, 2) + D)
    c = pkg(KL + D + KB * H, KL * H, 90)
    assert validity_conditions((a, b, c), Dimensions()) == []


def test_conditions_that_always_hold_are_dropped():
    # A lying and a standing package side by side: height = KL because KL >= KB always.
    lying = pkg(KL * H, KB * H)
    standing = pkg(KL + D + KB * H, KL * H, 90)
    assert validity_conditions((lying, standing), Dimensions()) == []


def test_asymmetric_l_shape():
    packages = grid(2, 2, skip={(1, 1)})
    assert check(packages).valid
    (_, x0, y0), (_, x1, y1), (_, x2, y2) = rows(packages)
    assert (x0, y0) == (form(H), form(0, H))
    assert (x1, y1) == (form(3 * H, 0, 1), form(0, H))
    assert (x2, y2) == (form(H), form(0, 3 * H, 1))


def test_half_offset_brick():
    # Upper package centred on the right edge of the lower one (brick bond).
    lower = pkg(KL * H, KB * H)
    upper = pkg(KL, KB * Fraction(3, 2) + D)
    (_, x_low, _), (_, x_up, _) = rows((lower, upper))
    assert x_low == form(H)
    assert x_up == form(1)
    assert check((lower, upper)).valid


def test_u_shape_is_valid():
    assert check(grid(3, 3, skip={(1, 1), (1, 2)})).valid


def test_ring_with_hole_is_valid():
    report = check(grid(3, 3, skip={(1, 1)}))
    assert report.valid
    centers = corner_relative(grid(3, 3, skip={(1, 1)}), Dimensions())
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
