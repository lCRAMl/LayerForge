"""Global preferences in the Windows registry via QSettings (no config files).

Per-pattern values never go here; they belong to the project file.
"""

from __future__ import annotations

from PyQt6.QtCore import QByteArray, QSettings

from layerpattern.domain.export_model import TiaNames
from layerpattern.domain.model import DEFAULT_MAX_PACKAGES, Dimensions

ORGANIZATION = "LayerPattern"
APPLICATION = "LayerPatternTool"
MAX_RECENT = 5
SENSITIVITIES = ("Low", "Normal", "High")


class AppSettings:
    def __init__(self, store: QSettings | None = None) -> None:
        self._s = store or QSettings(ORGANIZATION, APPLICATION)

    # --- helpers ---------------------------------------------------------
    def _get(self, key: str, default, kind=None):
        value = self._s.value(key, default)
        if kind is None or value is None:
            return value
        try:
            if kind is bool:
                return value if isinstance(value, bool) else str(value).lower() in ("1", "true")
            return kind(value)
        except (TypeError, ValueError):
            return default

    def _set(self, key: str, value) -> None:
        self._s.setValue(key, value)

    def sync(self) -> None:
        self._s.sync()

    # --- window ----------------------------------------------------------
    def window_geometry(self) -> QByteArray | None:
        value = self._s.value("window/geometry")
        return value if isinstance(value, QByteArray) else None

    def set_window_geometry(self, data: QByteArray) -> None:
        self._set("window/geometry", data)

    def splitter_state(self, name: str) -> QByteArray | None:
        value = self._s.value(f"window/splitter_{name}")
        return value if isinstance(value, QByteArray) else None

    def set_splitter_state(self, name: str, data: QByteArray) -> None:
        self._set(f"window/splitter_{name}", data)

    # --- appearance ------------------------------------------------------
    @property
    def theme(self) -> str:
        value = self._get("ui/theme", "dark", str)
        return value if value in ("dark", "light") else "dark"

    @theme.setter
    def theme(self, value: str) -> None:
        self._set("ui/theme", value)

    def display_option(self, name: str, default: bool) -> bool:
        return self._get(f"display/{name}", default, bool)

    def set_display_option(self, name: str, value: bool) -> None:
        self._set(f"display/{name}", value)

    # --- locations and recent projects -----------------------------------
    def last_dir(self, kind: str) -> str:
        return self._get(f"paths/{kind}", "", str)

    def set_last_dir(self, kind: str, path: str) -> None:
        self._set(f"paths/{kind}", path)

    def recent_projects(self) -> list[str]:
        value = self._s.value("paths/recent", [])
        if isinstance(value, str):
            value = [value]
        return [str(v) for v in (value or [])][:MAX_RECENT]

    def add_recent_project(self, path: str) -> None:
        items = [p for p in self.recent_projects() if p.lower() != path.lower()]
        self._set("paths/recent", [path] + items[:MAX_RECENT - 1])

    def remove_recent_project(self, path: str) -> None:
        self._set("paths/recent", [p for p in self.recent_projects() if p != path])

    # --- behaviour -------------------------------------------------------
    @property
    def sensitivity(self) -> str:
        value = self._get("recognition/sensitivity", "Normal", str)
        return value if value in SENSITIVITIES else "Normal"

    @sensitivity.setter
    def sensitivity(self, value: str) -> None:
        self._set("recognition/sensitivity", value)

    @property
    def max_packages(self) -> int:
        return max(1, self._get("validation/max_packages", DEFAULT_MAX_PACKAGES, int))

    @max_packages.setter
    def max_packages(self, value: int) -> None:
        self._set("validation/max_packages", int(value))

    @property
    def tia_names(self) -> TiaNames:
        default = TiaNames()
        return TiaNames(self._get("tia/package_type", default.package_type, str),
                        self._get("tia/index_type", default.index_type, str),
                        self._get("tia/db", default.db, str))

    @tia_names.setter
    def tia_names(self, names: TiaNames) -> None:
        self._set("tia/package_type", names.package_type)
        self._set("tia/index_type", names.index_type)
        self._set("tia/db", names.db)

    @property
    def default_dimensions(self) -> Dimensions:
        base = Dimensions()
        dims = Dimensions(self._get("defaults/kl", base.kl, int), self._get("defaults/kb", base.kb, int),
                          self._get("defaults/d", base.d, int),
                          self._get("defaults/pallet_x", base.pallet_x, int),
                          self._get("defaults/pallet_y", base.pallet_y, int))
        return dims if dims.is_valid() else base

    @default_dimensions.setter
    def default_dimensions(self, dims: Dimensions) -> None:
        for key, value in (("kl", dims.kl), ("kb", dims.kb), ("d", dims.d),
                           ("pallet_x", dims.pallet_x), ("pallet_y", dims.pallet_y)):
            self._set(f"defaults/{key}", value)
