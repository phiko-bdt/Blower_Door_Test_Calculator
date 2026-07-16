"""진행 상황 표시 페이지."""

from PyQt6.QtWidgets import (
    QWidget,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QFrame,
    QProgressBar,
)
from PyQt6.QtCore import Qt

from bdt.widgets import PageHeader


class ProgressPage(QWidget):
    """계산·그래프·성적서처럼 잠깐 걸리는 작업의 진행 상황을 보여주는 페이지.

    전에는 단계마다 별도 창이 떴다 사라졌지만, 이제 한 창 안에서 이 페이지로
    바뀌고 작업이 끝나면 자동으로 다음 단계로 넘어간다.

    작업 시간을 미리 알 수 없어 진행률을 숫자로 못 주므로, 막대를 미확정
    (indeterminate) 모드로 돌려 '멈춘 게 아니라 돌고 있다'를 보여준다.
    끝난 상태(done=True)면 막대를 감춘다.
    """

    def __init__(self, title="작업 중...", done=False):
        super().__init__()

        self.label = QLabel(title)
        self.label.setObjectName("Message")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.progress = QLabel("잠시만 기다려 주세요…")
        self.progress.setObjectName("Hint")
        self.progress.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress.setWordWrap(True)
        self.progress.setMinimumWidth(460)

        # 미확정 진행 막대 (min=max=0 이면 Qt 가 알아서 왕복시킨다)
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        self.bar.setTextVisible(False)
        self.bar.setFixedWidth(240)
        self.bar.setVisible(not done)

        card = QFrame()
        card.setObjectName("Card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(64, 40, 64, 40)
        card_layout.setSpacing(12)
        card_layout.addWidget(self.label)
        card_layout.addWidget(self.progress)
        bar_row = QHBoxLayout()
        bar_row.addStretch(1)
        bar_row.addWidget(self.bar)
        bar_row.addStretch(1)
        card_layout.addSpacing(6)
        card_layout.addLayout(bar_row)

        body = QVBoxLayout()
        body.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(card)
        row.addStretch(1)
        body.addLayout(row)
        body.addStretch(1)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 24, 40, 24)
        outer.setSpacing(16)
        outer.addWidget(PageHeader("기밀성능 시험", "Building Airtightness Test"))
        outer.addLayout(body, 1)

    def set_title(self, text):
        self.label.setText(text)

    def set_progress(self, text):
        """작업 스레드가 보내온 진행 상황을 표시한다."""
        self.progress.setText(text)

    def set_done(self):
        """작업이 끝났음을 알린다 (진행 막대를 감춘다)."""
        self.bar.setVisible(False)
