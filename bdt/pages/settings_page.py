"""시험 설정 페이지 — 예전에 코드에 박혀 있던 기준값들을 현장에서 고친다.

두 묶음이 있다.

1. **측정 기준값** (settings.json) — 목표 압력·허용 오차·유지 시간 등.
   settings.FIELDS 순서 그대로 그리므로, 설정 항목을 늘릴 때 이 파일은
   건드리지 않는다.
2. **팬 보정식** (fan_coefficients.json) — duty 를 누기량으로 바꾸는 1차식.
   팬을 교체하거나 재보정하면 이 값이 바뀐다. 계산부가 이 파일을 직접 읽고
   기존 데이터·스크립트도 이 형식을 쓰므로 파일은 그대로 두고 편집만 한다.

값이 범위를 벗어나면 저장 시점에 막는다 — 측정을 다 마친 뒤 계산에서 터지는
것보다 여기서 걸리는 편이 낫다 (조건 입력 페이지와 같은 방침).
"""

import json

from PyQt6.QtWidgets import (
    QWidget,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QGridLayout,
    QFrame,
    QMessageBox,
    QScrollArea,
)
from PyQt6.QtCore import Qt, pyqtSignal

from bdt import settings
from bdt.widgets import PageHeader, SectionTitle


class SettingsPage(QWidget):
    """측정 기준값 + 팬 보정식 편집."""

    closed = pyqtSignal()  # 저장했거나 취소했다 → 조건 입력으로 복귀

    def __init__(self):
        super().__init__()
        self.fields = {}       # settings 키 → QLineEdit
        self.fan_fields = {}   # ("reverse","slope") 등 → QLineEdit

        root = QVBoxLayout(self)
        root.setContentsMargins(40, 24, 40, 24)
        root.setSpacing(16)
        root.addWidget(PageHeader("시험 설정", "Test Settings"))

        hint = QLabel("여기서 바꾼 값은 다음 시험부터 바로 적용됩니다. "
                      "팬을 교체했거나 재보정했다면 보정식을 함께 고치세요.")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        # 항목이 많아 800×480 화면에서 잘리므로 스크롤 영역에 담는다
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 12, 0)
        body_layout.setSpacing(16)

        body_layout.addWidget(SectionTitle("측정 기준값"))
        body_layout.addWidget(self._values_card())
        body_layout.addWidget(SectionTitle("팬 보정식 (팬 세기 → 누기량)"))
        body_layout.addWidget(self._fan_card())
        body_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        # ── 버튼 줄 ────────────────────────────────────────────
        reset_button = QPushButton("기본값으로 되돌리기")
        reset_button.setObjectName("Secondary")
        reset_button.setMinimumHeight(48)
        reset_button.clicked.connect(self._reset_defaults)
        cancel_button = QPushButton("취소")
        cancel_button.setObjectName("Secondary")
        cancel_button.setMinimumHeight(48)
        cancel_button.setMinimumWidth(120)
        cancel_button.clicked.connect(self.closed.emit)
        save_button = QPushButton("저장")
        save_button.setMinimumHeight(48)
        save_button.setMinimumWidth(180)
        save_button.clicked.connect(self._save)

        buttons = QHBoxLayout()
        buttons.setSpacing(12)
        buttons.addWidget(reset_button)
        buttons.addStretch(1)
        buttons.addWidget(cancel_button)
        buttons.addWidget(save_button)
        root.addLayout(buttons)

        self._fill(settings.load(), settings.load_fan_coefficients())

    # ── 구성 ──────────────────────────────────────────────────
    def _values_card(self):
        card = QFrame()
        card.setObjectName("Card")
        grid = QGridLayout(card)
        grid.setContentsMargins(28, 20, 28, 20)
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(12)
        # 항목이 여덟이라 한 줄에 하나씩 놓으면 팬 보정식이 화면 밖으로 밀린다.
        # 이름·설명을 한 덩어리로 묶어 2열로 앉힌다.
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(2, 1)

        for idx, (key, name, unit, description) in enumerate(settings.FIELDS):
            row, col = divmod(idx, 2)
            label = QLabel(f"{name} ({unit})")
            label.setObjectName("FieldLabel")
            note = QLabel(description)
            note.setObjectName("Hint")
            note.setWordWrap(True)
            text_block = QVBoxLayout()
            text_block.setSpacing(1)
            text_block.setContentsMargins(0, 0, 0, 0)
            text_block.addWidget(label)
            text_block.addWidget(note)

            edit = QLineEdit()
            edit.setFixedWidth(100)
            lo, hi = settings.LIMITS[key]
            edit.setPlaceholderText(f"{self._fmt(lo)}~{self._fmt(hi)}")
            edit.setToolTip(f"허용 범위: {self._fmt(lo)} ~ {self._fmt(hi)} {unit}")
            self.fields[key] = edit

            grid.addLayout(text_block, row, col * 2)
            grid.addWidget(edit, row, col * 2 + 1,
                           Qt.AlignmentFlag.AlignTop)
        return card

    def _fan_card(self):
        card = QFrame()
        card.setObjectName("Card")
        outer = QVBoxLayout(card)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(12)

        note = QLabel(
            "누기량(㎥/h) = (기울기 × 팬 세기(%) + 절편) × 팬 수량. "
            "팬 보정 시험에서 얻은 1차식 계수를 그대로 넣습니다. "
            "아래 ‘팬 세기 사용 구간’ 밖에서는 이 식이 맞지 않습니다.")
        note.setObjectName("Hint")
        note.setWordWrap(True)
        outer.addWidget(note)

        grid = QGridLayout()
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(14)
        grid.setColumnStretch(5, 1)
        grid.addWidget(self._column_title("기울기 (㎥/h·%)"), 0, 1)
        grid.addWidget(self._column_title("절편 (㎥/h)"), 0, 3)

        for row, (side, label_text) in enumerate(settings.FAN_SIDES, start=1):
            label = QLabel(f"{label_text} 시험")
            label.setObjectName("FieldLabel")
            grid.addWidget(label, row, 0)
            for col, key in ((1, "slope"), (3, "intercept")):
                edit = QLineEdit()
                edit.setMaximumWidth(140)
                self.fan_fields[(side, key)] = edit
                grid.addWidget(edit, row, col)
        outer.addLayout(grid)

        # duty 사용 구간 — 보정식이 유효한 범위이자 PID 가 쓰는 팬 세기 구간
        duty_row = QHBoxLayout()
        duty_row.setSpacing(10)
        duty_label = QLabel("팬 세기 사용 구간 (%)")
        duty_label.setObjectName("FieldLabel")
        duty_row.addWidget(duty_label)
        for key in ("duty_min", "duty_max"):
            edit = QLineEdit()
            edit.setMaximumWidth(80)
            self.fan_fields[("duty_range", key)] = edit
            duty_row.addWidget(edit)
            if key == "duty_min":
                duty_row.addWidget(QLabel("~"))
        duty_hint = QLabel(
            "PID 가 이 구간 안에서만 팬을 돌립니다. 최소는 팬이 확실히 도는 "
            "값으로 잡으세요 (너무 낮으면 팬이 멈춥니다).")
        duty_hint.setObjectName("Hint")
        duty_hint.setWordWrap(True)
        duty_row.addWidget(duty_hint, 1)
        outer.addLayout(duty_row)
        return card

    @staticmethod
    def _column_title(text):
        label = QLabel(text)
        label.setObjectName("StatName")
        label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        return label

    @staticmethod
    def _fmt(value):
        return f"{value:g}"

    # ── 값 채우기·읽기 ────────────────────────────────────────
    def _fill(self, values, fan_coeffs):
        for key, edit in self.fields.items():
            edit.setText(self._fmt(values[key]))
        cover = fan_coeffs.get(settings.FAN_COVER, {})
        for (side, key), edit in self.fan_fields.items():
            if side == "duty_range":
                duty_range = cover.get("duty_range", [20, 100])
                edit.setText(str(duty_range[0 if key == "duty_min" else 1]))
            else:
                edit.setText(self._fmt(cover.get(side, {}).get(key, 0.0)))

    def _reset_defaults(self):
        """측정 기준값만 되돌린다 — 팬 계수는 장비 고유값이라 건드리지 않는다."""
        answer = QMessageBox.question(
            self, "기본값 복원",
            "측정 기준값을 기본값으로 되돌릴까요?\n\n"
            "팬 보정식은 장비마다 다른 값이라 그대로 둡니다.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        for key, edit in self.fields.items():
            edit.setText(self._fmt(settings.DEFAULTS[key]))

    def _number(self, edit, label):
        """숫자 하나를 읽는다. 비었거나 숫자가 아니면 알리고 None."""
        text = edit.text().strip().replace(",", "")
        if not text:
            QMessageBox.warning(self, "입력 오류", f"‘{label}’ 값을 넣어 주세요.")
            edit.setFocus()
            return None
        try:
            return float(text)
        except ValueError:
            QMessageBox.warning(
                self, "입력 오류",
                f"‘{label}’ 에는 숫자만 넣을 수 있습니다.\n입력한 값: {text}")
            edit.setFocus()
            edit.selectAll()
            return None

    def _save(self):
        values = {}
        for key, name, unit, _ in settings.FIELDS:
            value = self._number(self.fields[key], name)
            if value is None:
                return
            lo, hi = settings.LIMITS[key]
            if not (lo <= value <= hi):
                QMessageBox.warning(
                    self, "입력 오류",
                    f"‘{name}’ 은 {self._fmt(lo)} ~ {self._fmt(hi)} {unit} "
                    f"범위여야 합니다.\n입력한 값: {self._fmt(value)}")
                self.fields[key].setFocus()
                self.fields[key].selectAll()
                return
            values[key] = value

        fan = {side: {} for side, _ in settings.FAN_SIDES}
        for (side, key), edit in self.fan_fields.items():
            if side == "duty_range":
                continue
            label = dict(settings.FAN_SIDES)[side] + " " + (
                "기울기" if key == "slope" else "절편")
            value = self._number(edit, label)
            if value is None:
                return
            fan[side][key] = value
        duty = []
        for key, label in (("duty_min", "팬 세기 최소"), ("duty_max", "팬 세기 최대")):
            value = self._number(self.fan_fields[("duty_range", key)], label)
            if value is None:
                return
            duty.append(round(value))
        fan["duty_range"] = duty

        # 범위·정합성 검증은 settings 가 최종 판정한다 (파일에 들어가는 값의
        # 규칙이 한 곳에만 있어야 화면과 저장이 어긋나지 않는다).
        # 둘 다 검증한 뒤에 쓴다 — 앞을 쓰고 뒤가 걸리면 "저장 실패"라고
        # 알리면서 실제로는 절반이 저장된 상태가 된다.
        try:
            settings.validate(values)
            settings.validate_fan_coefficients(fan)
        except ValueError as exc:
            QMessageBox.warning(self, "입력 오류", str(exc))
            return
        try:
            settings.save(values)
            settings.save_fan_coefficients(fan)
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            QMessageBox.warning(self, "저장 실패", str(exc))
            return

        tolerance = settings.tolerance_pa(values)
        QMessageBox.information(
            self, "저장 완료",
            f"설정을 저장했습니다.\n\n"
            f"목표 압력 {values['target_pressure']:g} Pa "
            f"(허용 오차 ±{tolerance:.1f} Pa)로 다음 시험을 진행합니다.")
        self.closed.emit()
