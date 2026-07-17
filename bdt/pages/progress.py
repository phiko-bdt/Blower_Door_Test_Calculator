"""진행 상황 표시 페이지."""

from PyQt6.QtWidgets import (
    QWidget,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QFrame,
    QProgressBar,
)
from PyQt6.QtCore import Qt, pyqtSignal

from bdt.widgets import PageHeader


class ProgressPage(QWidget):
    """계산·그래프·성적서처럼 잠깐 걸리는 작업의 진행 상황을 보여주는 페이지.

    전에는 단계마다 별도 창이 떴다 사라졌지만, 이제 한 창 안에서 이 페이지로
    바뀌고 작업이 끝나면 자동으로 다음 단계로 넘어간다.

    작업 시간을 미리 알 수 없어 진행률을 숫자로 못 주므로, 막대를 미확정
    (indeterminate) 모드로 돌려 '멈춘 게 아니라 돌고 있다'를 보여준다.
    끝난 상태(done=True)면 막대를 감춘다.
    """

    def __init__(self, title="작업 중…", done=False):
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


class ErrorPage(QWidget):
    """작업이 실패했음을 알리고 시험을 다시 시작할 수 있게 하는 화면.

    예전에는 오류가 나도 error 시그널이 어디에도 연결돼 있지 않아, 화면은
    아무 일 없다는 듯 다음 단계로 넘어갔다. 계산이 실패하면 지난 시험의
    결과 파일이 그대로 쓰여 **다른 건물의 측정값이 이번 건물 이름으로**
    성적서에 실렸다. 실패는 반드시 눈에 보여야 하고 흐름은 멈춰야 한다.
    """

    restart = pyqtSignal()  # '처음으로' → 조건 입력부터 다시

    def __init__(self, message, detail=""):
        super().__init__()

        title = QLabel(message)
        title.setObjectName("ErrorTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setWordWrap(True)

        self.detail = QLabel(detail)
        self.detail.setObjectName("Hint")
        self.detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail.setWordWrap(True)
        self.detail.setMinimumWidth(520)

        note = QLabel("이번 시험 결과는 저장되지 않았습니다. "
                      "원인을 확인한 뒤 다시 시험하세요.")
        note.setObjectName("Hint")
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        note.setWordWrap(True)

        button = QPushButton("처음으로")
        button.setMinimumWidth(200)
        button.clicked.connect(self.restart.emit)
        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(button)
        button_row.addStretch(1)

        card = QFrame()
        card.setObjectName("Card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(56, 40, 56, 40)
        card_layout.setSpacing(12)
        card_layout.addWidget(title)
        card_layout.addWidget(self.detail)
        card_layout.addSpacing(4)
        card_layout.addWidget(note)
        card_layout.addSpacing(12)
        card_layout.addLayout(button_row)

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
