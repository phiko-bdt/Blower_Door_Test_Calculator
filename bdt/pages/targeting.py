"""목표 압력 조절 페이지 — 팬을 조이며 70 Pa 를 찾아가는 과정을 보여준다.

측정 시작 직후 PID 제어가 건물 체적·누기량에 맞는 팬 세기를 찾는 동안
(짧으면 수십 초, 목표에 못 미치면 더 오래) 예전엔 측정 차트 페이지의
진행 문구 한 줄로만 보였다. 압력이 목표선으로 기어오르는 과정을 전용
화면으로 보여주면 지금 장비가 무엇을 하는지가 한눈에 드러난다.

센서는 측정 스레드가 읽고 있으므로 이 페이지는 직접 센서를 읽지 않는다
(직렬 포트 동시 접근 금지). 모든 값은 작업 스레드의 시그널로 받는다.
"""

from PyQt6.QtWidgets import (
    QWidget,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QFrame,
    QMessageBox,
)
from PyQt6.QtCore import QPointF, Qt, QMargins, pyqtSignal
from PyQt6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis
from PyQt6.QtGui import QFont, QColor, QPen, QBrush, QPainter

import math

from bdt import theme
from bdt.scale import nice_step


class TargetingPage(QWidget):
    """PID 가 목표 압력을 찾아가는 동안의 압력 추이 + 현재 상태."""

    cancelled = pyqtSignal()  # 시험 중단 버튼 → 측정 작업 취소

    # 화면에 유지할 최근 표본 수 (0.1~0.5초 간격이라 약 1~2분치)
    MAX_SAMPLES = 300

    def __init__(self, initial_message="목표 압력을 맞추는 중…", target=70.0):
        super().__init__()
        self.target = float(target)
        self._samples = []
        self._next_x = 0

        # ── 상단: 메시지(좌) + 압력/팬 세기 타일 + 중단 버튼(우) ──
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
        top_bar.addSpacing(16)
        top_bar.addWidget(self.cancel_button, 0, Qt.AlignmentFlag.AlignTop)

        # ── 압력 추이 차트 (목표선 포함) ─────────────────────────
        self.series = QLineSeries()
        pen = QPen(QColor(theme.COLOR_DEP))
        pen.setWidth(2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        self.series.setPen(pen)
        self.series.setName("압력차")

        # 목표 압력 기준선 — 측정 차트의 50 Pa 기준선과 같은 표현
        self.target_line = QLineSeries()
        self.target_line.setName(f"목표 {self.target:.0f} Pa")
        target_pen = QPen(QColor(theme.COLOR_CROSSHAIR))
        target_pen.setWidthF(1.1)
        target_pen.setStyle(Qt.PenStyle.DashLine)
        self.target_line.setPen(target_pen)

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
        self.chart.addSeries(self.series)
        self.chart.addSeries(self.target_line)

        self.axis_x = QValueAxis()
        self.axis_x.setTitleText("경과 (측정 횟수)")
        self.axis_x.setLabelFormat("%.0f")
        self.axis_x.setTickCount(5)
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
        for s in (self.series, self.target_line):
            s.attachAxis(self.axis_x)
            s.attachAxis(self.axis_y)
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

    @staticmethod
    def _axis_up_from_zero(top, ticks=5):
        """0 에서 시작해 top 을 덮는 (상한, 눈금 수)를 예쁜 간격으로 만든다.

        압력차 절대값·표본 수는 음수가 없으므로 하한은 항상 0 이다.
        padded_range 는 아래쪽에도 여백을 줘 축이 음수로 내려간다.
        """
        step = nice_step(max(top, 1.0) / ticks)
        hi = math.ceil(top / step) * step
        return hi, int(round(hi / step)) + 1

    def _rescale(self):
        """표본과 목표선이 함께 보이도록 축을 다시 잡는다."""
        ys = [p.y() for p in self._samples] + [self.target]
        y_hi, y_ticks = self._axis_up_from_zero(max(ys) * 1.15)
        self.axis_y.setRange(0, y_hi)
        self.axis_y.setTickCount(y_ticks)

        x_lo = max(0, self._next_x - self.MAX_SAMPLES)
        x_hi, x_ticks = self._axis_up_from_zero(max(self._next_x, 50))
        self.axis_x.setRange(x_lo, x_hi)
        self.axis_x.setTickCount(x_ticks)
        self.target_line.replace([QPointF(x_lo, self.target),
                                  QPointF(x_hi, self.target)])

    def update_position(self, duty, pressure):
        """작업 스레드가 보내온 (팬 세기, 압력차) 표본 하나를 반영한다."""
        self.pressure_value.setText(f"{pressure:.1f}")
        self.duty_value.setText(f"{duty:.0f}")
        self._samples.append(QPointF(self._next_x, pressure))
        self._next_x += 1
        if len(self._samples) > self.MAX_SAMPLES:
            self._samples.pop(0)
        self.series.replace(self._samples)
        self._rescale()

    def set_progress(self, text):
        """작업 스레드의 진행 상황 문구."""
        self.progress.setText(text)

    def _confirm_cancel(self):
        """실수로 눌러 조절 과정을 날리지 않도록 한 번 되묻는다."""
        answer = QMessageBox.question(
            self, "시험 중단",
            "목표 압력 조절을 중단할까요?\n\n팬은 정지합니다.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            self.cancel_button.setEnabled(False)
            self.cancel_button.setText("중단하는 중…")
            self.cancelled.emit()
