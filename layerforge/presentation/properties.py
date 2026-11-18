"""Right-hand panel: pattern status, example values, selected package, display options."""

from __future__ import annotations

from dataclasses import replace

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup, QFrame, QGridLayout, QHBoxLayout, QLabel, QMenu, QScrollArea, QToolButton,
    QVBoxLayout, QWidget
)
from qt_controls_pyrs import (
    CompactButton, CompactCheckBox, CompactGroupBox, CompactIntField, CompactRadioButton,
    CompactResultGrid, HaloScrollBar
)

from layerforge.domain import operations as ops
from layerforge.domain.export_model import is_verified
from layerforge.domain.fitting import applicable_hints, fit_to_pallet
from layerforge.domain.geometry import Condition
from layerforge.domain.linear import LinearForm
from layerforge.domain.model import Dimensions
from layerforge.domain.rational import real_literal
from layerforge.presentation.editor.view import fmt_mm
from layerforge.presentation.theme import ERROR, OK, WARNING


class PackageGrid(CompactResultGrid):
    """One value per row: the formulas are too long for two columns."""

    COLUMNS = 1


DISPLAY_LABELS = (
    ("pallet", "Pallet"), ("sequence", "Sequence numbers"), ("orientation", "BaseOrientation"),
    ("guides", "Snap guides"), ("centres", "Package centres"), ("bbox", "Bounding box"),
    ("overhang", "Overhang"),
)


