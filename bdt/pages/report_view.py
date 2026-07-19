"""성적서 화면 — 발행한 PDF 를 앱 안에서 그대로 보여준다.

예전엔 성적서를 외부 뷰어(evince)로 띄웠다. 앱이 전체화면인 현장 단말에서
남의 창이 위를 덮고, 작업자가 그 창을 닫아야 앱으로 돌아올 수 있었다.
이제 시험의 마지막 화면까지 앱 안에 둔다.

PDF 를 직접 그리지 않고 pdftoppm 이 렌더한 PNG 한 장을 띄운다. 성적서는
1페이지 고정이고 poppler 는 이미 깔려 있어(성적서 검증에 쓴다) 의존성이
늘지 않는다. 렌더는 tasks.reporting 이 백그라운드에서 미리 해 둔다 —
여기서 하면 화면 전환이 1초쯤 멈춘다.

PDF 파일 자체는 예전과 같은 자리에 그대로 저장된다 (report.pdf).
"""

import os
import shutil

from PyQt6.QtWidgets import (
    QWidget,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QFrame,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QPixmap

from bdt import paths
from bdt.widgets import alert


def _qr_pixmap(url, size=150):
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


class ReportPage(QWidget):
    """성적서 이미지 + 화면맞춤/100% 전환 + 새 시험."""

    restart = pyqtSignal()  # 새 시험 → 조건 입력부터 다시

    def __init__(self, png_path=None, pdf_path=None, archive_path=None):
        super().__init__()
        self._png_path = png_path or paths.REPORT_PNG
        self._pdf_path = pdf_path or paths.REPORT_PDF
        self._archive_path = archive_path
        self._pixmap = QPixmap(self._png_path)
        self._fit = True   # 처음엔 한 장이 다 보이게

        # 페이지 제목을 따로 두지 않는다. 성적서 지면 자체가 "기밀성능 시험
        # 성적서" 라는 제목을 크게 달고 있어 중복이고, 그 100px 을 성적서에
        # 주는 편이 낫다 (A4 세로를 800px 화면에 넣으면 여유가 없다).
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 14, 40, 14)
        root.setSpacing(10)

        # ── 성적서 이미지(좌) + 폰 공유 QR(우) ─────────────────
        # A4 세로 지면이라 가로로 여백이 남는다 — 그 오른쪽에 QR 을 둔다.
        self.sheet = QLabel()
        self.sheet.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll.setWidget(self.sheet)

        content = QHBoxLayout()
        content.setSpacing(16)
        content.addWidget(self.scroll, 1)
        content.addWidget(self._qr_panel())
        root.addLayout(content, 1)

        # ── 하단 줄 ────────────────────────────────────────────
        self.zoom_button = QPushButton("100% 로 보기")
        self.zoom_button.setObjectName("Secondary")
        self.zoom_button.setMinimumWidth(150)
        self.zoom_button.clicked.connect(self._toggle_zoom)

        # 저장 위치 — 작업자가 성적서를 어디서 찾는지가 이 화면의 핵심 정보다.
        # 예전엔 회색 힌트 한 줄이라 눈에 안 띄었다. 캡션(accent) + 경로(진한
        # 잉크)로 두 줄로 또렷하게 보여준다.
        saved_caption = QLabel("성적서 저장 위치")
        saved_caption.setObjectName("StatName")
        self.saved_label = QLabel(self._where_saved())
        self.saved_label.setObjectName("SavedPath")
        self.saved_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        saved_block = QVBoxLayout()
        saved_block.setSpacing(1)
        saved_block.addWidget(saved_caption)
        saved_block.addWidget(self.saved_label)

        # USB 복사 — USB 저장소가 꽂혀 있을 때만 뜬다. 성적서 화면이 떠 있는
        # 동안 꽂아도 나타나게 주기적으로 확인한다.
        self.usb_button = QPushButton("USB로 복사")
        self.usb_button.setObjectName("Secondary")
        self.usb_button.setMinimumWidth(150)
        self.usb_button.clicked.connect(self._copy_to_usb)
        self.usb_button.setVisible(False)

        restart_button = QPushButton("새 시험 시작")
        restart_button.setMinimumWidth(180)
        restart_button.clicked.connect(self.restart.emit)

        bottom = QHBoxLayout()
        bottom.setSpacing(16)
        bottom.addWidget(self.zoom_button)
        bottom.addLayout(saved_block)
        bottom.addStretch(1)
        bottom.addWidget(self.usb_button)
        bottom.addWidget(restart_button)
        root.addLayout(bottom)

        # PDF 가 없으면(렌더 실패해도 PDF 는 있어야 정상) USB 복사도 막는다
        self._can_copy = os.path.exists(self._pdf_path)
        # USB·네트워크 QR 을 2초마다 갱신 (화면 떠 있는 동안 꽂거나 연결해도
        # 반영되게). 한 타이머로 둘 다 본다.
        self._poll = QTimer(self)
        self._poll.timeout.connect(self._refresh_devices)
        self._poll.start(2000)
        self._refresh_devices()

        if self._pixmap.isNull():
            # 렌더가 없거나 깨졌다 — 성적서 PDF 는 만들어졌으므로 시험은
            # 실패가 아니다. 화면에서만 못 보여준다는 것을 분명히 알린다.
            self.sheet.setText(
                "성적서를 화면에 표시하지 못했습니다.\n\n"
                f"PDF 파일은 저장돼 있습니다: {self._pdf_path}")
            self.sheet.setObjectName("Message")
            self.zoom_button.setEnabled(False)

    def _where_saved(self):
        """성적서를 어디서 찾는지 — 바탕화면 보관함 기준으로 알린다.

        작업자가 찾는 건 저장소 안의 report.pdf 가 아니라 바탕화면의 사본이다
        (report.pdf 는 다음 시험이 덮어쓴다). 폴더 구분자를 ' › ' 로 바꿔
        '바탕화면 › 결과보고서 › …' 처럼 어디를 열어야 하는지 바로 읽히게 한다.
        """
        if not self._archive_path:
            # 보관 실패 폴백 — 최소한 PDF 원본 자리라도 알린다
            return self._pdf_path
        try:
            rel = os.path.relpath(self._archive_path, paths.DESKTOP_DIR)
            crumbs = ["바탕화면"] + rel.split(os.sep)
        except ValueError:
            crumbs = self._archive_path.split(os.sep)
        # NanumSquare 에 '›'(U+203A) 글리프가 없어 공백으로 렌더된다 — '/' 사용
        return "  /  ".join(crumbs)

    # ── 폰 공유 QR (① WiFi 연결 → ② 스캔해 받기) ─────────────
    def _qr_step(self, caption_text):
        """QR 한 단계 (캡션 + QR 그림 + 아래 설명). (블록, 이미지, 설명) 반환."""
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
        return block, img, sub

    def _qr_panel(self):
        """A4 지면 오른쪽 여백의 폰 공유 카드.

        ① 폰을 단말 WiFi 에 연결(WiFi QR) → ② 성적서 다운로드(주소 QR).
        AP(bdt-share)가 떠 있으면 두 단계, 사무실 WiFi 등에선 ②만 보인다.
        """
        # 패널 제목 — 이 영역이 '폰으로 받는 곳'임을 먼저 알린다. 예전엔 곧바로
        # '① …' 로 시작해 무엇을 하는 자리인지 안 잡혔다.
        title = QLabel("폰으로 성적서 받기")
        title.setObjectName("Section")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rule = QFrame()
        rule.setObjectName("SectionRule")

        self._wifi_block, self.wifi_qr, self.wifi_sub = self._qr_step(
            "① 폰 카메라로 스캔 → WiFi 자동 연결")
        self._url_block, self.url_qr, self.url_sub = self._qr_step(
            "② 연결됐으면 스캔 → 성적서 받기")

        self.qr_panel = QFrame()
        self.qr_panel.setObjectName("Card")
        self.qr_panel.setFixedWidth(210)
        lay = QVBoxLayout(self.qr_panel)
        lay.setContentsMargins(14, 16, 14, 16)
        lay.setSpacing(12)
        lay.addWidget(title)
        lay.addWidget(rule)
        lay.addStretch(1)
        lay.addWidget(self._wifi_block)
        lay.addWidget(self._url_block)
        lay.addStretch(1)
        self.qr_panel.setVisible(False)
        self._wifi_shown = None
        self._url_shown = None
        return self.qr_panel

    def _set_qr(self, img_label, sub_label, payload, sub_text, size=120):
        pixmap = _qr_pixmap(payload, size)
        if pixmap is None:
            img_label.setText("(QR 없음)")   # segno 미설치 폴백
        else:
            img_label.setPixmap(pixmap)
        sub_label.setText(sub_text)

    def _refresh_qr(self):
        """AP·네트워크 상태에 맞춰 공유 QR 을 갱신한다."""
        from bdt import web
        url = web.base_url()
        if not url:                       # 네트워크·AP 둘 다 없음
            self.qr_panel.setVisible(False)
            self._wifi_shown = self._url_shown = None
            return

        # ① WiFi 접속 QR — AP(bdt-share)가 떠 있을 때만
        wifi = web.wifi_qr_payload()
        cred = web.ap_credentials() if wifi else None
        if wifi and cred:
            self._wifi_block.setVisible(True)
            if wifi != self._wifi_shown:
                # 비밀번호가 QR 에 박혀 있어 스캔하면 바로 붙는다. 아래 SSID·
                # 비번은 QR 이 안 될 때 손으로 연결하는 예비 정보임을 밝힌다.
                self._set_qr(self.wifi_qr, self.wifi_sub, wifi,
                             f"스캔하면 자동 연결\n(수동: {cred[0]} / {cred[1]})")
                self._wifi_shown = wifi
        else:
            self._wifi_block.setVisible(False)
            self._wifi_shown = None

        # ② 다운로드 주소 QR
        if url != self._url_shown:
            self._set_qr(self.url_qr, self.url_sub, url,
                         url.replace("http://", "").rstrip("/"))
            self._url_shown = url
        self.qr_panel.setVisible(True)

    # ── USB 복사 ──────────────────────────────────────────────
    def _refresh_devices(self):
        """USB·네트워크 상태를 확인해 관련 UI 를 켜고 끈다 (2초마다)."""
        self._refresh_usb()
        self._refresh_qr()

    def _refresh_usb(self):
        """USB 유무를 확인해 복사 버튼을 켜고 끈다."""
        self._usb = paths.usb_mounts() if self._can_copy else []
        self.usb_button.setVisible(bool(self._usb))

    def _copy_dest_name(self):
        """USB 에 남길 파일 이름 — 보관본과 같은 뜻있는 이름."""
        if self._archive_path:
            return os.path.basename(self._archive_path)
        return "기밀성능시험_성적서.pdf"

    def _copy_to_usb(self):
        """성적서 PDF 를 꽂힌 USB(들)에 복사한다.

        같은 이름이 이미 있으면 덮지 않고 번호를 붙인다 (보관함과 같은 방침).
        복사가 끝났거나 실패했음을 알린다 — USB 는 뽑으면 그만이라 결과를
        분명히 알려야 작업자가 안심하고 뽑는다.
        """
        mounts = paths.usb_mounts()
        if not mounts:
            # 버튼을 누르는 사이 뽑혔다
            self._refresh_usb()
            alert(self, "USB 없음", "USB 저장소가 연결돼 있지 않습니다.")
            return

        name = self._copy_dest_name()
        copied, failed = [], []
        for mount in mounts:
            dest = os.path.join(mount, name)
            stem, ext = os.path.splitext(dest)
            n = 2
            while os.path.exists(dest):
                dest = f"{stem}({n}){ext}"
                n += 1
            try:
                shutil.copy2(self._pdf_path, dest)
                # 뽑을 때 파일이 깨지지 않게 캐시를 디스크로 내린다
                os.sync()
                copied.append(os.path.basename(mount))
            except OSError as exc:
                failed.append(f"{os.path.basename(mount)} ({exc})")

        if copied and not failed:
            where = ", ".join(copied)
            alert(self, "USB 복사 완료",
                  f"성적서를 USB 에 복사했습니다.\n\n"
                  f"저장 위치: {where}\n파일 이름: {name}\n\n"
                  "USB 를 안전하게 뽑아도 됩니다.")
        elif copied and failed:
            alert(self, "일부만 복사됨",
                  f"복사됨: {', '.join(copied)}\n실패: {', '.join(failed)}")
        else:
            alert(self, "USB 복사 실패",
                  "성적서를 USB 에 복사하지 못했습니다.\n\n"
                  f"{', '.join(failed)}\n\n"
                  "USB 가 쓰기 금지(잠금)이거나 공간이 부족할 수 있습니다.")

    # ── 확대 ──────────────────────────────────────────────────
    def _toggle_zoom(self):
        self._fit = not self._fit
        self.zoom_button.setText("100% 로 보기" if self._fit else "화면에 맞추기")
        self._render()

    def _render(self):
        """현재 모드에 맞춰 이미지를 그린다.

        렌더는 300dpi 라 화면보다 훨씬 크다. '화면맞춤'은 뷰포트에 맞춰 줄이고,
        '100%'는 A4 를 원래 크기(96dpi 환산)로 보여준다 — 표의 작은 글씨를
        확인할 때 쓴다.
        """
        if self._pixmap.isNull():
            return
        if self._fit:
            size = self.scroll.viewport().size()
            scaled = self._pixmap.scaled(
                size, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
        else:
            # 300dpi 렌더 → 96dpi 화면 크기로 (약 1/3)
            scaled = self._pixmap.scaledToWidth(
                int(self._pixmap.width() * 96 / 300),
                Qt.TransformationMode.SmoothTransformation)
        self.sheet.setPixmap(scaled)
        self.sheet.resize(scaled.size())

    def resizeEvent(self, event):
        # 화면맞춤일 때만 창 크기를 따라간다 (100% 는 고정 배율이 의미다)
        super().resizeEvent(event)
        if self._fit:
            self._render()

    def showEvent(self, event):
        super().showEvent(event)
        self._render()
