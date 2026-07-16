#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import os
import json
import time
import shutil
import atexit
import traceback
from datetime import datetime
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QGridLayout,
    QCheckBox,
    QMainWindow,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QComboBox,
    QFrame,
    QHeaderView,
)
from PyQt6.QtCore import (
    QTimer,
    QPointF,
    Qt,
    QThread,
    pyqtSignal,
    QCoreApplication,
)
from PyQt6.QtCharts import (
    QChart,
    QChartView,
    QLegend,
    QLineSeries,
    QLogValueAxis,
    QScatterSeries,
    QValueAxis,
)
from PyQt6.QtGui import QFont, QFontDatabase, QPixmap, QColor, QPen, QPainter
import ACH_calculator
import graph_plotter
import reporting
import pwm_pid_control
import sensor_and_controller
import platform
current_os = platform.system()
if current_os == "Windows":
    test_mode = True
else:
    test_mode = False

# ──────────────────────────────────────────────────────────────
# 공통 디자인 테마 (모던 플랫 · 밝은 테마 · 1280×800 터치스크린)
# ──────────────────────────────────────────────────────────────
COLOR_BG = "#F5F7FA"            # 전체 배경
COLOR_SURFACE = "#FFFFFF"       # 입력칸/카드 표면
COLOR_PRIMARY = "#2D7FF9"       # 포인트(파랑)
COLOR_PRIMARY_DARK = "#1C6FE8"  # hover
COLOR_PRIMARY_PRESSED = "#1560CC"
COLOR_TEXT = "#2B2F36"          # 본문 글자
COLOR_SUBTLE = "#6B7280"        # 보조 글자
COLOR_BORDER = "#D8DEE9"        # 테두리

# 화면 기본 크기 (1280×800 화면에 여백을 두고 배치)
WIN_W = 1180
WIN_H = 720

APP_STYLE = f"""
QWidget, QMainWindow {{
    background-color: {COLOR_BG};
    color: {COLOR_TEXT};
    font-family: 'NanumSquare', 'Noto Sans CJK KR', sans-serif;
}}
QLabel {{
    font-size: 16px;
    background: transparent;
}}
QLabel#Title {{
    font-size: 22px;
    font-weight: bold;
    color: #FFFFFF;
    padding: 16px 24px;
    background-color: {COLOR_PRIMARY};
    border-radius: 12px;
}}
QLabel#Hint {{
    font-size: 13px;
    color: {COLOR_SUBTLE};
}}
QLabel#Message {{
    font-size: 26px;
    font-weight: bold;
    color: {COLOR_TEXT};
}}
QLineEdit, QComboBox {{
    font-size: 16px;
    min-height: 30px;
    padding: 8px 12px;
    background-color: {COLOR_SURFACE};
    border: 1px solid {COLOR_BORDER};
    border-radius: 10px;
}}
QLineEdit:focus, QComboBox:focus {{
    border: 2px solid {COLOR_PRIMARY};
}}
QComboBox::drop-down {{ border: none; width: 36px; }}
QComboBox QAbstractItemView {{
    font-size: 16px;
    background-color: {COLOR_SURFACE};
    selection-background-color: {COLOR_PRIMARY};
    selection-color: #FFFFFF;
    outline: none;
}}
QPushButton {{
    font-size: 17px;
    font-weight: bold;
    min-height: 48px;
    padding: 10px 28px;
    color: #FFFFFF;
    background-color: {COLOR_PRIMARY};
    border: none;
    border-radius: 12px;
}}
QPushButton:hover {{ background-color: {COLOR_PRIMARY_DARK}; }}
QPushButton:pressed {{ background-color: {COLOR_PRIMARY_PRESSED}; }}
QCheckBox {{
    font-size: 16px;
    spacing: 10px;
    padding: 6px;
    background: transparent;
}}
QCheckBox::indicator {{
    width: 26px;
    height: 26px;
    border: 2px solid {COLOR_BORDER};
    border-radius: 6px;
    background: {COLOR_SURFACE};
}}
QCheckBox::indicator:checked {{
    border: 2px solid {COLOR_PRIMARY};
    background-color: {COLOR_PRIMARY};
}}
QFrame#Card {{
    background-color: {COLOR_SURFACE};
    border: 1px solid {COLOR_BORDER};
    border-radius: 16px;
}}
QTableWidget {{
    font-size: 15px;
    background-color: {COLOR_SURFACE};
    border: 1px solid {COLOR_BORDER};
    border-radius: 10px;
    gridline-color: {COLOR_BORDER};
}}
QHeaderView::section {{
    font-size: 15px;
    font-weight: bold;
    color: #FFFFFF;
    background-color: {COLOR_PRIMARY};
    padding: 10px;
    border: none;
}}
QTableWidget::item {{ padding: 8px; }}
QTableCornerButton::section {{ background-color: {COLOR_PRIMARY}; border: none; }}
QMessageBox {{ background-color: {COLOR_SURFACE}; }}
QMessageBox QLabel {{ font-size: 16px; }}
"""


def center_on_screen(window):
    """창을 현재 화면 중앙에 배치한다 (터치스크린 키오스크 용)."""
    screen = QApplication.primaryScreen()
    if screen is None:
        return
    geo = window.frameGeometry()
    geo.moveCenter(screen.availableGeometry().center())
    window.move(geo.topLeft())


class CenteredWindow:
    """표시될 때 자동으로 화면 중앙에 배치되도록 하는 믹스인."""
    def showEvent(self, event):
        super().showEvent(event)
        center_on_screen(self)


