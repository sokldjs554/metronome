"""Tiny dependency-free SVG charts (the docs and README embed these files)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

PALETTE = {
    "never": "#8a8f8c",
    "periodic": "#1f6f5f",
    "ratio": "#c8742b",
    "ph": "#4b5ea6",
    "adwin": "#8e4d9e",
    "warm": "#5c7a29",
}
FONT = "font-family='system-ui, -apple-system, Segoe UI, Roboto, Noto Sans KR, sans-serif'"


def _scale(d0: float, d1: float, r0: float, r1: float):
    k = 0.0 if d1 == d0 else (r1 - r0) / (d1 - d0)
    return lambda v: r0 + (v - d0) * k


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


@dataclass
class Point:
    x: float
    y: float
    label: str
    kind: str
    y_lo: float | None = None
    y_hi: float | None = None


@dataclass
class Series:
    name: str
    xs: list[float]
    ys: list[float]
    color: str
    dash: str | None = None
    marks: list[float] = field(default_factory=list)


def _frame(
    width: int, height: int, pad: tuple[int, int, int, int], title: str, xlab: str, ylab: str
) -> list[str]:
    top, right, bottom, left = pad
    return [
        f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {width} {height}' width='{width}' height='{height}' {FONT} font-size='12'>",
        f"<rect width='{width}' height='{height}' fill='white'/>",
        f"<text x='{left}' y='18' font-size='14' font-weight='600' fill='#1d2320'>{_esc(title)}</text>",
        f"<text x='{(left + width - right) / 2}' y='{height - 6}' text-anchor='middle' fill='#66706a'>{_esc(xlab)}</text>",
        f"<text transform='translate(14,{(top + height - bottom) / 2}) rotate(-90)' text-anchor='middle' fill='#66706a'>{_esc(ylab)}</text>",
    ]


def _axes(
    parts: list[str], width: int, height: int, pad: tuple[int, int, int, int], x, y, xd, yd, xfmt, yfmt
) -> None:
    top, right, bottom, left = pad
    parts.append(
        f"<line x1='{left}' x2='{width - right}' y1='{height - bottom}' y2='{height - bottom}' stroke='#cfd4d0'/>"
    )
    parts.append(f"<line x1='{left}' x2='{left}' y1='{top}' y2='{height - bottom}' stroke='#cfd4d0'/>")
    for i in range(5):
        yv = yd[0] + (yd[1] - yd[0]) * i / 4
        parts.append(
            f"<line x1='{left}' x2='{width - right}' y1='{y(yv):.1f}' y2='{y(yv):.1f}' stroke='#eceeea'/>"
        )
        parts.append(
            f"<text x='{left - 6}' y='{y(yv) + 4:.1f}' text-anchor='end' fill='#66706a' font-size='11'>{yfmt(yv)}</text>"
        )
        xv = xd[0] + (xd[1] - xd[0]) * i / 4
        parts.append(
            f"<text x='{x(xv):.1f}' y='{height - bottom + 16}' text-anchor='middle' fill='#66706a' font-size='11'>{xfmt(xv)}</text>"
        )


def pareto_chart(
    points: list[Point], path: Path, title: str, xlab: str = "재학습 횟수 (1년)", ylab: str = "스트림 MAE"
) -> Path:
    width, height, pad = 520, 340, (28, 16, 40, 60)
    top, right, bottom, left = pad
    xs = [p.x for p in points]
    ys = (
        [p.y for p in points]
        + [p.y_lo for p in points if p.y_lo is not None]
        + [p.y_hi for p in points if p.y_hi is not None]
    )
    xd = (0.0, max(xs) * 1.05 or 1.0)
    span = max(max(ys) - min(ys), 1e-6)
    yd = (min(ys) - span * 0.12, max(ys) + span * 0.12)
    x = _scale(xd[0], xd[1], left, width - right)
    y = _scale(yd[0], yd[1], height - bottom, top)
    parts = _frame(width, height, pad, title, xlab, ylab)
    _axes(parts, width, height, pad, x, y, xd, yd, lambda v: f"{v:.0f}", lambda v: f"{v:.3f}")
    for p in points:
        color = PALETTE.get(p.kind, "#1d2320")
        if p.y_lo is not None and p.y_hi is not None:
            parts.append(
                f"<line x1='{x(p.x):.1f}' x2='{x(p.x):.1f}' y1='{y(p.y_lo):.1f}' y2='{y(p.y_hi):.1f}' stroke='{color}' stroke-width='1.2' opacity='.6'/>"
            )
        if p.kind == "periodic" or p.kind == "never":
            parts.append(
                f"<circle cx='{x(p.x):.1f}' cy='{y(p.y):.1f}' r='4.5' fill='{color}'><title>{_esc(p.label)}</title></circle>"
            )
        else:
            parts.append(
                f"<rect x='{x(p.x) - 4:.1f}' y='{y(p.y) - 4:.1f}' width='8' height='8' fill='{color}'><title>{_esc(p.label)}</title></rect>"
            )
        if p.kind in ("never", "periodic", "warm"):
            parts.append(
                f"<text x='{x(p.x) + 6:.1f}' y='{y(p.y) - 6:.1f}' font-size='10' fill='{color}'>{_esc(p.label)}</text>"
            )
    lx = left
    for kind, color in PALETTE.items():
        if any(p.kind == kind for p in points):
            parts.append(f"<rect x='{lx}' y='{height - 16}' width='9' height='9' fill='{color}'/>")
            parts.append(f"<text x='{lx + 12}' y='{height - 8}' font-size='10' fill='#66706a'>{kind}</text>")
            lx += 60
    parts.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(parts), encoding="utf-8")
    return path


def line_chart(
    series: list[Series],
    path: Path,
    title: str,
    xlab: str,
    ylab: str,
    *,
    x_ticks: list[tuple[float, str]] | None = None,
) -> Path:
    width, height, pad = 720, 300, (28, 16, 40, 60)
    top, right, bottom, left = pad
    xs = [v for s in series for v in s.xs]
    ys = [v for s in series for v in s.ys if v == v]
    xd = (min(xs), max(xs))
    span = max(max(ys) - min(ys), 1e-6)
    yd = (max(0.0, min(ys) - span * 0.1), max(ys) + span * 0.1)
    x = _scale(xd[0], xd[1], left, width - right)
    y = _scale(yd[0], yd[1], height - bottom, top)
    parts = _frame(width, height, pad, title, xlab, ylab)
    _axes(parts, width, height, pad, x, y, xd, yd, lambda v: f"{v:.0f}", lambda v: f"{v:.2f}")
    if x_ticks:
        for xv, label in x_ticks:
            parts.append(
                f"<text x='{x(xv):.1f}' y='{height - bottom + 28}' text-anchor='middle' fill='#66706a' font-size='10'>{_esc(label)}</text>"
            )
    for s in series:
        pts = " ".join(f"{x(a):.1f},{y(b):.1f}" for a, b in zip(s.xs, s.ys, strict=True) if b == b)
        dash = f" stroke-dasharray='{s.dash}'" if s.dash else ""
        parts.append(f"<polyline points='{pts}' fill='none' stroke='{s.color}' stroke-width='1.8'{dash}/>")
        for m in s.marks:
            parts.append(
                f"<line x1='{x(m):.1f}' x2='{x(m):.1f}' y1='{top}' y2='{height - bottom}' stroke='{s.color}' stroke-width='1' opacity='.35'/>"
            )
    lx = left
    for s in series:
        parts.append(
            f"<line x1='{lx}' x2='{lx + 18}' y1='{height - 12}' y2='{height - 12}' stroke='{s.color}' stroke-width='2'/>"
        )
        parts.append(
            f"<text x='{lx + 22}' y='{height - 8}' font-size='10' fill='#66706a'>{_esc(s.name)}</text>"
        )
        lx += 24 + 7 * len(s.name) + 10
    parts.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(parts), encoding="utf-8")
    return path
