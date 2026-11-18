"""Find package rectangles in a rendered page and group them into pattern candidates.

Colour is never used: the image is reduced to luminance first. Packages are the
closed regions between edges (filled shapes and cells of a line grid alike); text,
arrows and numbers inside a package only punch small holes into its region and are
ignored by filling the outer contour.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from statistics import median

import cv2
import numpy as np

from layerpattern.domain.cancel import Cancelled


TEXT_BLOCK_HOLES = 25     # glyph islands that mark a block of running text
TEXT_LABEL_HOLES = 10     # ... and a lone captioned rectangle (heading, note)


@dataclass(frozen=True, slots=True)
class Tuning:
    canny_low: int
    canny_high: int
    contrast: float          # luminance difference that counts as "filled"
    rect_fill: float         # contour area / min-area rectangle: rejects pills, L-shapes
    max_aspect: float        # longer bars are headers, rules, table lines
    min_side_rel: float      # smallest package side relative to the image's long side


SENSITIVITY = {
    "Low": Tuning(40, 120, 14.0, 0.965, 7.0, 0.012),
    "Normal": Tuning(25, 80, 9.0, 0.95, 8.0, 0.008),
    "High": Tuning(12, 45, 6.0, 0.93, 10.0, 0.005),
}


@dataclass(frozen=True, slots=True)
class Box:
    x0: float
    y0: float
    x1: float
    y1: float
    mean: float = 0.0        # mean luminance inside
    holes: int = 0           # internal contours (text, symbols)
    split: bool = False      # produced by splitting a merged region (estimated)

    @property
    def w(self) -> float:
        return self.x1 - self.x0

    @property
    def h(self) -> float:
        return self.y1 - self.y0

    @property
    def short(self) -> float:
        return min(self.w, self.h)

    @property
    def long(self) -> float:
        return max(self.w, self.h)


@dataclass(frozen=True, slots=True)
class Detection:
    boxes: list[Box]
    groups: list[list[int]]
    angle: float             # skew that was corrected, degrees (0 if none)
    shape: tuple[int, int]   # size of the analysed image (h, w)

    def to_image(self, x: float, y: float) -> tuple[float, float]:
        """Map a point of the (deskewed) analysis frame back to the rendered image."""
        if not self.angle:
            return x, y
        h, w = self.shape
        matrix = cv2.getRotationMatrix2D((w / 2, h / 2), -self.angle, 1.0)
        return (float(matrix[0, 0] * x + matrix[0, 1] * y + matrix[0, 2]),
                float(matrix[1, 0] * x + matrix[1, 1] * y + matrix[1, 2]))




def _check(cancel) -> None:
    if cancel is not None and cancel():
        raise Cancelled()


def luminance(rgb: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY) if rgb.ndim == 3 else rgb


def _regions(gray: np.ndarray, tuning: Tuning):
    """Connected regions that are free of edges, with their statistics."""
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(blur, tuning.canny_low, tuning.canny_high)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)
    free = (edges == 0).astype(np.uint8)
    return cv2.connectedComponentsWithStats(free, connectivity=4)


def _candidates(gray: np.ndarray, tuning: Tuning, cancel=None) -> tuple[list[Box], list[float]]:
    height, width = gray.shape
    count, labels, stats, _centroids = _regions(gray, tuning)
    min_side = max(6.0, tuning.min_side_rel * max(height, width))
    grow = 1.5          # half the edge band removed by the dilation
    boxes: list[Box] = []
    angles: list[float] = []
    for label in range(1, count):
        if label % 200 == 0:
            _check(cancel)
        x, y, w, h, _area = stats[label]
        if x == 0 or y == 0 or x + w >= width or y + h >= height:
            continue                                  # page background
        if min(w, h) < min_side or max(w, h) / max(min(w, h), 1) > tuning.max_aspect:
            continue
        mask = (labels[y:y + h, x:x + w] == label).astype(np.uint8)
        contours, hierarchy = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            continue
        outer = [i for i in range(len(contours)) if hierarchy[0][i][3] < 0]
        main = max(outer, key=lambda i: cv2.contourArea(contours[i]))
        (_cx, _cy), (rw, rh), angle = cv2.minAreaRect(contours[main])
        if rw < 1 or rh < 1:
            continue
        if cv2.contourArea(contours[main]) / (rw * rh) < tuning.rect_fill:
            continue
        holes = sum(1 for i in range(len(contours)) if hierarchy[0][i][3] == main
                    and cv2.contourArea(contours[i]) > 4)
        mean = cv2.mean(gray[y:y + h, x:x + w], mask)[0]
        boxes.append(Box(x - grow, y - grow, x + w + grow, y + h + grow, mean, holes))
        angles.append(angle - 90 if angle > 45 else angle)
    return boxes, angles


def _without_containers(boxes: list[Box]) -> list[Box]:
    """Drop regions that enclose other candidates: cards, pallet outlines, frames."""
    def inside(inner: Box, outer: Box) -> bool:
        return (inner is not outer and inner.x0 >= outer.x0 - 1 and inner.y0 >= outer.y0 - 1
                and inner.x1 <= outer.x1 + 1 and inner.y1 <= outer.y1 + 1)
    return [b for b in boxes if not any(inside(o, b) for o in boxes)]


def group_boxes(boxes: list[Box]) -> list[list[int]]:
    """Packages closer than about half a package belong to the same pattern."""
    parent = list(range(len(boxes)))

    def root(k: int) -> int:
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    for i, a in enumerate(boxes):
        for j in range(i + 1, len(boxes)):
            b = boxes[j]
            limit = 0.6 * min(a.short, b.short)
            dx = max(0.0, a.x0 - b.x1, b.x0 - a.x1)
            dy = max(0.0, a.y0 - b.y1, b.y0 - a.y1)
            if dx <= limit and dy <= limit:
                parent[root(i)] = root(j)
    groups: dict[int, list[int]] = {}
    for k in range(len(boxes)):
        groups.setdefault(root(k), []).append(k)
    return sorted(groups.values(), key=lambda g: (min(boxes[k].y0 for k in g), min(boxes[k].x0 for k in g)))


def _surrounding(gray: np.ndarray, boxes: list[Box], members: list[int]) -> float:
    """Median luminance of a ring around the group, i.e. what the shapes sit on."""
    height, width = gray.shape
    x0 = min(boxes[k].x0 for k in members)
    y0 = min(boxes[k].y0 for k in members)
    x1 = max(boxes[k].x1 for k in members)
    y1 = max(boxes[k].y1 for k in members)
    pad = max(4, int(0.25 * median(boxes[k].short for k in members)))
    X0, Y0 = max(0, int(x0) - pad), max(0, int(y0) - pad)
    X1, Y1 = min(width, int(x1) + pad + 1), min(height, int(y1) + pad + 1)
    mask = np.ones((Y1 - Y0, X1 - X0), np.uint8)
    for k in members:
        b = boxes[k]
        mask[max(0, int(b.y0) - Y0):max(0, int(b.y1) + 1 - Y0),
             max(0, int(b.x0) - X0):max(0, int(b.x1) + 1 - X0)] = 0
    values = gray[Y0:Y1, X0:X1][mask > 0]
    return float(np.median(values)) if values.size else 255.0


def _split_merged(boxes: list[Box], members: list[int]) -> list[Box]:
    """Split regions that are an exact grid of the group's typical package (estimated)."""
    if len(members) < 2:
        return [boxes[k] for k in members]
    long_med = median(boxes[k].long for k in members)
    short_med = median(boxes[k].short for k in members)
    out: list[Box] = []
    for k in members:
        b = boxes[k]
        best = None
        for cw, ch in ((long_med, short_med), (short_med, long_med)):
            nx, ny = round(b.w / cw), round(b.h / ch)
            if nx < 1 or ny < 1 or nx * ny < 2:
                continue
            err = max(abs(b.w / nx - cw) / cw, abs(b.h / ny - ch) / ch)
            if err < 0.12 and (best is None or err < best[0]):
                best = (err, nx, ny)
        if best is None:
            out.append(b)
            continue
        _err, nx, ny = best
        sw, sh = b.w / nx, b.h / ny
        for r in range(ny):
            for c in range(nx):
                out.append(replace(b, x0=b.x0 + c * sw, y0=b.y0 + r * sh,
                                   x1=b.x0 + (c + 1) * sw, y1=b.y0 + (r + 1) * sh, split=True))
    return out


