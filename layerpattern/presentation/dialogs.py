"""Modal dialogs - only where a decision or a destructive confirmation is needed."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QLabel,
    QLayout, QMessageBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
)
from qt_controls_pyrs import (
    CompactButton, CompactCheckBox, CompactDropdown, CompactGroupBox, CompactIntField,
    CompactLineEdit
)

from layerpattern.application.export_service import ExportRequest, output_files, safe_base_name
from layerpattern.domain.export_model import TiaNames, package_rows
from layerpattern.domain.model import MAX_PATTERN_ID, MIN_PATTERN_ID, Dimensions, Pattern
from layerpattern.domain.validation import PatternReport
from layerpattern.presentation.settings import FIT_STEPS, SENSITIVITIES
from layerpattern.presentation.theme import ERROR, OK, WARNING


def ask_unsaved(parent: QWidget, what: str) -> str:
    """'save', 'discard' or 'cancel'."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle("Unsaved changes")
    box.setText(f"{what} has unsaved changes.")
    box.setInformativeText("Do you want to save them?")
    box.setStandardButtons(QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
                           | QMessageBox.StandardButton.Cancel)
    box.setDefaultButton(QMessageBox.StandardButton.Save)
    answer = box.exec()
    return {QMessageBox.StandardButton.Save: "save",
            QMessageBox.StandardButton.Discard: "discard"}.get(answer, "cancel")


def confirm(parent: QWidget, title: str, text: str, detail: str = "", strong: bool = False) -> bool:
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning if strong else QMessageBox.Icon.Question)
    box.setWindowTitle(title)
    box.setText(text)
    if detail:
        box.setInformativeText(detail)
    box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
    box.setDefaultButton(QMessageBox.StandardButton.Cancel if strong else QMessageBox.StandardButton.Yes)
    return box.exec() == QMessageBox.StandardButton.Yes


def show_details(parent: QWidget, message: str, details: str) -> None:
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Information)
    box.setWindowTitle("Details")
    box.setText(message)
    box.setDetailedText(details)
    box.exec()


class Message(QLabel):
    """Error line of a form. Hidden while empty, so it takes no room."""

    def __init__(self) -> None:
        super().__init__()
        self.setWordWrap(True)
        self.hide()

    def set_error(self, text: str) -> None:
        self.setText(f"<span style='color:{ERROR}'>{text}</span>" if text else "")
        self.setVisible(bool(text))


def _fit_to_content(layout: QLayout) -> None:
    # Without this a word-wrapping label lets the dialog open taller than its content,
    # and the surplus collects as an empty band above the buttons.
    layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)


def _buttons(dialog: QDialog, ok_text: str) -> QDialogButtonBox:
    buttons = QDialogButtonBox()
    ok = CompactButton(ok_text)
    cancel = CompactButton("Cancel")
    buttons.addButton(ok, QDialogButtonBox.ButtonRole.AcceptRole)
    buttons.addButton(cancel, QDialogButtonBox.ButtonRole.RejectRole)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    ok.setDefault(True)
    return buttons


