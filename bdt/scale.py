"""차트 축 범위 계산 헬퍼.

실시간 압력 그래프(pages.live_pressure)와 압력-풍량 산점도(pages.live_chart)가
같은 규칙으로 축을 잡도록 한곳에 모아둔다. Qt 를 임포트하지 않는 순수 계산
모듈이라 따로 시험하기도 쉽다.
"""

import math


def nice_step(rough):
    """rough 이상이면서 사람이 읽기 좋은 눈금 간격(1·2·2.5·5·10 ×10ⁿ)을 고른다."""
    if rough <= 0:
        return 1.0
    exp = math.floor(math.log10(rough))
    base = 10 ** exp
    for mult in (1, 2, 2.5, 5, 10):
        if rough <= mult * base:
            return mult * base
    return 10 * base


def padded_range(lo, hi, pad=0.10, min_span=1.0, ticks=6, max_ticks=9):
    """측정값이 plot 을 채우도록 여백을 주고, 눈금이 예쁜 수로 떨어지게 맞춘다.

    범위를 데이터에 딱 붙이면 눈금이 1063·1176 같은 읽히지 않는 수로 찍힌다.
    여백을 준 뒤 1·2·5 계열 간격의 배수로 스냅해 30·40·50 처럼 읽게 만든다.
    값이 거의 일정해도(팬 정지 상태의 0 Pa 등) 선이 축에 달라붙지 않도록
    최소 폭을 확보한다.

    눈금 간격을 크게 잡으면 스냅 과정에서 범위가 필요 이상으로 넓어져(예:
    19~68 데이터에 0~80 축) 데이터가 다시 plot 한쪽으로 몰린다. 그래서 촘촘한
    쪽을 먼저 시도하고, 눈금이 max_ticks 를 넘을 때만 한 단계씩 키운다.

    반환: (min, max, 눈금 개수)
    """
    span = max(hi - lo, min_span)
    margin = span * pad
    lo, hi = lo - margin, hi + margin

    step = nice_step((hi - lo) / max(ticks, 1))
    while True:
        low = math.floor(lo / step) * step
        high = math.ceil(hi / step) * step
        count = int(round((high - low) / step)) + 1
        if count <= max_ticks:
            return low, high, count
        # 눈금이 너무 많으면 다음 단계로 키운다 (nice_step 은 입력보다 크거나
        # 같은 값을 주므로, 살짝 키워 넣어야 실제로 다음 단계가 나온다)
        step = nice_step(step * 1.5)
