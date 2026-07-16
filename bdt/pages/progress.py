"""진행 상황 표시 페이지."""

from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QFrame
from PyQt6.QtCore import Qt


class ProgressPage(QWidget):
    """계산·그래프·성적서처럼 잠깐 걸리는 작업의 진행 상황을 보여주는 페이지.

    전에는 단계마다 별도 창이 떴다 사라졌지만, 이제 한 창 안에서 이 페이지로
    바뀌고 작업이 끝나면 자동으로 다음 단계로 넘어간다.
    """

    def __init__(self, title="작업 중..."):
        super().__init__()

        self.label = QLabel(title)
        self.label.setObjectName("Message")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)

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

        outer = QVBoxLayout(self)
        outer.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(card)
        row.addStretch(1)
        outer.addLayout(row)
        outer.addStretch(1)

    def set_title(self, text):
        self.label.setText(text)

    def set_progress(self, text):
        """작업 스레드가 보내온 진행 상황을 표시한다."""
        self.progress.setText(text)
