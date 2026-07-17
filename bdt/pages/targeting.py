"""목표 압력 조절 페이지 — 팬을 조이며 목표 압력을 찾아가는 과정을 보여준다.

측정 시작 직후 PID 제어가 건물 체적·누기량에 맞는 팬 세기를 찾는 동안
(짧으면 수십 초, 목표에 못 미치면 더 오래) 예전엔 측정 차트 페이지의
진행 문구 한 줄로만 보였다. 압력이 목표선으로 기어오르는 과정을 전용
화면으로 보여주면 지금 장비가 무엇을 하는지가 한눈에 드러난다.

get_duty 에는 10초 카운터가 둘 있다 — 허용 오차 안에 머무는 수렴 카운트와,
팬이 한계에 붙은 채 오차가 남는 실패 카운트. 둘 다 "조건이 이만큼 유지되면
넘어간다"는 같은 구조라, 화면에서도 같은 언어로 보여준다: **유지된 구간을
색칠하고, 남은 시간을 타일에 센다.** 색만 다르다 (수렴=accent, 실패=경고색).

센서는 측정 스레드가 읽고 있으므로 이 페이지는 직접 센서를 읽지 않는다
(직렬 포트 동시 접근 금지). 모든 값은 작업 스레드의 시그널로 받는다.
"""

import math

from PyQt6.QtWidgets import (
    QWidget,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QProgressBar,
    QFrame,
)
from PyQt6.QtCore import QPointF, Qt, QMargins, pyqtSignal
from PyQt6.QtCharts import QChart, QChartView, QLineSeries, QAreaSeries, QValueAxis
from PyQt6.QtGui import QFont, QColor, QPen, QBrush, QPainter

from bdt import theme
from bdt.widgets import confirm
from bdt.scale import nice_step


