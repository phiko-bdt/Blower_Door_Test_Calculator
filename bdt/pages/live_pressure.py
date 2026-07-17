"""시험 준비 페이지 — 실시간 압력을 보며 측정 시작을 기다린다."""

from PyQt6.QtWidgets import (
    QWidget,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QFrame,
)
from PyQt6.QtCore import QTimer, QPointF, Qt, QMargins, pyqtSignal
from PyQt6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis
from PyQt6.QtGui import QFont, QColor, QPen, QBrush, QPainter

from bdt import hardware
from bdt.config import TEST_MODE
from bdt.scale import padded_range
from bdt.theme import (
    COLOR_DEP,
    COLOR_INK,
    COLOR_SUB,
    COLOR_CHART_GRID,
    COLOR_CHART_GRID_SOFT,
    COLOR_PLOT,
)


# 영기류(팬 정지) 압력의 허용 한계 (KS L ISO 9972 n항)
ZERO_FLOW_LIMIT_PA = 3.0


class LivePressureData(QWidget):
    """시험 준비 페이지 — 실시간 압력을 보며 측정 시작을 기다린다."""
    started = pyqtSignal()  # 측정 시작 버튼 → 다음 단계로

    def __init__(self, initial_message="실시간 압력 측정"):
        super(LivePressureData, self).__init__()

        # 초기 시리즈와 차트 설정
        self.series = QLineSeries()
        pen = QPen(QColor(COLOR_DEP))
        pen.setWidth(2)  # 얇은 마크 (성적서 그래프의 선 두께와 맞춘다)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        self.series.setPen(pen)

        self.chart = QChart()
        self.chart.legend().setVisible(False)  # 계열이 하나뿐이라 범례는 두지 않는다
        self.chart.addSeries(self.series)
        self.chart.setTheme(QChart.ChartTheme.ChartThemeLight)
        # QChartView 는 QWidget 이라 전역 스타일시트의 배경색(COLOR_BG)을 받는다.
        # 그대로 두면 흰 카드 안에 회색 판이 얹힌 것처럼 보이므로, 차트가 직접
        # 팔레트 검증 기준 표면색(COLOR_PLOT)을 칠하게 한다.
        self.chart.setBackgroundVisible(True)
        self.chart.setBackgroundBrush(QBrush(QColor(COLOR_PLOT)))
        self.chart.setBackgroundPen(QPen(Qt.PenStyle.NoPen))
        self.chart.setBackgroundRoundness(6)
        self.chart.setPlotAreaBackgroundVisible(False)
        self.chart.setMargins(QMargins(8, 4, 16, 4))
        # 애니메이션은 반드시 꺼둔다.
        # 시리즈 애니메이션은 1회 1초인데 update_chart 가 100ms 마다 replace() 를
        # 호출해 매번 애니메이션을 처음부터 다시 시작시킨다. 그 결과 선이 영영
        # 다 그려지지 못하고 사실상 보이지 않았다. 100ms 로 갱신되는 실시간
        # 차트에 등장 애니메이션은 의미도 없다.
        self.chart.setAnimationOptions(QChart.AnimationOption.NoAnimation)
        chart_title_font = QFont()
        chart_title_font.setPointSize(11)
        chart_title_font.setBold(True)
        self.chart.setTitleFont(chart_title_font)
        self.chart.setTitleBrush(QColor(COLOR_INK))
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
        axis_font.setPointSize(9)
        title_font = QFont()
        title_font.setPointSize(9)
        # 격자는 데이터 뒤로 물리되 화면에서 보이는 정도는 유지한다.
        # 글자색은 성적서 그래프와 같은 단계 (축 제목 INK, 틱 라벨 SUB).
        for ax in (self.axis_x, self.axis_y):
            ax.setLabelsFont(axis_font)
            ax.setTitleFont(title_font)
            ax.setGridLineColor(QColor(COLOR_CHART_GRID))
            ax.setMinorGridLineColor(QColor(COLOR_CHART_GRID_SOFT))
            ax.setLinePenColor(QColor(COLOR_CHART_GRID))
            ax.setLabelsColor(QColor(COLOR_SUB))
            ax.setTitleBrush(QColor(COLOR_INK))
            ax.setShadesVisible(False)
        self.axis_x.setTickCount(5)
        self.axis_x.setLabelFormat("%.0f")  # 초 단위에 소수점은 잡음이다
        self.axis_y.setLabelFormat("%.1f")

        self.chart.addAxis(self.axis_x, Qt.AlignmentFlag.AlignBottom)
        self.chart.addAxis(self.axis_y, Qt.AlignmentFlag.AlignLeft)

        self.series.attachAxis(self.axis_x)
        self.series.attachAxis(self.axis_y)

        # 상단 바: 안내 메시지(좌) + 현재 압력 스탯 타일 + 측정 시작 버튼(우)
        self.message_label = QLabel(initial_message)
        self.message_label.setObjectName("Message")
        hint = QLabel(f"팬 정지 상태에서 압력이 ±{ZERO_FLOW_LIMIT_PA:.0f} Pa 이내로 안정되면 시작하세요.")
        hint.setObjectName("Hint")
        head = QVBoxLayout()
        head.setSpacing(4)
        head.addWidget(self.message_label)
        head.addWidget(hint)

        # 압력이 0 Pa 근처면 그래프만으로는 값이 들어오는지 알기 어려워 숫자도
        # 함께 보여준다. 값 하나가 주인공이라 차트가 아니라 스탯 타일로 싣는다.
        self.value_label = QLabel("–")
        self.value_label.setObjectName("StatValue")
        unit = QLabel("Pa")
        unit.setObjectName("StatUnit")
        value_row = QHBoxLayout()
        value_row.setSpacing(4)
        value_row.setContentsMargins(0, 0, 0, 0)
        value_row.addStretch(1)
        value_row.addWidget(self.value_label)
        value_row.addWidget(unit, 0, Qt.AlignmentFlag.AlignBottom)

        self.stat_name = QLabel("현재 압력")
        self.stat_name.setObjectName("StatName")
        self.stat_name.setAlignment(Qt.AlignmentFlag.AlignRight)
        stat = QFrame()
        stat.setObjectName("Card")
        stat.setMinimumWidth(190)
        stat_layout = QVBoxLayout(stat)
        stat_layout.setContentsMargins(18, 10, 18, 12)
        stat_layout.setSpacing(0)
        stat_layout.addWidget(self.stat_name)
        stat_layout.addLayout(value_row)

        self.stop_button = QPushButton("측정 시작")
        self.stop_button.setMinimumWidth(190)
        self.stop_button.setMinimumHeight(62)

        top_bar = QHBoxLayout()
        top_bar.setSpacing(0)
        top_bar.addLayout(head)
        top_bar.addStretch(1)
        top_bar.addWidget(stat)
        top_bar.addSpacing(16)
        top_bar.addWidget(self.stop_button)

        # 차트 뷰 (안티앨리어싱)
        self.chart_view = QChartView(self.chart)
        self.chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 차트를 카드 프레임 안에 담아 깔끔하게 표시
        chart_card = QFrame()
        chart_card.setObjectName("Card")
        chart_card_layout = QVBoxLayout(chart_card)
        chart_card_layout.setContentsMargins(16, 14, 16, 14)
        chart_card_layout.addWidget(self.chart_view)

        # 페이지 레이아웃
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 20, 40, 28)
        layout.setSpacing(18)
        layout.addLayout(top_bar)
        layout.addWidget(chart_card, 1)

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
        아무것도 표시되지 않는 것처럼 보인다. 눈금이 -48.5·-52.0 같은
        어중간한 수로 찍히지 않도록 padded_range 로 예쁜 수에 맞춘다.
        """
        values = [point.y() for point in self.data]
        low, high, ticks = padded_range(min(values), max(values),
                                        pad=0.2, min_span=5.0, ticks=5)
        self.axis_y.setRange(low, high)
        self.axis_y.setTickCount(ticks)

    def _set_stat(self, name, state):
        """스탯 타일의 이름·상태를 바꾼다 (변화 없으면 아무 것도 안 한다)."""
        if self.stat_name.text() == name:
            return
        self.stat_name.setText(name)
        self.stat_name.setProperty("state", state)
        self.stat_name.style().unpolish(self.stat_name)
        self.stat_name.style().polish(self.stat_name)

    def update_chart(self):
        # 새로운 측정값을 데이터에 추가
        try:
            new = hardware.pressure_read(test=TEST_MODE)
        except hardware.SensorTimeout as exc:
            # 센서가 끊겨도 창이 멈추지 않도록 알리기만 하고 이전 값을 유지한다.
            # 큰 숫자 자리에 문장을 넣으면 타일이 깨지므로, 값은 비우고
            # 이름 자리에 상태를 적는다 (색만으로 알리지 않는다).
            self.value_label.setText("–")
            self._set_stat("⚠ 센서 응답 없음", "warn")
            print(exc)
            return

        # 영기류 압력 확인 (KS L ISO 9972 n항: 절대값 3 Pa 초과면 시험을
        # 수행하지 않는다). 이 화면은 팬 정지 상태의 준비 화면이라, 지금
        # 읽히는 압력이 곧 영기류 압력이다. 측정을 막지는 않고 알리기만 한다
        # — 판단은 시험자 몫이다.
        if abs(new) > ZERO_FLOW_LIMIT_PA:
            self._set_stat(f"⚠ 영기류 압력 ±{ZERO_FLOW_LIMIT_PA:.0f} Pa 초과", "warn")
        else:
            self._set_stat("현재 압력", "")
        self.value_label.setText(f"{new:.1f}")
        self.data.append(QPointF(self.data[-1].x() + 1, new))
        # 데이터가 100개를 초과하면 가장 오래된 데이터를 제거
        if len(self.data) > 100:
            self.data.pop(0)
            self.axis_x.setRange(self.data[0].x(), self.data[-1].x())

        # 시리즈와 축을 업데이트
        self.series.replace(self.data)
        self.rescale_y()
