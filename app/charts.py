"""Dependency-free chart geometry shared by dashboard projections."""

from __future__ import annotations

from typing import Any


def plot(values: list[float], target: float | None = None) -> dict[str, Any]:
    """Map a numeric series into the shared compact SVG view box."""

    domain = [*values, *([] if target is None else [target])]
    if not domain:
        return {"points": "", "target_y": None, "last": None, "single": False}
    low, high = min(domain), max(domain)
    if low == high:
        low, high = low - 1, high + 1

    def y(value: float) -> float:
        return round(34 - ((value - low) / (high - low) * 30), 2)

    if len(values) == 1:
        points = f"50,{y(values[0])}"
    else:
        points = " ".join(
            f"{round(index * 100 / (len(values) - 1), 2)},{y(value)}"
            for index, value in enumerate(values)
        )
    last = {"x": 50 if len(values) == 1 else 100, "y": y(values[-1])} if values else None
    return {
        "points": points,
        "target_y": y(target) if target is not None else None,
        "last": last,
        "single": len(values) == 1,
    }
