"""Dependency-free chart geometry shared by dashboard projections."""

from __future__ import annotations

from typing import Any


def series_plot(
    values: list[float],
    presentation: str,
    target: float | None = None,
    context: list[float] | None = None,
) -> dict[str, Any]:
    """Project one series into the selected dependency-free visual."""

    geometry = bar_plot(values, target) if presentation == "bar" else plot(values, target, context)
    return {**geometry, "presentation": presentation}


def plot(
    values: list[float], target: float | None = None, context: list[float] | None = None
) -> dict[str, Any]:
    """Map a numeric series into the shared compact SVG view box."""

    context = context or []
    domain = [*values, *context, *([] if target is None else [target])]
    if not domain:
        return {"points": "", "target_y": None, "last": None, "single": False}
    low, high = min(domain), max(domain)
    if low == high:
        low, high = low - 1, high + 1

    def y(value: float) -> float:
        return round(34 - ((value - low) / (high - low) * 30), 2)

    def points(series: list[float]) -> str:
        if len(series) == 1:
            return f"50,{y(series[0])}"
        return " ".join(
            f"{round(index * 100 / (len(series) - 1), 2)},{y(value)}"
            for index, value in enumerate(series)
        )

    plotted = points(values)
    last = {"x": 50 if len(values) == 1 else 100, "y": y(values[-1])} if values else None
    return {
        "points": plotted,
        "context_points": points(context) if context else "",
        "target_y": y(target) if target is not None else None,
        "last": last,
        "single": len(values) == 1,
    }


def bar_plot(values: list[float], target: float | None = None) -> dict[str, Any]:
    """Map values into honest zero-baseline SVG bars."""

    domain = [0.0, *values, *([] if target is None else [target])]
    low, high = min(domain), max(domain)
    if low == high:
        high = low + 1

    def y(value: float) -> float:
        return round(34 - ((value - low) / (high - low) * 30), 2)

    zero = y(0)
    step = 100 / len(values) if values else 100
    width = step * (0.72 if len(values) <= 7 else 0.62)
    bars = [
        {
            "x": round(index * step + (step - width) / 2, 2),
            "y": min(zero, y(value)),
            "width": round(width, 2),
            "height": round(abs(zero - y(value)), 2),
        }
        for index, value in enumerate(values)
    ]
    return {
        "bars": bars,
        "baseline_y": zero,
        "target_y": y(target) if target is not None else None,
        "last": None,
        "single": len(values) == 1,
        "points": "",
        "context_points": "",
    }
