"""측정 진행 상황 + 누기 그래프(압력차-누기량 산점도) 페이지."""

from PyQt6.QtWidgets import (
    QWidget,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QProgressBar,
    QFrame,
)
from PyQt6.QtCore import QPointF, Qt, pyqtSignal
from PyQt6.QtCharts import (
    QChart,
    QChartView,
    QLegend,
    QLineSeries,
    QScatterSeries,
    QValueAxis,
)
from PyQt6.QtGui import QFont, QColor, QPen, QBrush, QPainter

from bdt import theme
from bdt.widgets import confirm
from bdt.scale import padded_range


class LiveMeasurementChart(QWidget):
    """측정 진행 상황 + 누기 그래프를 실시간으로 보여주는 페이지.

    x축은 압력차(Pa), y축은 누기량(㎥/h)이다.
    감압/가압을 서로 다른 마커로 그리며, 창이 새로 열려도 앞 시험의 점을
    계속 보여주기 위해 측정값을 클래스 변수에 누적한다.
    """

    cancelled = pyqtSignal()  # 시험 중단 버튼 → 측정 작업 취소

    # {시험 종류: [(압력차, 풍량, 압력 변동폭), ...]}
    # 감압→가압으로 창이 바뀌어도 유지된다.
    # 보고서 그래프(report.graph)와 같은 축 배치라 (x, y) 순서 그대로 담는다.
    accumulated = {"depressurization": [], "pressurization": []}

    # 감압/가압 두 계열 색은 CVD(색각이상) 안전이 검증된 blue/orange 조합.
    # (bdt.theme 참고 — dataviz 검증기 6개 검사 통과)
    # 마커 모양도 달라 색만으로 구분하지 않는다.
    STYLES = {
        "depressurization": ("감압", QScatterSeries.MarkerShape.MarkerShapeCircle,
                             theme.COLOR_DEP),
        "pressurization": ("가압", QScatterSeries.MarkerShape.MarkerShapeRectangle,
                           theme.COLOR_PRE),
    }

    # 색은 bdt.theme 이 단일 소스 (recessive 그리드 + 또렷한 데이터).
    # 글자색은 성적서 그래프와 같은 단계를 쓴다: 제목·축 제목은 INK,
    # 틱 라벨은 SUB. (SUB 는 표면 대비 5.70:1 로 작은 글씨 AA 를 넘긴다.
    # 예전에 쓰던 MUTED 는 3.00:1 로 미달이라 현장에서 읽기 어려웠다.)
    C_SURFACE = theme.COLOR_PLOT        # plot 배경
    C_INK = theme.COLOR_INK             # 차트 제목·축 제목
    C_TICK = theme.COLOR_SUB            # 틱 라벨
    C_GRID_MAJOR = theme.COLOR_CHART_GRID       # 주 격자·축선 (화면용)
    C_GRID_MINOR = theme.COLOR_CHART_GRID_SOFT  # 보조 격자 (화면용)
    C_CROSSHAIR = theme.COLOR_CROSSHAIR    # 50 Pa 기준선 (성적서와 같은 색)
    # 현재 위치 원 — 데이터(파랑·주황)와 섞이지 않으면서 가장 진한 색.
    # 연한 회색(COLOR_CURSOR)으로 뒀더니 격자에 묻혀 안 보였다.
    C_CURSOR = theme.COLOR_INK             # 현재 위치 원

    # 시험의 기준 압력. 성적서 그래프처럼 항상 보이게 축에 포함시킨다.
    PRESSURE_REF = 50.0

    # 측정점이 아직 없을 때 쓰는 씨앗 범위.
    # 점이 들어오는 대로 rescale() 이 데이터에 맞춰 다시 잡는다.
    # 누기량은 팬 개수에 비례하므로 팬 1개 기준 값에 팬 개수를 곱한다.
    FLOW_MIN_PER_FAN, FLOW_MAX_PER_FAN = 800.0, 1600.0
    # KS L ISO 9972 의 시험 압력 구간
    PRESSURE_MIN, PRESSURE_MAX = 10.0, 100.0  # 압력차 (Pa)

    @classmethod
    def reset(cls):
        """새 시험을 시작할 때 누적된 점을 비운다."""
        for points in cls.accumulated.values():
            points.clear()

    def __init__(self, initial_message="측정 중…", num_fans=1):
        super(LiveMeasurementChart, self).__init__()

        # 측정점이 없을 때 쓸 씨앗 범위. 점이 들어오면 rescale() 이 데이터에 맞춰
        # 다시 잡는다. 누기량은 팬 개수에 비례한다.
        self.flow_min = self.FLOW_MIN_PER_FAN * num_fans
        self.flow_max = self.FLOW_MAX_PER_FAN * num_fans
        self.x_lo, self.x_hi = self.PRESSURE_MIN, self.PRESSURE_MAX
        self._cursor = None  # 현재 위치 원의 자리 (압력, 풍량)

        self.label = QLabel(initial_message)
        self.label.setObjectName("Message")
        # 작업 진행 상황을 실시간으로 보여준다 (set_progress 로 갱신)
        self.progress = QLabel("잠시만 기다려 주세요…")
        self.progress.setObjectName("Hint")
        self.progress.setWordWrap(True)

        # 끝이 정해진 일(안정화 대기·측정)의 남은 시간. 문구만으론 숫자가
        # 줄지 않아 멈춘 건지 기다리는 건지 알 수 없었다.
        self.countdown_bar = QProgressBar()
        self.countdown_bar.setTextVisible(False)
        self.countdown_bar.setFixedHeight(6)
        self.countdown_bar.setMaximumWidth(360)
        self.countdown_bar.setRange(0, 1000)
        self.countdown_bar.setVisible(False)

        head = QVBoxLayout()
        head.setSpacing(6)
        head.addWidget(self.label)
        head.addWidget(self.progress)
        head.addWidget(self.countdown_bar)

        # 시험 중단 — 몇 분씩 걸리는 측정을 화면에서 멈출 수단이 없으면
        # 잘못된 걸 알아채도 앱을 강제 종료하는 수밖에 없다.
        self.cancel_button = QPushButton("시험 중단")
        self.cancel_button.setObjectName("Secondary")
        self.cancel_button.setMinimumWidth(140)
        self.cancel_button.clicked.connect(self._confirm_cancel)

        top_bar = QHBoxLayout()
        top_bar.setSpacing(0)
        top_bar.addLayout(head)
        top_bar.addStretch(1)
        top_bar.addWidget(self.cancel_button, 0, Qt.AlignmentFlag.AlignTop)

        # 압력-풍량 산점도
        self.chart = QChart()
        # QChartView 는 QWidget 이라 전역 배경색을 받는다. 차트가 직접 표면색을
        # 칠해야 흰 카드 안에 회색 판이 얹힌 것처럼 보이지 않는다.
        self.chart.setBackgroundVisible(True)
        self.chart.setBackgroundBrush(QBrush(QColor(self.C_SURFACE)))
        self.chart.setBackgroundPen(QPen(Qt.PenStyle.NoPen))
        self.chart.setBackgroundRoundness(6)
        self.chart.setPlotAreaBackgroundVisible(False)
        self.chart.setTitle("누기 그래프")
        title_font = QFont()
        title_font.setPointSize(11)
        title_font.setBold(True)
        self.chart.setTitleFont(title_font)
        self.chart.setTitleBrush(QColor(self.C_INK))
        self.chart.legend().setVisible(True)
        self.chart.legend().setAlignment(Qt.AlignmentFlag.AlignBottom)
        legend_font = QFont()
        legend_font.setPointSize(10)
        self.chart.legend().setFont(legend_font)
        self.chart.legend().setLabelColor(QColor(self.C_TICK))
        # 범례 마커를 시리즈 마커 모양(원/사각)과 같게 해 색·모양이 함께 식별되도록 한다
        self.chart.legend().setMarkerShape(
            QLegend.MarkerShape.MarkerShapeFromSeries)

        # 축 배치는 성적서 그래프와 동일하게 x=압력차, y=풍량으로 둔다.
        #
        # 성적서는 멱함수 Q=C·ΔP^n 을 직선으로 읽히게 로그-로그로 그리지만,
        # 여기서는 선형 축을 쓴다. QLogValueAxis 는 밑수의 거듭제곱(10·100…)
        # 에만 major 눈금을 두는데 실제 시험 구간(약 20~70 Pa)은 한 십진 구간
        # 안이라 눈금 라벨이 하나도 표시되지 않는다(matplotlib 은 minor 눈금에
        # 라벨을 달 수 있어 성적서에선 문제가 없다). 축에 숫자가 없는 실시간
        # 화면은 쓸모가 없다. 이 화면의 일은 "지금 어느 지점을 찍고 있는가"를
        # 보여주는 것이고, 회귀선 판독은 성적서가 맡는다.
        self.axis_x = QValueAxis()
        self.axis_x.setTitleText("압력차 Δp (Pa)")
        self.axis_x.setLabelFormat("%.0f")
        self.axis_x.setTickCount(6)
        self.axis_x.setRange(self.PRESSURE_MIN, self.PRESSURE_MAX)
        self.axis_y = QValueAxis()
        self.axis_y.setTitleText("누기량 (㎥/h)")
        self.axis_y.setLabelFormat("%.0f")
        self.axis_y.setTickCount(6)
        self.axis_y.setRange(self.flow_min, self.flow_max)
        axis_font = QFont()
        axis_font.setPointSize(9)
        title_ax_font = QFont()
        title_ax_font.setPointSize(9)
        for ax in (self.axis_x, self.axis_y):
            ax.setLabelsFont(axis_font)
            ax.setTitleFont(title_ax_font)
            ax.setLabelsColor(QColor(self.C_TICK))
            ax.setTitleBrush(QColor(self.C_INK))
            ax.setGridLineColor(QColor(self.C_GRID_MAJOR))
            # 주 눈금 사이 보조선 1개 — 주선보다 더 연하게 깔아 눈금 감각만 준다
            ax.setMinorTickCount(1)
            ax.setMinorGridLineColor(QColor(self.C_GRID_MINOR))
            ax.setLinePenColor(QColor(self.C_GRID_MAJOR))
        self.chart.addAxis(self.axis_x, Qt.AlignmentFlag.AlignBottom)
        self.chart.addAxis(self.axis_y, Qt.AlignmentFlag.AlignLeft)

        # 50 Pa 기준선 — 성적서 그래프와 같은 자리에 같은 모양으로 둔다.
        # 측정이 겨냥하는 압력이라 지금 얼마나 왔는지 가늠하는 기준이 된다.
        self.ref_line = QLineSeries()
        self.ref_line.setName(f"{self.PRESSURE_REF:.0f} Pa 기준")
        ref_pen = QPen(QColor(self.C_CROSSHAIR))
        ref_pen.setWidthF(1.1)
        ref_pen.setStyle(Qt.PenStyle.DashLine)
        self.ref_line.setPen(ref_pen)
        self.chart.addSeries(self.ref_line)
        self.ref_line.attachAxis(self.axis_x)
        self.ref_line.attachAxis(self.axis_y)

        # 현재 측정 위치 — 빈 동그라미.
        #
        # 예전엔 가로·세로 점선 십자였다. 점선 두 줄이 격자·기준선과 섞여
        # 정작 현재 위치가 어디인지 눈에 안 들어왔다 (실기기에서 확인). 빈
        # 원은 한 점을 가리키면서 속이 비어 있어 아래 측정 마커를 가리지 않는다.
        self.cursor = QScatterSeries()
        self.cursor.setName("현재 위치")
        self.cursor.setMarkerShape(
            QScatterSeries.MarkerShape.MarkerShapeCircle)
        self.cursor.setMarkerSize(16)
        self.cursor.setBrush(QBrush(Qt.BrushStyle.NoBrush))  # 속이 빈 원
        cursor_pen = QPen(QColor(self.C_CURSOR))
        cursor_pen.setWidthF(2.0)
        self.cursor.setPen(cursor_pen)
        self.chart.addSeries(self.cursor)
        self.cursor.attachAxis(self.axis_x)
        self.cursor.attachAxis(self.axis_y)

        # 변동폭 가로선의 범례 항목.
        # 막대는 지점마다 별도 시리즈로 그려야 해서(QLineSeries 는 NaN 으로
        # 선을 끊지 못하고 Qt 가 아예 무시한다) 범례가 지저분해진다. 그래서
        # 막대들의 범례 표시는 모두 끄고, 설명용으로 이 시리즈 하나만 남긴다.
        self.range_legend = QLineSeries()
        self.range_legend.setName("측정 중 압력 변동 (±1σ)")
        legend_pen = QPen(QColor(self.C_TICK))
        legend_pen.setWidthF(1.6)
        self.range_legend.setPen(legend_pen)
        self.chart.addSeries(self.range_legend)
        self.range_legend.attachAxis(self.axis_x)
        self.range_legend.attachAxis(self.axis_y)

        # 지점별 변동폭 가로선 (그린 뒤 참조를 들고 있어야 GC 되지 않는다)
        self.range_bars = []

        # 감압/가압 각각의 시리즈를 만들고 누적된 점을 복원한다
        self.series = {}
        for test_type, (name, shape, color) in self.STYLES.items():
            scatter = QScatterSeries()
            scatter.setName(name)
            scatter.setMarkerShape(shape)
            scatter.setMarkerSize(13)
            scatter.setColor(QColor(color))
            # 겹치는 마크는 2px 표면색 링으로 분리 (dataviz 마크 스펙)
            scatter.setBorderColor(QColor(theme.COLOR_SURFACE))
            pen = QPen(QColor(theme.COLOR_SURFACE))
            pen.setWidthF(2)
            scatter.setPen(pen)
            self.chart.addSeries(scatter)
            scatter.attachAxis(self.axis_x)
            scatter.attachAxis(self.axis_y)
            self.series[test_type] = scatter

        # 누적된 점과 그 변동폭 가로선을 복원한다 (시리즈를 모두 만든 뒤에
        # 해야 두 시험의 막대가 제 색으로 붙는다)
        for test_type in self.STYLES:
            for pressure, flow, sigma in self.accumulated[test_type]:
                self.series[test_type].append(pressure, flow)
                self._draw_range(pressure, flow, sigma, test_type)

        # 앞 시험에서 넘어온 점이 있으면 그 점들에 맞춰 축을 잡고,
        # 없으면 씨앗 범위에 기준선만 그린다.
        self.rescale()

        chart_view = QChartView(self.chart)
        chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        chart_card = QFrame()
        chart_card.setObjectName("Card")
        chart_card_layout = QVBoxLayout(chart_card)
        chart_card_layout.setContentsMargins(16, 14, 16, 14)
        chart_card_layout.addWidget(chart_view)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 20, 40, 28)
        outer.setSpacing(18)
        outer.addLayout(top_bar)
        outer.addWidget(chart_card, 1)

    def _confirm_cancel(self):
        """실수로 눌러 몇 분치 측정을 날리지 않도록 한 번 되묻는다."""
        if confirm(self, "시험 중단",
                   "진행 중인 측정을 중단할까요? 지금까지 측정한 값은 "
                   "저장되지 않고, 팬은 정지합니다.",
                   ok_text="시험 중단", cancel_text="계속 측정", danger=True):
            self.cancel_button.setEnabled(False)
            self.cancel_button.setText("중단하는 중…")
            self.cancelled.emit()

    def set_progress(self, text):
        """작업 스레드가 보내온 진행 상황을 표시한다."""
        self.progress.setText(text)
        # 카운트다운이 아닌 일반 문구가 오면 막대를 치운다 (남은 시간이
        # 없는 상태에서 멈춘 막대가 남아 있으면 그게 더 헷갈린다)
        self.countdown_bar.setVisible(False)

    def set_countdown(self, label, remaining, total):
        """끝이 정해진 일의 남은 시간을 문구 + 막대로 보여준다."""
        self.progress.setText(f"{label} — {remaining:.0f}초 남음")
        done = (total - remaining) / total if total > 0 else 1.0
        self.countdown_bar.setValue(int(min(max(done, 0.0), 1.0) * 1000))
        self.countdown_bar.setVisible(True)

    def rescale(self):
        """측정점에 맞춰 두 축 범위를 다시 잡는다.

        고정 범위(예전 0.1~100 Pa)로 두면 실제 시험 구간이 plot 한구석에
        몰려 점들이 어떻게 늘어서는지 눈으로 읽을 수 없다.
        50 Pa 기준선은 항상 보이도록 범위에 포함시킨다.
        """
        xs = [self.PRESSURE_REF]
        ys = []
        for points in self.accumulated.values():
            for pressure, flow, sigma in points:
                # 변동폭 가로선의 양 끝까지 축 안에 들어와야 잘리지 않는다
                xs.extend((pressure - sigma, pressure + sigma))
                ys.append(flow)

        if not ys:
            # 측정점이 아직 없다 — 기준선(50 Pa) 하나로 범위를 잡으면 x축이
            # ±0.6 Pa 로 붕괴해 십자 포인터가 50 근처에 클램프돼 버린다.
            # 씨앗 범위(시험 압력 구간)를 유지하고 기준선·십자만 갱신한다.
            self.x_lo, self.x_hi = self.PRESSURE_MIN, self.PRESSURE_MAX
            self.axis_x.setRange(self.x_lo, self.x_hi)
            self.axis_y.setRange(self.flow_min, self.flow_max)
            self.ref_line.replace([QPointF(self.PRESSURE_REF, self.flow_min),
                                   QPointF(self.PRESSURE_REF, self.flow_max)])
            self._redraw_crosshair()
            return

        self.x_lo, self.x_hi, x_ticks = padded_range(min(xs), max(xs),
                                                      min_span=5.0)
        self.axis_x.setRange(self.x_lo, self.x_hi)
        self.axis_x.setTickCount(x_ticks)
        if ys:
            self.flow_min, self.flow_max, y_ticks = padded_range(
                min(ys), max(ys), min_span=100.0)
            self.axis_y.setRange(self.flow_min, self.flow_max)
            self.axis_y.setTickCount(y_ticks)

        # 기준선·십자 포인터는 축 범위를 따라 길이가 달라진다
        self.ref_line.replace([QPointF(self.PRESSURE_REF, self.flow_min),
                               QPointF(self.PRESSURE_REF, self.flow_max)])
        self._redraw_crosshair()

    def _redraw_crosshair(self):
        """현재 위치 원을 다시 찍는다 (축 범위가 바뀌면 클램프도 다시 한다)."""
        if self._cursor is None:
            return
        pressure, flow = self._cursor
        self.cursor.replace([QPointF(pressure, flow)])

    def move_crosshair(self, flow, pressure):
        """현재 측정 위치를 빈 원으로 표시한다 (측정 마커는 찍지 않는다).

        축이 x=압력차, y=풍량이다. 축 밖으로 나가면 원이 사라져 위치를 잃으므로
        범위 안으로 붙여 둔다.
        """
        flow = min(max(flow, self.flow_min), self.flow_max)
        pressure = min(max(abs(pressure), self.x_lo), self.x_hi)
        self._cursor = (pressure, flow)
        self._redraw_crosshair()

    def _draw_range(self, pressure, flow, sigma, test_type):
        """측정 중 압력이 흔들린 폭(±1σ)을 점 위에 가로선으로 그린다.

        y(풍량)는 duty 에서 계산한 값이라 변동이 없고, 흔들리는 축은 x(압력차)
        뿐이라 가로선이 된다. 0 기류 보정을 생략하는 운용이므로, 이 선이 길면
        바람이 센 상태에서 잡힌 점이라는 뜻이다.
        """
        if sigma <= 0:
            return
        bar = QLineSeries()
        pen = QPen(QColor(self.STYLES[test_type][2]))
        pen.setWidthF(1.6)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        bar.setPen(pen)
        bar.append(pressure - sigma, flow)
        bar.append(pressure + sigma, flow)
        self.chart.addSeries(bar)
        bar.attachAxis(self.axis_x)
        bar.attachAxis(self.axis_y)
        # 막대마다 범례가 생기면 못 쓸 정도로 지저분해진다. 설명은
        # range_legend 하나가 대신한다.
        markers = self.chart.legend().markers(bar)
        if markers:
            markers[0].setVisible(False)
        # 마커(점)가 가로선 위에 오도록 순서를 유지 — 산점도를 다시 맨 앞으로
        scatter = self.series[test_type]
        self.chart.removeSeries(scatter)
        self.chart.addSeries(scatter)
        scatter.attachAxis(self.axis_x)
        scatter.attachAxis(self.axis_y)
        self.range_bars.append(bar)

    def add_point(self, flow, pressure, sigma, test_type):
        """확정된 측정점을 마커로 찍는다. 압력차는 절대값으로 그린다.

        sigma 는 그 지점을 측정하는 동안의 압력 표준편차다.
        """
        if test_type not in self.series:
            return
        # 그래프 좌표는 (x=압력차, y=풍량)
        self.accumulated[test_type].append((abs(pressure), flow, sigma))
        self.series[test_type].append(abs(pressure), flow)
        self._draw_range(abs(pressure), flow, sigma, test_type)
        # 새 점이 범위 밖일 수 있으므로 축을 다시 잡는다
        self.rescale()
        self.move_crosshair(flow, pressure)
