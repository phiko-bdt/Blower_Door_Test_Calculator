"""폰으로 성적서를 받는 2단계 QR 카드 — 성적서 화면과 시작 화면이 공유한다.

① 폰을 단말 WiFi(AP)에 연결(WiFi QR) → ② 성적서 다운로드 목록 열기(주소 QR).
AP·네트워크 상태를 2초마다 스스로 확인해 갱신하고, 어느 망도 없으면 숨는다.

예전엔 이 로직이 성적서 화면(ReportPage)에만 박혀 있었다. 시작 화면에서도
지난 성적서를 폰으로 받게 하려고 위젯으로 떼어, 두 화면이 같은 카드·같은
갱신 규칙을 쓴다 (문구·간격이 갈리지 않게).
"""

from PyQt6.QtWidgets import (
    QWidget,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QFrame,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal


def qr_pixmap(url, size=150):
    """URL 을 담은 QR 코드 QPixmap. segno 가 없으면 None (주소 텍스트로 대체).

    segno 로 PNG 를 메모리에 그려 QPixmap 으로 읽는다. 외부 파일을 안 만든다.
    """
    try:
        import io
        import segno
        from PyQt6.QtGui import QPixmap
        buf = io.BytesIO()
        # scale 을 키워 또렷하게 그린 뒤 위젯 크기로 부드럽게 줄인다
        segno.make(url, error="m").save(buf, kind="png", scale=8, border=2)
        pm = QPixmap()
        pm.loadFromData(buf.getvalue(), "PNG")
        return pm.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)
    except Exception:
        # segno 미설치·인코딩 실패 — QR 없이도 주소 안내는 되게 조용히 넘어간다
        return None


