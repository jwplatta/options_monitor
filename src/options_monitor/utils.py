"""Shared utility functions for options_monitor."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path


def downsample_snapshots(
    grouped: dict[date, list[tuple[datetime, Path]]],
    interval_minutes: int,
) -> dict[date, list[tuple[datetime, Path]]]:
    """Keep the latest snapshot per N-minute interval bucket per expiry.

    Args:
        grouped: Mapping of expiry date → list of (fetch_datetime, path) sorted ascending.
        interval_minutes: Bucket width in minutes.

    Returns:
        Same structure as input but with at most one entry per interval bucket per expiry.
    """
    result: dict[date, list[tuple[datetime, Path]]] = {}
    for expiry, snaps in grouped.items():
        buckets: dict[datetime, tuple[datetime, Path]] = {}
        for ts, path in snaps:
            bucket = ts.replace(
                minute=(ts.minute // interval_minutes) * interval_minutes,
                second=0,
                microsecond=0,
            )
            if bucket not in buckets or ts > buckets[bucket][0]:
                buckets[bucket] = (ts, path)
        result[expiry] = sorted(buckets.values(), key=lambda x: x[0])
    return result
