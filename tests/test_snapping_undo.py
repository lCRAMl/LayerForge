from helpers import D, H, KB, KL, grid, pattern

from layerforge.application.undo import Step, UndoStack
from layerforge.domain import snapping as s
from layerforge.domain import validation as v
from layerforge.domain.model import DEFAULT_MAX_PACKAGES, Dimensions, Project

DIMS = Dimensions()


def test_adjacent_right_is_found_near_cursor():
    refs = list(enumerate(grid(1, 1)))               # one lying package, x 0..600
    cands = s.axis_candidates("x", 0, refs, DIMS)
    best = s.resolve(cands, 920.0, radius_mm=40)     # right of it would be 600 + 20 + 300
    assert best.value == KL + D + KL * H
    assert best.strength == s.ADJACENT and best.text == "right of #1"


def test_nothing_within_radius_while_dragging():
    refs = list(enumerate(grid(1, 1)))
    assert s.resolve(s.axis_candidates("x", 0, refs, DIMS), 5000.0, radius_mm=40) is None


def test_ties_prefer_the_simplest_relation():
    # Same orientation and size: flush-left, flush-right and centred coincide.
    refs = list(enumerate(grid(1, 1)))
    cands = s.axis_candidates("x", 0, refs, DIMS)
    best = s.resolve(cands, 300.0, radius_mm=10)
    assert best.strength == s.FLUSH


def test_equal_forms_are_deduplicated():
    refs = list(enumerate(grid(1, 1)))
    cands = s.axis_candidates("y", 0, refs, DIMS)
    assert len({c.value for c in cands}) == len(cands)


def test_snap_package_builds_a_valid_neighbour():
    packages = grid(2, 1)
    moved, cx, cy = s.snap_package(packages, None, 0, (300.0, 640.0), DIMS)
    assert cy.text.startswith("above")
    report = v.check_pattern(pattern(packages + (moved,)), DEFAULT_MAX_PACKAGES)
    assert report.valid


def test_rotation_resnaps_at_same_spot():
    # A standing package placed where a lying one was: it snaps flush, not floating.
    packages = grid(2, 1)
    lying = packages[1]
    centre = (float(lying.x.value(600, 400, 20)), float(lying.y.value(600, 400, 20)))
    rotated, cx, _cy = s.snap_package(packages, 1, 90, centre, DIMS)
    assert rotated.orientation == 90
    assert cx.strength in (s.ADJACENT, s.FLUSH)


def test_first_package_sits_at_origin():
    p, cx, cy = s.snap_package((), None, 90, (1234.0, 99.0), DIMS)
    assert p.x == KB * H and p.y == KL * H and cx is None and cy is None


# --- undo --------------------------------------------------------------------

def test_undo_redo_and_clean_state():
    a, b, c = Project(name="a"), Project(name="b"), Project(name="c")
    stack = UndoStack()
    assert stack.is_clean() and not stack.can_undo()
    stack.push(Step("first", a, b))
    stack.push(Step("second", b, c))
    stack.mark_clean()
    assert stack.undo().before is b and not stack.is_clean()
    assert stack.redo_label() == "second"
    assert stack.redo().after is c and stack.is_clean()
    stack.undo()
    stack.push(Step("branch", b, a))        # discards "second"
    assert not stack.can_redo() and not stack.is_clean()
    stack.undo()
    stack.undo()
    assert not stack.can_undo()


def test_undo_limit_drops_oldest():
    stack = UndoStack(limit=3)
    projects = [Project(name=str(i)) for i in range(6)]
    for before, after in zip(projects, projects[1:]):
        stack.push(Step("x", before, after))
    count = 0
    while stack.can_undo():
        stack.undo()
        count += 1
    assert count == 3


# --- incremental validation --------------------------------------------------

def test_incremental_validator_matches_full_check():
    from layerforge.application.validator import ProjectValidator
    from layerforge.domain import operations as ops
    from dataclasses import replace
    from helpers import eu13

    project = Project()
    project, a = ops.add_pattern(project, eu13(), pattern_id=1)
    mirrored = tuple(replace(p, x=-p.x) for p in eu13())
    project, b = ops.add_pattern(project, mirrored, pattern_id=2)
    project, c = ops.add_pattern(project, grid(2, 1), pattern_id=3)
    project, d = ops.add_pattern(project, grid(2, 1), pattern_id=4)
    # add_pattern refuses a used PatternId; a damaged file could still contain one.
    project = project.with_pattern(replace(project.pattern(d), pattern_id=3))
    validator = ProjectValidator(DEFAULT_MAX_PACKAGES)
    fast = validator.reports(project)
    full = v.check_project(project, DEFAULT_MAX_PACKAGES)
    for uid in (a, b, c, d):
        assert {i.code for i in fast[uid].issues} == {i.code for i in full[uid].issues}
    assert validator.reports(project) is fast                 # same project: cached

    # Only the edited pattern object is checked again; the others come from the cache.
    from unittest import mock
    edited = ops.set_packages(project, c, grid(3, 1))
    with mock.patch("layerforge.application.validator.v.check_pattern",
                    wraps=v.check_pattern) as spy:
        again = validator.reports(edited)
    assert spy.call_count == 1
    assert again[a] == fast[a]
    assert not again[c].has(v.DUPLICATE_GEOMETRY)
    assert validator.export_blockers(edited)


def test_export_blockers_list_unverified_patterns():
    from layerforge.application.validator import ProjectValidator
    from layerforge.domain import operations as ops

    project, uid = ops.add_pattern(Project(), grid(2, 1), pattern_id=4)
    validator = ProjectValidator(DEFAULT_MAX_PACKAGES)
    assert validator.export_blockers(project) == ["Invalid patterns: 4."]      # no name yet
    project = ops.set_name(project, uid, "P4")
    assert validator.export_blockers(project) == ["Not verified: 4."]
    assert validator.export_blockers(ops.verify(project, uid)) == []
    assert validator.export_blockers(Project())
