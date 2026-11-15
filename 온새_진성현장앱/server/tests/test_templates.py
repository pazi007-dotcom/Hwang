"""물량산출·토공·야장 기준 사례 (설계안 12장 '기준 사례 테스트')."""
from decimal import Decimal as D

import pytest

from jinsung import Store, earthwork, level, yoseong
from jinsung.stations import covered_length, format_sta, gaps, parse_sta, progress_bar, records_at
from jinsung.store import StoreError
from jinsung.templates import calc, open_channel as oc

V3 = yoseong.EXEC


def q(result, name):
    return oc.item(result, name)


# ---------- 요성리 개거: 도면 단면 = 내역 수량 ----------
def test_drawing_section_matches_contract():
    r = calc(9, {})
    assert r["section"]["body"] == D("0.7025")            # 재료표 0.703 ㎥/m
    assert round(r["section"]["body"] * 250) == 176       # 내역 176 ㎥
    assert r["section"]["lean"] * 250 == 40               # 버림 25-18-08 40 ㎥


def test_old_execution_plan_base_85m3_and_417_panels():
    r = calc(9, {"base_w": "1.7"})
    assert q(r, "레미콘 기초") == 85                       # 1.7 × 0.2 × 250
    assert q(r, "외벽 패널 전체 연장 환산(측당)") == 417   # 양측 각 약 417장


# ---------- 요성리 개거: 실행 단면(버림 삭제, 기초 250) = 물량산출서 v3 ----------
def test_execution_section_v3():
    r = calc(9, V3)
    assert q(r, "레미콘 기초") == D("87.5")
    assert q(r, "레미콘 벽체+헌치") == D("105.625")
    assert q(r, "레미콘 발주") == 198
    assert not any(i["name"] == "버림 콘크리트" for i in r["items"])
    assert float(r["form_area"]) == pytest.approx(1156.066, abs=0.001)
    assert q(r, "기초 측면 (양측)") == 125                 # 기초는 양측 거푸집
    assert r["joints"] == 16 and r["blocks"][-1] == 10
    assert r["ubar_count"] == 1250 and r["dist_length"] == D("4296.24")
    assert float(q(r, "철근 합계(할증 포함)")) == pytest.approx(14.2567, abs=0.0005)
    assert q(r, "지수판") == D("53.6") and q(r, "조인트휠러") == D("12.36")


def test_form_sets_cover_both_sides_and_reuse_accessories():
    r = calc(9, V3)
    assert q(r, "3012 (기초, 눕힘)") == 24 and q(r, "3006 (기초 보정)") == 2
    assert q(r, "6012 (외벽, 세움)") == 50 and q(r, "6090 (내벽)") == 50
    assert r["pins"] == (48, 500) and q(r, "폼핀(웨지핀)") == 500     # 합(548)이 아니라 큰 값
    assert q(r, "비계파이프 6m(띠장)") == 24 and q(r, "말뚝(단관 1.0m)") == 28
    assert q(r, "플랫타이") == 1732                                    # 소모자재는 블록별 합
    assert all(c["ok"] for c in r["checks"])


def test_assembly_check_flags_wrong_base_width():
    r = calc(9, {**V3, "base_w": "1.7"})
    bad = [c["name"] for c in r["checks"] if not c["ok"]]
    assert bad == ["기초폭 = 벽체 외면 간 거리"]


def test_unopened_template_says_so():
    with pytest.raises(NotImplementedError):
        calc(13, {})


def test_pavement():
    r = calc(1, {"length": 100, "width": 3, "thickness": "0.2", "wire_mesh": True})
    assert r["items"][0]["qty"] == 60


# ---------- 측점 ----------
def test_station_parse_format():
    assert parse_sta("No.2+10") == 50 and parse_sta("NO.0+5.8") == D("5.8")
    assert parse_sta("no 12") == 240 and parse_sta("3+15") == 75 and parse_sta("45m") == 45
    assert format_sta(50) == "No.2+10" and format_sta(240) == "No.12" and format_sta("5.8") == "No.0+5.8"
    assert parse_sta("No 6", label_shift=-6) == 0          # 종단도 시점 'No 6' = 실제 No.0
    with pytest.raises(StoreError):
        parse_sta("No.2+25")


