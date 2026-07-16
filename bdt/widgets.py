"""공용 위젯 모음."""

from PyQt6.QtWidgets import (
    QWidget,
    QLabel,
    QFrame,
    QHBoxLayout,
    QVBoxLayout,
)
from PyQt6.QtCore import Qt

from bdt.theme import STANDARD_NAME, STANDARD_NOTE


def _apply_state(widget, state):
    """상태 property 를 바꾸고 스타일을 다시 입힌다.

    Qt 는 property 만 바꿔서는 스타일시트를 다시 계산하지 않는다.
    """
    widget.setProperty("state", state)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class StepHeader(QWidget):
    """상단 진행 단계 표시. 시험은 정해진 순서로 진행되므로 현재 위치를 보여준다.

    수행할 시험(감압/가압)이 조건 입력 후에 정해지므로 단계 목록은 나중에 채운다.
    현재 단계는 색 + 굵기 + 밑줄로, 지나온 단계는 체크 표시로 알린다
    (색 하나에만 기대지 않는다).
    """

    def __init__(self):
        super().__init__()
        self.steps = []       # [(라벨, 밑줄, 이름), ...]

        self.row = QHBoxLayout()
        self.row.setContentsMargins(40, 14, 40, 0)
        self.row.setSpacing(0)

        # 헤더와 본문을 가르는 실선 한 줄 (성적서의 구분선과 같은 역할)
        rule = QFrame()
        rule.setObjectName("HeaderRule")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)
        outer.addLayout(self.row)
        outer.addWidget(rule)

    def _clear(self):
        while self.row.count():
            item = self.row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def set_steps(self, steps):
        """단계 목록을 새로 구성한다."""
        self._clear()
        self.steps = []
        for i, name in enumerate(steps):
            if i:
                sep = QLabel("›")
                sep.setObjectName("StepSep")
                self.row.addWidget(sep)

            label = QLabel(name)
            label.setObjectName("Step")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            # 현재 단계를 알리는 밑줄. 색맹·저시력에서도 위치가 드러난다.
            mark = QFrame()
            mark.setObjectName("StepMark")

            cell = QWidget()
            cell_layout = QVBoxLayout(cell)
            cell_layout.setContentsMargins(0, 0, 0, 0)
            cell_layout.setSpacing(4)
            cell_layout.addWidget(label)
            cell_layout.addWidget(mark)

            self.row.addWidget(cell)
            self.steps.append((label, mark, name))
        self.row.addStretch(1)

    def set_current(self, index):
        """현재 단계는 강조, 지나온 단계는 체크로 표시한다."""
        for i, (label, mark, name) in enumerate(self.steps):
            if i < index:
                state = "done"
                label.setText(f"✓ {name}")
            elif i == index:
                state = "current"
                label.setText(name)
            else:
                state = "todo"
                label.setText(name)
            _apply_state(label, state)
            _apply_state(mark, state)


class PageHeader(QWidget):
    """페이지 제목 — 성적서 헤더와 같은 구성.

    왼쪽에 제목·영문 부제, 오른쪽에 적용 규격을 두고 그 아래 accent 룰을 깐다.
    성적서를 펼쳤을 때와 같은 인상을 화면에서도 주기 위한 것이다.
    """

    def __init__(self, title, subtitle=""):
        super().__init__()

        title_label = QLabel(title)
        title_label.setObjectName("Title")
        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(2)
        left.addWidget(title_label)
        if subtitle:
            subtitle_label = QLabel(subtitle)
            subtitle_label.setObjectName("Subtitle")
            left.addWidget(subtitle_label)

        standard = QLabel(STANDARD_NAME)
        standard.setObjectName("Standard")
        standard.setAlignment(Qt.AlignmentFlag.AlignRight)
        note = QLabel(STANDARD_NOTE)
        note.setObjectName("StandardNote")
        note.setAlignment(Qt.AlignmentFlag.AlignRight)
        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(1)
        right.addWidget(standard)
        right.addWidget(note)

        bar = QHBoxLayout()
        bar.setContentsMargins(0, 0, 0, 0)
        bar.addLayout(left)
        bar.addStretch(1)
        bar.addLayout(right)

        rule = QFrame()
        rule.setObjectName("TitleRule")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)
        outer.addLayout(bar)
        outer.addWidget(rule)


class SectionTitle(QWidget):
    """섹션 제목 — 성적서처럼 작은 accent 라벨 뒤로 실선을 흘린다."""

    def __init__(self, text):
        super().__init__()
        label = QLabel(text)
        label.setObjectName("Section")

        rule = QFrame()
        rule.setObjectName("SectionRule")

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        row.addWidget(label)
        row.addWidget(rule, 1)
