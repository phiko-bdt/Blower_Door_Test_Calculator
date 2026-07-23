"""이전 보고서 받기 화면 — 시작 화면에서 폰으로 지난 성적서를 받는다.

시험을 새로 하지 않고도 이미 발행한 성적서를 의뢰자 폰으로 넘길 수 있어야
한다. 성적서 화면과 똑같은 2단계 QR(SharePanel)을 그대로 보여주되, 여기선
지면 옆이 아니라 화면 가운데에 크게 놓는다. AP·네트워크가 없어 QR 을 띄울 수
없을 때는 카드 대신 '준비 안 됨' 안내를 보여준다 (성적서 화면은 여백이라
그냥 숨겼지만, 이 화면은 QR 이 유일한 내용이라 빈 화면이 되면 안 된다).
"""

from PyQt6.QtWidgets import (
    QWidget,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
)
from PyQt6.QtCore import Qt, pyqtSignal

from bdt.widgets import PageHeader
from bdt.pages.share_panel import SharePanel


class PastReportsPage(QWidget):
    """폰으로 지난 성적서를 받는 화면 (SharePanel + 닫기)."""

    closed = pyqtSignal()  # 닫으면 조건 입력으로 복귀

    def __init__(self):
        super().__init__()

        close_button = QPushButton("닫기")
        close_button.setObjectName("Secondary")
        close_button.setMinimumWidth(96)
        close_button.clicked.connect(self.closed.emit)

        root = QVBoxLayout(self)
        root.setContentsMargins(40, 20, 40, 24)
        root.setSpacing(16)
        root.addWidget(PageHeader("이전 보고서", "Past Reports",
                                  actions=[close_button], show_standard=False))

        hint = QLabel("이미 발행한 성적서를 폰으로 받습니다. "
                      "새 시험을 하지 않아도 됩니다.")
        hint.setObjectName("Hint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(hint)

        # 공유 QR — 스스로 2초마다 AP·네트워크 상태를 보고 자신을 켜고 끈다.
        # wide=True: 성적서 화면의 좁은 카드를 재사용하지 않고, 두 QR 을 화면
        # 좌우로 크게 벌린다 (폰으로 찍을 때 옆 QR 이 겹치지 않게).
        self.share = SharePanel(self, wide=True)
        self.share.state_changed.connect(self._on_share_state)

        # QR 이 없을 때 대신 보여줄 안내. SharePanel 과 같은 자리에 두고 둘 중
        # 하나만 보인다 (숨은 쪽은 자리를 차지하지 않는다).
        self.not_ready = QLabel(
            "네트워크(공유용 WiFi·AP)가 아직 준비되지 않았습니다.\n\n"
            "단말의 공유 WiFi(BlowerDoor-Test)가 켜져 있는지 확인하고\n"
            "잠시 뒤 다시 시도하세요.")
        self.not_ready.setObjectName("Message")
        self.not_ready.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.not_ready.setWordWrap(True)

        # wide SharePanel 은 전체 폭을 쓴다. QR(있음)과 안내(없음)는 한 번에
        # 하나만 보이며, 위아래 stretch 로 보이는 쪽을 세로 가운데에 둔다.
        not_ready_row = QHBoxLayout()
        not_ready_row.addStretch(1)
        not_ready_row.addWidget(self.not_ready)
        not_ready_row.addStretch(1)
        root.addStretch(1)
        root.addLayout(not_ready_row)
        root.addWidget(self.share)
        root.addStretch(1)

        # SharePanel 은 생성될 때 이미 한 번 refresh 해 상태를 정한다 — 그
        # 최초 state_changed 는 위 connect 이전에 나가 놓친다. 지금 실제
        # 상태(available)로 안내를 한 번 맞춘다 (이후 변화는 시그널이 따라온다).
        # isVisible() 은 페이지가 아직 화면에 안 붙어 못 믿는다.
        self.not_ready.setVisible(not self.share.available)

    def _on_share_state(self, visible):
        # SharePanel 은 QR 이 뜰 때만 자신을 보이게 한다. 그 반대로 안내를
        # 켜고 끈다 — 둘이 동시에 뜨거나 둘 다 사라지지 않게.
        self.not_ready.setVisible(not visible)