class InputInitialValues(CenteredWindow, QWidget):
    def __init__(self):
        super().__init__()

        # 루트 레이아웃 (세로): 헤더 → 안내 → 폼 → 옵션 → 체크박스 → 저장 버튼
        root = QVBoxLayout()
        root.setContentsMargins(40, 32, 40, 32)
        root.setSpacing(18)
        self.setLayout(root)

        # 상단 제목 바
        title = QLabel("기밀성능 시험 · 시험 조건 입력")
        title.setObjectName("Title")
        root.addWidget(title)

        # 안내 문구
        hint = QLabel("‘실내 체적’은 필수 입력이며, 감압 / 가압 중 하나 이상을 선택해야 합니다.")
        hint.setObjectName("Hint")
        root.addWidget(hint)

        # 입력 필드와 레이블 생성
        # (표시되는 레이블, 저장되는 key, placeholder)
        labels = [
            ("시험 목적", "purpose", "기밀 시험"),
            ("위치", "location", "서울시 송파구 풍납동 497"),
            ("테스트 방식", "method", "method A / method B"),
            ("의뢰자", "requester", "홍길동, 010-0000-0000"),
            ("설계사", "designer", "OO건축사사무소"),
            ("시험자", "tester", "김철수 (주)기밀시험"),
            ("시공사(시공자)", "builder", "OO건축"),
            ("실내 체적 (㎥)", "interior volume", "(필수) 424.21 와 같이 숫자만 작성 가능합니다."),
            ("연면적 (㎡)", "floor area", "92.4"),
            ("구조", "structure", "경량목구조")
        ]
        self.input_fields = {}

        # 입력 폼을 카드 안에 2열(라벨·입력 | 라벨·입력)로 배치해 와이드 화면을 활용
        card = QFrame()
        card.setObjectName("Card")
        form = QGridLayout(card)
        form.setContentsMargins(28, 24, 28, 24)
        form.setHorizontalSpacing(24)
        form.setVerticalSpacing(16)
        form.setColumnStretch(1, 1)
        form.setColumnStretch(3, 1)

        for idx, (label_text, label_key, placeholder) in enumerate(labels):
            r, c = divmod(idx, 2)
            label = QLabel(label_text)
            input_field = QLineEdit()
            input_field.setPlaceholderText(placeholder)
            form.addWidget(label, r, c * 2)
            form.addWidget(input_field, r, c * 2 + 1)
            self.input_fields[label_key] = input_field
        base_row = (len(labels) + 1) // 2

        # Fan Cover / Fan Count 를 같은 행에 나란히 배치
        self.cover_combo = QComboBox()
        self.cover_combo.addItems(["none", "low", "high"])
        self.count_combo = QComboBox()
        self.count_combo.addItems(["1", "2"])
        form.addWidget(QLabel("Fan Cover"), base_row, 0)
        form.addWidget(self.cover_combo, base_row, 1)
        form.addWidget(QLabel("Fan Count"), base_row, 2)
        form.addWidget(self.count_combo, base_row, 3)
        root.addWidget(card)

        # 체크박스 (감압 / 가압) — 가로 배치
        self.checkbox_states = {}
        check_row = QHBoxLayout()
        check_row.setSpacing(32)
        checkbox1 = QCheckBox("감압 실험")
        checkbox1.setObjectName("depressurization")
        checkbox1.stateChanged.connect(self.save_checkbox_state)
        checkbox2 = QCheckBox("가압 실험")
        checkbox2.setObjectName("pressurization")
        checkbox2.stateChanged.connect(self.save_checkbox_state)
        check_row.addWidget(checkbox1)
        check_row.addWidget(checkbox2)
        check_row.addStretch(1)
        root.addLayout(check_row)

        root.addStretch(1)

        # 저장 버튼 (하단, 크게 — 터치용)
        save_button = QPushButton("저장하고 시작")
        save_button.setMinimumHeight(56)
        save_button.setMinimumWidth(260)
        save_button.clicked.connect(self.save_data)
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(save_button)
        btn_row.addStretch(1)
        root.addLayout(btn_row)

    def save_checkbox_state(self):
        sender = self.sender()
        checkbox_text = sender.objectName()
        checkbox_state = sender.isChecked()

        self.checkbox_states[checkbox_text] = checkbox_state

    def save_data(self):
        # 필수 값인 'interior volume' 값이 비어있는지 확인
        interior_volume = self.input_fields["interior volume"].text()
        if not interior_volume.strip():
            # 경고 메시지 표시
            QMessageBox.warning(self, "입력 오류", "'실내 체적 (㎥)'는 필수 입력 사항입니다.")
            return
        
        # 감압 또는 가압 중 적어도 하나가 선택되었는지 확인
        is_checked = self.checkbox_states.get("depressurization", False) or self.checkbox_states.get("pressurization", False)
        if not is_checked:
            QMessageBox.warning(self, "선택 오류", "'감압 실험' 또는 '가압 실험' 중 하나는 선택해야 합니다.")
            return

        data = {}
        # 입력값을 JSON 파일로 저장
        for key, input_field in self.input_fields.items():
            value = input_field.text()
            data[key] = value
        # Fan options
        data["fan_cover"] = self.cover_combo.currentText()
        data["fan_count"] = int(self.count_combo.currentText())
        # 체크박스 데이터 저장
        for key, checkbox in self.checkbox_states.items():
            data[key] = checkbox
        # json으로 저장 (다음 프로세스용)
        with open("conditions.json", "w") as file:
            json.dump(data, file, indent=4)
        # json으로 저장 (백업용)
        now = datetime.now().strftime("%y%m%d-%H%M%S")
        os.makedirs("conditions", exist_ok=True)
        with open(f"./conditions/conditions_{now}.json", "w") as file:
            json.dump(data, file, indent=4)
        # 종료
        self.close()