class VerifyDialog(QDialog):
    """Summary shown before a pattern is marked as verified."""

    def __init__(self, pattern: Pattern, report: PatternReport, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Verify pattern {pattern.pattern_id}")
        self.resize(640, 520)
        layout = QVBoxLayout(self)
        rows = package_rows(pattern)
        checks = [
            ("PatternId", str(pattern.pattern_id)),
            ("Packages", str(len(rows))),
            ("Sequence", f"complete, 1..{len(rows)}"),
            ("Coefficients", "valid (multiples of 1/16)"),
            ("Overlaps", "none"),
            ("Neighbour graph", "connected"),
        ]
        text = "".join(f"<tr><td>{k}</td><td style='padding-left:14px;color:{OK}'>&#10004; {v}</td></tr>"
                       for k, v in checks)
        notes = "".join(f"<p style='color:{WARNING}'>&#9650; {i.message}</p>" for i in report.notes)
        if report.conditions:
            notes += ("<p>Coefficients are valid for the PLC while: <b>"
                      + "; ".join(c.text() for c in report.conditions) + "</b></p>")
        info = QLabel(f"<table>{text}</table>{notes}<p>Example values used for this check: "
                      f"KL {pattern.dims.kl}, KB {pattern.dims.kb}, D {pattern.dims.d} mm. "
                      "Different PLC values must be checked again in this tool.</p>")
        info.setWordWrap(True)
        layout.addWidget(info)
        table = QTableWidget(len(rows), 4)
        table.setHorizontalHeaderLabels(["Seq", "BaseOrientation", "X", "Y"])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for r, (orientation, x, y) in enumerate(rows):
            for c, value in enumerate((str(r + 1), str(orientation), x.text(), y.text())):
                table.setItem(r, c, QTableWidgetItem(value))
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(table, 1)
        layout.addWidget(_buttons(self, "Verify"))


class ChangeIdDialog(QDialog):
    def __init__(self, pattern: Pattern, used: set[int], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Change PatternId")
        self.used = used - {pattern.pattern_id}
        layout = QVBoxLayout(self)
        warning = QLabel(f"<span style='color:{WARNING}'>PLC programs and recipes may refer to "
                         f"PatternId {pattern.pattern_id}. Changing it also resets the "
                         "verification.</span>")
        warning.setWordWrap(True)
        layout.addWidget(warning)
        form = QFormLayout()
        self.field = CompactIntField("", minimum=MIN_PATTERN_ID, maximum=MAX_PATTERN_ID,
                                     value=pattern.pattern_id)
        form.addRow("New PatternId", self.field)
        layout.addLayout(form)
        self.error = Message()
        layout.addWidget(self.error)
        layout.addWidget(_buttons(self, "Change"))
        _fit_to_content(layout)
        self.field.value_changed.connect(lambda _v: self._check())
        self._check()

    def _check(self) -> bool:
        taken = self.field.value() in self.used
        self.error.set_error(f"PatternId {self.field.value()} is already in use." if taken else "")
        return not taken

    def accept(self) -> None:
        if self._check():
            super().accept()

    def value(self) -> int:
        return self.field.value()


class DimensionsDialog(QDialog):
    """KL/KB/D (and pallet) used to rebuild patterns from a generated DB."""

    def __init__(self, title: str, intro: str, dims: Dimensions, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        layout = QVBoxLayout(self)
        label = QLabel(intro)
        label.setWordWrap(True)
        layout.addWidget(label)
        form = QFormLayout()
        self.fields = {}
        for key, text, minimum in (("kl", "KL", 1), ("kb", "KB", 1), ("d", "D", 0),
                                   ("pallet_x", "Pallet width", 1), ("pallet_y", "Pallet length", 1)):
            field = CompactIntField("mm", minimum=minimum, maximum=99_999, value=getattr(dims, key))
            form.addRow(text, field)
            self.fields[key] = field
        layout.addLayout(form)
        self.error = Message()
        layout.addWidget(self.error)
        layout.addWidget(_buttons(self, "OK"))
        _fit_to_content(layout)

    def dimensions(self) -> Dimensions:
        return Dimensions(**{k: f.value() for k, f in self.fields.items()})

    def accept(self) -> None:
        problems = self.dimensions().problems()
        if problems:
            self.error.set_error(" ".join(problems))
            return
        super().accept()


class OptionsDialog(QDialog):
    """All application-wide settings in one place (stored in the registry)."""

    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Options")
        layout = QVBoxLayout(self)

        general = CompactGroupBox("General")
        form = QFormLayout(general)
        self.theme = CompactDropdown()
        self.theme.addItems(["Dark", "Light"])
        self.theme.setCurrentIndex(0 if settings.theme == "dark" else 1)
        form.addRow("Theme (applies after restart)", self.theme)
        self.sensitivity = CompactDropdown()
        self.sensitivity.addItems(list(SENSITIVITIES))
        self.sensitivity.setCurrentIndex(SENSITIVITIES.index(settings.sensitivity))
        form.addRow("Recognition sensitivity", self.sensitivity)
        self.max_packages = CompactIntField("", minimum=1, maximum=999, value=settings.max_packages)
        form.addRow("Maximum packages per pattern", self.max_packages)
        layout.addWidget(general)

        names = CompactGroupBox("Siemens names")
        form = QFormLayout(names)
        current = settings.tia_names
        self.package_type = CompactLineEdit()
        self.package_type.setText(current.package_type)
        self.index_type = CompactLineEdit()
        self.index_type.setText(current.index_type)
        self.db = CompactLineEdit()
        self.db.setText(current.db)
        form.addRow("Package type", self.package_type)
        form.addRow("Pattern index type", self.index_type)
        form.addRow("Pattern DB", self.db)
        layout.addWidget(names)

        defaults = CompactGroupBox("Example values for new patterns")
        form = QFormLayout(defaults)
        dims = settings.default_dimensions
        self.dims = {}
        for key, text, minimum in (("kl", "KL", 1), ("kb", "KB", 1), ("d", "D", 0),
                                   ("pallet_x", "Pallet width", 1), ("pallet_y", "Pallet length", 1)):
            field = CompactIntField("mm", minimum=minimum, maximum=99_999, value=getattr(dims, key))
            form.addRow(text, field)
            self.dims[key] = field
        layout.addWidget(defaults)

        fit = CompactGroupBox("Fit to pallet")
        form = QFormLayout(fit)
        self.fit_step = CompactDropdown()
        self.fit_step.addItems([f"{step} mm" for step in FIT_STEPS])
        self.fit_step.setCurrentIndex(FIT_STEPS.index(settings.fit_step))
        form.addRow("Grid for KL and KB", self.fit_step)
        self.fit_band = CompactIntField("mm", minimum=0, maximum=500, value=settings.fit_band)
        self.fit_band.setToolTip("How much worse a rounder size may fit than the best one\n"
                                 "(overhang counts double, unused pallet edge single).")
        form.addRow("Tolerance for round values", self.fit_band)
        layout.addWidget(fit)

        self.error = Message()
        layout.addWidget(self.error)
        layout.addWidget(_buttons(self, "Apply"))
        _fit_to_content(layout)

    def names(self) -> TiaNames:
        return TiaNames(self.package_type.text().strip(), self.index_type.text().strip(),
                        self.db.text().strip())

    def accept(self) -> None:
        dims = Dimensions(**{k: f.value() for k, f in self.dims.items()})
        problems = self.names().problems() + dims.problems()
        if problems:
            self.error.set_error(" ".join(problems))
            return
        s = self.settings
        s.theme = "dark" if self.theme.currentIndex() == 0 else "light"
        s.sensitivity = SENSITIVITIES[self.sensitivity.currentIndex()]
        s.max_packages = self.max_packages.value()
        s.tia_names = self.names()
        s.default_dimensions = dims
        s.fit_step = FIT_STEPS[self.fit_step.currentIndex()]
        s.fit_band = self.fit_band.value()
        s.sync()
        super().accept()


class ExportDialog(QDialog):
    """Formats, target folder, resulting file names and the Siemens names in use."""

    def __init__(self, project_name: str, settings, parent=None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Export")
        layout = QVBoxLayout(self)
        self.excel = CompactCheckBox("Export Excel workbook")
        self.excel.setChecked(True)
        self.tia = CompactCheckBox("Export TIA Portal sources (type + DB)")
        self.tia.setChecked(True)
        layout.addWidget(self.excel)
        layout.addWidget(self.tia)

        row = QHBoxLayout()
        self.folder = CompactLineEdit()
        self.folder.setMinimumWidth(380)         # long paths stay readable
        self.folder.setText(settings.last_dir("export") or str(Path.home()))
        browse = CompactButton("Browse")
        browse.clicked.connect(self._browse)
        row.addWidget(self.folder, 1)
        row.addWidget(browse)
        form = QFormLayout()
        form.addRow("Target folder", row)
        self.base = CompactLineEdit()
        self.base.setText(safe_base_name(project_name))
        form.addRow("File name prefix", self.base)
        layout.addLayout(form)

        self.files = QLabel()
        self.files.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.files)
        names = settings.tia_names
        layout.addWidget(QLabel(f"Siemens names: <b>{names.package_type}</b>, "
                                f"<b>{names.index_type}</b>, <b>{names.db}</b> "
                                "(change in Options)"))
        self.error = Message()
        layout.addWidget(self.error)
        layout.addWidget(_buttons(self, "Export"))
        _fit_to_content(layout)
        for signal in (self.excel.toggled, self.tia.toggled, self.folder.textChanged, self.base.textChanged):
            signal.connect(lambda *_: self._update())
        self._update()

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Target folder", self.folder.text())
        if folder:
            self.folder.setText(folder)

    def request(self) -> ExportRequest:
        return ExportRequest(Path(self.folder.text().strip()),
                             safe_base_name(self.base.text().strip()),
                             self.excel.isChecked(), self.tia.isChecked())

    def _update(self) -> None:
        req = self.request()
        names = [p.name for p in output_files(req).values()]
        self.files.setText("Files: " + (", ".join(names) if names else "-"))
        self.error.set_error("" if names else "Select at least one format.")

    def accept(self) -> None:
        req = self.request()
        if not (req.excel or req.tia):
            return
        if not req.folder.is_dir():
            self.error.set_error("The folder does not exist.")
            return
        self.settings.set_last_dir("export", str(req.folder))
        super().accept()
