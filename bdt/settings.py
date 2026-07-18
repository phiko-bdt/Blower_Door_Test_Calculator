"""시험 설정 — 기본값과 저장/불러오기.

현장마다 목표 압력·팬 특성이 달라질 수 있어, 예전에 코드에 박혀 있던 값들을
설정 화면에서 고칠 수 있게 모았다. 저장 위치는 저장소 루트의 settings.json
이고, 없거나 값이 빠져 있으면 아래 DEFAULTS 로 메운다.

설정을 읽는 쪽은 항상 `load()` 로 최신 값을 가져온다 (모듈 수준 상수로
캐시하지 않는다 — 설정 화면에서 바꾼 값이 다음 시험에 바로 먹어야 한다).

팬 보정식(duty→누기량)은 예전부터 fan_coefficients.json 에 따로 있었고
calculation.py 가 그 파일을 직접 읽는다. 파일을 옮기면 기존 데이터·스크립트가
깨지므로 그대로 두고, 설정 화면이 그 파일을 편집한다.
"""

import json
import os

from bdt import paths

SETTINGS_JSON = os.path.join(paths.ROOT, "settings.json")

DEFAULTS = {
    # ── 목표 압력 조절 (get_duty) ───────────────────────────
    # 측정 시작점으로 삼을 압력차. KS L ISO 9972 의 시험 압력 구간 안에서
    # 가장 높은 지점을 잡아, 여기서부터 duty 를 낮춰가며 측정한다.
    "target_pressure": 70.0,
    # 수렴 판정 허용 오차 = 목표의 몇 % 인가. 예전엔 target/10 으로 코드에
    # 박혀 있었다 (=10%). 목표를 60 으로 바꾸면 ±6 Pa 로 함께 움직인다.
    "tolerance_percent": 10.0,
    # 허용 오차 안에 이만큼 연속으로 머물러야 수렴으로 본다 (초).
    # 같은 시간을 실패 판정(팬이 한계에 붙은 채 오차가 남음)에도 쓴다.
    "hold_seconds": 10.0,
    # 시험을 진행할 수 있는 압력 상한. 팬을 최소로 낮춰도 이보다 높으면
    # 압력을 제어할 수 없으므로 시험 불가로 본다.
    "max_pressure": 100.0,
    # 조절 화면 압력·수렴 판정에 쓰는 이동평균 점수 (0.1초 간격 → 10점 ≈ 1초).
    # 크게 잡으면 매끄럽지만 불안정을 늦게 감지하고, 1 이면 평활 없이 원시값.
    "smooth_window": 10,

    # ── 지점 측정 (blower_door_test) ───────────────────────
    "measure_seconds": 10.0,      # 한 지점에서 압력을 평균낼 시간
    "settle_seconds_per_duty": 2.0,  # duty 1 당 안정화 대기 시간
    "num_points": 10,             # 측정 지점 개수
    # 이보다 낮은 압력의 측정점은 바람 노이즈가 지배해 신뢰도가 낮다.
    # 경고만 하고 회귀에는 포함한다 (제외하지 않기로 결정).
    "low_pressure_warn": 10.0,
}

# 화면에 보여줄 이름·단위·설명 (설정 페이지가 이 순서로 그린다).
# 설명은 명사로 끝나는 한 줄 — 설정 화면에서 두 줄로 넘어가면 항목 높이가
# 들쭉날쭉해지고 팬 보정식이 화면 밖으로 밀린다.
FIELDS = [
    ("target_pressure", "목표 압력", "Pa", "측정을 시작할 압력차"),
    ("tolerance_percent", "수렴 허용 오차", "%",
     "수렴 판정 폭 (70 Pa 의 10% → ±7 Pa)"),
    ("hold_seconds", "수렴 유지 시간", "초", "허용 오차 안에 머물 연속 시간"),
    ("max_pressure", "시험 가능 상한", "Pa", "넘으면 시험 불가로 판정"),
    ("smooth_window", "압력 평활 창", "점", "조절 압력·수렴 판정 이동평균 점수"),
    ("measure_seconds", "지점 측정 시간", "초", "측정 지점당 압력 평균 시간"),
    ("settle_seconds_per_duty", "안정화 대기", "초/duty",
     "duty 1 당 압력 안정화 대기"),
    ("num_points", "측정 지점 수", "개", "시작 압력에서 최저 지점까지 등분 수"),
    ("low_pressure_warn", "저압 경고 기준", "Pa", "경고를 표시할 압력"),
]

