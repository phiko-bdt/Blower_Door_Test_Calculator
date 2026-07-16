#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""기밀성능 시험 성적서를 HTML 로 그린 뒤 chromium 으로 A4 PDF 로 만든다.

기존 xlsx 템플릿(report_template.xlsx)의 정보 구성을 따르되, 전문적인
Blower Door Test 성적서처럼 보이도록 미니멀하게 재디자인했다.
"""

import os
import base64
import html
import shutil
import subprocess


# ── 데이터 포맷 ─────────────────────────────────────────────
def _num(value, digits=2):
    """숫자는 자리수 맞춰, 없거나 빈 값은 '–' 로."""
    if value is None or value == "" or value == "-":
        return "–"
    try:
        return f"{float(value):,.{digits}f}"
    except (ValueError, TypeError):
        return html.escape(str(value))


def _text(value):
    value = "" if value is None else str(value).strip()
    return html.escape(value) if value else "–"


def _data_uri(path, mime):
    with open(path, "rb") as f:
        return f"data:{mime};base64," + base64.b64encode(f.read()).decode()


# ── HTML 생성 ───────────────────────────────────────────────
def build_html(conditions, report, graph_path=None, font_path=None):
    has_dep = bool(conditions.get("depressurization"))
    has_pre = bool(conditions.get("pressurization"))

    def pick(metric):
        """대표값: 감·가압 모두면 평균, 하나면 그 값."""
        if has_dep and has_pre and f"{metric}_avg" in report:
            return report.get(f"{metric}_avg")
        if has_dep:
            return report.get(f"{metric}-")
        return report.get(f"{metric}+")

    # 시험 종류 라벨
    kinds = []
    if has_dep:
        kinds.append("감압")
    if has_pre:
        kinds.append("가압")
    kind_label = " · ".join(kinds) if kinds else "–"

    # 대표 지표 3종
    kpis = [
        ("ACH50", _num(pick("ACH50")), "1/h", "시간당 공기교환횟수"),
        ("Q50", _num(pick("Q50"), 1), "㎥/h", "50 Pa 기준 누기량"),
        ("AL50", _num(pick("AL50"), 4), "㎡", "유효 누기면적"),
    ]

    # 상세표 행: (라벨, 감압, 가압, 단위)
    def row(metric, digits=2, unit=""):
        return (
            _num(report.get(f"{metric}-"), digits),
            _num(report.get(f"{metric}+"), digits),
            unit,
        )

    detail_rows = [
        ("Q50", "누기량", *row("Q50", 1, "㎥/h")),
        ("ACH50", "공기교환횟수", *row("ACH50", 2, "1/h")),
        ("AL50", "유효 누기면적", *row("AL50", 4, "㎡")),
        ("C0", "누기 계수 C", *row("C0", 2, "㎥/(h·Paⁿ)")),
        ("n", "기류 지수 n", *row("n", 3, "")),
        ("r2", "결정 계수 R²", _num(report.get("r^2-"), 4),
         _num(report.get("r^2+"), 4), ""),
    ]

    info_fields = [
        ("시험 목적", "purpose"),
        ("시험 위치", "location"),
        ("시험 방식", "method"),
        ("의뢰자", "requester"),
        ("설계자", "designer"),
        ("시험자", "tester"),
        ("시공자", "builder"),
        ("실내 체적", "interior volume"),
        ("연면적", "floor area"),
        ("구조", "structure"),
    ]

    # 리소스 임베드
    font_face = ""
    if font_path and os.path.exists(font_path):
        font_uri = _data_uri(font_path, "font/ttf")
        font_face = (
            "@font-face{font-family:'ReportKR';"
            f"src:url({font_uri}) format('truetype');"
            "font-weight:400 800;font-display:swap;}"
        )
    graph_img = ""
    if graph_path and os.path.exists(graph_path):
        graph_uri = _data_uri(graph_path, "image/png")
        graph_img = f'<img class="graph" src="{graph_uri}" alt="압력-유량 그래프">'

    # 표 행 HTML
    info_html = "".join(
        f'<div class="info-item"><span class="info-label">{_text(label)}</span>'
        f'<span class="info-value">{_text(conditions.get(key))}</span></div>'
        for label, key in info_fields
    )
    kpi_html = "".join(
        f'<div class="kpi"><div class="kpi-name">{name}</div>'
        f'<div class="kpi-value">{value}<span class="kpi-unit">{unit}</span></div>'
        f'<div class="kpi-desc">{desc}</div></div>'
        for name, value, unit, desc in kpis
    )
    detail_html = "".join(
        f'<tr><td class="metric">{label}</td>'
        f'<td class="dep">{dep}</td><td class="pre">{pre}</td>'
        f'<td class="unit">{unit or "–"}</td></tr>'
        for _key, label, dep, pre, unit in detail_rows
    )

    period = _text(conditions.get("test_period"))
    fan_cover = _text(conditions.get("fan_cover"))
    fan_count = _text(conditions.get("fan_count"))

    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<style>
{font_face}
:root{{
  --ink:#1c2430; --sub:#5b6672; --muted:#8a94a0;
  --line:#e4e8ee; --line2:#eef1f5;
  --accent:#1f5fa8; --accent-soft:#eef4fb; --surface:#ffffff;
}}
*{{margin:0;padding:0;box-sizing:border-box;}}
@page{{size:A4;margin:11mm 13mm;}}
html{{font-family:'ReportKR','Noto Sans CJK KR',sans-serif;color:var(--ink);
  font-size:9.5pt;line-height:1.4;-webkit-print-color-adjust:exact;print-color-adjust:exact;}}
.sheet{{max-width:184mm;margin:0 auto;}}

/* 헤더 */
.header{{display:flex;justify-content:space-between;align-items:flex-end;
  border-bottom:2.5px solid var(--accent);padding-bottom:8px;margin-bottom:4px;}}
.title{{font-size:19pt;font-weight:800;letter-spacing:-.5px;}}
.subtitle{{font-size:9pt;color:var(--sub);margin-top:1px;letter-spacing:.5px;}}
.standard{{text-align:right;font-size:8pt;color:var(--muted);}}
.standard b{{display:block;font-size:10pt;color:var(--accent);font-weight:700;}}
.meta-strip{{display:flex;gap:18px;font-size:8.5pt;color:var(--sub);
  padding:5px 0 0;margin-bottom:13px;}}
.meta-strip b{{color:var(--ink);font-weight:600;}}

/* 섹션 제목 */
.section-title{{font-size:8.5pt;font-weight:700;color:var(--accent);
  letter-spacing:.8px;margin:0 0 7px;
  display:flex;align-items:center;gap:8px;}}
.section-title::after{{content:"";flex:1;height:1px;background:var(--line2);}}

/* 시험 정보 */
.info-grid{{display:grid;grid-template-columns:1fr 1fr;gap:0 32px;margin-bottom:15px;}}
.info-item{{display:flex;justify-content:space-between;gap:12px;
  padding:4px 0;border-bottom:1px solid var(--line2);}}
.info-label{{color:var(--sub);font-size:8.5pt;flex-shrink:0;}}
.info-value{{font-weight:600;text-align:right;font-size:8.5pt;}}

/* KPI */
.kpi-row{{display:grid;grid-template-columns:repeat(3,1fr);gap:11px;margin-bottom:15px;}}
.kpi{{border:1px solid #d7dde5;border-radius:9px;
  padding:11px 14px;}}
.kpi-name{{font-size:8pt;font-weight:700;color:var(--accent);letter-spacing:.5px;}}
.kpi-value{{font-size:21pt;font-weight:800;line-height:1.1;margin-top:2px;letter-spacing:-1px;}}
.kpi-unit{{font-size:9pt;font-weight:600;color:var(--sub);margin-left:5px;letter-spacing:0;}}
.kpi-desc{{font-size:7.5pt;color:var(--muted);margin-top:1px;}}

/* 상세표 */
table{{width:100%;border-collapse:collapse;margin-bottom:15px;font-size:8.5pt;}}
thead th{{text-align:right;font-size:7.5pt;font-weight:700;color:var(--sub);
  text-transform:uppercase;letter-spacing:.6px;padding:0 0 6px;
  border-bottom:1.5px solid var(--ink);}}
thead th:first-child{{text-align:left;}}
tbody td{{padding:5px 0;border-bottom:1px solid var(--line2);
  text-align:right;font-variant-numeric:tabular-nums;}}
tbody td.metric{{text-align:left;font-weight:600;color:var(--ink);}}
tbody td.unit{{color:var(--muted);font-size:7.5pt;width:18%;}}
tbody td.dep,tbody td.pre{{color:var(--ink);}}

/* 그래프 */
.graph-wrap{{text-align:center;margin-bottom:6px;}}
.graph{{max-width:100%;max-height:72mm;object-fit:contain;}}

/* 푸터 */
.footer{{display:flex;justify-content:space-between;align-items:flex-end;
  padding-top:10px;border-top:1px solid var(--line2);
  font-size:7.5pt;color:var(--muted);}}
.sign{{text-align:right;}}
.sign-line{{display:inline-block;width:120px;border-bottom:1px solid var(--sub);
  margin-top:18px;}}
</style></head>
<body><div class="sheet">
  <div class="header">
    <div>
      <div class="title">기밀성능 시험 성적서</div>
      <div class="subtitle">Building Airtightness Test Report</div>
    </div>
    <div class="standard"><b>KS L ISO 9972</b>팬 가압법 (Fan pressurization method)</div>
  </div>
  <div class="meta-strip">
    <span>시험 종류 <b>{kind_label}</b></span>
    <span>시험 기간 <b>{period}</b></span>
  </div>

  <div class="section-title">시험 정보</div>
  <div class="info-grid">{info_html}</div>

  <div class="section-title">주요 결과 (50 Pa 기준)</div>
  <div class="kpi-row">{kpi_html}</div>

  <div class="section-title">상세 결과</div>
  <table>
    <thead><tr><th>항목</th><th>감압</th><th>가압</th><th>단위</th></tr></thead>
    <tbody>{detail_html}</tbody>
  </table>

  <div class="section-title">압력 – 유량 곡선</div>
  <div class="graph-wrap">{graph_img}</div>

  <div class="footer">
    <div>본 성적서는 KS L ISO 9972 절차에 따라 측정·산출되었습니다.</div>
  </div>
</div></body></html>"""