class TargetingPage(QWidget):
    """PID 가 목표 압력을 찾아가는 동안의 압력 추이 + 유지 카운트."""

    cancelled = pyqtSignal()  # 시험 중단 버튼 → 측정 작업 취소

    # 화면에 유지할 최근 표본 수 (0.1~0.5초 간격이라 약 1~2분치)
    MAX_SAMPLES = 300

    def __init__(self, initial_message="목표 압력을 맞추는 중…", target=70.0,
                 tolerance=7.0):
        super().__init__()
        self.target = float(target)
        self.tolerance = float(tolerance)
        self._samples = []
        self._next_x = 0
        self._hold_kind = None    # "converge" | "fail" | None
        self._hold_start_x = None
        self._limit_level = None  # 팬 한계에서 도달한 압력 (실패 유지 중에만)

        # ── 상단: 메시지(좌) + 압력/팬 세기/유지 타일 + 중단 버튼(우) ──
        self.message_label = QLabel(initial_message)
        self.message_label.setObjectName("Message")
        self.progress = QLabel("팬 속도를 조절하고 있습니다…")
        self.progress.setObjectName("Hint")
        self.progress.setWordWrap(True)
        head = QVBoxLayout()
        head.setSpacing(4)
        head.addWidget(self.message_label)
        head.addWidget(self.progress)

        self.pressure_value = QLabel("–")
        pressure_tile = self._stat_tile(
            f"현재 압력 / 목표 {self.target:.0f}", self.pressure_value, "Pa")
        self.duty_value = QLabel("–")
        duty_tile = self._stat_tile("팬 세기", self.duty_value, "%")
        self.hold_tile, self.hold_name, self.hold_value, self.hold_bar = \
            self._hold_tile()

        self.cancel_button = QPushButton("시험 중단")
        self.cancel_button.setObjectName("Secondary")
        self.cancel_button.setMinimumWidth(140)
        self.cancel_button.clicked.connect(self._confirm_cancel)

        top_bar = QHBoxLayout()
        top_bar.setSpacing(0)
        top_bar.addLayout(head)
        top_bar.addStretch(1)
        top_bar.addWidget(pressure_tile)
        top_bar.addSpacing(12)
        top_bar.addWidget(duty_tile)
        top_bar.addSpacing(12)
        top_bar.addWidget(self.hold_tile)
        top_bar.addSpacing(16)
        top_bar.addWidget(self.cancel_button, 0, Qt.AlignmentFlag.AlignTop)

        # ── 압력 추이 차트 ──────────────────────────────────────
        self.chart = QChart()
        self.chart.setBackgroundVisible(True)
        self.chart.setBackgroundBrush(QBrush(QColor(theme.COLOR_PLOT)))
        self.chart.setBackgroundPen(QPen(Qt.PenStyle.NoPen))
        self.chart.setBackgroundRoundness(6)
        self.chart.setPlotAreaBackgroundVisible(False)
        self.chart.setMargins(QMargins(8, 4, 16, 4))
        # 실시간 갱신 차트라 애니메이션 금지 (live_pressure 의 교훈:
        # 갱신마다 애니메이션이 재시작돼 선이 영영 그려지지 않았다)
        self.chart.setAnimationOptions(QChart.AnimationOption.NoAnimation)
        title_font = QFont()
        title_font.setPointSize(11)
        title_font.setBold(True)
        self.chart.setTitleFont(title_font)
        self.chart.setTitleBrush(QColor(theme.COLOR_INK))
        self.chart.setTitle("압력 조절 추이")
        self.chart.legend().setVisible(True)
        self.chart.legend().setAlignment(Qt.AlignmentFlag.AlignBottom)
        legend_font = QFont()
        legend_font.setPointSize(10)
        self.chart.legend().setFont(legend_font)
        self.chart.legend().setLabelColor(QColor(theme.COLOR_SUB))

        self.axis_x = QValueAxis()
        self.axis_x.setTitleText("경과 (측정 횟수)")
        self.axis_x.setLabelFormat("%.0f")
        self.axis_y = QValueAxis()
        self.axis_y.setTitleText("압력차 Δp (Pa)")
        self.axis_y.setLabelFormat("%.0f")
        axis_font = QFont()
        axis_font.setPointSize(9)
        for ax in (self.axis_x, self.axis_y):
            ax.setLabelsFont(axis_font)
            ax.setTitleFont(axis_font)
            ax.setLabelsColor(QColor(theme.COLOR_SUB))
            ax.setTitleBrush(QColor(theme.COLOR_INK))
            ax.setGridLineColor(QColor(theme.COLOR_CHART_GRID))
            ax.setMinorTickCount(1)
            ax.setMinorGridLineColor(QColor(theme.COLOR_CHART_GRID_SOFT))
            ax.setLinePenColor(QColor(theme.COLOR_CHART_GRID))
            ax.setShadesVisible(False)
        self.chart.addAxis(self.axis_x, Qt.AlignmentFlag.AlignBottom)
        self.chart.addAxis(self.axis_y, Qt.AlignmentFlag.AlignLeft)

        # 수렴 허용 범위 띠 — 목표선 하나만 있으면 곡선이 선을 넘나드는 게
        # '못 맞추고 헤매는 것'처럼 보인다. 판정 기준을 깔아 두면 같은 곡선이
        # '범위 안에 있다'로 읽힌다.
        self._band_hi, self._band_lo, self.band = self._add_area(
            self.target + self.tolerance, self.target - self.tolerance,
            theme.COLOR_ACCENT, 28, f"수렴 범위 ±{self.tolerance:.0f} Pa")
        # 띠 자체는 배경이라 옅어야 하지만, 그 alpha 그대로면 범례 마커가 흰
        # 네모로 보여 이름표가 무엇을 가리키는지 알 수 없다. 마커만 진하게 준다.
        band_marker = QColor(theme.COLOR_ACCENT)
        band_marker.setAlpha(90)
        self.chart.legend().markers(self.band)[0].setBrush(QBrush(band_marker))
        # 조건이 유지된 구간만 진하게 덧칠한다 (수렴이면 accent, 실패면 경고색).
        # 범위를 벗어나면 색칠이 사라져 카운트가 리셋된 것이 눈에 보인다.
        self._hold_hi, self._hold_lo, self.hold_area = self._add_area(
            self.target + self.tolerance, self.target - self.tolerance,
            theme.COLOR_ACCENT, 0, "유지 구간")
        self.chart.legend().markers(self.hold_area)[0].setVisible(False)

        # 팬 한계에서 실제로 도달한 압력 (실패 경로에서만 보인다)
        self.limit_line = QLineSeries()
        self.limit_line.setName("팬 한계 도달")
        limit_pen = QPen(QColor(theme.COLOR_WARNING))
        limit_pen.setWidthF(1.2)
        limit_pen.setStyle(Qt.PenStyle.DashLine)
        self.limit_line.setPen(limit_pen)
        self.chart.addSeries(self.limit_line)
        self.limit_line.attachAxis(self.axis_x)
        self.limit_line.attachAxis(self.axis_y)
        # 표시 여부는 _redraw_limit 이 _limit_level 하나만 보고 정한다

        # 목표 압력 기준선
        self.target_line = QLineSeries()
        self.target_line.setName(f"목표 {self.target:.0f} Pa")
        target_pen = QPen(QColor(theme.COLOR_CROSSHAIR))
        target_pen.setWidthF(1.1)
        target_pen.setStyle(Qt.PenStyle.DashLine)
        self.target_line.setPen(target_pen)
        self.chart.addSeries(self.target_line)
        self.target_line.attachAxis(self.axis_x)
        self.target_line.attachAxis(self.axis_y)

        # 압력 추이 (띠 위에 그려야 하므로 마지막에 추가)
        self.series = QLineSeries()
        pen = QPen(QColor(theme.COLOR_DEP))
        pen.setWidth(2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        self.series.setPen(pen)
        self.series.setName("압력차")
        self.chart.addSeries(self.series)
        self.series.attachAxis(self.axis_x)
        self.series.attachAxis(self.axis_y)

        self._rescale()

        chart_view = QChartView(self.chart)
        chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        chart_card = QFrame()
        chart_card.setObjectName("Card")
        chart_layout = QVBoxLayout(chart_card)
        chart_layout.setContentsMargins(16, 14, 16, 14)
        chart_layout.addWidget(chart_view)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 20, 40, 28)
        outer.setSpacing(18)
        outer.addLayout(top_bar)
        outer.addWidget(chart_card, 1)

    # ── 구성 헬퍼 ──────────────────────────────────────────────
    def _add_area(self, y_hi, y_lo, color, alpha, name):
        """가로 띠 하나를 만든다. (상단선, 하단선, 영역) 을 돌려준다.

        QLineSeries 참조를 잃으면 파이썬이 GC 해 띠가 사라지므로 함께 반환해
        페이지가 들고 있게 한다.
        """
        hi, lo = QLineSeries(), QLineSeries()
        for x in (0.0, 1.0):
            hi.append(x, y_hi)
            lo.append(x, y_lo)
        area = QAreaSeries(hi, lo)
        area.setName(name)
        c = QColor(color)
        c.setAlpha(alpha)
        area.setBrush(QBrush(c))
        area.setPen(QPen(Qt.PenStyle.NoPen))
        self.chart.addSeries(area)
        area.attachAxis(self.axis_x)
        area.attachAxis(self.axis_y)
        return hi, lo, area

    @staticmethod
    def _stat_tile(name, value_label, unit):
        """성적서 KPI 카드와 같은 구성의 스탯 타일을 만든다."""
        title = QLabel(name)
        title.setObjectName("StatName")
        title.setAlignment(Qt.AlignmentFlag.AlignRight)
        value_label.setObjectName("StatValue")
        value_label.setAlignment(Qt.AlignmentFlag.AlignRight
                                 | Qt.AlignmentFlag.AlignBottom)
        unit_label = QLabel(unit)
        unit_label.setObjectName("StatUnit")
        row = QHBoxLayout()
        row.setSpacing(4)
        row.setContentsMargins(0, 0, 0, 0)
        row.addStretch(1)
        row.addWidget(value_label)
        row.addWidget(unit_label, 0, Qt.AlignmentFlag.AlignBottom)
        tile = QFrame()
        tile.setObjectName("Card")
        tile.setMinimumWidth(170)
        layout = QVBoxLayout(tile)
        layout.setContentsMargins(18, 10, 18, 12)
        layout.setSpacing(0)
        layout.addWidget(title)
        layout.addLayout(row)
        return tile

    def _hold_tile(self):
        """유지 카운트 타일 (이름 + 경과/목표 + 진행 막대)."""
        name = QLabel("수렴 유지")
        name.setObjectName("StatName")
        name.setAlignment(Qt.AlignmentFlag.AlignRight)
        value = QLabel("–")
        value.setObjectName("StatValue")
        value.setAlignment(Qt.AlignmentFlag.AlignRight
                           | Qt.AlignmentFlag.AlignBottom)
        unit = QLabel("초")
        unit.setObjectName("StatUnit")
        row = QHBoxLayout()
        row.setSpacing(4)
        row.setContentsMargins(0, 0, 0, 0)
        row.addStretch(1)
        row.addWidget(value)
        row.addWidget(unit, 0, Qt.AlignmentFlag.AlignBottom)
        bar = QProgressBar()
        bar.setTextVisible(False)
        bar.setFixedWidth(150)
        bar.setRange(0, 100)
        bar.setValue(0)
        tile = QFrame()
        tile.setObjectName("Card")
        tile.setMinimumWidth(170)
        layout = QVBoxLayout(tile)
        layout.setContentsMargins(18, 10, 18, 12)
        layout.setSpacing(2)
        layout.addWidget(name)
        layout.addLayout(row)
        layout.addWidget(bar)
        return tile, name, value, bar

    # ── 축 ────────────────────────────────────────────────────
    @staticmethod
    def _axis_up_from_zero(top, ticks=5):
        """0 에서 시작해 top 을 덮는 (상한, 눈금 수)를 예쁜 간격으로 만든다.

        압력차 절대값·표본 수는 음수가 없으므로 하한은 항상 0 이다.
        """
        step = nice_step(max(top, 1.0) / ticks)
        hi = math.ceil(top / step) * step
        return hi, int(round(hi / step)) + 1

    def _rescale(self):
        """표본·목표선·띠가 함께 보이도록 축을 다시 잡는다."""
        ys = [p.y() for p in self._samples] + [self.target + self.tolerance]
        y_hi, y_ticks = self._axis_up_from_zero(max(ys) * 1.1)
        self.axis_y.setRange(0, y_hi)
        self.axis_y.setTickCount(y_ticks)

        x_lo = max(0, self._next_x - self.MAX_SAMPLES)
        x_hi, x_ticks = self._axis_up_from_zero(max(self._next_x, 50))
        self.axis_x.setRange(x_lo, x_hi)
        self.axis_x.setTickCount(x_ticks)

        self.target_line.replace([QPointF(x_lo, self.target),
                                  QPointF(x_hi, self.target)])
        self._span(self._band_hi, self._band_lo, x_lo, x_hi,
                   self.target + self.tolerance, self.target - self.tolerance)
        self._redraw_limit(x_lo, x_hi)
        self._redraw_hold(x_hi)

    @staticmethod
    def _span(hi_series, lo_series, x0, x1, y_hi, y_lo):
        hi_series.replace([QPointF(x0, y_hi), QPointF(x1, y_hi)])
        lo_series.replace([QPointF(x0, y_lo), QPointF(x1, y_lo)])

    def _redraw_limit(self, x_lo, x_hi):
        """팬 한계 기준선을 현재 축 범위에 맞춰 다시 긋는다.

        _rescale 이 이 선을 갱신하지 않으면, x 축이 늘어난 뒤에도 선은 옛
        범위에 남아 플롯 중간에서 끊긴 토막이 된다.
        """
        marker = self.chart.legend().markers(self.limit_line)[0]
        if self._limit_level is None:
            self.limit_line.clear()
            marker.setVisible(False)
            return
        self.limit_line.setName(f"팬 한계 도달 {self._limit_level:.0f} Pa")
        self.limit_line.replace([QPointF(x_lo, self._limit_level),
                                 QPointF(x_hi, self._limit_level)])
        marker.setVisible(True)

    def _redraw_hold(self, x_hi=None):
        """유지 구간 색칠을 현재 상태에 맞춰 다시 그린다."""
        if self._hold_kind is None or self._hold_start_x is None:
            self._span(self._hold_hi, self._hold_lo, 0.0, 0.0, 0.0, 0.0)
            return
        x1 = self._next_x if x_hi is None else min(self._next_x, x_hi)
        if self._hold_kind == "converge":
            y_hi = self.target + self.tolerance
            y_lo = self.target - self.tolerance
        else:
            # 실패 유지 — 팬 한계에서 실제로 도달한 압력 주변을 칠한다.
            # 목표 띠를 칠하면 닿지도 못한 범위를 유지 중이라고 오해시킨다.
            level = self._samples[-1].y() if self._samples else self.target
            y_hi, y_lo = level + self.tolerance * 0.35, level - self.tolerance * 0.35
        self._span(self._hold_hi, self._hold_lo,
                   float(self._hold_start_x), float(x1), y_hi, y_lo)

    # ── 작업 스레드에서 오는 갱신 ──────────────────────────────
    def update_position(self, duty, pressure):
        """(팬 세기, 압력차) 표본 하나를 반영한다."""
        self.pressure_value.setText(f"{pressure:.1f}")
        self.duty_value.setText(f"{duty:.0f}")
        self._samples.append(QPointF(self._next_x, pressure))
        self._next_x += 1
        if len(self._samples) > self.MAX_SAMPLES:
            self._samples.pop(0)
        self.series.replace(self._samples)
        self._rescale()

    def update_hold(self, kind, elapsed, total):
        """수렴·실패 유지 카운트를 반영한다 (get_duty 의 두 카운터).

        elapsed 가 0 이면 조건이 깨진 것 — 색칠을 지우고 카운트를 되돌린다.
        """
        if elapsed <= 0:
            if self._hold_kind == kind:
                self._hold_kind = None
                self._hold_start_x = None
                self._limit_level = None
                self._set_hold_style(None)
                self.hold_name.setText("수렴 유지")
                self.hold_value.setText("–")
                self.hold_bar.setValue(0)
                self._redraw_hold()
                self._redraw_limit(self.axis_x.min(), self.axis_x.max())
            return

        if self._hold_kind != kind:
            self._hold_kind = kind
            self._hold_start_x = max(0, self._next_x - 1)
            # 종류가 바뀌면 이전 종류의 흔적(팬 한계선)은 지운다 — 수렴으로
            # 돌아왔는데 "팬 한계 도달" 선이 남아 있으면 상태를 오해시킨다.
            if kind != "fail":
                self._limit_level = None
                self._redraw_limit(self.axis_x.min(), self.axis_x.max())
            self._set_hold_style(kind)

        self.hold_value.setText(f"{elapsed:.0f}")
        self.hold_bar.setValue(int(min(100, elapsed / total * 100)))
        self.hold_name.setText(
            "수렴 유지" if kind == "converge" else "⚠ 팬 한계 유지")
        self._redraw_hold()

        # 실패 유지 중이면 도달한 압력 수준을 기준선으로 보여준다
        if kind == "fail" and self._samples:
            self._limit_level = self._samples[-1].y()
            self._redraw_limit(self.axis_x.min(), self.axis_x.max())

    def _set_hold_style(self, kind):
        """유지 색칠·막대 색을 종류에 맞춘다 (수렴=accent, 실패=경고색)."""
        if kind is None:
            color, alpha = theme.COLOR_ACCENT, 0
        elif kind == "converge":
            color, alpha = theme.COLOR_ACCENT, 75
        else:
            color, alpha = theme.COLOR_WARNING, 60
        c = QColor(color)
        c.setAlpha(alpha)
        self.hold_area.setBrush(QBrush(c))
        bar_color = theme.COLOR_WARNING if kind == "fail" else theme.COLOR_ACCENT
        self.hold_bar.setStyleSheet(
            f"QProgressBar::chunk{{background-color:{bar_color};border-radius:3px;}}")
        self.hold_name.setProperty("state", "warn" if kind == "fail" else "")
        self.hold_name.style().unpolish(self.hold_name)
        self.hold_name.style().polish(self.hold_name)

    def set_progress(self, text):
        """작업 스레드의 진행 상황 문구."""
        self.progress.setText(text)

    def _confirm_cancel(self):
        """실수로 눌러 조절 과정을 날리지 않도록 한 번 되묻는다."""
        if confirm(self, "시험 중단",
                   "목표 압력 조절을 중단할까요? 팬은 정지합니다.",
                   ok_text="시험 중단", cancel_text="계속 조절", danger=True):
            self.cancel_button.setEnabled(False)
            self.cancel_button.setText("중단하는 중…")
            self.cancelled.emit()