# 값 검증 규칙: (최소, 최대) — 벗어나면 설정 화면이 막는다
LIMITS = {
    "target_pressure": (10.0, 100.0),
    "tolerance_percent": (1.0, 50.0),
    "hold_seconds": (1.0, 120.0),
    "max_pressure": (10.0, 500.0),
    "smooth_window": (1, 60),
    "measure_seconds": (1.0, 120.0),
    "settle_seconds_per_duty": (0.0, 30.0),
    "num_points": (5, 30),
    "low_pressure_warn": (0.0, 50.0),
}

INTEGER_KEYS = {"num_points", "smooth_window"}


def load():
    """설정을 읽는다. 파일이 없거나 깨졌으면 기본값으로 메운다."""
    values = dict(DEFAULTS)
    if os.path.exists(SETTINGS_JSON):
        try:
            with open(SETTINGS_JSON, "r") as f:
                saved = json.load(f)
        except (json.JSONDecodeError, OSError):
            # 설정이 깨졌다고 시험을 못 하면 안 된다 — 기본값으로 진행한다
            return values
        if not isinstance(saved, dict):
            # 파싱은 됐지만 형식이 아니다 (예: 파일 내용이 숫자 하나).
            # 여기서 걸러야 아래 `in saved` 가 TypeError 로 터지지 않는다.
            return values
        for key in DEFAULTS:
            if key not in saved:
                continue
            try:
                value = int(saved[key]) if key in INTEGER_KEYS else float(saved[key])
            except (TypeError, ValueError):
                continue
            lo, hi = LIMITS[key]
            if lo <= value <= hi:
                values[key] = value
    return values


def validate(values):
    """설정값을 검증하고 정규화한 dict 를 돌려준다. 문제가 있으면 ValueError.

    저장과 분리해 둔 이유: 설정 화면은 측정 기준값과 팬 계수를 함께 저장하는데,
    앞의 것을 쓴 뒤 뒤의 것이 검증에 걸리면 절반만 저장된 채 "저장 실패"로
    보인다. 화면이 먼저 둘 다 검증하고 나서 쓰게 하려면 검증만 따로 필요하다.
    """
    # 빠진 키는 저장된 현재 값으로 메운다 (DEFAULTS 가 아니다 — 일부만 넘긴
    # 호출이 나머지를 조용히 기본값으로 되돌리면 현장 설정이 리셋된다).
    clean = load()
    for key in DEFAULTS:
        if key not in values:
            continue
        try:
            value = int(values[key]) if key in INTEGER_KEYS else float(values[key])
        except (TypeError, ValueError):
            raise ValueError(f"{key} 에 숫자가 아닌 값이 들어왔습니다: {values[key]!r}")
        lo, hi = LIMITS[key]
        if not (lo <= value <= hi):
            raise ValueError(f"{key} 는 {lo}~{hi} 범위여야 합니다 (받은 값: {value})")
        clean[key] = value

    # 항목별 범위만 봐서는 못 잡는 조합 — 시험 가능 상한이 목표보다 낮으면
    # 목표 압력에 정상적으로 도달한 시험까지 '시험 불가'가 된다.
    if clean["max_pressure"] <= clean["target_pressure"]:
        raise ValueError(
            f"시험 가능 상한({clean['max_pressure']:g} Pa)은 목표 압력"
            f"({clean['target_pressure']:g} Pa)보다 높아야 합니다.")
    return clean


def save(values):
    """설정을 저장한다 (알려진 키만, 검증을 통과한 값만)."""
    clean = validate(values)
    with open(SETTINGS_JSON, "w") as f:
        json.dump(clean, f, indent=4, ensure_ascii=False)
    return clean


