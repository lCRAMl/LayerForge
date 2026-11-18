"""Application start. Heavy libraries (PDF, OpenCV, NumPy, openpyxl, Jinja2) are imported
only when first used, so the window appears quickly."""

from __future__ import annotations

import sys
import traceback

from PyQt6.QtWidgets import QApplication

from layerpattern import APP_NAME
from layerpattern.presentation.settings import APPLICATION, ORGANIZATION, AppSettings
from layerpattern.presentation.theme import apply_theme


def main(argv: list[str] | None = None) -> int:
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORGANIZATION)
    app.setApplicationDisplayName(APP_NAME)
    settings = AppSettings()
    apply_theme(app, settings.theme)

    from layerpattern.presentation.main_window import MainWindow
    window = MainWindow(settings)

    def report(kind, value, tb) -> None:
        # Unexpected errors must not end the program; show them with details instead.
        details = "".join(traceback.format_exception(kind, value, tb))
        try:
            window.status.show_message(f"Unexpected error: {value}", "error", details)
        except Exception:  # noqa: BLE001 - last resort while the window is torn down
            sys.__excepthook__(kind, value, tb)

    sys.excepthook = report
    window.show()
    return app.exec()


__all__ = ["main", "APPLICATION"]
