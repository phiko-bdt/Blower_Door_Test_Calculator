"""성적서 로컬 웹 공유 — 같은 네트워크의 폰·노트북으로 주고받는다.

`python3 -m bdt.web` 로 실행하며, systemd 유닛 bdt-web.service 가 상시 띄운다.
성적서 화면의 QR 코드가 이 서버 주소(http://<Pi IP>:8080)를 담아, 작업자가
폰으로 스캔하면 바로 목록을 열어 성적서를 내려받는다. 폰에서 파일을 올릴
수도 있다(받은파일 폴더).

**계정·비밀번호·클라우드가 없다.** Pi 와 같은 네트워크(현장 WiFi·폰 핫스팟)
에만 있으면 된다. 그만큼 같은 네트워크의 누구나 접근할 수 있으니 — 성적서에
의뢰자 이름·연락처가 실린다 — 신뢰할 수 있는 망에서만 쓴다. USB 복사를
대체가 아니라 보완으로 둔다 (현장에 망이 늘 있는 건 아니다).

파일 경로는 반드시 보관 폴더 안으로 가둔다 (../ 로 시스템 파일을 못 읽게).
"""

import os
import socket
import html
import subprocess
from datetime import datetime

from flask import (Flask, send_from_directory, request, redirect,
                   abort, Response)

from bdt import paths

PORT = 8080
# 이 단말이 띄우는 AP(핫스팟) NetworkManager 연결 이름. 전용 USB WiFi(wlan1)
# 에 고정돼 상시 방송한다 — 폰이 여기 붙어 성적서를 받는다. wlan0(내장)은
# 인터넷용으로 따로 둔다. 설정: nmcli con(bdt-share), ipv4.method shared →
# 10.42.0.1 + DHCP.
AP_CON = "bdt-share"
# 폰에서 올린 파일을 받는 곳 (바탕화면). 성적서 보관함과 나란히 둔다.
UPLOAD_DIR = os.path.join(paths.DESKTOP_DIR, "받은파일")

app = Flask(__name__)
# 성적서 PDF 는 작아도 폰 사진 업로드는 클 수 있어 여유를 둔다 (25 MB).
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024


