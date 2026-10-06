"""Draw the endurance results as a small SVG graph (no plotting library needed).

Usage (from bench/it8951):
    uv run python -m it8951bench.graph results/<csv> ../../docs/images/it8951-endurance.svg
"""

import csv
import statistics
import sys
from collections import OrderedDict

W, H, LEFT, RIGHT = 760, 200, 60, 20
COLOURS = {"fast": "#1f6fb4", "full": "#2a9d4b", "fault": "#c0392b", "recover": "#8e44ad",
           "ram": "#555555", "files": "#1f6fb4"}  # fmt: skip


def _x(i: int, n: int) -> float:
    return LEFT + i * (W - LEFT - RIGHT) / max(1, n - 1)


def _panel(top: float, title: str, series: list, ymax: float, ticks: list[float]) -> list[str]:
    out = [f'<text x="{LEFT}" y="{top - 12}" font-weight="bold">{title}</text>']
    for t in ticks:
        y = top + H - t / ymax * H
        out.append(f'<line x1="{LEFT}" x2="{W - RIGHT}" y1="{y:.1f}" y2="{y:.1f}" stroke="#ddd"/>')
        out.append(
            f'<text x="{LEFT - 6}" y="{y + 4:.1f}" text-anchor="end" fill="#444">{t:g}</text>'
        )
    for label, values, colour in series:
        pts = [
            f"{_x(i, len(values)):.1f},{top + H - v / ymax * H:.1f}"
            for i, v in enumerate(values)
            if v is not None
        ]
        out.append(
            f'<polyline points="{" ".join(pts)}" fill="none" stroke="{colour}" stroke-width="2"/>'
        )
        x, y = pts[-1].split(",")
        out.append(
            f'<text x="{float(x) - 4}" y="{float(y) - 6}" text-anchor="end" '
            f'fill="{colour}">{label}</text>'
        )
    return out


def draw(csv_path: str) -> str:
    rows = list(csv.DictReader(open(csv_path)))
    hours: OrderedDict[str, list[dict]] = OrderedDict()
    for r in rows:
        hours.setdefault(r["time"][:13], []).append(r)
    keys = list(hours)

    def median(key: str, kind: str) -> float | None:
        s = [float(r["seconds"]) for r in hours[key] if r["kind"] == kind]
        return statistics.median(s) if s else None

    times = [
        (label, [median(k, kind) for k in keys], COLOURS[kind])
        for kind, label in (("fault", "fault (error after time limit)"), ("recover", "recover"),
                            ("full", "full GC16"), ("fast", "fast DU"))
    ]  # fmt: skip
    ram = [max(int(r["rss_kb"]) for r in hours[k]) / 1024 for k in keys]
    files = [max(int(r["open_files"]) for r in hours[k]) for k in keys]

    top1, top2 = 30, 30 + H + 60
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {top2 + H + 30}" '
        'font-family="sans-serif" font-size="12">',
        '<rect width="100%" height="100%" fill="#fff"/>',
    ]
    svg += _panel(top1, "Write time per hour (median, seconds)", times, 3, [0, 1, 2, 3])
    svg += _panel(
        top2,
        "Run memory in RAM (MB, highest per hour; later partly moved to swap) and open files",
        [("memory in RAM, MB", ram, COLOURS["ram"]), ("open files", files, COLOURS["files"])],
        30,
        [0, 10, 20, 30],
    )
    for i in (0, len(keys) // 2, len(keys) - 1):
        k = keys[i]
        svg.append(
            f'<text x="{_x(i, len(keys)):.1f}" y="{top2 + H + 18}" text-anchor="middle" '
            f'fill="#444">{k[5:10]} {k[11:]}:00</text>'
        )
    svg.append("</svg>")
    return "\n".join(svg)


if __name__ == "__main__":
    with open(sys.argv[2], "w") as f:
        f.write(draw(sys.argv[1]))