def test_overlapping_ranges_not_double_counted():
    assert covered_length([(0, 30), (20, 45), (60, 80)]) == 65
    assert gaps([(0, 30), (60, 80)], 0, 100) == [(30, 60), (80, 100)]


def test_progress_bar_and_records_by_station():
    s = Store()
    y = yoseong.seed(s)
    p = s.create_payee("가은레미콘")
    s.add_progress(y["site"], "2026-11-12", y["base"], 30, "m", sta_from="0", sta_to="30")
    s.add_progress(y["site"], "2026-11-13", y["base"], 30, "m", sta_from="15", sta_to="45")
    s.add_input(y["site"], "2026-11-13", "자재", "레미콘", 8, p, spec="25-21-08", unit="㎥",
                unit_price=105000, work_type_id=y["base"], sta_from="30", sta_to="45")
    s.add_photo(y["site"], "2026-11-13", "사진/기초_전.jpg", stage="전", sta_from="40", sta_to="40")
    bar = progress_bar(s, y["base"])
    assert bar["done_length"] == 45 and bar["rate"] == D(45) / 250
    assert bar["done"] == [("No.0", "No.2+5")] and bar["todo"] == [("No.2+5", "No.12+10")]
    rec = records_at(s, y["site"], 35, 45)
    assert len(rec["inputs"]) == 1 and len(rec["photos"]) == 1 and len(rec["progress"]) == 1


# ---------- 토공 ----------
def test_average_end_area_matches_designer_table():
    r = earthwork.average_end_area([("5.8", "5.2", 0), ("10.7", "5.3", 0)])   # 모전 토적표
    assert round(r["cut"], 1) == D("25.7")


def test_yoseong_earthwork_vs_contract():
    r = earthwork.average_end_area(yoseong.SECTIONS)
    assert r["cut"] == D("379.5") and r["fill"] == D("362")     # 내역 382 / 363 (1% 이내)
    assert abs(r["cut"] - 382) / 382 < D("0.01")
    assert earthwork.haul(r["surplus"])["kind"] == "잔토 반출"


# ---------- 야장 ----------
def test_level_run_cut_fill_and_closure():
    s = Store()
    y = yoseong.seed(s)
    run = level.start_run(s, y["site"], "2026-11-12", "임시BM-전봇대", "100.500", "1.200", assumed=True)
    level.foresight(s, run, 0, "1.345")        # 지반 100.355, 계획 100.00 → 절토 0.355
    level.foresight(s, run, 20, "2.400")       # 지반 99.300, 계획 99.47 → 성토 0.170
    level.foresight(s, run, 10, "1.700")       # 계획고 보간 99.735 → 지반 100.000 → 절토 0.265
    level.turning_point(s, run, "2.000", "0.800")   # HI 101.700 → 100.500
    level.foresight(s, run, 40, "1.560")       # 지반 98.940 = 계획고
    level.turning_point(s, run, "0.800", "2.000")   # HI → 101.700
    level.close(s, run, "1.198")               # BM 다시 읽음 → 오차 +2mm
    r = level.compute(s, run)
    p = r["points"]
    assert (p[0]["work"], p[0]["depth"]) == ("절토", D("0.355"))
    assert (p[1]["work"], p[1]["depth"]) == ("성토", D("0.170"))
    assert (p[2]["plan"], p[2]["depth"]) == (D("99.735"), D("0.265"))
    assert p[3]["work"] == "계획고"
    assert r["closure"]["error"] == D("0.002") and r["closure"]["ok"] and r["assumed"]


def test_channel_must_flow_downhill():
    assert level.check_flow([(s, e) for s, _, e in yoseong.PROFILE]) == []     # 요성리 계획고: 정상
    bad = level.check_flow([(0, "100.00"), (20, "99.80"), (40, "99.85"), (60, "99.60")])
    assert [(b["from"], b["kind"]) for b in bad] == [(20, "역구배")]
    plan = level.grade_plan("100.00", "95.98", 250, [0, 125, 250])
    assert plan[1]["plan"] == D("97.99")
