"""시험 조건 입력 페이지."""

import os
import json
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QGridLayout,
    QCheckBox,
    QMessageBox,
    QComboBox,
    QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal

from bdt import paths
from bdt.theme import COLOR_ACCENT
from bdt.widgets import PageHeader, SectionTitle


class InputInitialValues(QWidget):
    """시험 조건 입력 페이지."""
    saved = pyqtSignal()  # 조건 저장 완료 → 다음 단계로
    settings_requested = pyqtSignal()  # 설정 페이지로

    def __init__(self):
        super().__init__()

        # 루트 레이아웃 (세로): 헤더 → 폼 → 옵션 → 체크박스 → 저장 버튼
        root = QVBoxLayout()
        root.setContentsMargins(40, 24, 40, 24)
        root.setSpacing(16)
        self.setLayout(root)

        # 상단 제목 — 성적서 헤더와 같은 처리 (제목 + 영문 부제 + 규격 + accent 룰)
        root.addWidget(PageHeader("기밀성능 시험", "Building Airtightness Test"))

        # 안내 문구
        hint = QLabel("＊ 표시된 항목은 필수입니다. 나머지는 성적서에 실릴 정보로, 비워 둘 수 있습니다.")
        hint.setObjectName("Hint")
        root.addWidget(hint)

        self.input_fields = {}

        # ── 필수 항목 — 시험 수행에 반드시 필요한 값만 따로 묶고
        #    테두리를 accent 색으로 둘러 눈에 띄게 한다 (색만으로 구분하지
        #    않도록 라벨에도 ＊ 표시를 함께 단다)
        root.addWidget(SectionTitle("필수 항목"))
        required_card = QFrame()
        required_card.setObjectName("Card")
        req = QGridLayout(required_card)
        req.setContentsMargins(28, 24, 28, 24)
        req.setHorizontalSpacing(24)
        req.setVerticalSpacing(16)
        req.setColumnStretch(1, 1)
        req.setColumnStretch(3, 1)

        volume_field = QLineEdit()
        volume_field.setPlaceholderText("예: 424.21 — 숫자만 입력")
        volume_field.setProperty("required", True)
        self.input_fields["interior volume"] = volume_field
        req.addWidget(self._required_label("실내 체적 (㎥)"), 0, 0)
        req.addWidget(volume_field, 0, 1)

        # 팬 수량 — duty→누기량 환산이 팬 개수에 비례하므로 반드시 맞아야 한다.
        # (팬 커버 선택은 기능을 쓰지 않기로 해 UI 에서 뺐다. 저장하지 않으면
        # 계산부가 기본값 "none" 을 쓴다.)
        self.count_combo = QComboBox()
        self.count_combo.addItems(["1", "2"])
        self.count_combo.setProperty("required", True)
        req.addWidget(self._required_label("팬 수량"), 0, 2)
        req.addWidget(self.count_combo, 0, 3)

        # 수행할 시험 (감압 / 가압) — 하나 이상 필수
        self.checkbox_states = {}
        checkbox1 = QCheckBox("감압 시험")
        checkbox1.setObjectName("depressurization")
        checkbox1.stateChanged.connect(self.save_checkbox_state)
        checkbox2 = QCheckBox("가압 시험")
        checkbox2.setObjectName("pressurization")
        checkbox2.stateChanged.connect(self.save_checkbox_state)
        check_row = QHBoxLayout()
        check_row.setSpacing(32)
        check_row.addWidget(checkbox1)
        check_row.addWidget(checkbox2)
        check_row.addStretch(1)
        req.addWidget(self._required_label("수행할 시험"), 1, 0)
        req.addLayout(check_row, 1, 1, 1, 3)
        root.addWidget(required_card)

        # ── 시험 정보 (선택) — 성적서에 실리는 문자 정보 ─────────
        root.addWidget(SectionTitle("시험 정보 (선택)"))
        labels = [
            ("시험 목적", "purpose", "신축 공동주택 기밀성능 확인"),
            ("시험 위치", "location", "서울시 송파구 풍납동 497"),
            ("시험 방법", "method", "method A / method B"),
            ("의뢰자", "requester", "홍길동, 010-0000-0000"),
            ("설계자", "designer", "OO건축사사무소"),
            ("시험자", "tester", "김철수 (주)기밀시험"),
            ("시공자", "builder", "OO건축"),
            ("연면적 (㎡)", "floor area", "92.4"),
            ("구조", "structure", "경량목구조")
        ]

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
            label.setObjectName("FieldLabel")
            input_field = QLineEdit()
            input_field.setPlaceholderText(placeholder)
            form.addWidget(label, r, c * 2)
            form.addWidget(input_field, r, c * 2 + 1)
            self.input_fields[label_key] = input_field
        root.addWidget(card)

        root.addStretch(1)

        # 저장 버튼 (하단, 크게 — 터치용)
        save_button = QPushButton("저장하고 시작")
        save_button.setMinimumHeight(56)
        save_button.setMinimumWidth(260)
        save_button.clicked.connect(self.save_data)
        # 설정은 시험 시작 전에만 바꿀 수 있게 여기에 둔다 (측정 중에 목표
        # 압력이나 팬 보정식이 바뀌면 같은 시험 안에서 기준이 갈린다)
        settings_button = QPushButton("설정")
        settings_button.setObjectName("Secondary")
        settings_button.setMinimumHeight(56)
        settings_button.setMinimumWidth(120)
        settings_button.clicked.connect(self.settings_requested.emit)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        btn_row.addStretch(1)
        btn_row.addWidget(settings_button)
        btn_row.addWidget(save_button)
        btn_row.addStretch(1)
        root.addLayout(btn_row)

    @staticmethod
    def _required_label(text):
        """필수 항목 라벨 — accent 색 ＊ 를 붙인다 (테두리 색과 짝)."""
        label = QLabel(f'{text} <span style="color:{COLOR_ACCENT};">＊</span>')
        label.setObjectName("FieldLabel")
        label.setTextFormat(Qt.TextFormat.RichText)
        return label

    def save_checkbox_state(self):
        sender = self.sender()
        checkbox_text = sender.objectName()
        checkbox_state = sender.isChecked()

        self.checkbox_states[checkbox_text] = checkbox_state

    def _check_number(self, key, label, required):
        """숫자 입력칸을 검증하고 정리된 문자열을 돌려준다. 문제가 있으면 None.

        예전에는 비어 있는지만 봤다. '424.21 ㎥' 나 '약 424' 처럼 단위·글자가
        섞이면 그대로 통과했다가, 3~5분짜리 측정을 다 마친 **뒤** 계산 단계에서
        ValueError 로 터졌다. 여기서 막으면 바로 고쳐 넣을 수 있다.
        """
        field = self.input_fields[key]
        text = field.text().strip()
        if not text:
            if required:
                QMessageBox.warning(self, "입력 오류",
                                    f"‘{label}’ 항목은 필수 입력입니다.")
                field.setFocus()
                return None
            return ""

        # 천 단위 쉼표는 흔한 입력이라 받아준다
        try:
            value = float(text.replace(",", ""))
        except ValueError:
            QMessageBox.warning(
                self, "입력 오류",
                f"‘{label}’ 항목에는 숫자만 넣을 수 있습니다.\n"
                f"입력한 값: {text}\n\n단위나 글자를 빼고 숫자만 적어 주세요.")
            field.setFocus()
            field.selectAll()
            return None
        if value <= 0:
            QMessageBox.warning(self, "입력 오류",
                                f"‘{label}’ 항목은 0보다 커야 합니다.")
            field.setFocus()
            field.selectAll()
            return None
        return text.replace(",", "")

    def save_data(self):
        # 숫자 칸 검증 — 계산부가 float() 로 읽으므로 여기서 걸러야 한다
        volume = self._check_number("interior volume", "실내 체적 (㎥)",
                                    required=True)
        if volume is None:
            return
        self.input_fields["interior volume"].setText(volume)

        area = self._check_number("floor area", "연면적 (㎡)", required=False)
        if area is None:
            return
        self.input_fields["floor area"].setText(area)

        # 감압 또는 가압 중 적어도 하나가 선택되었는지 확인
        is_checked = self.checkbox_states.get("depressurization", False) or self.checkbox_states.get("pressurization", False)
        if not is_checked:
            QMessageBox.warning(self, "선택 오류", "감압 시험과 가압 시험 중 하나 이상을 선택해야 합니다.")
            return

        data = {}
        # 입력값을 JSON 파일로 저장
        for key, input_field in self.input_fields.items():
            value = input_field.text()
            data[key] = value
        # Fan options
        data["fan_count"] = int(self.count_combo.currentText())
        # 체크박스 데이터 저장
        for key, checkbox in self.checkbox_states.items():
            data[key] = checkbox
        # json으로 저장 (다음 프로세스용)
        with open(paths.CONDITIONS_JSON, "w") as file:
            json.dump(data, file, indent=4)
        # json으로 저장 (백업용)
        now = datetime.now().strftime("%y%m%d-%H%M%S")
        backup_path = os.path.join(paths.ensure_dir(paths.CONDITIONS_DIR),
                                   f"conditions_{now}.json")
        with open(backup_path, "w") as file:
            json.dump(data, file, indent=4)
        # 다음 단계로
        self.saved.emit()
