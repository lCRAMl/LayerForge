"""Drawing -> symbolic pattern. Coordinates are read off the two real sample PDFs."""

from helpers import eu13, grid, pattern

from layerpattern.domain import validation as v
from layerpattern.domain.export_model import package_rows
from layerpattern.domain.model import DEFAULT_MAX_PACKAGES, Dimensions
from layerpattern.domain.reconstruct import flip_y, reconstruct

PAGE_H = 400.0


def rel(packages, dims=Dimensions()):
    return sorted((o, x.coefficients(), y.coefficients())
                  for o, x, y in package_rows(pattern(packages, dims=dims)))


def drawn_grid(cols, rows, w, h, gap, x=10.0, y=10.0):
    return [(x + c * (w + gap), y + r * (h + gap), x + c * (w + gap) + w, y + r * (h + gap) + h)
            for r in range(rows) for c in range(cols)]


def test_grid_with_gaps_like_kave():
    result = reconstruct(drawn_grid(3, 2, 80, 50, 4), Dimensions())
    assert rel(result.packages) == rel(grid(3, 2))
    assert result.uncertain == () and result.estimated == ()


def test_touching_outlined_cells_like_excel():
    # Cells of a line grid touch; the shared line may even make them overlap by a pixel.
    cells = drawn_grid(2, 3, 60, 40, -1)
    result = reconstruct(cells, Dimensions())
    assert rel(result.packages) == rel(grid(2, 3))


def test_eu13_from_the_raster_pdf():
    # Page 3 of Kave_Layerpattern.pdf, pixel coordinates (Y down).
    drawn = flip_y([(247, 123, 379, 203), (247, 207, 379, 285), (383, 123, 462, 255)], PAGE_H)
    result = reconstruct(drawn, Dimensions())
    assert rel(result.packages) == rel(eu13())
    assert result.estimated == ()
    assert v.check_pattern(pattern(result.packages), DEFAULT_MAX_PACKAGES).valid


def test_pinwheel_from_the_vector_pdf_is_not_to_scale():
    # Pallet-formats.pdf page 1, 28 cases: standing cases drawn 53 x 70, lying ones 80 x 45.
    cells = []
    for x0, x1 in ((80, 133), (133, 186), (186, 238)):            # top left, standing
        for y0, y1 in ((213, 283), (283, 350)):
            cells.append((x0, y0, x1, y1))
    for x0, x1 in ((238, 318), (318, 397)):                       # top right, lying
        for y0, y1 in ((213, 260), (260, 305), (305, 350)):
            cells.append((x0, y0, x1, y1))
    for x0, x1 in ((80, 160), (160, 238), (238, 318), (318, 397)):  # middle row
        cells.append((x0, 350, x1, 395))
    for x0, x1 in ((80, 160), (160, 238)):                        # bottom left, lying
        for y0, y1 in ((395, 440), (440, 486), (486, 530)):
            cells.append((x0, y0, x1, y1))
    for x0, x1 in ((238, 290), (290, 343), (343, 397)):           # bottom right, standing
        for y0, y1 in ((395, 463), (463, 530)):
            cells.append((x0, y0, x1, y1))
    assert len(cells) == 28

    # The drawing implies 2*KL = 3*KB; with such a case it is a clean pinwheel.
    dims = Dimensions(kl=300, kb=200, d=0, pallet_x=1200, pallet_y=1000)
    result = reconstruct(flip_y(cells, 600.0), dims)
    orientations = [p.orientation for p in result.packages]
    assert orientations.count(90) == 12 and orientations.count(0) == 16
    assert result.estimated == ()
    assert result.uncertain              # drawn sizes differ by far more than 10 %
    report = v.check_pattern(pattern(result.packages, dims=dims), DEFAULT_MAX_PACKAGES)
    assert report.valid, report.issues


def test_isolated_rectangle_is_estimated():
    drawn = drawn_grid(2, 1, 80, 50, 4) + [(400, 300, 480, 350)]
    result = reconstruct(drawn, Dimensions())
    assert len(result.estimated) == 1
    assert result.messages


def test_size_outlier_is_uncertain():
    drawn = drawn_grid(3, 1, 80, 50, 4)
    drawn[2] = (drawn[2][0], drawn[2][1], drawn[2][2] + 20, drawn[2][3])
    result = reconstruct(drawn, Dimensions())
    assert len(result.uncertain) == 1


def test_source_index_maps_back_to_input():
    drawn = list(reversed(drawn_grid(3, 1, 80, 50, 4)))
    result = reconstruct(drawn, Dimensions())
    # Automatic order is left to right; the input was right to left.
    assert result.source_index == (2, 1, 0)