def tolerance_pa(values=None):
    """수렴 허용 오차를 Pa 로 환산한다 (목표 × 비율)."""
    v = values or load()
    return v["target_pressure"] * v["tolerance_percent"] / 100.0


# ── 팬 보정식 (duty → 누기량) ─────────────────────────────────
# 파일 형식은 calculation.load_fan_coefficients 가 읽는 그대로 둔다.
# 설정 화면은 실제로 쓰는 커버("none")만 보여주지만, 저장할 때 나머지 커버
# 항목은 손대지 않고 그대로 남긴다 — 예전 데이터로 재계산할 여지를 남긴다.
FAN_COVER = "none"

# 방향 키 ↔ 화면 이름. 시험 종류와의 대응은 calculation.duty_to_flow 가 정한다
# (감압 = reverse, 가압 = forward). 현재 팬은 비리버서블이라 두 값이 같지만,
# 계수 파일 형식은 방향별로 나뉘어 있어 그대로 노출한다.
FAN_SIDES = [("reverse", "감압"), ("forward", "가압")]

FAN_LIMITS = {"slope": (0.0, 1000.0), "intercept": (-10000.0, 100000.0)}
DUTY_LIMITS = (0, 100)


def load_fan_coefficients():
    """설정 화면이 편집할 팬 계수를 읽는다 (파일 전체)."""
    from bdt import calculation  # 순환 import 회피 (calculation 이 무겁다)
    return calculation.load_fan_coefficients()


def validate_fan_coefficients(cover_values):
    """팬 계수를 검증하고 정규화해 돌려준다. 문제가 있으면 ValueError.

    cover_values: {"forward": {"slope":…, "intercept":…},
                   "reverse": {...}, "duty_range": [min, max]}
    """
    clean = {}
    for side, label in FAN_SIDES:
        clean[side] = {}
        for key, (lo, hi) in FAN_LIMITS.items():
            try:
                value = float(cover_values[side][key])
            except (KeyError, TypeError, ValueError):
                raise ValueError(f"{label} 시험의 {key} 값이 올바르지 않습니다.")
            if not (lo <= value <= hi):
                raise ValueError(
                    f"{label} 시험의 {key} 는 {lo:g}~{hi:g} 범위여야 합니다 "
                    f"(받은 값: {value:g})")
            clean[side][key] = value

    try:
        duty_min, duty_max = (int(v) for v in cover_values["duty_range"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("팬 세기 사용 구간이 올바르지 않습니다.")
    lo, hi = DUTY_LIMITS
    if not (lo <= duty_min <= hi and lo <= duty_max <= hi):
        raise ValueError(f"팬 세기는 {lo}~{hi}% 범위여야 합니다.")
    if duty_min >= duty_max:
        raise ValueError("팬 세기 최소는 최대보다 작아야 합니다.")
    clean["duty_range"] = [duty_min, duty_max]
    return clean


def save_fan_coefficients(cover_values, cover=FAN_COVER):
    """한 커버의 계수만 갈아끼운다. 파일의 나머지는 건드리지 않는다.

    calculation.load_fan_coefficients() 가 아니라 파일을 직접 읽는다 — 그쪽은
    기본값을 머지해 돌려주므로, 그 결과를 그대로 쓰면 파일에 없던 커버 항목이
    기본값으로 실체화된다. 편집하는 커버의 부가 키(보정 날짜 등)도 남긴다.
    """
    from bdt import paths

    clean = validate_fan_coefficients(cover_values)

    data = {}
    if os.path.exists(paths.FAN_COEFFICIENTS_JSON):
        with open(paths.FAN_COEFFICIENTS_JSON, "r") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("팬 계수 파일 형식이 올바르지 않습니다.")

    entry = dict(data.get(cover, {}))
    entry.update(clean)
    data[cover] = entry
    with open(paths.FAN_COEFFICIENTS_JSON, "w") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    return data
