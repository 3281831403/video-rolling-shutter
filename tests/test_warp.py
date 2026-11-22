"""Failing-before tests for the rolling-shutter exercise.

Every test calls into ``shutter.warp``. All fifteen tests must fail until the
stubs are implemented; none of them may fail at collection or import time.
"""

import math

import pytest

from shutter.warp import (
    ShutterError,
    apply_skew,
    estimate_skew,
    inverse_shifts,
    row_shift,
    row_time,
    validate,
    warp_batch,
    warp_frame,
)

FRAME = [
    [0.0, 1.0, 2.0, 3.0],
    [4.0, 5.0, 6.0, 7.0],
    [8.0, 9.0, 10.0, 11.0],
]


def assert_frames_close(actual, expected, abs_tol=1e-6):
    """Assert equal frame shapes and per-pixel values within *abs_tol*."""
    assert len(actual) == len(expected), "frame height differs"
    for row_index, (actual_row, expected_row) in enumerate(zip(actual, expected)):
        assert len(actual_row) == len(expected_row), (
            f"row {row_index} width differs"
        )
        for column_index, (actual_value, expected_value) in enumerate(
            zip(actual_row, expected_row)
        ):
            assert math.isclose(
                actual_value,
                expected_value,
                rel_tol=0.0,
                abs_tol=abs_tol,
            ), f"pixel ({row_index}, {column_index}) differs"


# One test per seeded defect (10).


def test_row_time_scales_with_height():
    short = row_time(2, 12.0)
    tall = row_time(6, 12.0)

    assert short == pytest.approx([0.0, 6.0], abs=1e-6)
    assert tall == pytest.approx([0.0, 2.0, 4.0, 6.0, 8.0, 10.0], abs=1e-6)


def test_row_shift_is_linear_in_time():
    times = [0.0, 10.0, 20.0, 30.0]

    first = row_shift(1, times, motion=12.0, total_ms=40.0)
    second = row_shift(2, times, motion=12.0, total_ms=40.0)

    assert first == pytest.approx(3.0, abs=1e-6)
    assert second == pytest.approx(6.0, abs=1e-6)
    assert second == pytest.approx(2.0 * first, abs=1e-6)


def test_warp_frame_clamps_at_edges_when_not_wrapping():
    clamped = warp_frame(FRAME, [1.0, 1.0, 1.0], wrap=False)
    wrapped = warp_frame(FRAME, [1.0, 1.0, 1.0], wrap=True)

    assert_frames_close(
        clamped,
        [
            [0.0, 0.0, 1.0, 2.0],
            [4.0, 4.0, 5.0, 6.0],
            [8.0, 8.0, 9.0, 10.0],
        ],
    )
    assert_frames_close(
        wrapped,
        [
            [3.0, 0.0, 1.0, 2.0],
            [7.0, 4.0, 5.0, 6.0],
            [11.0, 8.0, 9.0, 10.0],
        ],
    )


def test_inverse_shifts_negates_without_mutation():
    shifts = [0.0, 1.5, -2.25]

    inverse = inverse_shifts(shifts)

    assert inverse == pytest.approx([0.0, -1.5, 2.25], abs=1e-6)
    assert shifts == [0.0, 1.5, -2.25]


def test_estimate_skew_uses_maximum_not_mean():
    def probe(top_column, bottom_column):
        frame = [[0.0] * 8 for _ in range(4)]
        frame[0][top_column] = 1.0
        frame[-1][bottom_column] = 1.0
        return frame

    calm = probe(0, 0)
    sheared = probe(0, 3)
    frames = [calm, calm, sheared, calm, calm]

    assert estimate_skew(frames, max_shift=3.0) == pytest.approx(1.0, abs=1e-6)


def test_apply_skew_clamps_amount_instead_of_folding():
    assert_frames_close(apply_skew(FRAME, 4.0), apply_skew(FRAME, 1.0))
    assert_frames_close(apply_skew(FRAME, -3.5), apply_skew(FRAME, -1.0))


def test_validate_reports_row_count_mismatch():
    problems = validate(FRAME, [0.0, 0.0])

    assert problems
    assert any("row_count" in problem for problem in problems)


def test_validate_reports_nan_shift():
    problems = validate(FRAME, [0.0, float("nan"), 0.0])

    assert problems
    assert any("nan" in problem.lower() for problem in problems)


def test_warp_batch_applies_independent_shift_tables_atomically():
    frames = [FRAME, FRAME, FRAME]
    parts = warp_batch(
        frames,
        {
            "shifts": [
                [0.0, 0.0, 0.0],
                [1.0, 1.0, 1.0],
                [2.0, 2.0, 2.0],
            ],
            "wrap": False,
        },
    )

    assert parts["count"] == 3
    assert_frames_close(
        parts["frames"][0],
        [
            [0.0, 1.0, 2.0, 3.0],
            [4.0, 5.0, 6.0, 7.0],
            [8.0, 9.0, 10.0, 11.0],
        ],
    )
    assert_frames_close(
        parts["frames"][1],
        [
            [0.0, 0.0, 1.0, 2.0],
            [4.0, 4.0, 5.0, 6.0],
            [8.0, 8.0, 9.0, 10.0],
        ],
    )
    assert_frames_close(
        parts["frames"][2],
        [
            [0.0, 0.0, 0.0, 1.0],
            [4.0, 4.0, 4.0, 5.0],
            [8.0, 8.0, 8.0, 9.0],
        ],
    )

    with pytest.raises(ShutterError):
        warp_batch(
            frames,
            {
                "shifts": [
                    [0.0, 0.0, 0.0],
                    [0.0, float("nan"), 0.0],
                    [0.0, 0.0, 0.0],
                ],
                "wrap": False,
            },
        )


def test_row_time_rejects_zero_readout_even_for_empty_frame():
    with pytest.raises(ShutterError):
        row_time(0, 0.0)


# Five additional combination / edge tests.


def test_zero_shift_preserves_frame():
    warped = warp_frame(FRAME, [0.0, 0.0, 0.0], wrap=False)

    assert_frames_close(warped, FRAME, abs_tol=1e-9)


def test_single_row_time_is_zero():
    times = row_time(1, 24.0)

    assert times == pytest.approx([0.0], abs=1e-6)


def test_empty_frame_returns_empty():
    assert warp_frame([], [], wrap=False) == []


def test_readout_ms_zero_raises_shutter_error():
    with pytest.raises(ShutterError):
        row_time(4, 0.0)


def test_successful_batch_preserves_frame_order():
    frames = [
        [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]],
        [[7.0, 8.0, 9.0], [10.0, 11.0, 12.0]],
        [[13.0, 14.0, 15.0], [16.0, 17.0, 18.0]],
    ]
    shifts = [[0.0, 0.0] for _ in frames]

    parts = warp_batch(frames, {"shifts": shifts, "wrap": False})

    assert parts["count"] == 3
    for index, frame in enumerate(frames):
        assert_frames_close(parts["frames"][index], frame)
