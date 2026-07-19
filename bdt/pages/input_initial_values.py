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
    QFrame,
    QScrollArea,
    QScroller,
)
from PyQt6.QtCore import Qt, pyqtSignal

from bdt import paths
from bdt.theme import COLOR_ACCENT
from bdt.widgets import PageHeader, SectionTitle, alert


class InputInitialValues(QWidget):
    """시험 조건 입력 페이지."""
    saved = pyqtSignal()  # 조건 저장 완료 → 다음 단계로
    settings_requested = pyqtSignal()  # 설정 페이지로

    def __init__(self):
        super().__init__()

        # 루트 레이아웃 (세로): 제목 → 스크롤 본문(폼) → 저장 버튼
        #
        # 본문을 스크롤 영역에 담는 이유는 항목이 많아서가 아니라 **최소 높이를
        # 없애기 위해서**다. 이 페이지가 요구하는 최소 높이(793)가 화면(800)에서
        # 헤더를 뺀 예산(723)을 넘으면 창이 화면보다 커야 하고, 그러면 앱이
        # 전체화면으로 뜨지 못한다 (실제로 그랬다 — 페이지를 붙이는 순간
        # showFullScreen 이 풀렸다). 스크롤 영역은 축소를 허용해 이 제약을
        # 없앤다. 1280×800 에서는 스크롤이 생기지 않는다.
        # 여백이 progress·summary 같은 여백 많은 화면(24)보다 좁다. 이 페이지는
        # 항목이 많아 1280×800 에 스크롤 없이 담으려면 조금씩 조여야 한다
        # (설정 페이지도 같은 이유로 같은 값). 드리프트가 아니라 제약이다.
        root = QVBoxLayout()
        root.setContentsMargins(40, 20, 40, 20)
        root.setSpacing(14)
        self.setLayout(root)

        # 동작 버튼(설정·저장)은 헤더 오른쪽에 둔다. 하단에 두면 화면 키보드가
        # 뜰 때 버튼줄이 본문·키보드 사이 공간을 크게 잡아먹는다.
        save_button = QPushButton("저장하고 시작")
        save_button.setMinimumWidth(200)
        save_button.clicked.connect(self.save_data)
        # 설정은 시험 시작 전에만 바꿀 수 있게 여기에 둔다 (측정 중에 목표
        # 압력이나 팬 보정식이 바뀌면 같은 시험 안에서 기준이 갈린다)
        settings_button = QPushButton("설정")
        settings_button.setObjectName("Secondary")
        settings_button.setMinimumWidth(96)
        settings_button.clicked.connect(self.settings_requested.emit)

        # 상단 제목 — 성적서 헤더와 같은 처리 (제목 + 영문 부제 + 규격 + accent 룰)
        root.addWidget(PageHeader("기밀성능 시험", "Building Airtightness Test",
                                  actions=[settings_button, save_button],
                                  show_standard=False))

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 12, 0)
        body_layout.setSpacing(14)

        # 안내 문구
        hint = QLabel("＊ 표시된 항목은 필수입니다. 나머지는 성적서에 실릴 정보로, 비워 둘 수 있습니다.")
        hint.setObjectName("Hint")
        body_layout.addWidget(hint)

        self.input_fields = {}

        # ── 필수 항목 — 시험 수행에 반드시 필요한 값만 따로 묶고
        #    테두리를 accent 색으로 둘러 눈에 띄게 한다 (색만으로 구분하지
        #    않도록 라벨에도 ＊ 표시를 함께 단다)
        body_layout.addWidget(SectionTitle("필수 항목"))
        required_card = QFrame()
        required_card.setObjectName("Card")
        req = QGridLayout(required_card)
        req.setContentsMargins(28, 12, 28, 12)
        req.setHorizontalSpacing(24)
        req.setVerticalSpacing(12)
        req.setColumnStretch(1, 1)
        req.setColumnStretch(3, 1)

        volume_field = QLineEdit()
        volume_field.setPlaceholderText("예: 424.21 — 숫자만 입력")
        volume_field.setProperty("required", True)
        volume_field.setProperty("numeric", True)
        self.input_fields["interior volume"] = volume_field
        req.addWidget(self._required_label("실내 체적 (㎥)"), 0, 0)
        req.addWidget(volume_field, 0, 1)

        # 팬 수량 — 쓰는 팬을 고른다(체크한 개수 = 팬 수). duty→누기량 환산이
        # 팬 개수에 비례하므로 반드시 하나 이상 골라야 한다. 감압·가압 선택과
        # 같은 체크박스 방식이라 화면이 일관된다.
        # (팬 커버 선택은 기능을 쓰지 않기로 해 UI 에서 뺐다. 저장하지 않으면
        # 계산부가 기본값 "none" 을 쓴다.)
        self.fan_checks = [QCheckBox("팬 1"), QCheckBox("팬 2")]
        fan_row = QHBoxLayout()
        fan_row.setSpacing(32)
        for cb in self.fan_checks:
            fan_row.addWidget(cb)
        fan_row.addStretch(1)
        req.addWidget(self._required_label("팬 수량"), 0, 2)
        req.addLayout(fan_row, 0, 3)

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
        body_layout.addWidget(required_card)

        # ── 시험 정보 (선택) — 성적서에 실리는 문자 정보 ─────────
        body_layout.addWidget(SectionTitle("시험 정보 (선택)"))
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
        form.setContentsMargins(28, 12, 28, 12)
        form.setHorizontalSpacing(24)
        form.setVerticalSpacing(12)
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
            if label_key == "floor area":
                input_field.setProperty("numeric", True)
            self.input_fields[label_key] = input_field
        body_layout.addWidget(card)

        body_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(body)
        # 터치 플릭으로 본문을 스크롤할 수 있게 한다. 키보드가 뜨면 본문이
        # 세로로 줄어 스크롤이 생기는데, 폭 10px 스크롤바 핸들은 손가락으로
        # 잡을 수 없다 (터치 단말의 유일한 스크롤 수단이 플릭이다).
        QScroller.grabGesture(scroll.viewport(),
                              QScroller.ScrollerGestureType.LeftMouseButtonGesture)
        root.addWidget(scroll, 1)

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
                alert(self, "입력 오류", f"‘{label}’ 항목은 필수 입력입니다.")
                field.setFocus()
                return None
            return ""

        # 천 단위 쉼표는 흔한 입력이라 받아준다
        try:
            value = float(text.replace(",", ""))
        except ValueError:
            alert(self, "입력 오류",
                  f"‘{label}’ 항목에는 숫자만 넣을 수 있습니다.\n"
                  f"입력한 값: {text}\n\n단위나 글자를 빼고 숫자만 적어 주세요.")
            field.setFocus()
            field.selectAll()
            return None
        if value <= 0:
            alert(self, "입력 오류", f"‘{label}’ 항목은 0보다 커야 합니다.")
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

        # 팬을 하나 이상 선택했는지 확인 (체크한 개수 = 팬 수)
        fan_count = sum(cb.isChecked() for cb in self.fan_checks)
        if fan_count == 0:
            alert(self, "선택 오류", "팬을 하나 이상 선택해야 합니다.")
            return

        # 감압 또는 가압 중 적어도 하나가 선택되었는지 확인
        is_checked = self.checkbox_states.get("depressurization", False) or self.checkbox_states.get("pressurization", False)
        if not is_checked:
            alert(self, "선택 오류",
                  "감압 시험과 가압 시험 중 하나 이상을 선택해야 합니다.")
            return

        data = {}
        # 입력값을 JSON 파일로 저장
        for key, input_field in self.input_fields.items():
            value = input_field.text()
            data[key] = value
        # Fan options — 체크한 팬 개수
        data["fan_count"] = fan_count
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