class PropertiesPanel(QScrollArea):
    verifyRequested = pyqtSignal()
    changeIdRequested = pyqtSignal()

    def __init__(self, session, controller, parent=None) -> None:
        super().__init__(parent)
        self.session = session
        self.ctrl = controller
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBar(HaloScrollBar(self))
        body = QWidget()
        self.setWidget(body)
        column = QVBoxLayout(body)
        column.setContentsMargins(6, 6, 6, 6)
        column.setSpacing(8)

        # --- pattern status -------------------------------------------------
        head = QHBoxLayout()
        self.title = QLabel("No pattern")
        font = self.title.font()
        font.setPointSizeF(font.pointSizeF() * 1.35)
        font.setBold(True)
        self.title.setFont(font)
        head.addWidget(self.title, 1)
        self.change_id = CompactButton("Change ID")
        self.change_id.clicked.connect(self.changeIdRequested)
        head.addWidget(self.change_id)
        column.addLayout(head)

        status = QHBoxLayout()
        self.state = QLabel()
        status.addWidget(self.state, 1)
        self.verify = CompactButton("Verify")
        self.verify.setToolTip("Verify the current pattern (Ctrl+Enter)")
        self.verify.clicked.connect(self.verifyRequested)
        status.addWidget(self.verify)
        column.addLayout(status)

        self.issues = QLabel()
        self.issues.setWordWrap(True)
        self.issues.setTextFormat(Qt.TextFormat.RichText)
        column.addWidget(self.issues)

        # --- example values -------------------------------------------------
        values = CompactGroupBox("Example values (not exported)")
        grid = QGridLayout(values)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(4)
        self.fields: dict[str, CompactIntField] = {}
        for row, (key, label, minimum) in enumerate((
                ("kl", "KL", 1), ("kb", "KB", 1), ("d", "D", 0),
                ("pallet_x", "Pallet width", 1), ("pallet_y", "Pallet length", 1))):
            field = CompactIntField("mm", minimum=minimum, maximum=99_999)
            field.spin.setKeyboardTracking(False)     # commit on Enter / focus loss only
            field.value_changed.connect(lambda _v, k=key: self._commit_dimension(k))
            grid.addWidget(QLabel(label), row, 0)
            grid.addWidget(field, row, 1)
            self.fields[key] = field
        self.swap = CompactButton("Swap pallet")
        self.swap.setToolTip("Exchange pallet width and length")
        self.swap.clicked.connect(self._swap_pallet)
        grid.addWidget(self.swap, 5, 1)
        # A value that only fits together with the next one (KL = 333 while KB is still
        # 400) waits here instead of being thrown away; see _commit_dimension.
        self.pending = QLabel()
        self.pending.setWordWrap(True)
        self.pending.hide()
        self.revert = CompactButton("Revert")
        self.revert.setToolTip("Discard the values that are not applied yet")
        self.revert.clicked.connect(self._drop_draft)
        self.revert.hide()
        grid.addWidget(self.pending, 6, 0, 1, 2)
        grid.addWidget(self.revert, 7, 1)
        self._draft: tuple[int, Dimensions] | None = None
        fit_row = QHBoxLayout()
        self.fit = CompactButton("Fit to pallet")
        self.fit.setToolTip("Suggest round KL and KB so the pattern fits the pallet best.\n"
                            "The arrangement, D and the pallet stay as they are.")
        self.fit.clicked.connect(self.fit_to_pallet)
        self.fit_more = QToolButton()
        self.fit_more.setText("Alternatives")
        self.fit_more.setToolTip("The next best suggestions of the last Fit to pallet")
        self.fit_more.setAutoRaise(True)
        self.fit_more.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.fit_more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.fit_menu = QMenu(self)
        self.fit_more.setMenu(self.fit_menu)
        self.fit_more.setEnabled(False)
        self._fit_for: int | None = None        # pattern uid the alternatives belong to
        fit_row.addWidget(self.fit)
        fit_row.addWidget(self.fit_more)
        grid.addLayout(fit_row, 8, 0, 1, 2)
        column.addWidget(values)

        # --- selected package -----------------------------------------------
        self.package = PackageGrid("Selected package")
        for key, label in (("seq", "Sequence"), ("orient", "BaseOrientation"), ("x", "X"),
                           ("y", "Y"), ("xmm", "X [mm]"), ("ymm", "Y [mm]")):
            self.package.add_row(key, label)
        self.package.add_separator()
        for key in ("KxL", "KxB", "KxD", "KyL", "KyB", "KyD"):
            self.package.add_row(key, key)
        column.addWidget(self.package)

        # --- display options ------------------------------------------------
        display = CompactGroupBox("Display")
        box = QVBoxLayout(display)
        box.setSpacing(2)
        mode = QHBoxLayout()
        self.symbolic = CompactRadioButton("Symbolic")
        self.numeric = CompactRadioButton("Numeric")
        group = QButtonGroup(self)
        group.addButton(self.symbolic)
        group.addButton(self.numeric)
        (self.numeric if controller.display["numeric"] else self.symbolic).setChecked(True)
        self.numeric.toggled.connect(lambda on: controller.set_display("numeric", on))
        mode.addWidget(self.symbolic)
        mode.addWidget(self.numeric)
        mode.addStretch(1)
        box.addLayout(mode)
        self.toggles: dict[str, CompactCheckBox] = {}
        for key, label in DISPLAY_LABELS:
            check = CompactCheckBox(label)
            check.setChecked(controller.display[key])
            check.toggled.connect(lambda on, k=key: controller.set_display(k, on))
            box.addWidget(check)
            self.toggles[key] = check
        column.addWidget(display)
        column.addStretch(1)

        session.projectChanged.connect(lambda *_: self.refresh())
        session.currentChanged.connect(lambda *_: self.refresh())
        controller.selectionChanged.connect(lambda *_: self.refresh_package())
        self.refresh()

    # ------------------------------------------------------------------ refresh

    def set_numeric(self, numeric: bool) -> None:
        (self.numeric if numeric else self.symbolic).setChecked(True)

    def refresh(self) -> None:
        pattern = self.session.current_pattern()
        enabled = pattern is not None
        for widget in (self.change_id, self.verify, self.swap, self.fit, *self.fields.values()):
            widget.setEnabled(enabled)
        if pattern is None or pattern.uid != self._fit_for:
            self.fit_menu.clear()
            self.fit_more.setEnabled(False)
            self._fit_for = None
        if pattern is None:
            self.title.setText("No pattern")
            self.state.setText("")
            self.issues.setText("")
            self.package.clear_values()
            return
        self.title.setText(f"Pattern {pattern.pattern_id}")
        report = self.session.report(pattern.uid)
        verified = is_verified(pattern)
        valid = report is not None and report.valid
        if verified and valid:
            self.state.setText(f"<span style='color:{OK}'>&#10004; Verified</span>")
        elif valid:
            self.state.setText("Valid · not verified")
        else:
            self.state.setText(f"<span style='color:{ERROR}'>Invalid</span>")
        self.verify.setEnabled(valid and not verified)
        lines = []
        if report is not None:
            for issue in report.blockers:
                lines.append(f"<span style='color:{ERROR}'>&#9632; {issue.message}</span>")
            for issue in report.notes:
                lines.append(f"<span style='color:{WARNING}'>&#9650; {issue.message}</span>")
            if report.conditions:
                lines.append("Coefficients valid while: "
                             + "; ".join(c.text() for c in report.conditions))
        ratios = applicable_hints(pattern.packages, pattern.hints)
        if ratios:
            lines.append("Drawing proportions: " + "; ".join(
                Condition(LinearForm.of(a, b)).text(ge="=") for a, b in ratios))
        lines.append(f"{len(pattern.packages)} packages")
        self.issues.setText("<br>".join(lines))
        if self._draft is not None and self._draft[0] != pattern.uid:
            self._draft = None                   # a draft belongs to the pattern it was typed for
        shown = self._draft[1] if self._draft is not None else pattern.dims
        for key, field in self.fields.items():
            field.set_value(getattr(shown, key))             # set_value emits nothing
        self._show_draft_note()
        self.refresh_package()

    def refresh_package(self) -> None:
        geo = self.ctrl.geo
        selected = self.ctrl.selected()
        if geo is None or len(selected) != 1 or not geo.relative:
            self.package.clear_values("–")
            self.package.setTitle("Selected package" if not selected else
                                  f"{len(selected)} packages selected")
            return
        index = selected[0]
        pkg = geo.pattern.packages[index]
        rx, ry = geo.relative[index]
        dims = geo.pattern.dims
        self.package.setTitle(f"Package #{index + 1}")
        self.package.set_value("seq", str(index + 1))
        self.package.set_value("orient", f"{pkg.orientation}")
        self.package.set_value("x", rx.text("·"))
        self.package.set_value("y", ry.text("·"))
        self.package.set_value("xmm", fmt_mm(float(rx.value(dims.kl, dims.kb, dims.d))))
        self.package.set_value("ymm", fmt_mm(float(ry.value(dims.kl, dims.kb, dims.d))))
        for key, value in zip(("KxL", "KxB", "KxD", "KyL", "KyB", "KyD"),
                              rx.coefficients() + ry.coefficients()):
            self.package.set_value(key, real_literal(value))

    # ------------------------------------------------------------------ edits

    def _commit_dimension(self, key: str) -> None:
        """A committed field (Enter, focus loss, arrows) is applied together with the others.

        Each field alone is always in range (the spin boxes enforce that). Only KL >= KB
        spans two fields, and it must not depend on the order of typing: lowering both
        KL and KB would otherwise be impossible when KL is typed first. So an
        inconsistent set is kept as a draft, the pattern keeps its last valid values,
        and the draft is applied as soon as it fits together.
        """
        pattern = self.session.current_pattern()
        if pattern is None:
            return
        base = self._draft[1] if self._draft is not None else pattern.dims
        dims = replace(base, **{key: self.fields[key].value()})
        self._apply_candidate(pattern, dims, f"Set {key.upper().replace('_', ' ')}")

    def _apply_candidate(self, pattern, dims: Dimensions, label: str) -> None:
        if dims == pattern.dims:
            self._drop_draft()
            return
        if not dims.is_valid():
            self._draft = (pattern.uid, dims)
            self._show_draft_note()
            self.session.notify(" ".join(dims.problems()) + f" Pattern {pattern.pattern_id} keeps "
                                f"KL {pattern.dims.kl} / KB {pattern.dims.kb} until the values fit.",
                                "warning")
            return
        self._draft = None
        self._show_draft_note()
        self._set_dims(pattern.uid, dims, label)

    def _drop_draft(self) -> None:
        self._draft = None
        pattern = self.session.current_pattern()
        if pattern is not None:
            for key, field in self.fields.items():
                field.set_value(getattr(pattern.dims, key))
        self._show_draft_note()

    def _show_draft_note(self) -> None:
        pending = self._draft is not None
        if pending:
            self.pending.setText(f"<span style='color:{WARNING}'>Not applied yet: "
                                 + " ".join(self._draft[1].problems()) + "</span>")
        self.pending.setVisible(pending)
        self.revert.setVisible(pending)

    def fit_to_pallet(self) -> None:
        """Suggest KL/KB (rule in domain/fitting.py) and apply the best as one undo step."""
        pattern = self.session.current_pattern()
        if pattern is None or not pattern.packages:
            return
        base = self._draft[1] if self._draft is not None else pattern.dims
        settings = self.session.settings
        results = fit_to_pallet(pattern.packages, pattern.hints, base.pallet_x, base.pallet_y,
                                base.d, settings.fit_step, settings.fit_band)
        if not results:
            self.session.notify("No KL/KB found that keeps this pattern valid on the pallet.", "warning")
            return
        self.fit_menu.clear()
        for result in results:
            action = self.fit_menu.addAction(result.summary())
            action.triggered.connect(lambda _c=False, r=result, b=base: self._apply_fit(pattern.uid, b, r))
        self.fit_more.setEnabled(len(results) > 1)
        self._fit_for = pattern.uid
        self._apply_fit(pattern.uid, base, results[0])

    def _apply_fit(self, uid: int, base: Dimensions, result) -> None:
        self._draft = None
        self._show_draft_note()
        dims = replace(base, kl=result.kl, kb=result.kb)
        self.session.execute(f"Fit to pallet {result.kl} x {result.kb}",
                             lambda p: ops.set_dimensions(p, uid, dims))
        message = "Fit to pallet: " + result.summary() + "."
        if not result.drawing_kept:
            self.session.notify(message + " The proportions of the drawing could not be kept "
                                "on this pallet.", "warning")
        else:
            self.session.notify(message)

    def _swap_pallet(self) -> None:
        pattern = self.session.current_pattern()
        if pattern is not None:
            base = self._draft[1] if self._draft is not None else pattern.dims
            self._apply_candidate(pattern, replace(base, pallet_x=base.pallet_y, pallet_y=base.pallet_x),
                                  "Swap pallet")

    def _set_dims(self, uid: int, dims: Dimensions, label: str) -> None:
        self.session.execute(label, lambda p: ops.set_dimensions(p, uid, dims))
        pattern = self.session.current_pattern()
        if pattern is not None and pattern.verified and not is_verified(pattern):
            self.session.notify("These example values change the exported coefficients; "
                                "verify the pattern again.", "warning")
        else:
            self.session.notify(f"{fmt_mm(dims.kl)} / {fmt_mm(dims.kb)} / {fmt_mm(dims.d)} mm "
                                "applied (example values only).")
