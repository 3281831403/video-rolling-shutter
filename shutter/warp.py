"""Rolling-shutter timing, displacement, and frame-warping primitives.

Frame data is a rectangular two-dimensional list of floats:
``frame[row][column]``. A shift is a horizontal displacement in pixels;
positive values move image content to the right. Results are compared with an
absolute tolerance of ``1e-6`` unless a docstring says otherwise.
"""

from __future__ import annotations

import math


class ShutterError(ValueError):
    """Raised when rolling-shutter input violates the documented contract."""


def _is_real_number(value) -> bool:
    """Return True for real numeric values (excluding booleans)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def row_time(height: int, readout_ms: float) -> list[float]:
    """Return the exposure start time in milliseconds for each row.

    Row ``i`` starts at ``readout_ms * i / height``. The returned list has
    exactly ``height`` entries, starts at ``0.0`` and is strictly increasing
    whenever ``height > 1``. A single-row frame therefore gets ``[0.0]``, and
    a zero-height frame gets ``[]``.

    ``height`` must be a non-negative integer. ``readout_ms`` must be finite
    and strictly positive, so zero is rejected instead of causing a division
    by zero. Invalid input raises :class:`ShutterError`. Numeric results are
    compared with an absolute tolerance of ``1e-6``.
    """
    if not isinstance(height, int) or isinstance(height, bool) or height < 0:
        raise ShutterError("height must be a non-negative integer")
    if not _is_real_number(readout_ms) or not math.isfinite(readout_ms):
        raise ShutterError("readout_ms must be a finite number")
    if readout_ms <= 0:
        raise ShutterError("readout_ms must be strictly positive")
    return [readout_ms * i / height for i in range(height)]


def row_shift(
    row_index: int,
    row_times: list[float],
    motion: float,
    total_ms: float,
) -> float:
    """Return the horizontal pixel displacement of one row.

    The displacement is linear in row time::

        motion * row_times[row_index] / total_ms

    ``motion`` is the total horizontal travel in pixels over ``total_ms``.
    Positive motion moves content to the right. ``row_index`` must be a valid
    index into ``row_times``; the times must be finite and non-negative;
    ``motion`` must be finite; ``total_ms`` must be finite and positive.

    Invalid input raises :class:`ShutterError`. Results are compared with an
    absolute tolerance of ``1e-6``.
    """
    if not isinstance(row_index, int) or isinstance(row_index, bool):
        raise ShutterError("row_index must be an integer")
    if not isinstance(row_times, list) or not (
        0 <= row_index < len(row_times)
    ):
        raise ShutterError("row_index is out of range for row_times")
    for time in row_times:
        if not _is_real_number(time) or not math.isfinite(time) or time < 0:
            raise ShutterError("row_times must contain finite non-negative values")
    if not _is_real_number(motion) or not math.isfinite(motion):
        raise ShutterError("motion must be a finite number")
    if not _is_real_number(total_ms) or not math.isfinite(total_ms) or total_ms <= 0:
        raise ShutterError("total_ms must be a finite positive number")
    return motion * row_times[row_index] / total_ms


def warp_frame(
    frame: list[list[float]],
    shifts: list[float],
    wrap: bool,
) -> list[list[float]]:
    """Resample *frame* row by row using horizontal pixel *shifts*.

    For each output pixel ``(row, column)`` the source coordinate is
    ``column - shift``, so a positive shift moves image content to the right.
    Neighbouring source pixels are linearly interpolated.

    With ``wrap=True`` an out-of-range source coordinate wraps modulo the row
    width. With ``wrap=False`` it is clamped to ``[0, width - 1]``, which
    replicates the edge pixel and avoids wraparound ghosting. A zero shift
    reproduces the input within ``1e-9``; other results are compared with an
    absolute tolerance of ``1e-6``.

    The frame must be rectangular and ``len(shifts)`` must equal the number of
    rows. Every shift must be finite. An empty frame with no shifts returns
    ``[]``; width-zero rows remain empty. Invalid shape or non-finite input
    raises :class:`ShutterError`.
    """
    if not isinstance(frame, list) or not isinstance(shifts, list):
        raise ShutterError("frame and shifts must be lists")
    if len(frame) != len(shifts):
        raise ShutterError("number of shifts must equal number of rows")

    width = 0
    if frame:
        first_row = frame[0]
        if not isinstance(first_row, list):
            raise ShutterError("every frame row must be a list")
        width = len(first_row)
        for row in frame[1:]:
            if not isinstance(row, list) or len(row) != width:
                raise ShutterError("frame must be rectangular")

    for shift in shifts:
        if not _is_real_number(shift) or not math.isfinite(shift):
            raise ShutterError("every shift must be finite")

    if not frame:
        return []

    warped: list[list[float]] = []
    for row, shift in zip(frame, shifts):
        if width == 0:
            warped.append([])
            continue
        output_row: list[float] = []
        for column in range(width):
            source = column - shift
            if wrap:
                left = math.floor(source) % width
                right = (left + 1) % width
                fraction = source - math.floor(source)
                value = row[left] * (1.0 - fraction) + row[right] * fraction
            else:
                if source <= 0:
                    value = row[0]
                elif source >= width - 1:
                    value = row[width - 1]
                else:
                    left = math.floor(source)
                    right = left + 1
                    fraction = source - left
                    value = row[left] * (1.0 - fraction) + row[right] * fraction
            output_row.append(value)
        warped.append(output_row)
    return warped


def inverse_shifts(shifts: list[float]) -> list[float]:
    """Return the additive inverse of every horizontal shift.

    The result has the same order and length as ``shifts`` and is suitable for
    undoing a warp, because each returned value is ``-shifts[i]``. The input
    list is never mutated. Every input shift must be finite; otherwise
    :class:`ShutterError` is raised.

    Results are compared with an absolute tolerance of ``1e-6``.
    """
    if not isinstance(shifts, list):
        raise ShutterError("shifts must be a list")
    for shift in shifts:
        if not _is_real_number(shift) or not math.isfinite(shift):
            raise ShutterError("every shift must be finite")
    return [-shift for shift in shifts]


def estimate_skew(
    frames: list[list[list[float]]],
    max_shift: float,
) -> float:
    """Estimate rolling-shutter skew from multiple frames, in ``[0, 1]``.

    For every frame, estimate the horizontal lag between its first and last
    row by choosing the integer offset in ``[-max_shift, max_shift]`` that
    minimises the mean squared difference over the overlapping pixels. The
    per-frame skew is ``abs(offset) / max_shift``, clamped to ``[0, 1]``. The
    returned value is the maximum per-frame skew, not the mean, so one
    strongly sheared frame is not diluted by calm frames. Ties choose the
    smallest absolute offset.

    ``frames`` must hold at least one rectangular frame, all frames must have
    the same dimensions, and each frame must have at least two rows and one
    column. ``max_shift`` must be finite and positive. Invalid input raises
    :class:`ShutterError`. Results are compared with an absolute tolerance of
    ``1e-6``.
    """
    if not _is_real_number(max_shift) or not math.isfinite(max_shift) or max_shift <= 0:
        raise ShutterError("max_shift must be a finite positive number")
    if not isinstance(frames, list) or not frames:
        raise ShutterError("frames must be a non-empty list")

    height = None
    width = None
    for frame in frames:
        if not isinstance(frame, list) or len(frame) < 2:
            raise ShutterError("every frame must have at least two rows")
        first_row = frame[0]
        if not isinstance(first_row, list) or not first_row:
            raise ShutterError("every frame must have at least one column")
        frame_width = len(first_row)
        for row in frame:
            if not isinstance(row, list) or len(row) != frame_width:
                raise ShutterError("every frame must be rectangular")
        if height is None:
            height = len(frame)
            width = frame_width
        elif len(frame) != height or frame_width != width:
            raise ShutterError("all frames must share the same dimensions")

    limit = int(max_shift)
    offsets = sorted(range(-limit, limit + 1), key=abs)
    worst_skew = 0.0

    for frame in frames:
        top_row = frame[0]
        bottom_row = frame[-1]
        best_offset = 0
        best_error = math.inf
        for offset in offsets:
            if offset >= 0:
                overlap = width - offset
                if overlap <= 0:
                    continue
                differences = (
                    top_row[column] - bottom_row[column + offset]
                    for column in range(overlap)
                )
            else:
                overlap = width + offset
                if overlap <= 0:
                    continue
                differences = (
                    top_row[column - offset] - bottom_row[column]
                    for column in range(overlap)
                )
            error = sum(diff * diff for diff in differences) / overlap
            if error < best_error:
                best_error = error
                best_offset = offset
        skew = min(1.0, max(0.0, abs(best_offset) / max_shift))
        if skew > worst_skew:
            worst_skew = skew

    return worst_skew


def apply_skew(frame: list[list[float]], amount: float) -> list[list[float]]:
    """Synthesise a rolling-shutter skew into *frame*.

    ``amount`` is clamped to ``[-1, 1]`` before use; values outside that range
    must not wrap or fold. For a frame of height ``h`` and width ``w``, row
    ``i`` is shifted horizontally by::

        clamped_amount * (w - 1) * i / (h - 1)

    Edges use replication rather than wraparound. A one-row frame is returned
    unchanged, and empty frames remain empty. ``amount`` must be finite;
    non-finite input raises :class:`ShutterError`. Results are compared with an
    absolute tolerance of ``1e-6``.
    """
    if not _is_real_number(amount) or not math.isfinite(amount):
        raise ShutterError("amount must be a finite number")
    if not isinstance(frame, list):
        raise ShutterError("frame must be a list")
    if not frame:
        return []

    clamped = min(1.0, max(-1.0, amount))
    height = len(frame)
    if height == 1:
        return [list(frame[0])]

    width = len(frame[0])
    for row in frame:
        if not isinstance(row, list) or len(row) != width:
            raise ShutterError("frame must be rectangular")

    shifts = [
        clamped * (width - 1) * i / (height - 1) for i in range(height)
    ]
    return warp_frame(frame, shifts, wrap=False)


def validate(frame: list[list[float]], shifts: list[float]) -> list[str]:
    """Return every contract problem found in *frame* and *shifts*.

    An empty list means the input is valid. The function reports issues rather
    than raising for malformed frame data, and never mutates its inputs. The
    checks and report prefixes are:

    * ``"ragged_frame:<row>"`` -- a row has a different width from row zero.
    * ``"row_count_mismatch:..."`` -- ``len(shifts)`` differs from the frame
      height.
    * ``"nan_shift:<row>"`` -- a shift is NaN.
    * ``"non_finite_shift:<row>"`` -- a shift is positive or negative infinity.
    * ``"invalid_shift:<row>"`` -- a shift is not a real number.
    * ``"shift_out_of_bounds:<row>:<value>"`` -- ``abs(shift)`` exceeds the
      row width.

    An empty frame with an empty shift list has no problems. Results are
    compared with an absolute tolerance of ``1e-6``.
    """
    problems: list[str] = []

    width = 0
    if isinstance(frame, list) and frame:
        first_row = frame[0]
        width = len(first_row) if isinstance(first_row, list) else 0
        for row_index, row in enumerate(frame):
            if not isinstance(row, list) or len(row) != width:
                problems.append(f"ragged_frame:{row_index}")

    if not isinstance(shifts, list) or len(shifts) != len(frame):
        problems.append(
            f"row_count_mismatch:frames={len(frame) if isinstance(frame, list) else 0}"
            f":shifts={len(shifts) if isinstance(shifts, list) else 0}"
        )
        return problems

    for row_index, shift in enumerate(shifts):
        if not _is_real_number(shift):
            problems.append(f"invalid_shift:{row_index}")
            continue
        if math.isnan(shift):
            problems.append(f"nan_shift:{row_index}")
            continue
        if math.isinf(shift):
            problems.append(f"non_finite_shift:{row_index}")
            continue
        if abs(shift) > width:
            problems.append(f"shift_out_of_bounds:{row_index}:{shift}")

    return problems


def warp_batch(
    frames: list[list[list[float]]],
    config: dict,
) -> dict:
    """Warp every frame independently in an all-or-nothing batch.

    ``config`` must contain ``"shifts"``: a list with one shift list per
    frame. Each table is applied only to the frame at the same position; a
    fresh table is used for every frame. The optional ``"wrap"`` key defaults
    to ``False`` and is passed to :func:`warp_frame`.

    The call returns ``{"frames": warped_frames, "count": len(frames)}`` in
    the original frame order, without mutating the input frames or shift
    tables. Before producing any output, every frame and shift table is
    checked with :func:`validate`. If any issue exists, or the batch sizes do
    not match, the call raises :class:`ShutterError` and returns no partial
    result, giving the batch rollback semantics.

    All numeric results are compared with an absolute tolerance of ``1e-6``.
    """
    if not isinstance(config, dict) or "shifts" not in config:
        raise ShutterError("config must contain a 'shifts' entry")
    shift_tables = config["shifts"]
    if not isinstance(frames, list) or not isinstance(shift_tables, list):
        raise ShutterError("frames and shifts must both be lists")
    if len(frames) != len(shift_tables):
        raise ShutterError("number of shift tables must match number of frames")

    wrap = config.get("wrap", False)

    # Validate everything first: all-or-nothing rollback semantics.
    for frame, table in zip(frames, shift_tables):
        if validate(frame, table):
            raise ShutterError("invalid frame or shift table in batch")

    warped_frames = [
        warp_frame(frame, list(table), wrap)
        for frame, table in zip(frames, shift_tables)
    ]
    return {"frames": warped_frames, "count": len(frames)}
