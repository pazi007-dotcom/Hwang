"""기본 단가 초안. 모두 is_draft=1 (온새가 시안 화면에 쓴 예시 값).
영주형이 실제 단가로 고치기 전에는 보고서에 '초안 단가' 표시가 붙어야 한다.
값이 비어 있는 기종(2L, 덤프 1톤·2.5톤, 펌프카 등)은 영주형이 채운다.
"""
from .store import Store

DRAFT_RATES = [
    # (종류, 항목, 규격, 단위, 단가)
    ("인력", "보통인부", "", "인", 187_000),
    ("인력", "형틀목공", "", "인", 227_000),
    ("장비", "3W", "", "일", 560_000),
    ("장비", "6W", "", "일", 680_000),
    ("장비", "덤프 15톤", "", "대", 220_000),
    ("장비", "덤프 25톤", "", "대", 282_000),
    ("자재", "레미콘", "25-21-150", "㎥", 105_000),
]

TO_BE_FILLED = ["2L", "덤프 1톤", "덤프 2.5톤", "펌프카", "철근공", "특별인부"]


def load_draft_rates(store: Store, valid_from: str = "2026-01-01") -> int:
    for kind, item, spec, unit, price in DRAFT_RATES:
        store.add_rate(kind, item, unit, price, spec=spec, valid_from=valid_from, is_draft=True)
    return len(DRAFT_RATES)