def _deskew(gray: np.ndarray, angle: float) -> np.ndarray:
    h, w = gray.shape
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(gray, matrix, (w, h), flags=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_REPLICATE)


def detect(rgb: np.ndarray, sensitivity: str = "Normal", cancel=None) -> Detection:
    tuning = SENSITIVITY.get(sensitivity, SENSITIVITY["Normal"])
    gray = luminance(rgb)
    boxes, angles = _candidates(gray, tuning, cancel)
    angle = 0.0
    if len(angles) >= 2:
        skew = float(np.median(angles))
        if 0.3 < abs(skew) <= 5.0:
            angle = skew
            gray = _deskew(gray, angle)
            _check(cancel)
            boxes, _angles = _candidates(gray, tuning, cancel)
    boxes = _without_containers(boxes)
    _check(cancel)

    result_boxes: list[Box] = []
    result_groups: list[list[int]] = []
    for members in group_boxes(boxes):
        background = _surrounding(gray, boxes, members)
        contrasts = [abs(boxes[k].mean - background) for k in members]
        if median(contrasts) >= tuning.contrast:
            # Filled shapes: cells that look like the background are holes, not packages.
            members = [k for k, c in zip(members, contrasts) if c >= tuning.contrast]
        # Framed text (notes, legends) is rectangular too. A package may carry a short
        # label; a block of running text is not a package.
        members = [k for k in members if boxes[k].holes < TEXT_BLOCK_HOLES]
        if not members or (len(members) == 1 and boxes[members[0]].holes >= TEXT_LABEL_HOLES):
            continue
        parts = _split_merged(boxes, members)
        start = len(result_boxes)
        result_boxes.extend(parts)
        result_groups.append(list(range(start, start + len(parts))))
    return Detection(result_boxes, result_groups, angle, gray.shape)
