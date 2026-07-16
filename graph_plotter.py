import os
import json
import math
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from datetime import datetime
from matplotlib import font_manager
from matplotlib.ticker import ScalarFormatter, LogLocator


# 보고서·실시간 뷰와 같은 톤
C_DEP = "#2a78d6"      # 감압 (blue)
C_PRE = "#eb6834"      # 가압 (orange)
C_INK = "#1c2430"
C_SUB = "#5b6672"
C_MUTED = "#8a94a0"
C_GRID = "#e4e8ee"
C_GRID_MINOR = "#f1f3f6"
C_50 = "#94a0ae"       # 50 Pa 기준선
C_SURFACE = "#fcfcfb"


def _nice_range(lo, hi, pad=0.12):
    """로그 축에 여유를 둔 (min, max) 범위를 만든다."""
    lo_log, hi_log = math.log10(lo), math.log10(hi)
    span = max(hi_log - lo_log, 0.1)
    return 10 ** (lo_log - span * pad), 10 ** (hi_log + span * pad)


def plot_graph(resultsd, resultsp, report):
    font_path = "./NanumSquare_acL.ttf"
    font_manager.fontManager.addfont(font_path)
    f_tick = font_manager.FontProperties(fname=font_path, size=9)
    f_axis = font_manager.FontProperties(fname=font_path, size=10.5)
    f_legend = font_manager.FontProperties(fname=font_path, size=9)
    f_note = font_manager.FontProperties(fname=font_path, size=9)

    fig, ax = plt.subplots(figsize=(2200 / 300, 1180 / 300), dpi=300)
    fig.patch.set_facecolor("white")
    ax.set_facecolor(C_SURFACE)

    series = []
    if resultsd:
        series.append(("감압", resultsd, C_DEP, "o"))
    if resultsp:
        series.append(("가압", resultsp, C_PRE, "s"))

    all_x, all_y = [], []
    q50_notes = []
    for label, res, color, marker in series:
        xs, ys = zip(*res["measured values"])
        all_x += list(xs)
        all_y += list(ys)

        # 회귀선 Q = C0·ΔP^n (측정 압력 범위 안에서만 실선, 50 Pa 까지 연장은 점선)
        x_fit = np.logspace(math.log10(min(xs)), math.log10(max(xs)), 80)
        y_fit = res["C0"] * np.power(x_fit, res["n"])
        ax.plot(x_fit, y_fit, color=color, linewidth=1.8, zorder=5,
                solid_capstyle="round",
                label=f"{label}  $Q={res['C0']:.1f}\\,\\Delta P^{{{res['n']:.2f}}}$")

        # 50 Pa 로의 연장 (측정 범위를 벗어나면 점선으로)
        q50 = res["C0"] * math.pow(50, res["n"])
        if not (min(xs) <= 50 <= max(xs)):
            x_ext = np.logspace(math.log10(min(min(xs), 50)),
                                math.log10(max(max(xs), 50)), 40)
            ax.plot(x_ext, res["C0"] * np.power(x_ext, res["n"]),
                    color=color, linewidth=1.0, linestyle=(0, (4, 3)),
                    alpha=0.7, zorder=4)

        # 측정점
        ax.scatter(xs, ys, color=color, marker=marker, s=46, zorder=7,
                   edgecolor="white", linewidth=1.3, label=f"{label} 측정값")

        # Q50 지점
        ax.scatter([50], [q50], color=color, marker="D", s=42, zorder=8,
                   edgecolor="white", linewidth=1.2)
        all_x.append(50)
        all_y.append(q50)
        q50_notes.append((label, q50, color))

    # 50 Pa 기준 세로선
    ax.axvline(50, color=C_50, linewidth=1.1, linestyle=(0, (5, 4)), zorder=2)

    # 축 범위 (데이터 기반, 로그 여유)
    x_lo, x_hi = _nice_range(min(all_x), max(all_x))
    y_lo, y_hi = _nice_range(min(all_y), max(all_y))
    ax.set_xlim(x_lo, x_hi)
    ax.set_ylim(y_lo, y_hi)
    ax.set_xscale("log")
    ax.set_yscale("log")

    # 로그축 눈금을 정수로 표기 (2·3·5·7·10… 위치)
    for axis in (ax.xaxis, ax.yaxis):
        axis.set_major_locator(LogLocator(base=10, subs=(1.0,)))
        axis.set_minor_locator(LogLocator(base=10, subs=tuple(range(2, 10))))
        axis.set_major_formatter(ScalarFormatter())
        axis.set_minor_formatter(ScalarFormatter())
    ax.tick_params(axis="both", which="major", labelsize=9, length=4,
                   color=C_GRID, labelcolor=C_SUB, direction="out")
    ax.tick_params(axis="both", which="minor", labelsize=7.5, length=2,
                   color=C_GRID, labelcolor=C_MUTED, direction="out")
    for lbl in ax.get_xticklabels(which="both") + ax.get_yticklabels(which="both"):
        lbl.set_fontproperties(f_tick)

    # 그리드 (recessive: 주선 연하게, 보조선 더 연하게)
    ax.grid(True, which="major", linestyle="-", linewidth=0.7, color=C_GRID, zorder=0)
    ax.grid(True, which="minor", linestyle="-", linewidth=0.5, color=C_GRID_MINOR, zorder=0)
    ax.set_axisbelow(True)

    # 테두리 정리 (위·오른쪽 제거, 남은 축선 연하게)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(C_GRID)

    # 축 라벨
    ax.set_xlabel("압력차 ΔP  (Pa)", fontproperties=f_axis, color=C_INK, labelpad=8)
    ax.set_ylabel("침기(누기)량  (㎥/h)", fontproperties=f_axis, color=C_INK, labelpad=8)

    # 50 Pa 주석
    ax.annotate("50 Pa", xy=(50, y_lo), xytext=(0, 4),
                textcoords="offset points", ha="center", va="bottom",
                fontproperties=f_note, color=C_SUB)

    # Q50 값 주석 (미니멀하게 우하단에)
    note = "   ·   ".join(f"{lbl} Q50 {q:,.0f} ㎥/h" for lbl, q, _c in q50_notes)
    ax.annotate(note, xy=(1, 0), xycoords="axes fraction", xytext=(-4, 6),
                textcoords="offset points", ha="right", va="bottom",
                fontproperties=f_note, color=C_SUB)

    # 범례 (측정값 + 회귀식)
    legend = ax.legend(loc="upper left", prop=f_legend, frameon=True,
                       framealpha=0.9, edgecolor=C_GRID, borderpad=0.7,
                       labelspacing=0.5, handletextpad=0.6)
    legend.get_frame().set_facecolor("white")
    for text in legend.get_texts():
        text.set_color(C_INK)

    fig.tight_layout(pad=0.6)

    # 백업 + 사용 그래프 저장
    now = datetime.now().strftime("%d%m%Y-%H%M%S")
    os.makedirs("graphs", exist_ok=True)
    fig.savefig(f"./graphs/graph_{now}.png", dpi=300, bbox_inches="tight",
                facecolor="white")
    fig.savefig("./graph.png", dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    with open("conditions.json", "r") as file:
        conditions = json.load(file)
    with open("./calculation_raw.json", "r") as file:
        calculation_raw = json.load(file)

    if conditions.get("depressurization") and conditions.get("pressurization"):
        plot_graph(calculation_raw["depressurization"],
                   calculation_raw["pressurization"],
                   calculation_raw["report"])
    elif conditions.get("depressurization"):
        plot_graph(calculation_raw["depressurization"], False,
                   calculation_raw["report"])
    elif conditions.get("pressurization"):
        plot_graph(False, calculation_raw["pressurization"],
                   calculation_raw["report"])
