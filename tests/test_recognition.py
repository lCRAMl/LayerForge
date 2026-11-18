"""PDF recognition: synthetic vector and raster PDFs, plus optional real samples."""

from pathlib import Path

import pytest
from helpers import eu13, grid, pattern
from pdf_factory import grid as layout
from pdf_factory import raster_pdf, vector_pdf

from layerforge.domain import validation as v
from layerforge.domain.export_model import package_rows
from layerforge.domain.model import DEFAULT_MAX_PACKAGES, Dimensions
from layerforge.infrastructure.recognition.detect import Cancelled
from layerforge.infrastructure.recognition.pipeline import ERROR, OK, WARNING, recognize

PRIVATE = Path(__file__).with_name("fixtures") / "private"
DIMS = Dimensions()


def key(packages):
    return sorted((o, x.coefficients(), y.coefficients()) for o, x, y in package_rows(pattern(packages)))


def counts(proposals):
    return sorted(len(p.rects) for p in proposals)


# Two patterns separated only by white space: 3x2 lying and 1x2 standing.
TWO_PATTERNS = layout(60, 120, 3, 2, 80, 50, 4) + layout(380, 520, 2, 1, 50, 80, 4)


def test_vector_filled_patterns_separated_by_whitespace(tmp_path):
    pdf = vector_pdf(tmp_path / "filled.pdf", TWO_PATTERNS)
    proposals = recognize(str(pdf), 0, None, "Normal", DIMS)
    assert counts(proposals) == [2, 6]
    big = next(p for p in proposals if len(p.rects) == 6)
    assert key(big.reconstruction.packages) == key(grid(3, 2))
    assert all(p.level == OK for p in proposals)


def test_outlined_touching_cells(tmp_path):
    cells = layout(100, 150, 2, 3, 90, 60, 0)          # shared borders
    pdf = vector_pdf(tmp_path / "outlined.pdf", cells, filled=False)
    (proposal,) = recognize(str(pdf), 0, None, "Normal", DIMS)
    assert len(proposal.rects) == 6
    assert key(proposal.reconstruction.packages) == key(grid(2, 3))


def test_raster_page_with_mixed_orientation(tmp_path):
    # EU13 drawn as an image: two lying packages stacked, one standing, top-aligned.
    rects = [(100, 100, 132, 80), (100, 184, 132, 80), (236, 100, 80, 132)]
    pdf = raster_pdf(tmp_path / "eu13.pdf", rects)
    (proposal,) = recognize(str(pdf), 0, None, "Normal", DIMS)
    assert key(proposal.reconstruction.packages) == key(eu13())


def test_slightly_skewed_scan_is_deskewed(tmp_path):
    pdf = raster_pdf(tmp_path / "skew.pdf", layout(150, 200, 3, 2, 90, 60, 5), skew=2.0)
    (proposal,) = recognize(str(pdf), 0, None, "Normal", DIMS)
    assert len(proposal.rects) == 6
    assert key(proposal.reconstruction.packages) == key(grid(3, 2))


def test_merged_packages_are_split_and_marked_uncertain(tmp_path):
    rects = layout(100, 100, 3, 1, 80, 50, 4)
    rects.append((100, 154, 164, 50))                   # two packages drawn as one block
    pdf = raster_pdf(tmp_path / "merged.pdf", rects)
    (proposal,) = recognize(str(pdf), 0, None, "Normal", DIMS)
    assert len(proposal.rects) == 5
    assert proposal.level in (WARNING, ERROR)
    assert any("separated" in m for m in proposal.messages)


def test_region_recognition_only_sees_the_region(tmp_path):
    pdf = vector_pdf(tmp_path / "two.pdf", TWO_PATTERNS)
    proposals = recognize(str(pdf), 0, (360, 500, 520, 640), "Normal", DIMS)
    assert counts(proposals) == [2]
    # Region results are reported in page coordinates, not region coordinates.
    x0, y0, _x1, _y1 = proposals[0].rects[0]
    assert 370 < x0 < 400 and 510 < y0 < 540


def test_cancel_stops_recognition(tmp_path):
    pdf = vector_pdf(tmp_path / "c.pdf", TWO_PATTERNS)
    with pytest.raises(Cancelled):
        recognize(str(pdf), 0, None, "Normal", DIMS, cancel=lambda: True)


def test_page_text_and_rules_are_ignored(tmp_path):
    rects = layout(60, 120, 2, 2, 80, 50, 4) + [(40, 60, 500, 3)]      # a horizontal rule
    pdf = vector_pdf(tmp_path / "text.pdf", rects, text="EU01 1x1  Alto 8.0-127.0 cm")
    assert counts(recognize(str(pdf), 0, None, "Normal", DIMS)) == [4]


# --- optional real samples ---------------------------------------------------

KAVE = PRIVATE / "Kave_Layerpattern.pdf"
PALLET = PRIVATE / "Pallet-formats.pdf"


@pytest.mark.skipif(not KAVE.exists(), reason="private sample not present")
def test_kave_sample_finds_all_18_patterns():
    expected = [[1, 2, 4], [6, 8, 2, 3, 9, 6], [3, 7, 10, 4, 5, 9], [5, 5, 6]]
    for page, sizes in enumerate(expected):
        proposals = recognize(str(KAVE), page, None, "Normal", DIMS)
        assert [len(p.rects) for p in proposals] == sizes, f"page {page + 1}"
        for p in proposals:
            assert p.level != ERROR
            assert v.check_pattern(pattern(p.reconstruction.packages), DEFAULT_MAX_PACKAGES).valid
    eu13_found = recognize(str(KAVE), 2, None, "Normal", DIMS)[0]
    assert key(eu13_found.reconstruction.packages) == key(eu13())


@pytest.mark.skipif(not PALLET.exists(), reason="private sample not present")
def test_pallet_formats_sample():
    # Page 2 is drawn with 27 rectangles although its text says 22 cases.
    assert [len(p.rects) for p in recognize(str(PALLET), 0, None, "Normal", DIMS)] == [28, 15]
    assert [len(p.rects) for p in recognize(str(PALLET), 1, None, "Normal", DIMS)] == [27, 12]


def test_concurrent_pdf_access_is_serialised(tmp_path):
    """Two threads rendering and recognising at once used to corrupt PDFium's heap."""
    import threading

    from layerforge.infrastructure.pdf_source import PdfFile

    pdf = vector_pdf(tmp_path / "t.pdf", TWO_PATTERNS)
    errors = []

    def render_many():
        try:
            for _ in range(15):
                with PdfFile(pdf) as f:
                    f.render(0, 2.0)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    def recognise_many():
        try:
            for _ in range(5):
                recognize(str(pdf), 0, None, "Normal", DIMS)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=render_many), threading.Thread(target=recognise_many),
               threading.Thread(target=render_many)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
