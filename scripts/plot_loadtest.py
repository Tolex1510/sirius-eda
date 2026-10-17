"""
Графики «до / после» для README по результатам scripts/loadtest.sh.

    python scripts/plot_loadtest.py nocache cache
"""
import csv
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

RESULTS = Path("docs/lab4/results")
# 500 пользователей при 10 в секунду подключаются за 50 с. Средние считаются после разгона.
STEADY_FROM = 60
CHARTS = Path("docs/lab4")

SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#e4e3df"
# Слоты 1 и 2 проверенной категориальной палитры: различимы и при дальтонизме.
SERIES = [("#2a78d6", "Без кеша"), ("#eb6834", "С кешем Redis")]


def locust_history(label: str) -> tuple[list[float], list[float], list[float]]:
    seconds, rps, p95 = [], [], []
    with open(RESULTS / f"{label}_stats_history.csv") as f:
        rows = [r for r in csv.DictReader(f) if r["Name"] == "Aggregated" and r["95%"] != "N/A"]
    start = int(rows[0]["Timestamp"])
    for row in rows:
        seconds.append(int(row["Timestamp"]) - start)
        rps.append(float(row["Requests/s"]))
        p95.append(float(row["95%"]) / 1000)
    return seconds, rps, p95


def db_cpu(label: str) -> tuple[list[float], list[float]]:
    with open(RESULTS / f"{label}_system.csv") as f:
        rows = [r for r in csv.DictReader(f) if r["db_cpu"]]
    start = int(rows[0]["time"])
    return [int(r["time"]) - start for r in rows], [float(r["db_cpu"]) for r in rows]


def line_chart(path: Path, title: str, subtitle: str, unit: str, digits: int, series: list[tuple[list, list]]) -> None:
    fig, ax = plt.subplots(figsize=(8, 3.6), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    top = max(max(y) for _, y in series)
    for (color, name), (x, y) in zip(SERIES, series):
        ax.plot(x, y, color=color, linewidth=2, label=name, solid_capstyle="round")
        steady = [v for t, v in zip(x, y) if t >= STEADY_FROM]
        mean = sum(steady) / len(steady)
        # Подпись у конца линии: серия читается без легенды и без цвета.
        ax.annotate(
            f"{name}\nв среднем {mean:.{digits}f} {unit}",
            xy=(x[-1], mean),
            xytext=(6, 0),
            textcoords="offset points",
            va="center",
            fontsize=8.5,
            color=TEXT_SECONDARY,
        )

    ax.set_ylim(0, top * 1.12)
    ax.set_xlabel("Секунды с начала теста", color=TEXT_SECONDARY, fontsize=9)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=TEXT_SECONDARY, labelsize=8.5, length=0)
    ax.legend(loc="upper left", frameon=False, fontsize=8.5, labelcolor=TEXT, ncol=2, bbox_to_anchor=(0, 1.02))

    fig.text(0.012, 0.965, title, fontsize=12, fontweight="bold", color=TEXT, va="top")
    fig.text(0.012, 0.895, subtitle, fontsize=9, color=TEXT_SECONDARY, va="top")
    fig.subplots_adjust(left=0.07, right=0.8, top=0.76, bottom=0.15)
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)
    print("saved", path)


def main() -> None:
    before, after = sys.argv[1], sys.argv[2]
    b_sec, b_rps, b_p95 = locust_history(before)
    a_sec, a_rps, a_p95 = locust_history(after)

    line_chart(
        CHARTS / "rps.png",
        "Пропускная способность GET /menu",
        "Запросов в секунду, 500 пользователей. Средние после 60-й секунды, когда все подключены",
        "RPS",
        0,
        [(b_sec, b_rps), (a_sec, a_rps)],
    )
    line_chart(
        CHARTS / "latency_p95.png",
        "95-й перцентиль времени ответа",
        "Секунды. При 500 пользователях это в основном время в очереди",
        "с",
        1,
        [(b_sec, b_p95), (a_sec, a_p95)],
    )
    line_chart(
        CHARTS / "db_cpu.png",
        "Загрузка CPU контейнера PostgreSQL",
        "Проценты одного ядра, docker stats раз в 5 секунд",
        "%",
        0,
        [db_cpu(before), db_cpu(after)],
    )


if __name__ == "__main__":
    main()
