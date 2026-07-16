"""측정 진행 상황 + 압력-침기(누기)량 산점도 페이지."""

from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QFrame
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtCharts import (
    QChart,
    QChartView,
    QLegend,
    QLineSeries,
    QLogValueAxis,
    QScatterSeries,
)
from PyQt6.QtGui import QFont, QColor, QPen, QPainter


class LiveMeasurementChart(QWidget):
    """측정 진행 상황 + 압력-침기(누기)량 산점도를 실시간으로 보여주는 페이지.

    x축은 풍량(㎥/h), y축은 압력차 절대값(Pa)이다.
    감압/가압을 서로 다른 마커로 그리며, 창이 새로 열려도 앞 시험의 점을
    계속 보여주기 위해 측정값을 클래스 변수에 누적한다.
    """

    # {시험 종류: [(압력차, 풍량), ...]} — 감압→가압으로 창이 바뀌어도 유지된다.
    # 보고서 그래프(report.graph)와 같은 축 배치라 (x, y) 순서 그대로 담는다.
    accumulated = {"depressurization": [], "pressurization": []}

    # 감압/가압 두 계열 색은 CVD(색각이상) 안전이 검증된 blue/orange 조합.
    # 마커 모양도 달라 색만으로 구분하지 않는다.
    STYLES = {
        "depressurization": ("감압", QScatterSeries.MarkerShape.MarkerShapeCircle, "#2a78d6"),
        "pressurization": ("가압", QScatterSeries.MarkerShape.MarkerShapeRectangle, "#eb6834"),
    }

    # 차트 표면·잉크·그리드 색 (recessive 그리드 + 또렷한 데이터)
    C_SURFACE = "#FCFCFB"     # plot 배경
    C_INK = "#2B2F36"         # 제목·축 제목
    C_INK_SUB = "#6B7280"     # 틱 라벨
    C_GRID_MAJOR = "#DDE2E8"  # 주 격자
    C_GRID_MINOR = "#EDEFF2"  # 보조 격자
    C_CROSSHAIR = "#94A0AE"   # 십자 포인터

    # 로그 축 범위 (로그 스케일이라 하한은 0 이 될 수 없다)
    # 침기(누기)량은 팬 개수에 비례하므로 팬 1개 기준 값에 팬 개수를 곱해 축을 잡는다.
    # (팬 1개 → 500~2000, 팬 2개 → 1000~4000 ㎥/h)
    FLOW_MIN_PER_FAN, FLOW_MAX_PER_FAN = 500.0, 2000.0
    # 공간에 따라 형성되는 압력차가 크게 달라져 0.1~100 Pa 를 오간다
    PRESSURE_MIN, PRESSURE_MAX = 0.1, 100.0  # 압력차 (Pa)

    @classmethod
    def reset(cls):
        """새 시험을 시작할 때 누적된 점을 비운다."""
        for points in cls.accumulated.values():
            points.clear()

    def __init__(self, initial_message="측정 중...", num_fans=1):
        super(LiveMeasurementChart, self).__init__()

        # 팬 개수에 맞춰 침기(누기)량 축 범위를 정한다
        self.flow_min = self.FLOW_MIN_PER_FAN * num_fans
        self.flow_max = self.FLOW_MAX_PER_FAN * num_fans

        self.label = QLabel(initial_message)
        self.label.setObjectName("Message")
        # 작업 진행 상황을 실시간으로 보여준다 (set_progress 로 갱신)
        self.progress = QLabel("잠시만 기다려 주세요…")
        self.progress.setObjectName("Hint")
        self.progress.setWordWrap(True)

        top_bar = QVBoxLayout()
        top_bar.setSpacing(6)
        top_bar.addWidget(self.label)
        top_bar.addWidget(self.progress)

        # 압력-풍량 산점도
        self.chart = QChart()
        self.chart.setBackgroundVisible(False)
        self.chart.setPlotAreaBackgroundBrush(QColor(self.C_SURFACE))
        self.chart.setPlotAreaBackgroundVisible(True)
        self.chart.setTitle("압력 – 침기(누기)량  (log–log)")
        title_font = QFont()
        title_font.setPointSize(13)
        title_font.setBold(True)
        self.chart.setTitleFont(title_font)
        self.chart.setTitleBrush(QColor(self.C_INK))
        self.chart.legend().setVisible(True)
        self.chart.legend().setAlignment(Qt.AlignmentFlag.AlignBottom)
        legend_font = QFont()
        legend_font.setPointSize(10)
        self.chart.legend().setFont(legend_font)
        self.chart.legend().setLabelColor(QColor(self.C_INK_SUB))
        # 범례 마커를 시리즈 마커 모양(원/사각)과 같게 해 색·모양이 함께 식별되도록 한다
        self.chart.legend().setMarkerShape(
            QLegend.MarkerShape.MarkerShapeFromSeries)

        # 압력-풍량 관계는 멱함수라 로그-로그 축으로 봐야 직선으로 읽힌다.
        # 축 배치는 보고서 그래프와 동일하게 x=압력차, y=풍량으로 둔다.
        self.axis_x = QLogValueAxis()
        self.axis_x.setTitleText("압력차 ΔP (Pa)")
        self.axis_x.setBase(10)
        self.axis_x.setLabelFormat("%g")
        self.axis_x.setRange(self.PRESSURE_MIN, self.PRESSURE_MAX)
        self.axis_y = QLogValueAxis()
        self.axis_y.setTitleText("침기(누기)량 (㎥/h)")
        self.axis_y.setBase(10)
        self.axis_y.setLabelFormat("%g")
        self.axis_y.setRange(self.flow_min, self.flow_max)
        axis_font = QFont()
        axis_font.setPointSize(10)
        title_ax_font = QFont()
        title_ax_font.setPointSize(11)
        title_ax_font.setBold(True)
        # 로그축이라 10의 배수마다 주선, 그 사이 2·3·…·9 위치에 보조선을 둔다.
        # 보조선을 major 보다 더 연하게 깔아 눈금 감각을 주되 데이터를 가리지 않는다.
        for ax in (self.axis_x, self.axis_y):
            ax.setLabelsFont(axis_font)
            ax.setTitleFont(title_ax_font)
            ax.setLabelsColor(QColor(self.C_INK_SUB))
            ax.setTitleBrush(QColor(self.C_INK))
            ax.setGridLineColor(QColor(self.C_GRID_MAJOR))
            ax.setMinorTickCount(8)  # 로그 십진 구간 안 2~9
            ax.setMinorGridLineColor(QColor(self.C_GRID_MINOR))
            ax.setLinePenColor(QColor(self.C_GRID_MAJOR))
        self.chart.addAxis(self.axis_x, Qt.AlignmentFlag.AlignBottom)
        self.chart.addAxis(self.axis_y, Qt.AlignmentFlag.AlignLeft)

        # 현재 측정 위치를 나타내는 십자 포인터 (수평선 + 수직선)
        self.crosshair = {}
        for key in ("h", "v"):
            line = QLineSeries()
            line.setName("현재 위치" if key == "h" else "")
            pen = QPen(QColor(self.C_CROSSHAIR))
            pen.setWidthF(1.4)
            pen.setStyle(Qt.PenStyle.DashLine)
            line.setPen(pen)
            self.chart.addSeries(line)
            line.attachAxis(self.axis_x)
            line.attachAxis(self.axis_y)
            self.crosshair[key] = line
        # 수직선은 범례에 중복 표시되지 않도록 숨긴다
        self.chart.legend().markers(self.crosshair["v"])[0].setVisible(False)

        # 감압/가압 각각의 시리즈를 만들고 누적된 점을 복원한다
        self.series = {}
        for test_type, (name, shape, color) in self.STYLES.items():
            scatter = QScatterSeries()
            scatter.setName(name)
            scatter.setMarkerShape(shape)
            scatter.setMarkerSize(13)
            scatter.setColor(QColor(color))
            # 겹치는 마크는 2px 흰 링으로 분리 (dataviz 마크 스펙)
            scatter.setBorderColor(QColor("#FFFFFF"))
            pen = QPen(QColor("#FFFFFF"))
            pen.setWidthF(2)
            scatter.setPen(pen)
            self.chart.addSeries(scatter)
            scatter.attachAxis(self.axis_x)
            scatter.attachAxis(self.axis_y)
            for pressure, flow in self.accumulated[test_type]:
                scatter.append(pressure, flow)
            self.series[test_type] = scatter

        chart_view = QChartView(self.chart)
        chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        chart_card = QFrame()
        chart_card.setObjectName("Card")
        chart_card_layout = QVBoxLayout(chart_card)
        chart_card_layout.setContentsMargins(12, 12, 12, 12)
        chart_card_layout.addWidget(chart_view)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 24, 40, 32)
        outer.setSpacing(18)
        outer.addLayout(top_bar)
        outer.addWidget(chart_card)

    def set_progress(self, text):
        """작업 스레드가 보내온 진행 상황을 표시한다."""
        self.progress.setText(text)

    def move_crosshair(self, flow, pressure):
        """현재 측정 위치를 십자 포인터로 표시한다 (마커는 찍지 않는다).

        축이 x=압력차, y=풍량이므로 수직선은 압력, 수평선은 풍량에 맞춘다.
        """
        flow = min(max(flow, self.flow_min), self.flow_max)
        pressure = min(max(abs(pressure), self.PRESSURE_MIN), self.PRESSURE_MAX)
        self.crosshair["h"].replace([QPointF(self.PRESSURE_MIN, flow),
                                     QPointF(self.PRESSURE_MAX, flow)])
        self.crosshair["v"].replace([QPointF(pressure, self.flow_min),
                                     QPointF(pressure, self.flow_max)])

    def add_point(self, flow, pressure, test_type):
        """확정된 측정점을 마커로 찍는다. 압력차는 절대값으로 그린다."""
        if test_type not in self.series:
            return
        # 그래프 좌표는 (x=압력차, y=풍량)
        self.accumulated[test_type].append((abs(pressure), flow))
        self.series[test_type].append(abs(pressure), flow)
        self.move_crosshair(flow, pressure)