class LivePressureData(CenteredWindow, QMainWindow):
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

        # 메인 위젯 설정
        main_widget = QWidget()
        layout = QVBoxLayout(main_widget)
        layout.setContentsMargins(40, 32, 40, 32)
        layout.setSpacing(20)
        layout.addLayout(top_bar)
        layout.addWidget(chart_card)
        self.setCentralWidget(main_widget)

        # 초기 데이터 (x는 시간, y는 압력)
        self.data = [QPointF(i, sensor_and_controller.pressure_read(test=test_mode)) for i in range(10)]
        self.series.replace(self.data)
        self.rescale_y()

        # 타이머 설정 (1초마다 update_chart 호출)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_chart)
        self.timer.start(100)

        # 측정 종료 버튼 클릭 이벤트 연결
        self.stop_button.clicked.connect(self.timer.stop)
        self.stop_button.clicked.connect(self.close)

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
            new = sensor_and_controller.pressure_read(test=test_mode)
        except sensor_and_controller.SensorTimeout as exc:
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


class SimpleMessageAutoDisappear(CenteredWindow, QMainWindow):
    def __init__(self, initial_message="warning", time_to_close=10):
        super(SimpleMessageAutoDisappear, self).__init__()
        # 창의 제목을 초기 메시지로 설정
        self.setWindowTitle(initial_message)
        self.time_to_close = time_to_close

        # 메시지 + 카운트다운을 중앙 카드에 배치
        self.label = QLabel(initial_message)
        self.label.setObjectName("Message")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.count_label = QLabel("")
        self.count_label.setObjectName("Hint")
        self.count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QFrame()
        card.setObjectName("Card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(56, 44, 56, 44)
        card_layout.setSpacing(16)
        card_layout.addWidget(self.label)
        card_layout.addWidget(self.count_label)

        center = QWidget()
        outer = QVBoxLayout(center)
        outer.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(card)
        row.addStretch(1)
        outer.addLayout(row)
        outer.addStretch(1)
        self.setCentralWidget(center)

        # 메시지 업데이트 메서드 호출
        self.update_message()

    def update_message(self):
        if self.time_to_close >= 0:
            self.count_label.setText(f"{self.time_to_close}초 후에 창이 닫힙니다.")
            self.time_to_close -= 1
            # 1초 후에 다시 메시지 업데이트
            QTimer.singleShot(1000, self.update_message)
        else:
            self.close()


class SimpleMessage(CenteredWindow, QMainWindow):
    def __init__(self, initial_message="warning"):
        super(SimpleMessage, self).__init__()
        # 창의 제목 설정
        self.setWindowTitle(initial_message)

        # 메시지 + 진행 안내를 중앙 카드에 배치
        self.label = QLabel(initial_message)
        self.label.setObjectName("Message")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # 작업 진행 상황을 실시간으로 보여준다 (set_progress 로 갱신)
        self.progress = QLabel("잠시만 기다려 주세요…")
        self.progress.setObjectName("Hint")
        self.progress.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress.setWordWrap(True)
        self.progress.setMinimumWidth(560)

        card = QFrame()
        card.setObjectName("Card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(56, 44, 56, 44)
        card_layout.setSpacing(14)
        card_layout.addWidget(self.label)
        card_layout.addWidget(self.progress)

        center = QWidget()
        outer = QVBoxLayout(center)
        outer.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(card)
        row.addStretch(1)
        outer.addLayout(row)
        outer.addStretch(1)
        self.setCentralWidget(center)

    def set_progress(self, text):
        """작업 스레드가 보내온 진행 상황을 표시한다."""
        self.progress.setText(text)


class LiveMeasurementChart(CenteredWindow, QMainWindow):
    """측정 진행 상황 + 압력-풍량 산점도를 실시간으로 보여주는 창.

    x축은 풍량(㎥/h), y축은 압력차 절대값(Pa)이다.
    감압/가압을 서로 다른 마커로 그리며, 창이 새로 열려도 앞 시험의 점을
    계속 보여주기 위해 측정값을 클래스 변수에 누적한다.
    """

    # {시험 종류: [(압력차, 풍량), ...]} — 감압→가압으로 창이 바뀌어도 유지된다.
    # 보고서 그래프(graph_plotter)와 같은 축 배치라 (x, y) 순서 그대로 담는다.
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
    # 풍량은 팬 개수에 비례하므로 팬 1개 기준 값에 팬 개수를 곱해 축을 잡는다.
    # (팬 1개 → 500~2000, 팬 2개 → 1000~4000 ㎥/h)
    FLOW_MIN_PER_FAN, FLOW_MAX_PER_FAN = 500.0, 2000.0
    PRESSURE_MIN, PRESSURE_MAX = 1.0, 150.0  # 압력차 (Pa)

    @classmethod
    def reset(cls):
        """새 시험을 시작할 때 누적된 점을 비운다."""
        for points in cls.accumulated.values():
            points.clear()

    def __init__(self, initial_message="측정 중...", num_fans=1):
        super(LiveMeasurementChart, self).__init__()
        self.setWindowTitle(initial_message)

        # 팬 개수에 맞춰 풍량 축 범위를 정한다
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
        self.chart.setTitle("압력 – 풍량 관계 (log–log)")
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
        self.axis_y.setTitleText("풍량 Q (㎥/h)")
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

        center = QWidget()
        outer = QVBoxLayout(center)
        outer.setContentsMargins(40, 32, 40, 32)
        outer.setSpacing(18)
        outer.addLayout(top_bar)
        outer.addWidget(chart_card)
        self.setCentralWidget(center)

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


class ResultImageWindow(CenteredWindow, QWidget):
    def __init__(self, image_path, size_w, size_h):
        super().__init__()
        self.setWindowTitle('시험 결과 그래프')

        # 상단 제목 바
        title = QLabel("시험 결과 그래프")
        title.setObjectName("Title")

        # 이미지 라벨 (가로세로 비율 유지, 부드럽게 스케일)
        self.label = QLabel()
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = QPixmap(image_path)
        if not pixmap.isNull():
            pixmap = pixmap.scaled(size_w, size_h,
                                   Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
            self.label.setPixmap(pixmap)
        else:
            self.label.setText("그래프 이미지를 불러올 수 없습니다.")

        # 이미지를 카드 안에 배치
        card = QFrame()
        card.setObjectName("Card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.addWidget(self.label)

        root = QVBoxLayout(self)
        root.setContentsMargins(40, 32, 40, 32)
        root.setSpacing(20)
        root.addWidget(title)
        root.addWidget(card)


class ResultTableWindow(CenteredWindow, QWidget):
    def __init__(self, test_data):
        super().__init__()
        self.setWindowTitle('Blower Door Test Report')

        # 상단 제목 바
        title = QLabel("Blower Door Test 결과")
        title.setObjectName("Title")

        # 테이블 위젯 설정
        self.tableWidget = QTableWidget()
        self.tableWidget.setRowCount(14)  # 필요한 행의 수
        self.tableWidget.setColumnCount(6)  # 필요한 열의 수
        self.tableWidget.setHorizontalHeaderLabels(['', '감압', '오차', '가압', '오차', '단위'])
        # 터치 환경에 맞춰 행을 키우고, 열은 폭에 맞게 균등 분배
        self.tableWidget.verticalHeader().setVisible(False)
        self.tableWidget.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tableWidget.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.tableWidget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tableWidget.verticalHeader().setDefaultSectionSize(42)

        # 테이블 데이터 채우기
        self.populate_table(test_data)

        # 레이아웃 설정
        layout = QVBoxLayout()
        layout.setContentsMargins(40, 32, 40, 32)
        layout.setSpacing(20)
        layout.addWidget(title)
        layout.addWidget(self.tableWidget)
        self.setLayout(layout)

    def populate_table(self, data):
        # 시험 정보 섹션
        # 화면 표시 라벨 -> conditions.json / report 의 실제 키 매핑
        test_info_labels = ['시험 기간', '위치', '의뢰자', '시험자', '실내 체적', '연면적', '시험 목적', '테스트 방법', '설계사', '시공사', '구조']
        test_info_keys = {
            '시험 기간': 'test_period',
            '위치': 'location',
            '의뢰자': 'requester',
            '시험자': 'tester',
            '실내 체적': 'interior volume',
            '연면적': 'floor area',
            '시험 목적': 'purpose',
            '테스트 방법': 'method',
            '설계사': 'designer',
            '시공사': 'builder',
            '구조': 'structure',
        }
        for i, label in enumerate(test_info_labels):
            self.tableWidget.setItem(i, 0, QTableWidgetItem(label))
            self.tableWidget.setItem(i, 1, QTableWidgetItem(str(data.get(test_info_keys[label], '-'))))

        # 시험 결과 섹션
        # 결과 키는 감압='<key>-', 가압='<key>+', 오차='<key>+-(-/+)' 형식으로 저장된다
        test_result_labels = ['시험 기준', 'Q50', 'ACH50', 'AL50', '누기 계수, C', '기류 지수, n', '결정 계수, r^2']
        test_result_keys = {
            'Q50': 'Q50',
            'ACH50': 'ACH50',
            'AL50': 'AL50',
            '누기 계수, C': 'C0',
            '기류 지수, n': 'n',
            '결정 계수, r^2': 'r^2',
        }
        for i, label in enumerate(test_result_labels, start=7):
            self.tableWidget.setItem(i, 0, QTableWidgetItem(label))
            if label == '시험 기준':
                self.tableWidget.setItem(i, 1, QTableWidgetItem('KS-L-ISO-9972'))
            else:
                base = test_result_keys[label]
                # 감압(열1)/가압(열3) 값, 오차는 '<base>+--'(감압) / '<base>+-+'(가압)
                self.tableWidget.setItem(i, 1, QTableWidgetItem(str(data.get(base + '-', '-'))))
                self.tableWidget.setItem(i, 2, QTableWidgetItem(str(data.get(base + '+--', '-'))))
                self.tableWidget.setItem(i, 3, QTableWidgetItem(str(data.get(base + '+', '-'))))
                self.tableWidget.setItem(i, 4, QTableWidgetItem(str(data.get(base + '+-+', '-'))))

        # 단위 설정 (결과 행 8~13: Q50, ACH50, AL50, C, n, r^2 에 맞춰 정렬)
        self.tableWidget.setItem(8, 5, QTableWidgetItem('㎥/h'))           # Q50
        self.tableWidget.setItem(9, 5, QTableWidgetItem('1/h'))            # ACH50
        self.tableWidget.setItem(10, 5, QTableWidgetItem('㎡'))            # AL50
        self.tableWidget.setItem(11, 5, QTableWidgetItem('㎥/(h·Pa^n)'))   # 누기 계수 C
        self.tableWidget.setItem(12, 5, QTableWidgetItem('-'))             # 기류 지수 n
        self.tableWidget.setItem(13, 5, QTableWidgetItem('-'))             # 결정 계수 r^2


class BackgroundTask(QThread):
    finished = pyqtSignal()  # 작업 완료 시그널
    error = pyqtSignal(str)  # 작업 오류 시그널
    progress = pyqtSignal(str)  # 진행 상황 시그널 (측정 중 창에 표시)
    point = pyqtSignal(float, float, str)  # (풍량, 압력차, 시험종류) 확정 측정점 → 마커
    position = pyqtSignal(float, float)  # (풍량, 압력차) 현재 위치 → 십자 포인터

    def __init__(self, task_type):
        super().__init__()
        self.task_type = task_type
        self.result = 0 # Initialize the result attribute
        # duty→풍량 변환에 쓰는 팬 계수 (blower_door_test 에서 설정)
        self.fan_coeff = None
        self.num_fans = 1

    def report(self, message):
        """진행 상황을 터미널과 GUI 양쪽에 알린다."""
        print(message)
        self.progress.emit(message)

    def duty_flow(self, duty):
        """duty 를 풍량(㎥/h)으로 바꾼다. 팬 계수가 없으면 None."""
        if not self.fan_coeff:
            return None
        return ACH_calculator.duty_to_flow(duty, self.fan_coeff, self.num_fans,
                                           self.task_type)

    def report_point(self, duty, pressure):
        """확정된 측정점을 마커로 찍는다."""
        flow = self.duty_flow(duty)
        if flow is not None:
            self.point.emit(flow, abs(pressure), self.task_type)

    def report_position(self, duty, pressure):
        """제어 중 현재 위치를 십자 포인터로만 표시한다 (마커는 찍지 않음)."""
        flow = self.duty_flow(duty)
        if flow is not None:
            self.position.emit(flow, abs(pressure))

    def run(self):
        try:
            if self.task_type == "depressurization":
                self.blower_door_test(self.task_type)
            elif self.task_type == "pressurization":
                self.blower_door_test(self.task_type)
            elif self.task_type == "calculation":
                self.calculation()
            elif self.task_type == "graph_plotting":
                self.graph_plotting()
            elif self.task_type == "reporting":
                self.reporting()
        except Exception as exc:
            # 측정/계산 중 예외가 나도 GUI가 멈추지 않도록 로그를 남기고 시그널로 알림
            traceback.print_exc()
            # 측정 작업 중 오류면 팬을 반드시 정지시켜 안전 상태로 둔다
            if self.task_type in ("depressurization", "pressurization"):
                try:
                    sensor_and_controller.duty_set(0, test=test_mode)
                except Exception:
                    traceback.print_exc()
            self.error.emit(str(exc))
        finally:
            # 성공/실패와 무관하게 항상 완료 시그널을 보내 대기 창이 닫히도록 한다
            self.finished.emit()  # 작업 완료 시그널 발생

    @staticmethod
    def measuring_pressure(total_duration, local_duration):
        # 압력 측정
        pressure = []
        # 측정 시간
        pressure_size = total_duration
        while pressure_size:
            measuring_duration = local_duration
            pressure.append(sensor_and_controller.
                            pressure_read(average_time=
                                          measuring_duration,
                                          test=test_mode))
            pressure_size -= measuring_duration
        # 측정 평균값 저장
        return sum(pressure)/len(pressure)

    def blower_door_test(self, test):

        # 측정 모드에 따른 변수 설정
        # 9GV2048P0G201 fan only (formerly OF-OD172SAP-Reversible)
        zero_duty = 0

        with open('conditions.json', 'r') as f:
            conditions = json.load(f)
        cover = conditions.get("fan_cover", "none").lower()
        fan_coeffs = ACH_calculator.load_fan_coefficients()
        coeff = fan_coeffs.get(cover, fan_coeffs.get("none", {}))
        # 실시간 그래프에서 duty 를 풍량으로 바꾸는 데 사용한다
        self.fan_coeff = coeff
        self.num_fans = int(conditions.get("fan_count", 1))

        duty_range = coeff.get("duty_range", [20, 100])
        min_duty, max_duty = duty_range
        initial_duty = min_duty - 1

        # 측정
        measuring = {}
        measuring["measured_value"] = []
        # 온습도, 대기압
        measuring["temperature"] = 20
        measuring["relative_humidity"] = 50
        measuring["atmospheric_pressure"] = 101325
        # 테스트 기록
        measuring["test"] = test
        # 시험 시작 시간
        time_start = datetime.now().strftime("%H:%M:%S")

        # 시작 0 기류 압력 측정 # 현재 버전에서는 생략
        # measuring["initial_zero_pressure"] = self.measuring_pressure(10, 1)

        # 시험 시작
        success = False
        self.report("팬 속도를 조절해 목표 압력(70 Pa)을 맞추는 중…")
        # 70Pa PWM duty 값 추출
        (duty, success, pressure) = pwm_pid_control.get_duty(target=70,
                                                             delay=5,
                                                             average_time=0.5,
                                                             control_limit=10,
                                                             duty_min=min_duty,
                                                             duty_max=max_duty,
                                                             test=test_mode,
                                                             progress=self.report,
                                                             on_point=self.report_position)
        if success:
            self.report(f"목표 압력 도달 — 팬 세기 {duty}%, 압력 {pressure:.1f} Pa")
        else:
            self.report(f"70 Pa 도달 실패 — 최대 팬 세기({max_duty}%)로 측정을 진행합니다")

        # 70Pa PWM duty 값 추출 실패 시 = 누기량/침기량 대비 압력형성을 위한 풍량 부족
        # max duty부터 min duty 전 까지 10번 수행
        if not success:
            duty = max_duty
            success = True

        # duty 최대값 설정 완료 후 측정 수행
        if success:
            # 60Pa 측정 값 저장
            measuring["measured_value"].append([pressure, duty])
            self.report_point(duty, pressure)
            # 측정 범위 설정
            num_to_measure = 10
            step = (duty - initial_duty) / (num_to_measure - 1)  # 간격 계산
            duty_range = [round(duty - i * step) for i in range(num_to_measure)]
            # 데이터 측정
            before = duty
            total = len(duty_range)
            for i, d in enumerate(duty_range, start=1):
                sensor_and_controller.duty_set(d, test=test_mode)
                settle = abs(before - d)
                self.report(f"[{i}/{total}] 팬 세기 {d}% — 압력 안정화 대기 중… ({settle}초)")
                time.sleep(settle)
                self.report(f"[{i}/{total}] 팬 세기 {d}% — 압력 측정 중… (10초)")
                p = self.measuring_pressure(10, 1)
                self.report(f"[{i}/{total}] 팬 세기 {d}% — 측정 완료: {p:.1f} Pa")
                measuring["measured_value"].append([p, d])
                self.report_point(d, p)
                before = d

        # 종료 0 기류 압력 측정 # 현재 버전에서는 생략
        # measuring["final_zero_pressure"] = self.measuring_pressure(10, 1)
        # 시험 종료 — 팬 정지 후 실제로 멈췄는지 확인한다
        self.report("측정 완료 — 팬을 정지하는 중…")
        if sensor_and_controller.duty_set(zero_duty, test=test_mode) != 0:
            self.report("⚠ 팬 정지 실패 — PWM 핀 손상이 의심됩니다. 전원을 수동으로 차단하세요.")
        # 시험 종료 시간 기록
        time_end = datetime.now().strftime("%H:%M:%S")
        measuring["test time"] = [time_start, time_end]

        # Raw data 백업 저장
        now = datetime.now().strftime("%y%m%d-%H%M%S")
        os.makedirs("measurements", exist_ok=True)
        with open(f"./measurements/{test}_{now}.json", 'w') as file:
            json.dump(measuring, file, indent=4)
        # 데이터 저장
        with open(f"./{test}_raw.json", 'w') as file:
            json.dump(measuring, file, indent=4)

    def calculation(self):
        # 시험 조건 불러오기
        conditions = 'conditions.json'
        with open(conditions, 'r') as file:
            data = json.load(file)
        
        # 아무 시험 결과 없는 경우, Just in case.
        if not data.get("depressurization") and not data.get("pressurization"):
            pass

        # 결과 저장 변수 선언
        calculation_raw = {}
        # 보고서 용 값 저장
        calculation_raw["report"] = {}

        # 저장 할 값 지정
        need_to_save = ["C0", 
                        "n", 
                        "C0 range", 
                        "n range", 
                        "t", 
                        "variance of n", 
                        "variance of x", 
                        "mean x",
                        "N", 
                        "measured values", 
                        "margin of error of y",
                        "Q50",
                        "ACH50",
                        "AL50",
                        "r^2",
                        "Q50+-",
                        "ACH50+-",
                        "n+-",
                        "C0+-",
                        "interior_volume"]
        
        need_to_report = ["Q50", 
                          "ACH50", 
                          "AL50", 
                          "C0", 
                          "n", 
                          "Q50+-", 
                          "C0+-", 
                          "n+-", 
                          "r^2",
                          "interior_volume"]
            
        # 감압 시험을 수행 한 경우
        if data.get("depressurization"):
            # 파일 불러오기
            depressureization = ACH_calculator.BlowerDoorTestCalculator.from_file('depressurization_raw.json',
                                                                                'conditions.json')
            # 결과 계산
            results_depr = depressureization.calculate_results()
            # Raw data 저장
            now = datetime.now().strftime("%y%m%d-%H%M%S")
            os.makedirs("calculations", exist_ok=True)
            with open(f"./calculations/depressurization_{now}.json", 'w') as file:
                json.dump(results_depr, file, indent=4)
            # 결과 값 변수 저장
            calculation_raw['depressurization'] = {}
            for i in results_depr.keys():
                if i in need_to_save:
                    calculation_raw['depressurization'][i]=results_depr[i]
            
            for i in need_to_report:
                report_key = i + "-"
                calculation_raw["report"][report_key] = calculation_raw["depressurization"][i]

        # 가압 시험을 수행 한 경우
        if data.get("pressurization"):
            # 파일 불러오기
            pressureization = ACH_calculator.BlowerDoorTestCalculator.from_file('pressurization_raw.json',
                                                                                'conditions.json')
            # 결과 계산
            results_pres = pressureization.calculate_results()
            # Raw data 저장
            now = datetime.now().strftime("%y%m%d-%H%M%S")
            os.makedirs("calculations", exist_ok=True)
            with open(f"./calculations/pressurization_{now}.json", 'w') as file:
                json.dump(results_pres, file, indent=4)
            # 결과 값 변수 저장
            calculation_raw['pressurization'] = {}
            for i in results_pres.keys():
                if i in need_to_save:
                    calculation_raw['pressurization'][i]=results_pres[i]
            
            for i in need_to_report:
                report_key = i + "+"
                calculation_raw["report"][report_key] = calculation_raw["pressurization"][i]

        # 감/가압 시험 모두 수행 한 경우, 평균 값 계산
        if data.get("depressurization") and data.get("pressurization"):
            calculation_raw["average"] = {}
            for i in ["Q50", "ACH50", "AL50"]:
                calculation_raw["report"][i + "_avg"] = (calculation_raw["depressurization"][i] \
                                                        + calculation_raw["pressurization"][i])/2

        with open(f"./calculation_raw.json", 'w') as file:
            json.dump(calculation_raw, file, indent=4)

        self.report("시험 결과 계산 완료")

    def graph_plotting(self):
        # 시험 조건 불러오기
        conditions = 'conditions.json'
        with open(conditions, 'r') as file:
            conditions = json.load(file)

        # 계산 결과 불러오기
        with open(f"./calculation_raw.json", 'r') as file:
            calculation_raw = json.load(file)

        self.report("압력-유량 그래프를 그리는 중…")

        if conditions.get("depressurization") and conditions.get("pressurization"):
            graph_plotter.plot_graph(calculation_raw['depressurization'],
                                     calculation_raw['pressurization'],
                                     calculation_raw['report'])
        elif conditions.get("depressurization"):
            graph_plotter.plot_graph(calculation_raw['depressurization'],
                                     False,
                                     calculation_raw['report'])
        elif conditions.get("pressurization"):
            graph_plotter.plot_graph(False,
                                     calculation_raw['pressurization'],
                                     calculation_raw['report'])

    def reporting(self):
        import report_html

        with open('conditions.json', 'r') as f:
            conditions = json.load(f)
        with open('calculation_raw.json', 'r') as f:
            report_data = json.load(f).get("report", {})

        self.report("성적서를 만드는 중…")
        pdf_path = os.path.abspath("report.pdf")
        result = report_html.make_report_pdf(
            conditions, report_data, pdf_path,
            graph_path="graph.png", font_path="NanumSquare_acL.ttf")

        if not result:
            self.report("성적서 PDF 생성 실패 (chromium 확인 필요)")
            return
        self.report("성적서 생성 완료: report.pdf")
        if platform.system() == "Linux":
            self.open_pdf(pdf_path)

    def open_pdf(self, pdf_path):
        """생성된 PDF를 뷰어로 연다. 뷰어가 없어도 조용히 넘어간다."""
        import subprocess as sub
        viewer = (shutil.which("evince") or shutil.which("xpdf")
                  or shutil.which("qpdfview") or shutil.which("xdg-open"))
        if not viewer:
            self.report("PDF 뷰어가 없어 파일만 저장했습니다: report.pdf")
            return
        self.report("성적서를 화면에 표시합니다: report.pdf")
        # start_new_session=True 로 새 세션에 분리해야 시험 종료 후 프로그램이
        # 닫힐 때(터미널 SIGHUP) 뷰어까지 같이 꺼지지 않는다.
        sub.Popen([viewer, pdf_path],
                  stdout=sub.DEVNULL, stderr=sub.DEVNULL,
                  start_new_session=True)


def stop_fan_on_exit():
    """프로그램이 어떤 경로로 끝나든 팬을 정지시킨다.

    hardware_PWM 설정은 프로세스가 끝나도 하드웨어에 그대로 남으므로,
    종료 시 duty 0 을 명시하지 않으면 팬이 계속 돈다.
    """
    try:
        sensor_and_controller.duty_set(0, test=test_mode)
    except Exception:
        traceback.print_exc()


if __name__ == '__main__':
    # Ensure the fan PWM duty is zero on startup so that the fan does not run
    # even if powered. This provides a safe default state before any test begins.
    # duty_set 이 핀 레벨을 되읽어 검증하므로, 실패하면 팬이 계속 도는 상태다.
    fan_stop_failed = sensor_and_controller.duty_set(0, test=test_mode) != 0
    # 정상 종료·예외·창 닫기 등 모든 종료 경로에서 팬을 정지시킨다
    atexit.register(stop_fan_on_exit)

    app = QApplication(sys.argv)
    # 전역 디자인 테마 적용 (모든 창에 일관 적용)
    app.setStyleSheet(APP_STYLE)

    # 창 사이즈 설정 (1280×800 터치스크린 기준)
    size_w = WIN_W
    size_h = WIN_H
    # 폰트 설정
    font_id = QFontDatabase.addApplicationFont("./NanumSquare_acL.ttf")

    if font_id != -1:
        font_families = QFontDatabase.applicationFontFamilies(font_id)
        # 로드한 글꼴의 첫 번째 패밀리를 사용
        app.setFont(QFont(font_families[0], 11))
    else:
        print("Failed to load font.")

    # 메세지 종료 시간
    time_to_close = 2

    # 시작 시 팬 정지에 실패했다면(PWM 핀 손상 의심) 시험 전에 반드시 알린다
    if fan_stop_failed:
        QMessageBox.warning(
            None, "팬 정지 실패",
            f"팬을 정지시키지 못했습니다 (PWM 핀 GPIO{sensor_and_controller.PWM_GPIO} 손상 의심).\n\n"
            "팬이 계속 회전할 수 있으니 전원을 수동으로 차단하고,\n"
            "PWM 배선과 핀 상태를 점검한 뒤 시험을 진행하세요.")

    # 시험 조건 입력
    initialize = InputInitialValues()
    initialize.setWindowTitle("시험 조건 입력")
    initialize.resize(size_w, size_h)
    initialize.show()
    app.exec()

    # 시험 조건 불러오기
    with open('conditions.json', 'r') as file:
        data = json.load(file)

    # 측정 시작 시간 저장
    time_start = datetime.now().strftime("%y/%m/%d %H:%M:%S")

    # 새 시험이므로 이전 시험의 그래프 점을 비운다
    LiveMeasurementChart.reset()
    # 풍량 축 범위는 팬 개수에 비례한다
    fan_count = int(data.get("fan_count", 1))

    # 감압 시험
    if data.get("depressurization"):
        # 감압 시험 준비
        long_message = "측정 시작 버튼을 눌리세요."
        pressure = LivePressureData(long_message)
        pressure.setWindowTitle("감압 시험 준비")
        pressure.resize(size_w, size_h)
        pressure.show()
        app.exec()
        ###################    
        ## 데이터 측정 시작 with depressurization 파일명
        ###################    
        message = LiveMeasurementChart("감압 시험 측정 중...", num_fans=fan_count)
        message.setWindowTitle("감압 시험 측정 중")
        message.resize(size_w, size_h)
        message.show()
        wait_for_end = BackgroundTask("depressurization")
        wait_for_end.progress.connect(message.set_progress)
        wait_for_end.point.connect(message.add_point)
        wait_for_end.position.connect(message.move_crosshair)
        wait_for_end.finished.connect(message.close)
        wait_for_end.start()
        app.exec()
        # 측정 종료
        end_of_test = SimpleMessageAutoDisappear("감압 시험 측정 완료.", time_to_close)
        end_of_test.resize(size_w, size_h)
        end_of_test.show()
        app.exec()

    # 가압 시험
    if data.get("pressurization"):
        # 가압 시험 준비
        long_message = "측정 시작 버튼을 눌리세요."
        pressure = LivePressureData(long_message)
        pressure.setWindowTitle("가압시험 준비")
        pressure.resize(size_w, size_h)
        pressure.show()
        app.exec()
        ###################    
        ## 데이터 측정 시작 with pressurization 파일명
        ###################
        message = LiveMeasurementChart("가압 시험 측정 중...", num_fans=fan_count)
        message.setWindowTitle("가압 시험 측정 중")
        message.resize(size_w, size_h)
        message.show()
        wait_for_end = BackgroundTask("pressurization")
        wait_for_end.progress.connect(message.set_progress)
        wait_for_end.point.connect(message.add_point)
        wait_for_end.position.connect(message.move_crosshair)
        wait_for_end.finished.connect(message.close)
        wait_for_end.start()
        app.exec()
        # 측정 종료
        end_of_test = SimpleMessageAutoDisappear("가압 시험 측정 완료.", time_to_close)
        end_of_test.resize(size_w, size_h)
        end_of_test.show()
        app.exec()

    # 측정 종료 시간 저장
    time_end = datetime.now().strftime("%H:%M:%S")
    data["test_period"] = f"{time_start}~{time_end}"
    with open("conditions.json", "w") as file:
        json.dump(data, file, indent=4)

    ###################
    ## 결과 계산 코드 실행
    ###################

    # 계산 중 메시지 창
    message = SimpleMessage("시험 결과 계산 중...")
    message.setWindowTitle("...")
    message.resize(size_w, size_h)
    message.show()
    wait_for_end = BackgroundTask("calculation")
    wait_for_end.progress.connect(message.set_progress)
    wait_for_end.finished.connect(message.close)
    wait_for_end.start()    
    app.exec()
    # 계산 종료
    end_of_test = SimpleMessageAutoDisappear("시험 결과 계산 완료.", time_to_close)
    end_of_test.resize(size_w, size_h)
    end_of_test.show()
    app.exec()

    ###################
    ## 그래프 작성 코드 실행
    ###################
    
    # 그래프 작성 메시지 창
    message = SimpleMessage("그래프 작성 중...")
    message.setWindowTitle("...")
    message.resize(size_w, size_h)
    message.show()
    # 작성 시작
    wait_for_end = BackgroundTask("graph_plotting")
    wait_for_end.progress.connect(message.set_progress)
    wait_for_end.finished.connect(message.close)
    wait_for_end.start()    
    app.exec()
    # 그래프 작성 종료
    end_of_test = SimpleMessageAutoDisappear("그래프 작성 완료.", time_to_close)
    end_of_test.resize(size_w, size_h)
    end_of_test.show()
    app.exec()

    ###################
    ## 보고서 생성 코드 실행
    ###################
    
    # 보고서 생성 중 메시지 창
    message = SimpleMessage("보고서 생성 중...")
    message.setWindowTitle("...")
    message.resize(size_w, size_h)
    message.show()
    wait_for_end = BackgroundTask("reporting")
    wait_for_end.progress.connect(message.set_progress)
    wait_for_end.finished.connect(message.close)
    wait_for_end.start()    
    app.exec()
    # 보고서 생성 종료
    end_of_test = SimpleMessageAutoDisappear("보고서 생성 완료.", time_to_close)
    end_of_test.resize(size_w, size_h)
    end_of_test.show()
    app.exec()

    # 시험 종료
    end_of_test = SimpleMessageAutoDisappear("시험이 모두 종료되었습니다.", time_to_close)
    end_of_test.resize(size_w, size_h)
    end_of_test.show()
    app.exec()
