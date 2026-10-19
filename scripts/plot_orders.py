"""
Графики «до / после» для README лабораторной № 5 по результатам
scripts/order_probe.py и scripts/loadtest_orders.sh.

    python scripts/plot_orders.py sync celery
"""
import csv
import statistics
import sys
from pathlib import Path

import matplotlib.pyplot as plt

from plot_loadtest import GRID, SERIES, SURFACE, TEXT, TEXT_SECONDARY, line_chart, locust_history

RESULTS = Path("docs/lab5/results")
CHARTS = Path("docs/lab5")
NAMES = ["Синхронно", "Celery"]


def probe_ms(label: str) -> list[float]:
    with open(RESULTS / f"{label}_probe.csv") as f:
        return [float(row["ms"]) for row in csv.DictReader(f)]


def queue_history(label: str) -> tuple[list[int], list[int]]:
    with open(RESULTS / f"{label}_system.csv") as f:
        rows = [r for r in csv.DictReader(f) if r["queue"].isdigit()]
    start = int(rows[0]["time"])
    return [int(r["time"]) - start for r in rows], [int(r["queue"]) for r in rows]


def style(fig, ax, title: str, subtitle: str) -> None:
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=TEXT_SECONDARY, labelsize=8.5, length=0)
    fig.text(0.012, 0.965, title, fontsize=12, fontweight="bold", color=TEXT, va="top")
    fig.text(0.012, 0.895, subtitle, fontsize=9, color=TEXT_SECONDARY, va="top")


def response_time_chart(before: str, after: str) -> None:
    medians = [statistics.median(probe_ms(label)) for label in (before, after)]
    fig, ax = plt.subplots(figsize=(8, 2.6), dpi=150)
    style(fig, ax, "Время ответа POST /orders/create", "Медиана 30 последовательных заказов, миллисекунды")
    bars = ax.barh(NAMES[::-1], medians[::-1], color=[c for c, _ in SERIES][::-1], height=0.5)
    for bar, value in zip(bars, medians[::-1]):
        ax.annotate(f"{value:.0f} мс", xy=(bar.get_width(), bar.get_y() + bar.get_height() / 2),
                    xytext=(6, 0), textcoords="offset points", va="center", fontsize=9, color=TEXT)
    ax.set_xlim(0, max(medians) * 1.15)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(axis="y", labelsize=9.5, labelcolor=TEXT)
    fig.subplots_adjust(left=0.13, right=0.95, top=0.72, bottom=0.12)
    path = CHARTS / "response_time.png"
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)
    print("saved", path)


def queue_chart(label: str, load_seconds: int) -> None:
    seconds, queue = queue_history(label)
    fig, ax = plt.subplots(figsize=(8, 3.2), dpi=150)
    style(fig, ax, "Очередь задач Celery в Redis",
          "Сколько задач ждут свободный воркер. После пунктира нагрузки нет, воркер разбирает остаток")
    ax.plot(seconds, queue, color=SERIES[0][0], linewidth=2, solid_capstyle="round")
    ax.axvline(load_seconds, color=TEXT_SECONDARY, linewidth=1, linestyle=(0, (4, 3)))
    ax.set_ylim(0, max(max(queue), 1) * 1.15)
    ax.set_xlabel("Секунды с начала теста", color=TEXT_SECONDARY, fontsize=9)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    fig.subplots_adjust(left=0.08, right=0.97, top=0.74, bottom=0.17)
    path = CHARTS / "queue.png"
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)
    print("saved", path)


def main() -> None:
    before, after = sys.argv[1], sys.argv[2]
    b_sec, b_rps, b_p95 = locust_history(before, RESULTS)
    a_sec, a_rps, a_p95 = locust_history(after, RESULTS)

    response_time_chart(before, after)
    line_chart(
        CHARTS / "rps.png",
        "Оформленных заказов в секунду",
        "40 пользователей, пауза между заказами 2–4 с. Средние после 60-й секунды",
        "RPS",
        1,
        [(b_sec, b_rps), (a_sec, a_rps)],
        NAMES,
    )
    line_chart(
        CHARTS / "latency_p95.png",
        "95-й перцентиль времени ответа под нагрузкой",
        "Секунды. Синхронно запрос ждёт PDF, email и SMS",
        "с",
        2,
        [(b_sec, b_p95), (a_sec, a_p95)],
        NAMES,
    )
    queue_chart(after, a_sec[-1])


if __name__ == "__main__":
    main()
