"""
Графики для README лабораторной № 7 по результатам scripts/event_probe.py.

    python scripts/plot_events.py
"""
import csv
import statistics
from pathlib import Path

import matplotlib.pyplot as plt

from plot_loadtest import GRID, SERIES, SURFACE, TEXT, TEXT_SECONDARY

RESULTS = Path("docs/lab7/results")
CHARTS = Path("docs/lab7")
STEPS = [
    ("relay_ms", "Событие ушло в RabbitMQ"),
    ("kitchen_ms", "Кухня поставила в очередь"),
    ("delivery_ms", "Доставка назначила курьера\nили опубликовала отказ"),
    ("saga_ms", "Сага: деньги вернулись,\nзаказ снят с кухни"),
]
RUNS = [("poll", "Релей опрашивает outbox раз в секунду", SERIES[0][0]),
        ("notify", "Релей просыпается по NOTIFY", SERIES[1][0])]


def medians(label: str) -> list[float]:
    with open(RESULTS / f"{label}.csv") as f:
        rows = list(csv.DictReader(f))
    return [statistics.median(float(r[column]) for r in rows if r[column]) for column, _ in STEPS]


def style(ax) -> None:
    ax.set_facecolor(SURFACE)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=TEXT_SECONDARY, labelsize=8.5, length=0)


def latency_chart() -> None:
    fig, ax = plt.subplots(figsize=(8.4, 4.2), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    style(ax)
    height = 0.36
    positions = range(len(STEPS))[::-1]
    for offset, (label, name, color) in zip((height / 2 + 0.02, -height / 2 - 0.02), RUNS):
        values = medians(label)
        bars = ax.barh([p + offset for p in positions], values, height=height, color=color, label=name)
        for bar, value in zip(bars, values):
            text = f"{value / 1000:.1f} с" if value >= 1000 else f"{value:.0f} мс"
            ax.annotate(text, xy=(bar.get_width(), bar.get_y() + bar.get_height() / 2), xytext=(5, 0),
                        textcoords="offset points", va="center", fontsize=8.5, color=TEXT)
    ax.set_yticks(list(positions), [name for _, name in STEPS])
    ax.tick_params(axis="y", labelsize=9, labelcolor=TEXT)
    ax.set_xlim(0, 4600)
    ax.xaxis.set_major_formatter(lambda x, _: f"{x / 1000:g} с")
    ax.legend(loc="upper right", frameon=False, fontsize=8.5, labelcolor=TEXT)
    fig.text(0.012, 0.975, "От оплаты до реакции получателей", fontsize=12, fontweight="bold", color=TEXT, va="top")
    fig.text(0.012, 0.915, "Медиана по 200 заказам, время от записи OrderPaid в outbox", fontsize=9,
             color=TEXT_SECONDARY, va="top")
    fig.subplots_adjust(left=0.29, right=0.97, top=0.83, bottom=0.08)
    save(fig, "latency.png")


def outage_chart() -> None:
    with open(RESULTS / "outage_timeline.csv") as f:
        rows = [(float(r["seconds"]), int(r["outbox_pending"]), int(r["orders_finished"])) for r in csv.DictReader(f)]
    with open(RESULTS / "outage_marks.csv") as f:
        marks = {r["event"]: float(r["seconds"]) for r in csv.DictReader(f)}
    # Брокер готов, когда релей отправил накопленное: outbox впервые опустел после запуска контейнера.
    ready = next(t for t, pending, _ in rows if t > marks["rabbitmq_started"] and pending == 0)

    fig, ax = plt.subplots(figsize=(8.4, 3.8), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    style(ax)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.axvspan(marks["rabbitmq_stopped"], ready, color=GRID, alpha=0.55, linewidth=0)
    seconds = [t for t, _, _ in rows]
    ax.plot(seconds, [p for _, p, _ in rows], color=SERIES[0][0], linewidth=2, label="Ждут в outbox")
    ax.plot(seconds, [d for _, _, d in rows], color=SERIES[1][0], linewidth=2, label="Заказов прошли все шаги")
    ax.set_xlim(0, seconds[-1])
    ax.set_ylim(0, 56)
    ax.set_xlabel("секунды", fontsize=8.5, color=TEXT_SECONDARY)
    labels = (
        (marks["rabbitmq_stopped"], "RabbitMQ\nостановлен", "right"),
        (marks["rabbitmq_started"], "контейнер\nзапущен", "left"),
        (ready, "брокер принял\nсоединение", "right"),
    )
    for x, text, side in labels:
        ax.axvline(x, color=TEXT_SECONDARY, linewidth=0.8, linestyle=(0, (3, 3)))
        ax.text(x + (0.3 if side == "left" else -0.3), 46, text, fontsize=7.5, color=TEXT_SECONDARY, va="top", ha=side)
    ax.legend(loc="center", bbox_to_anchor=(0.45, 0.4), frameon=False, fontsize=8.5, labelcolor=TEXT)
    fig.text(0.012, 0.975, "RabbitMQ недоступен: оплаты принимаются, события ждут в outbox", fontsize=12,
             fontweight="bold", color=TEXT, va="top")
    fig.text(0.012, 0.91, "50 оплат во время простоя, ни одно событие не потеряно", fontsize=9,
             color=TEXT_SECONDARY, va="top")
    fig.subplots_adjust(left=0.07, right=0.97, top=0.82, bottom=0.14)
    save(fig, "outage.png")


def save(fig, name: str) -> None:
    path = CHARTS / name
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)
    print("saved", path)


if __name__ == "__main__":
    latency_chart()
    outage_chart()
