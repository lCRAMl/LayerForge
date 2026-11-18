"""PDF access through pypdfium2 (decision D4: permissive licence).

PDFium is not thread-safe at all - not even for different documents in different
threads (concurrent calls corrupt its heap). Every PDFium call therefore runs under one
process-wide lock, and pages and bitmaps are closed explicitly inside it, so that no
finalizer releases PDFium memory later on some other thread. Rendering a page holds the
lock for a few dozen milliseconds; the expensive OpenCV work runs outside it.

Coordinates handed out are PDF points with the origin at the top left of the page
(like the rendered image), not PDF's bottom-left convention.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

PageRect = tuple[float, float, float, float]    # x0, y0, x1, y1 in points, Y down

PDFIUM_LOCK = threading.RLock()


class PdfError(Exception):
    """The file cannot be opened or rendered; message meant for the user."""


@dataclass(frozen=True, slots=True)
class Raster:
    """Rendered RGB pixels plus the mapping back to page points."""

    pixels: object          # numpy array H x W x 3 (RGB) uint8, owned by Python
    scale: float            # pixels per point
    origin: tuple[float, float]   # page point of pixel (0, 0)

    def to_page(self, x: float, y: float) -> tuple[float, float]:
        return self.origin[0] + x / self.scale, self.origin[1] + y / self.scale


class PdfFile:
    def __init__(self, path: str | Path) -> None:
        import pypdfium2 as pdfium

        self.path = str(path)
        with PDFIUM_LOCK:
            try:
                self._doc = pdfium.PdfDocument(self.path)
            except (pdfium.PdfiumError, OSError) as exc:
                raise PdfError(f"Cannot open {Path(path).name}: {exc}") from exc

    def __enter__(self) -> PdfFile:
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def close(self) -> None:
        with PDFIUM_LOCK:
            self._doc.close()

    @contextmanager
    def _page(self, index: int):
        with PDFIUM_LOCK:
            page = self._doc[index]
            try:
                yield page
            finally:
                page.close()

    def page_count(self) -> int:
        with PDFIUM_LOCK:
            return len(self._doc)

    def page_size(self, index: int) -> tuple[float, float]:
        with self._page(index) as page:
            return tuple(page.get_size())

    def render(self, index: int, scale: float, region: PageRect | None = None) -> Raster:
        """RGB pixels of the page or of `region` (page points, Y down)."""
        with self._page(index) as page:
            width, height = page.get_size()
            if region is None:
                crop, origin = (0, 0, 0, 0), (0.0, 0.0)
            else:
                x0, y0, x1, y1 = region
                x0, y0 = max(0.0, x0), max(0.0, y0)
                x1, y1 = min(width, x1), min(height, y1)
                # pdfium crops by margins: left, bottom, right, top.
                crop, origin = (x0, height - y1, width - x1, y0), (x0, y0)
            bitmap = page.render(scale=scale, crop=crop, rev_byteorder=True)
            try:
                pixels = bitmap.to_numpy()
                if pixels.ndim == 3 and pixels.shape[2] == 4:
                    pixels = pixels[:, :, :3]
                pixels = pixels.copy()          # detach from PDFium memory before closing
            finally:
                bitmap.close()
        return Raster(pixels, scale, origin)

    def thumbnail(self, index: int, longest_px: int) -> Raster:
        width, height = self.page_size(index)
        return self.render(index, longest_px / max(width, height))

    def native_scale(self, index: int) -> float:
        """Pixels per point needed to keep embedded raster images at full resolution.

        The bounds of nested images are reported in their own form space, so the
        estimate assumes an image spans the page - true for scanned or exported
        pages, and on the safe side otherwise.
        """
        import pypdfium2.raw as raw

        best = 0.0
        with self._page(index) as page:
            width = page.get_width()
            for obj in page.get_objects(filter=[raw.FPDF_PAGEOBJ_IMAGE]):
                try:
                    px_w, _px_h = obj.get_px_size()
                except Exception:  # noqa: BLE001 - damaged image streams are simply ignored
                    continue
                best = max(best, px_w / max(width, 1.0))
        return best

    def vector_edges(self, index: int) -> tuple[list[float], list[float]]:
        """Candidate X and Y edge coordinates (page points, Y down) from path objects.

        Thin paths are lines: their centre line counts. Other paths contribute all
        four sides. Used to sharpen raster-detected edges; never to decide anything.
        """
        import pypdfium2.raw as raw

        xs: list[float] = []
        ys: list[float] = []
        with self._page(index) as page:
            height = page.get_height()
            for obj in page.get_objects(filter=[raw.FPDF_PAGEOBJ_PATH]):
                left, bottom, right, top = obj.get_bounds()
                y_top, y_bottom = height - top, height - bottom
                w, h = right - left, y_bottom - y_top
                if w < 3.0 <= h:
                    xs.append((left + right) / 2)
                elif h < 3.0 <= w:
                    ys.append((y_top + y_bottom) / 2)
                elif w >= 3.0 and h >= 3.0:
                    xs += [left, right]
                    ys += [y_top, y_bottom]
        return sorted(xs), sorted(ys)
