from dataclasses import replace
from datetime import datetime

import pytest
from helpers import H, KB, KL, eu13, form, grid, pattern, pkg

from layerforge.domain import operations as ops
from layerforge.domain import validation as v
from layerforge.domain.duplicates import compare
from layerforge.domain.export_model import (
    TiaNames, build_snapshot, fingerprint, is_verified, package_rows
)
from layerforge.domain.model import DEFAULT_MAX_PACKAGES, Dimensions, Project
from layerforge.domain.sequence import auto_order, moved, reordered
from layerforge.domain.transform import rotate_packages

DIMS = Dimensions()


def coeffs(packages):
    return [(o, x, y) for o, x, y in package_rows(pattern(packages))]


# --- rotation ----------------------------------------------------------------

def test_quarter_turn_maps_x_y_and_swaps_orientation():
    before = coeffs(eu13())
    after = coeffs(rotate_packages(eu13(), 1, DIMS))
    for (o0, x0, y0), (o1, x1, y1) in zip(before, after):
        assert x1 == -y0 and y1 == x0
        assert o1 == (90 if o0 == 0 else 0)


def test_half_and_three_quarter_turns():
    before = coeffs(eu13())
    half = coeffs(rotate_packages(eu13(), 2, DIMS))
    three = coeffs(rotate_packages(eu13(), 3, DIMS))
    for (o0, x0, y0), (o2, x2, y2), (o3, x3, y3) in zip(before, half, three):
        assert (x2, y2, o2) == (-x0, -y0, o0)
        assert (x3, y3) == (y0, -x0) and o3 != o0


def test_four_quarter_turns_are_identity_and_sequence_is_kept():
    packages = eu13()
    turned = packages
    for _ in range(4):
        turned = rotate_packages(turned, 1, DIMS)
    assert coeffs(turned) == coeffs(packages)
    # The standing package stays third in the sequence through every rotation.
    assert [o for o, *_ in coeffs(rotate_packages(packages, 2, DIMS))] == [0, 0, 90]


# --- duplicates and mirrors --------------------------------------------------

def test_duplicate_independent_of_sequence():
    a = pattern(eu13(), uid=1, pattern_id=1)
    b = pattern(tuple(reversed(eu13())), uid=2, pattern_id=2)
    duplicates, similar = compare([a, b])
    assert duplicates == {1: [2], 2: [1]}
    assert similar == {}


def test_duplicate_independent_of_translation():
    shifted = tuple(p.moved(KL * 5, KB * -3) for p in eu13())
    duplicates, _ = compare([pattern(eu13(), uid=1), pattern(shifted, uid=2, pattern_id=2)])
    assert duplicates


def test_rotated_pattern_is_not_a_duplicate():
    rotated = rotate_packages(eu13(), 1, DIMS)
    duplicates, similar = compare([pattern(eu13(), uid=1), pattern(rotated, uid=2, pattern_id=2)])
    assert duplicates == {} and similar == {}


def test_mirrored_pattern_is_similar_not_duplicate():
    mirrored = tuple(replace(p, x=-p.x) for p in eu13())
    project = Project(patterns=(pattern(eu13(), uid=1, pattern_id=1),
                                pattern(mirrored, uid=2, pattern_id=2)))
    reports = v.check_project(project, DEFAULT_MAX_PACKAGES)
    for uid in (1, 2):
        assert reports[uid].has(v.MIRROR_SIMILAR)
        assert not reports[uid].has(v.DUPLICATE_GEOMETRY)
        assert reports[uid].valid


def test_symmetric_pattern_is_not_similar_to_itself():
    _, similar = compare([pattern(grid(2, 2), uid=1)])
    assert similar == {}


def test_exact_duplicate_blocks_both_patterns():
    project = Project(patterns=(pattern(grid(2, 1), uid=1, pattern_id=1),
                                pattern(grid(2, 1), uid=2, pattern_id=5)))
    reports = v.check_project(project, DEFAULT_MAX_PACKAGES)
    assert reports[1].has(v.DUPLICATE_GEOMETRY) and not reports[1].valid
    assert "5" in reports[1].blockers[0].message


def test_duplicate_pattern_id_is_blocking():
    project = Project(patterns=(pattern(grid(2, 1), uid=1, pattern_id=4),
                                pattern(grid(1, 2), uid=2, pattern_id=4)))
    reports = v.check_project(project, DEFAULT_MAX_PACKAGES)
    assert reports[1].has(v.DUPLICATE_ID) and reports[2].has(v.DUPLICATE_ID)


# --- sequence ----------------------------------------------------------------

def test_auto_order_rows_bottom_up_left_to_right():
    packages = grid(3, 2)
    shuffled = reordered(packages, [5, 2, 0, 4, 1, 3])
    assert auto_order(shuffled, DIMS) == packages


def test_auto_order_eu13():
    a, b, c = eu13()
    # Bottom edges: a = 0, c = 2KB + D - KL = 220, b = KB + D = 420.
    assert auto_order((c, b, a), DIMS) == (a, c, b)


def test_sequence_moves_and_reorder_validation():
    packages = grid(3, 1)
    assert moved(packages, 0, 2) == (packages[1], packages[2], packages[0])
    with pytest.raises(ValueError):
        reordered(packages, [0, 0, 1])


def test_sequence_is_part_of_the_fingerprint():
    p = pattern(grid(2, 1))
    swapped = p.with_packages(reordered(p.packages, [1, 0]))
    assert fingerprint(p) != fingerprint(swapped)


# --- project operations ------------------------------------------------------