def lan_ip():
    """이 기기의 LAN IP. 게이트웨이로 향하는 소켓의 로컬 주소로 알아낸다.

    실제로 데이터를 보내지 않는다(UDP connect 는 라우팅만 정한다). 네트워크가
    없으면 None.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def _nmcli(*args):
    """nmcli 를 조용히 실행해 표준출력을 준다. 실패하면 빈 문자열."""
    try:
        r = subprocess.run(("nmcli",) + args, capture_output=True,
                           text=True, timeout=4)
        return r.stdout if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def ap_ip():
    """상시 AP(bdt-share)의 IP. 보통 10.42.0.1. AP 가 안 떠 있으면 None.

    폰은 AP 망(10.42.0.x)에 붙으므로, 다운로드 주소는 반드시 이 IP 여야 한다
    — 인터넷용 wlan0 의 IP(예: 192.168.x)로는 폰이 못 온다.
    """
    for line in _nmcli("-g", "IP4.ADDRESS", "con", "show", AP_CON).splitlines():
        ip = line.split("/")[0].strip()
        if ip:
            return ip
    return None


def ap_credentials():
    """(SSID, 비밀번호) — WiFi 접속 QR 에 쓴다. NetworkManager 에서 그대로 읽어
    AP 설정과 QR 이 어긋나지 않게 한다. 설정이 없으면 None."""
    out = _nmcli("-s", "-g",
                 "802-11-wireless.ssid,802-11-wireless-security.psk",
                 "con", "show", AP_CON)
    lines = out.splitlines()
    if len(lines) >= 2 and lines[0].strip():
        return lines[0].strip(), lines[1].strip()
    return None


def wifi_qr_payload():
    """폰이 스캔하면 AP 에 바로 접속되는 WiFi QR 문자열. 설정 없으면 None.

    형식 'WIFI:T:WPA;S:<ssid>;P:<pw>;;' — iOS·안드로이드 카메라가 인식한다.
    값 안의 특수문자(\\ ; , : ")는 백슬래시로 escape 한다 (WIFI QR 규격).
    """
    cred = ap_credentials()
    if not cred:
        return None
    def esc(v):
        for ch in '\\;,:"':
            v = v.replace(ch, "\\" + ch)
        return v
    ssid, pw = cred
    return f"WIFI:T:WPA;S:{esc(ssid)};P:{esc(pw)};;"


def base_url():
    """폰이 접속할 다운로드 주소. AP IP 를 우선한다 (폰이 붙는 망).

    AP 가 없으면 일반 LAN IP 로 폴백한다 (사무실 WiFi 등에서 쓸 때)."""
    ip = ap_ip() or lan_ip()
    return f"http://{ip}:{PORT}/" if ip else None


def _archived_reports():
    """보관된 성적서 목록 — (상대경로, 파일명, 수정시각) 최신순."""
    root = paths.REPORT_ARCHIVE_DIR
    items = []
    for dirpath, _, files in os.walk(root):
        for name in files:
            if not name.lower().endswith(".pdf"):
                continue
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root)
            try:
                mtime = os.path.getmtime(full)
            except OSError:
                mtime = 0
            items.append((rel, name, mtime))
    items.sort(key=lambda x: x[2], reverse=True)
    return items


@app.route("/")
def index():
    rows = []
    for rel, name, mtime in _archived_reports():
        when = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M") if mtime else ""
        href = "/download/" + rel.replace(os.sep, "/")
        rows.append(
            f'<li><a href="{html.escape(href)}">{html.escape(name)}</a>'
            f'<span class="when">{when}</span></li>')
    listing = "\n".join(rows) or '<li class="empty">아직 발행된 성적서가 없습니다.</li>'
    return Response(_PAGE.format(count=len(rows), listing=listing), mimetype="text/html")


@app.route("/download/<path:relpath>")
def download(relpath):
    # send_from_directory 가 ../ 탈출을 막지만, 명시적으로 보관 폴더 안에
    # 있는지 한 번 더 확인한다.
    root = os.path.realpath(paths.REPORT_ARCHIVE_DIR)
    target = os.path.realpath(os.path.join(root, relpath))
    if os.path.commonpath([root, target]) != root or not os.path.isfile(target):
        abort(404)
    return send_from_directory(root, relpath, as_attachment=True)


@app.route("/upload", methods=["POST"])
def upload():
    f = request.files.get("file")
    if not f or not f.filename:
        return redirect("/")
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    # 파일명에서 경로 요소를 떼어내 보관 폴더 밖으로 못 나가게 한다.
    safe = paths._safe_name(os.path.basename(f.filename)) or "받은파일"
    dest = os.path.join(UPLOAD_DIR, safe)
    stem, ext = os.path.splitext(dest)
    n = 2
    while os.path.exists(dest):
        dest = f"{stem}({n}){ext}"
        n += 1
    f.save(dest)
    return redirect("/")


_PAGE = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>기밀성능 시험 성적서</title>
<style>
  body {{ font-family: -apple-system, "Noto Sans KR", sans-serif; margin: 0;
         background: #f4f6f9; color: #1c2430; }}
  header {{ background: #1f5fa8; color: #fff; padding: 18px 20px; }}
  header h1 {{ margin: 0; font-size: 18px; }}
  header p {{ margin: 4px 0 0; font-size: 13px; opacity: .85; }}
  main {{ max-width: 720px; margin: 0 auto; padding: 16px; }}
  ul {{ list-style: none; padding: 0; margin: 0; }}
  li {{ background: #fff; border: 1px solid #e4e8ee; border-radius: 8px;
        margin-bottom: 8px; padding: 14px 16px; display: flex;
        justify-content: space-between; align-items: center; }}
  li a {{ color: #1f5fa8; text-decoration: none; font-weight: bold;
          word-break: break-all; }}
  .when {{ color: #5b6672; font-size: 12px; margin-left: 12px;
           white-space: nowrap; }}
  .empty {{ color: #5b6672; justify-content: center; }}
  form {{ background: #fff; border: 1px dashed #ccd3dc; border-radius: 8px;
          padding: 16px; margin-top: 16px; text-align: center; }}
  button {{ background: #1f5fa8; color: #fff; border: none; border-radius: 8px;
            padding: 10px 20px; font-size: 15px; font-weight: bold; }}
</style></head>
<body>
<header><h1>기밀성능 시험 성적서</h1>
<p>성적서 {count}건 · 아래에서 내려받으세요</p></header>
<main>
<ul>
{listing}
</ul>
<form action="/upload" method="post" enctype="multipart/form-data">
  <p>파일 보내기 (사진·서명 등 → 단말 바탕화면 '받은파일')</p>
  <input type="file" name="file" required>
  <button type="submit">올리기</button>
</form>
</main>
</body></html>
"""


def main():
    url = base_url()
    if url:
        print(f"성적서 웹 공유 시작: {url} (같은 네트워크에서 접속)")
    else:
        print("네트워크가 없어 아직 접속 주소가 없습니다 — 연결되면 자동으로 열립니다.")
    # 0.0.0.0 = 모든 인터페이스. 같은 LAN 의 폰이 붙을 수 있어야 한다.
    # 개발 서버지만 동시 접속 몇 대 수준이라 충분하다.
    app.run(host="0.0.0.0", port=PORT, threaded=True)


if __name__ == "__main__":
    main()
