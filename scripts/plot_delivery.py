"""
График для README лабораторной № 6 по результатам scripts/delivery_probe.py.

    python scripts/plot_delivery.py
"""
import csv
import statistics
from pathlib import Path

import matplotlib.pyplot as plt

from plot_loadtest import GRID, SERIES, SURFACE, TEXT, TEXT_SECONDARY

RESULTS = Path("docs/lab6/results")
PATHS = [
    ("local_http", "HTTP, доставка в монолите"),
    ("grpc_http", "HTTP, монолит → gRPC-сервис"),
    ("grpc_direct", "gRPC напрямую"),
]


def median_ms(label: str) -> float:
    with open(RESULTS / f"{label}.csv") as f:
        return statistics.median(float(row["ms"]) for row in csv.DictReader(f))


def main() -> None:
    names = [name for _, name in PATHS][::-1]
    values = [median_ms(label) for label, _ in PATHS][::-1]
    fig, ax = plt.subplots(figsize=(8, 2.9), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    bars = ax.barh(names, values, color=SERIES[0][0], height=0.5)
    for bar, value in zip(bars, values):
        ax.annotate(f"{value:.1f} мс", xy=(bar.get_width(), bar.get_y() + bar.get_height() / 2),
                    xytext=(6, 0), textcoords="offset points", va="center", fontsize=9, color=TEXT)
    ax.set_xlim(0, max(values) * 1.2)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=TEXT_SECONDARY, labelsize=8.5, length=0)
    ax.tick_params(axis="y", labelsize=9, labelcolor=TEXT)
    fig.text(0.012, 0.965, "GET /delivery/{id}: цена сетевого вызова", fontsize=12, fontweight="bold", color=TEXT, va="top")
    fig.text(0.012, 0.88, "Медиана 500 последовательных запросов, миллисекунды", fontsize=9, color=TEXT_SECONDARY, va="top")
    fig.subplots_adjust(left=0.3, right=0.95, top=0.74, bottom=0.12)
    path = Path("docs/lab6/latency.png")
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)
    print("saved", path)


if __name__ == "__main__":
    main()
