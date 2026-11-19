"""T6: decoding of the detector's output and its input preprocessing (needs numpy)."""

import pytest

np = pytest.importorskip("numpy")
from body import detector  # noqa: E402


def outputs_with(person_at: list[tuple[int, int, float, list[int]]]):
    """Synthetic NanoDet outputs: (stride index, anchor index, score, [l, t, r, b] bins)."""
    sizes = [(detector.SIDE // s) ** 2 for s in detector.STRIDES]
    cls = [np.zeros((1, n, 80), np.float32) for n in sizes]
    reg = [np.full((1, n, 32), -20.0, np.float32) for n in sizes]
    for k, anchor, score, bins in person_at:
        cls[k][0, anchor, detector.PERSON] = score
        for side, b in enumerate(bins):  # a sharp distribution at bin b
            reg[k][0, anchor, side * 8 + b] = 20.0
    return cls + reg


def anchor_index(k, cx, cy):
    n = detector.SIDE // detector.STRIDES[k]
    return cy * n + cx


def test_decode_returns_a_normalized_box_without_the_letterbox_padding():
    points = detector.anchor_points()
    # Stride 32, anchor (6, 6): center (207.5, 207.5); 4 bins = 128 px on each side.
    found = detector.decode(outputs_with([(2, anchor_index(2, 6, 6), 0.9, [4, 2, 4, 2])]),
                            points, threshold=0.35)  # fmt: skip
    assert len(found) == 1
    score, x, y, w, h = found[0]
    assert score == pytest.approx(0.9)
    assert x == pytest.approx((207.5 - 128) / 416, abs=1e-3)
    assert w == pytest.approx(256 / 416, abs=1e-3)
    # y: 207.5 - 64 = 143.5 in model space, minus the 91 px of padding, over 234.
    assert y == pytest.approx((143.5 - detector.TOP) / 234, abs=1e-3)
    assert h == pytest.approx(128 / 234, abs=1e-3)


def test_decode_applies_threshold_and_suppresses_duplicates():
    points = detector.anchor_points()
    a, b = anchor_index(2, 6, 6), anchor_index(2, 7, 6)  # neighbours, same big box
    found = detector.decode(outputs_with([(2, a, 0.9, [4, 2, 4, 2]), (2, b, 0.8, [5, 2, 3, 2])]),
                            points, threshold=0.35)  # fmt: skip
    assert len(found) == 1 and found[0][0] == pytest.approx(0.9)
    weak = detector.decode(outputs_with([(2, a, 0.2, [4, 2, 4, 2])]), points, threshold=0.35)
    assert weak == []


def test_a_box_only_in_the_padding_is_not_a_person():
    points = detector.anchor_points()
    top_row = anchor_index(0, 10, 2)  # stride 8, y = 19.5: inside the top padding
    found = detector.decode(outputs_with([(0, top_row, 0.9, [1, 1, 1, 1])]), points,
                            threshold=0.35)  # fmt: skip
    assert found == []


def test_preprocess_pads_and_normalizes():
    frame = bytes([255, 0, 0, 0]) * (detector.FRAME_W * detector.FRAME_H)  # blue BGRx
    blob = detector.preprocess(frame, detector.blank_canvas())
    assert blob.shape == (1, 3, 416, 416) and blob.flags["C_CONTIGUOUS"]
    assert blob[0, :, 0, 0].tolist() == [0, 0, 0]  # padding
    inside = blob[0, :, detector.TOP + 1, 10]
    assert inside[0] == pytest.approx((255 - 103.53) / 57.375)