def test_new_pattern_ids_are_highest_plus_one():
    project = Project()
    project, _ = ops.add_pattern(project, grid(1, 1), pattern_id=3)
    project, uid = ops.add_pattern(project, grid(2, 1))
    assert project.pattern(uid).pattern_id == 4
    project, _ = ops.add_pattern(project, grid(1, 2), pattern_id=99)
    project, uid = ops.add_pattern(project, grid(3, 1))
    assert project.pattern(uid).pattern_id == 1        # 99 taken: lowest free


def test_change_pattern_id_rules():
    project = Project()
    project, a = ops.add_pattern(project, grid(1, 1), pattern_id=1)
    project, b = ops.add_pattern(project, grid(2, 1), pattern_id=2)
    project = ops.verify(project, a)
    assert is_verified(project.pattern(a))
    with pytest.raises(ops.OperationError):
        ops.change_pattern_id(project, a, 2)
    with pytest.raises(ops.OperationError):
        ops.change_pattern_id(project, a, 100)
    with pytest.raises(ops.OperationError):
        ops.change_pattern_id(project, a, 0)
    changed = ops.change_pattern_id(project, a, 7)
    assert changed.pattern(a).pattern_id == 7
    assert not is_verified(changed.pattern(a))


def test_dimension_change_keeps_verification_geometry_change_drops_it():
    project, uid = ops.add_pattern(Project(), grid(2, 2))
    project = ops.verify(project, uid)
    kept = ops.set_dimensions(project, uid, Dimensions(kl=700, kb=500, d=10))
    assert is_verified(kept.pattern(uid))
    dropped = ops.set_packages(project, uid, grid(2, 1))
    assert not is_verified(dropped.pattern(uid))
    with pytest.raises(ops.OperationError):
        ops.set_dimensions(project, uid, Dimensions(kl=100, kb=200))


def test_rotated_copy_gets_new_id_and_sits_after_original():
    project, uid = ops.add_pattern(Project(), eu13(), pattern_id=5)
    project, _ = ops.add_pattern(project, grid(2, 1), pattern_id=9)
    project, copy_uid = ops.rotated_copy(project, uid, 1)
    assert project.pattern(copy_uid).pattern_id == 10
    assert project.index_of(copy_uid) == project.index_of(uid) + 1
    reports = v.check_project(project, DEFAULT_MAX_PACKAGES)
    assert reports[copy_uid].valid


def test_list_order_is_independent_of_ids():
    project = Project()
    for pid in (5, 2, 9):
        project, _ = ops.add_pattern(project, grid(pid % 3 + 1, 1), pattern_id=pid)
    first = project.patterns[0].uid
    project = ops.move_in_list(project, first, 2)
    assert [p.pattern_id for p in project.patterns] == [2, 9, 5]


def test_pdf_references():
    project, a = ops.add_pdf(Project(), "C:/x/a.pdf")
    project, again = ops.add_pdf(project, "C:/x/a.pdf")
    project, b = ops.add_pdf(project, "C:/x/b.pdf")
    assert a == again and b == a + 1
    project = ops.relink_pdf(project, a, "D:/new/a.pdf")
    assert project.pdf(a).path == "D:/new/a.pdf"


# --- export snapshot ---------------------------------------------------------

def test_flat_package_list_with_id_gaps():
    project = Project()
    project, _ = ops.add_pattern(project, grid(3, 1), pattern_id=7)
    project, _ = ops.add_pattern(project, grid(1, 1), pattern_id=1)
    project, _ = ops.add_pattern(project, grid(2, 1), pattern_id=3)
    snap = build_snapshot(project, TiaNames(), datetime(2026, 11, 18, 12, 0))

    assert [(r.pattern_id, r.first_index, r.count) for r in snap.patterns] == \
        [(1, 1, 1), (3, 2, 2), (7, 4, 3)]
    assert [r.global_index for r in snap.packages] == list(range(1, 7))
    assert [(r.pattern_id, r.sequence) for r in snap.packages] == \
        [(1, 1), (3, 1), (3, 2), (7, 1), (7, 2), (7, 3)]
    table = snap.index_table()
    assert len(table) == 99
    assert table[0] == (1, 1) and table[1] == (0, 0) and table[2] == (2, 2) and table[6] == (4, 3)
    # Access rule: FirstPackageIndex + Sequence - 1
    first, _ = table[6]
    assert snap.packages[first + 2 - 1 - 1].sequence == 2


def test_deleting_a_pattern_compacts_the_package_array():
    project = Project()
    project, a = ops.add_pattern(project, grid(2, 1), pattern_id=1)
    project, _ = ops.add_pattern(project, grid(3, 1), pattern_id=2)
    project = ops.delete_pattern(project, a)
    snap = build_snapshot(project, TiaNames(), datetime(2026, 1, 1))
    assert snap.index_table()[0] == (0, 0)
    assert snap.index_table()[1] == (1, 3)


def test_tia_name_rules():
    assert TiaNames().problems() == []
    assert TiaNames(db="1abc").problems()
    assert TiaNames(db="BEGIN").problems()
    assert TiaNames(db="UDT_LayerPackage").problems()


def test_quarter_coefficient_survives_into_snapshot():
    lower = pkg(KL * H, KB * H)
    upper = pkg(KL, KB * 3 * H)                    # touching, D = 0
    project, uid = ops.add_pattern(Project(), (lower, upper), dims=Dimensions(d=0))
    assert v.check_pattern(project.pattern(uid), DEFAULT_MAX_PACKAGES).valid
    snap = build_snapshot(project, TiaNames(), datetime(2026, 1, 1))
    assert snap.packages[0].kx == form(-0.25)
