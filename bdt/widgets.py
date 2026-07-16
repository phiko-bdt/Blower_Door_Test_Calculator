"""공용 위젯 모음."""

from PyQt6.QtWidgets import QWidget, QLabel, QHBoxLayout


class StepHeader(QWidget):
    """상단 진행 단계 표시. 시험은 정해진 순서로 진행되므로 현재 위치를 보여준다.

    수행할 시험(감압/가압)이 조건 입력 후에 정해지므로 단계 목록은 나중에 채운다.
    """

    def __init__(self):
        super().__init__()
        self.labels = []
        self.row = QHBoxLayout(self)
        self.row.setContentsMargins(40, 18, 40, 10)
        self.row.setSpacing(0)
        self.row.addStretch(1)

    def set_steps(self, steps):
        """단계 목록을 새로 구성한다."""
        while self.row.count():
            item = self.row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.labels = []
        for i, name in enumerate(steps):
            if i:
                sep = QLabel("›")
                sep.setObjectName("StepSep")
                self.row.addWidget(sep)
            label = QLabel(name)
            label.setObjectName("Step")
            self.row.addWidget(label)
            self.labels.append(label)
        self.row.addStretch(1)

    def set_current(self, index):
        """현재 단계는 강조, 지나온 단계는 흐리게 표시한다."""
        for i, label in enumerate(self.labels):
            if i < index:
                state = "done"
            elif i == index:
                state = "current"
            else:
                state = "todo"
            label.setProperty("state", state)
            # 스타일 재적용 (property 변경만으로는 갱신되지 않는다)
            label.style().unpolish(label)
            label.style().polish(label)
