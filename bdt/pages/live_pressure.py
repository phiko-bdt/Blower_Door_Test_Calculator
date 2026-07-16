"""시험 준비 페이지 — 실시간 압력을 보며 측정 시작을 기다린다."""

from PyQt6.QtWidgets import (
    QWidget,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QFrame,
)
from PyQt6.QtCore import QTimer, QPointF, Qt, pyqtSignal
from PyQt6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis
from PyQt6.QtGui import QFont, QColor, QPen, QPainter

from bdt import hardware
from bdt.config import TEST_MODE
from bdt.theme import COLOR_PRIMARY, COLOR_TEXT, COLOR_SUBTLE, COLOR_BORDER


class LivePressureData(QWidget):
    """시험 준비 페이지 — 실시간 압력을 보며 측정 시작을 기다린다."""
    started = pyqtSignal()  # 측정 시작 버튼 → 다음 단계로

    def __init__(self, initial_message="실시간 압력 측정"):
        super(LivePressureData, self).__init__()

        # 초기 시리즈와 차트 설정
        self.series = QLineSeries()
        pen = QPen(QColor(COLOR_PRIMARY))
        pen.setWidth(3)
        self.series.setPen(pen)

        self.chart = QChart()
        self.chart.legend().setVisible(False)  # Hide the legend
        self.chart.addSeries(self.series)
        # 차트 테마/제목/애니메이션 (밝은 테마에 맞춤)
        self.chart.setTheme(QChart.ChartTheme.ChartThemeLight)
        self.chart.setBackgroundVisible(False)
        self.chart.setAnimationOptions(QChart.AnimationOption.SeriesAnimations)
        chart_title_font = QFont()
        chart_title_font.setPointSize(13)
        chart_title_font.setBold(True)
        self.chart.setTitleFont(chart_title_font)
        self.chart.setTitleBrush(QColor(COLOR_TEXT))
        self.chart.setTitle("실시간 압력")

        # x, y 축 생성
        self.axis_x = QValueAxis()
        self.axis_y = QValueAxis()

        # 축 범위 설정
        self.axis_x.setRange(0, 100)
        self.axis_y.setRange(0, 100)

        # 축 레이블 설정
        self.axis_x.setTitleText("시간 (s)")
        self.axis_y.setTitleText("압력 (Pa)")
        axis_font = QFont()
        axis_font.setPointSize(10)
        for ax in (self.axis_x, self.axis_y):
            ax.setLabelsFont(axis_font)
            ax.setTitleFont(axis_font)
            ax.setGridLineColor(QColor(COLOR_BORDER))
            ax.setLabelsColor(QColor(COLOR_SUBTLE))

        self.chart.addAxis(self.axis_x, Qt.AlignmentFlag.AlignBottom)
        self.chart.addAxis(self.axis_y, Qt.AlignmentFlag.AlignLeft)

        self.series.attachAxis(self.axis_x)
        self.series.attachAxis(self.axis_y)

        # 상단 바: 안내 메시지(좌) + 현재 압력 + 측정 시작 버튼(우)
        self.message_label = QLabel(initial_message)
        self.message_label.setObjectName("Message")
        # 압력이 0 Pa 근처면 그래프만으로는 값이 들어오는지 알기 어려워 숫자도 함께 보여준다
        self.value_label = QLabel("– Pa")
        self.value_label.setObjectName("Message")
        self.stop_button = QPushButton("측정 시작")
        self.stop_button.setMinimumWidth(200)
        top_bar = QHBoxLayout()
        top_bar.addWidget(self.message_label)
        top_bar.addStretch(1)
        top_bar.addWidget(self.value_label)
        top_bar.addSpacing(24)
        top_bar.addWidget(self.stop_button)

        # 차트 뷰 (안티앨리어싱)
        self.chart_view = QChartView(self.chart)
        self.chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 차트를 카드 프레임 안에 담아 깔끔하게 표시
        chart_card = QFrame()
        chart_card.setObjectName("Card")
        chart_card_layout = QVBoxLayout(chart_card)
        chart_card_layout.setContentsMargins(12, 12, 12, 12)
        chart_card_layout.addWidget(self.chart_view)

        # 페이지 레이아웃
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 24, 40, 32)
        layout.setSpacing(20)
        layout.addLayout(top_bar)
        layout.addWidget(chart_card)

        # 초기 데이터 (x는 시간, y는 압력)
        self.data = [QPointF(i, hardware.pressure_read(test=TEST_MODE)) for i in range(10)]
        self.series.replace(self.data)
        self.rescale_y()

        # 타이머 설정 (100ms 마다 update_chart 호출)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_chart)
        self.timer.start(100)

        # 측정 시작 버튼 → 타이머를 멈추고 다음 단계로
        self.stop_button.clicked.connect(self.timer.stop)
        self.stop_button.clicked.connect(self.started.emit)

    def rescale_y(self):
        """측정값이 항상 보이도록 y축 범위를 데이터에 맞춘다.

        고정 범위(0~100)로 두면 팬 정지 상태의 0 Pa 선이 x축에 붙어
        아무것도 표시되지 않는 것처럼 보인다.
        """
        values = [point.y() for point in self.data]
        low, high = min(values), max(values)
        # 값이 거의 일정해도 선이 축에 붙지 않도록 최소 여백을 확보한다
        margin = max(5.0, (high - low) * 0.2)
        self.axis_y.setRange(low - margin, high + margin)

    def update_chart(self):
        # 새로운 측정값을 데이터에 추가
        try:
            new = hardware.pressure_read(test=TEST_MODE)
        except hardware.SensorTimeout as exc:
            # 센서가 끊겨도 창이 멈추지 않도록 알리기만 하고 이전 값을 유지한다
            self.value_label.setText("센서 응답 없음")
            print(exc)
            return

        self.value_label.setText(f"{new:.1f} Pa")
        self.data.append(QPointF(self.data[-1].x() + 1, new))
        # 데이터가 100개를 초과하면 가장 오래된 데이터를 제거
        if len(self.data) > 100:
            self.data.pop(0)
            self.axis_x.setRange(self.data[0].x(), self.data[-1].x())

        # 시리즈와 축을 업데이트
        self.series.replace(self.data)
        self.rescale_y()
