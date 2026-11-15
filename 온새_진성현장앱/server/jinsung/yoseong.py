"""기준 사례: 문경읍 요성리 용배수로 개체공사 (U형 개거 1.0×1.0, L=250m).

도면(3차 수정)·내역서에서 읽은 값. 앱 개발의 기준 시험 자료다 (설계안 9-3).
- 종단도 3장의 시점이 'No 6'으로 표기돼 있으나 실제는 No.0 (2026-11-15 영주형 확인).
- 횡단면도는 No.0~No.11만 있다. No.12·No.12+10 단면적은 1차 산출값(확인 필요).
- 실행 단면(2026-11-15 영주형 지시): 버림 삭제, 기초 250 1회 타설, 기초폭 정확히 1,400,
  25-21-08 단일 규격. 벽체는 설계대로 200.
"""
from __future__ import annotations

from .store import Store

LENGTH = 250
# (누가거리, 지반고, 계획고)
PROFILE = [
    (0, "100.00", "100.00"), (20, "99.30", "99.47"), (40, "98.77", "98.94"), (60, "98.16", "98.41"),
    (80, "97.63", "97.88"), (100, "97.35", "97.35"), (120, "97.05", "97.12"), (140, "96.69", "96.90"),
    (160, "96.54", "96.67"), (180, "96.36", "96.45"), (200, "96.23", "96.23"), (220, "96.15", "96.15"),
    (240, "96.00", "96.06"), (250, "95.86", "95.98"),
]
# (누가거리, 터파기 단면적, 되메우기 단면적) — 횡단면도 표
SECTIONS = [
    (0, "1.8", "1.3"), (20, "1.8", "1.7"), (40, "0.8", "1.0"), (60, "0.8", "0.9"), (80, "1.2", "1.5"),
    (100, "1.9", "1.6"), (120, "1.3", "1.5"), (140, "1.3", "1.5"), (160, "1.5", "1.5"),
    (180, "1.9", "1.6"), (200, "2.0", "1.6"), (220, "1.8", "1.5"), (240, "1.9", "1.6"), (250, "1.4", "1.4"),
]
DESIGN = {}                                             # 도면 단면 = 템플릿 기본값
EXEC = {"base_t": "0.25", "lean_t": "0", "cover_bottom": "0.075"}   # 실행 단면
# 내역: 설계 수량 / 관급 배정(할증 포함)
ALLOCATIONS = [
    ("레미콘", "25-21-08", "㎥", "176", "180"),
    ("레미콘", "25-18-08", "㎥", "40", "41"),
    ("철근", "D16", "ton", "9.5", "9.785"),
    ("철근", "D13", "ton", "4.25", "4.378"),
]
CONTRACT_CHECK = {"터파기": "382", "되메우기": "363", "유로폼 보통": "1130", "유로폼 간단": "50"}


def seed(store: Store, with_exec: bool = True) -> dict:
    from .stations import format_sta
    site = store.create_site("요성리 용배수로", "정식", client="문경시", sta_interval="20")
    for sta, ground, plan in PROFILE:
        store.add_station(site, sta, format_sta(sta), plan_elev=plan, ground_elev=ground)
    ids = {}
    for key, name, part in (("base", "개거 기초", "base"), ("wall", "개거 벽체", "wall")):
        ids[key] = store.add_work_type(
            site, 9, name, design_length=LENGTH, design_params={**DESIGN, "part": part},
            exec_params={**EXEC, "part": part} if with_exec else None)
    # 실행 단면: 버림(25-18-08) 배정을 기초(25-21-08)로 치환해서 쓴다 → 레미콘은 합쳐서 본다(참고용)
    for item, spec, unit, design, alloc in ALLOCATIONS:
        store.add_allocation(site, item, unit, design, alloc, spec=spec,
                             pool="레미콘" if with_exec and item == "레미콘" else None)
    return {"site": site, "base": ids["base"], "wall": ids["wall"]}