class SharePanel(QFrame):
    """폰 공유 QR 카드 (① WiFi 접속 → ② 다운로드 목록).

    AP(bdt-share)가 떠 있으면 두 단계, 사무실 WiFi 등에선 ②만 보인다. 어느
    망도 없으면 카드 전체가 숨는다 — 없는 망에 붙으라고 안내할 수는 없다.
    상태가 바뀔 때마다 state_changed(보임여부) 를 낸다 (시작 화면이 '네트워크
    없음' 안내를 대신 띄우는 데 쓴다). 성적서 화면은 이 신호를 무시한다.
    """

    state_changed = pyqtSignal(bool)

    def __init__(self, parent=None, poll=True, wide=False):
        super().__init__(parent)
        # wide=False(기본, 성적서 화면): A4 지면 옆 좁은 카드에 두 QR 을 세로로
        # 쌓는다. wide=True(시작 화면 '이전 보고서'): 화면 전체 폭을 써서 두
        # QR 을 좌우로 크게 벌린다 — 폰으로 한쪽을 찍을 때 다른 QR 이 프레임에
        # 같이 잡혀 겹치지 않게. 갱신·상태 로직(refresh)은 두 모드가 공유하고,
        # 배치와 QR 크기만 다르다.
        self._wide = wide
        self._qr_size = 260 if wide else 120

        # 패널 제목 — 이 영역이 '폰으로 받는 곳'임을 먼저 알린다.
        title = QLabel("폰으로 성적서 받기")
        title.setObjectName("Section")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rule = QFrame()
        rule.setObjectName("SectionRule")

        # 두 단계: ① WiFi 접속 QR(스캔하면 단말 AP 에 붙는다) → ② 목록 주소
        # QR(붙은 뒤 스캔하면 성적서 목록이 열린다). 캡티브 자동 열림에
        # 기대지 않고 두 QR 로 명시적으로 안내한다.
        self._wifi_block, self.wifi_cap, self.wifi_qr, self.wifi_sub = \
            self._qr_step("① 이 QR 로 단말 WiFi 접속")
        self._url_block, self.url_cap, self.url_qr, self.url_sub = \
            self._qr_step("② 접속 후 이 QR 로 목록 열기")

        # 위·아래 사용법 — 각 QR 캡션은 '무엇을 스캔하나'만 말한다. 이 두 줄은
        # 전체 흐름(폰 카메라로 시작 → 목록에서 받기로 끝)을 감싸 안내한다.
        top_help = QLabel("폰 카메라 앱을 열어\nQR 을 비추세요")
        top_help.setObjectName("Hint")
        top_help.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top_help.setWordWrap(True)
        bottom_help = QLabel("성적서 목록에서 '받기' 를 누르면 폰에 저장됩니다")
        bottom_help.setObjectName("Hint")
        bottom_help.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bottom_help.setWordWrap(True)

        if wide:
            # 좌우로 크게 벌린 배치. 카드 테두리 없이 전체 폭을 쓴다.
            outer = QVBoxLayout(self)
            outer.setContentsMargins(0, 0, 0, 0)
            outer.setSpacing(16)
            outer.addWidget(title)
            outer.addWidget(top_help)
            row = QHBoxLayout()
            row.setSpacing(0)
            row.addStretch(2)
            row.addWidget(self._wifi_block)
            # 두 QR 사이를 크게 벌린다 — 폰 카메라 한 프레임에 둘이 같이
            # 잡혀 겹치지 않게 (사용자 요청의 핵심).
            row.addStretch(3)
            row.addWidget(self._url_block)
            row.addStretch(2)
            outer.addLayout(row, 1)
            outer.addWidget(bottom_help)
        else:
            self.setObjectName("Card")
            self.setFixedWidth(210)
            lay = QVBoxLayout(self)
            lay.setContentsMargins(14, 16, 14, 16)
            lay.setSpacing(12)
            lay.addWidget(title)
            lay.addWidget(rule)
            lay.addWidget(top_help)
            lay.addStretch(1)
            lay.addWidget(self._wifi_block)
            # 두 QR 사이를 넉넉히 벌린다 — 붙어 있으면 폰으로 찍을 때 옆 QR 이
            # 같이 잡혀 어느 걸 스캔하는지 헷갈린다.
            lay.addStretch(1)
            lay.addWidget(self._url_block)
            lay.addStretch(1)
            lay.addWidget(bottom_help)

        self.setVisible(False)
        self._wifi_shown = None
        self._url_shown = None
        # QR 을 띄울 수 있는지의 '논리 상태'. isVisible() 은 위젯이 화면에
        # 실제로 붙기 전엔 False 라 믿을 수 없다 — 아직 안 뜬 페이지가 초기
        # 상태를 물을 때 이 값을 본다.
        self.available = False

        # 자체 폴링 — 화면이 떠 있는 동안 AP 를 켜거나 폰이 붙어도 반영되게.
        # poll=False 로 만들면 refresh() 를 바깥에서 불러야 한다 (테스트용).
        if poll:
            self._poll = QTimer(self)
            self._poll.timeout.connect(self.refresh)
            self._poll.start(2000)
            self.refresh()

    # ── QR 한 단계 (캡션 + QR 그림 + 아래 설명) ────────────────
    def _qr_step(self, caption_text):
        cap = QLabel(caption_text)
        cap.setObjectName("StatName")
        cap.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cap.setWordWrap(True)
        img = QLabel()
        img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub = QLabel()
        sub.setObjectName("Hint")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setWordWrap(True)
        sub.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        block = QWidget()
        v = QVBoxLayout(block)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)
        v.addWidget(cap)
        v.addWidget(img)
        v.addWidget(sub)
        return block, cap, img, sub

    def _set_qr(self, img_label, sub_label, payload, sub_text, size=120):
        pixmap = qr_pixmap(payload, size)
        if pixmap is None:
            img_label.setText("(QR 없음)")   # segno 미설치 폴백
        else:
            img_label.setPixmap(pixmap)
        sub_label.setText(sub_text)

    def refresh(self):
        """AP·네트워크 상태에 맞춰 공유 QR 을 갱신한다.

        2초마다 GUI 스레드에서 돌므로 nmcli 서브프로세스를 아껴야 한다 —
        NetworkManager 가 느린 순간엔 호출당 수 초씩 막혀 화면이 버벅인다.
        정상 상태(변화 없음)에선 AP 유무 확인(ap_ip) 한 번만 부르고,
        자격증명·SSID 조회는 QR 을 실제로 새로 그릴 때만 한다.
        """
        from bdt import web
        # AP(bdt-share)가 '실제로 떠 있는지'는 IP 유무로 본다. 연결 설정만 있고
        # 안 떠 있으면 접속 QR 을 보여줘선 안 된다 — 없는 망에 붙으라고
        # 안내하는 꼴이 된다.
        ap = web.ap_ip()                    # 폴링당 유일한 상시 nmcli 호출
        ip = ap or web.lan_ip()             # lan_ip 은 소켓 조회라 싸다
        if not ip:                          # 네트워크·AP 둘 다 없음
            self.setVisible(False)
            self._wifi_shown = self._url_shown = None
            self._emit_state(False)
            return
        ap_up = ap is not None
        url = f"http://{ip}:{web.PORT}/"

        # ① WiFi 접속 QR — AP 가 실제로 떠 있을 때만. 자격증명(nmcli)은 QR 이
        # 아직 안 그려졌을 때만 읽는다 (SSID·비번은 세션 중 바뀌지 않는다 —
        # 바꾸는 경로는 setup-hotspot.sh 뿐이고 그때 AP 가 재시작돼 여기로
        # 다시 온다).
        if ap_up:
            if self._wifi_shown is None:
                cred = web.ap_credentials()
                wifi = web.wifi_qr_payload(cred)
                if wifi and cred:
                    # 스캔하면 WiFi 자동 연결(비번 QR 에 박힘).
                    # 아래 SSID·비번은 QR 이 안 될 때 손으로 연결하는 예비 정보.
                    self._set_qr(self.wifi_qr, self.wifi_sub, wifi,
                                 f"스캔하면 WiFi 자동 접속\n"
                                 f"(수동: {cred[0]} / {cred[1]})",
                                 size=self._qr_size)
                    self._wifi_shown = wifi
                    # ① 이 이제 막 생겼다 — ② 캡션이 "1번으로…" 를 가리켜도
                    # 되도록 아래 갱신 블록을 강제로 태운다 (nmcli 추가 호출
                    # 없음 — ap_up 경로의 캡션은 고정 문구다).
                    self._url_shown = None
            self._wifi_block.setVisible(self._wifi_shown is not None)
        else:
            self._wifi_block.setVisible(False)
            self._wifi_shown = None

        # ② 다운로드 주소 QR — 주소가 바뀔 때만(첫 표시·망 전환) 다시 그린다.
        # 캡션도 이때만 정한다: ap_up 이 바뀌면 IP(10.42.0.1 ↔ LAN)가 바뀌어
        # 반드시 여기로 들어오므로 폴링마다 SSID(nmcli)를 조회할 필요가 없다.
        if url != self._url_shown:
            #   AP 있음: 폰이 AP 에 붙은 뒤 ① 자동 열림이 안 될 때의 폴백.
            #   AP 없음: 폰이 '이미 같은 WiFi 에 있어야' 열린다 — 그렇지 않으면
            #            스캔해도 접속이 안 되므로 전제 조건을 분명히 알린다.
            if ap_up and self._wifi_shown is not None:
                self.url_cap.setText("② 접속 후 이 QR 로 목록 열기")
            elif ap_up:
                # AP 는 떠 있는데 자격증명을 못 읽어 ① QR 이 없다 (드묾) —
                # 존재하지 않는 1번을 가리키는 캡션은 헷갈린다.
                self.url_cap.setText("단말 WiFi 에 연결한 폰에서 스캔")
            else:
                # 폰이 어느 망에 붙어야 하는지 실제 SSID 로 알린다
                ssid = web.lan_ssid()
                if ssid:
                    self.url_cap.setText(f"'{ssid}' WiFi 의 폰에서만")
                else:
                    self.url_cap.setText("같은 WiFi 에 연결된 폰에서만")
            self._set_qr(self.url_qr, self.url_sub, url,
                         url.replace("http://", "").rstrip("/"),
                         size=self._qr_size)
            self._url_shown = url
        self.setVisible(True)
        self._emit_state(True)

    def _emit_state(self, visible):
        """보임 여부가 바뀐 순간에만 신호를 낸다 (폴링마다 반복 방출 방지)."""
        if visible != self.available:
            self.available = visible
            self.state_changed.emit(visible)
