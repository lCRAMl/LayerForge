"""Page or region -> recognition proposals. Runs in a worker thread.

Hybrid as specified: PDF objects decide the render resolution (embedded images at
full resolution) and sharpen edges (vector paths); the detection itself is one
raster path for vector and image PDFs alike.
"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass

from layerpattern.domain import validation as v
from layerpattern.domain.model import DEFAULT_MAX_PACKAGES, Dimensions, Pattern
from layerpattern.domain.reconstruct import Reconstruction, flip_y, reconstruct
from layerpattern.infrastructure.pdf_source import PageRect, PdfFile

OK, WARNING, ERROR = "ok", "warning", "error"
_GEOMETRY = (v.OVERLAP, v.CLEARANCE, v.DISCONNECTED)


@dataclass(frozen=True, slots=True)
class Proposal:
    page: int
    region: PageRect                      # bounding box of the pattern, page points
    rects: tuple[PageRect, ...]           # one per package, in the order of the packages
    reconstruction: Reconstruction
    level: str
    messages: tuple[str, ...]


def _snap(value: float, candidates: list[float], tolerance: float) -> float:
    if not candidates:
        return value
    i = bisect_left(candidates, value)
    best = min((candidates[j] for j in (i - 1, i) if 0 <= j < len(candidates)),
               key=lambda c: abs(c - value))
    return best if abs(best - value) <= tolerance else value


def _scale_for(pdf: PdfFile, page: int, region: PageRect | None) -> float:
    width, height = pdf.page_size(page)
    if region is not None:
        span = max(region[2] - region[0], region[3] - region[1], 1.0)
        return max(2.0, min(10.0, 1800.0 / span))
    base = max(2.0, pdf.native_scale(page) * 1.5)
    return min(base, 2800.0 / max(width, height))


def recognize(path: str, page: int, region: PageRect | None, sensitivity: str, dims: Dimensions,
              cancel=None, max_packages: int = DEFAULT_MAX_PACKAGES) -> list[Proposal]:
    from layerpattern.infrastructure.recognition.detect import detect

    with PdfFile(path) as pdf:
        scale = _scale_for(pdf, page, region)
        raster = pdf.render(page, scale, region)
        xs, ys = pdf.vector_edges(page)
    detection = detect(raster.pixels, sensitivity, cancel)
    tolerance = max(0.8, 2.0 / scale)        # points

    proposals: list[Proposal] = []
    for members in detection.groups:
        rects: list[PageRect] = []
        for k in members:
            b = detection.boxes[k]
            corners = [detection.to_image(x, y) for x, y in ((b.x0, b.y0), (b.x1, b.y1))]
            (x0, y0), (x1, y1) = (raster.to_page(*c) for c in corners)
            if not detection.angle:
                x0, x1 = _snap(x0, xs, tolerance), _snap(x1, xs, tolerance)
                y0, y1 = _snap(y0, ys, tolerance), _snap(y1, ys, tolerance)
            rects.append((min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)))
        # Reconstruction works with Y up; any page height flips consistently.
        rec = reconstruct(flip_y(rects, 10_000.0), dims)
        ordered = tuple(rects[k] for k in rec.source_index)
        messages = list(rec.messages)
        level = OK
        if rec.uncertain or any(detection.boxes[k].split for k in members):
            level = WARNING
            if any(detection.boxes[k].split for k in members):
                messages.append("Touching packages were separated by their repeated size; check them.")
        report = v.check_pattern(Pattern(0, 1, rec.packages, dims), max_packages)
        geometry = [i.message for i in report.blockers if i.code in _GEOMETRY]
        if rec.estimated or geometry:
            level = ERROR
            messages += geometry
        margin = 4.0
        region_pt = (min(r[0] for r in rects) - margin, min(r[1] for r in rects) - margin,
                     max(r[2] for r in rects) + margin, max(r[3] for r in rects) + margin)
        proposals.append(Proposal(page, region_pt, ordered, rec, level, tuple(messages)))
    return proposals