# ── PDF 렌더 ────────────────────────────────────────────────
def render_pdf(html_text, pdf_path, workdir=None):
    """HTML 문자열을 chromium headless 로 A4 PDF 로 변환한다.

    성공하면 pdf_path 를 반환하고, chromium 이 없으면 None 을 반환한다.
    """
    chromium = (shutil.which("chromium") or shutil.which("chromium-browser")
                or shutil.which("google-chrome") or shutil.which("chrome"))
    if not chromium:
        return None

    workdir = workdir or os.path.dirname(os.path.abspath(pdf_path)) or "."
    html_path = os.path.join(workdir, "_report.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_text)

    profile = os.path.join(workdir, "_chromium_profile")
    cmd = [
        chromium, "--headless=new", "--disable-gpu", "--no-sandbox",
        f"--user-data-dir={profile}",
        "--no-pdf-header-footer",
        f"--print-to-pdf={pdf_path}",
        "file://" + os.path.abspath(html_path),
    ]
    try:
        subprocess.run(cmd, check=True, timeout=120,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        print(f"chromium PDF 변환 오류: {exc}")
        return None
    finally:
        shutil.rmtree(profile, ignore_errors=True)
        try:
            os.remove(html_path)
        except OSError:
            pass
    return pdf_path if os.path.exists(pdf_path) else None


def make_report_pdf(conditions, report, pdf_path,
                    graph_path="graph.png", font_path="NanumSquare_acL.ttf",
                    workdir=None):
    """조건·결과 데이터로 HTML 성적서를 만들어 PDF 로 렌더한다."""
    html_text = build_html(conditions, report, graph_path, font_path)
    return render_pdf(html_text, pdf_path, workdir)
