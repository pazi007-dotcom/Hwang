"""0단계 고정 테스트 (설계안 12장 '검증 계획', 3장·5-1장 규칙)."""
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from jinsung import ConflictError, LockedError, Store, StoreError
from jinsung.reports import (allocation_status, log_coverage, match_invoices,
                             payment_summary, site_inputs)
from jinsung.seed_rates import load_draft_rates
from jinsung.store import KST


class Clock:
    def __init__(self, text):
        self.now = datetime.fromisoformat(text).replace(tzinfo=KST)

    def __call__(self):
        return self.now


@pytest.fixture
def env():
    clock = Clock("2026-11-14T21:10:00")
    s = Store(clock=clock)
    load_draft_rates(s)
    yoseong = s.create_site("요성리 용배수로", "정식", start_date="2026-11-01")
    a = s.create_payee("A중기")
    b = s.create_payee("B운수")
    c = s.create_payee("C레미콘")
    direct = s.create_payee("직영 인력", "직영")
    return s, clock, yoseong, a, b, c, direct


# ---------- 날짜 ----------
def test_backlog_entered_on_14th_stays_on_12th_and_13th(env):
    """12·13일 일지를 14일 밤에 몰아 입력·전송해도 각자의 작업일에 들어간다."""
    s, clock, ys, a, b, c, direct = env
    s.add_input(ys, "2026-11-12", "인력", "보통인부", 4, direct)
    s.add_input(ys, "2026-11-13", "장비", "6W", 1, a)
    clock.now = clock.now.replace(minute=30)  # 21:30 전송
    dates = [r["work_date"] for r in s.db.execute("SELECT work_date FROM work_log ORDER BY 1")]
    assert dates == ["2026-11-12", "2026-11-13"]


def test_month_boundary_entry_after_midnight(env):
    """11월 30일 일을 12월 1일 00:10에 입력해도 11월 보고에 들어간다."""
    s, clock, ys, a, b, c, direct = env
    clock.now = datetime(2026, 12, 1, 0, 10, tzinfo=KST)
    s.add_input(ys, "2026-11-30", "장비", "6W", 1, a)
    assert payment_summary(s, "2026-11")["total"] == 680_000
    assert payment_summary(s, "2026-12")["total"] == 0


def test_february_end_and_year_end(env):
    s, clock, ys, a, b, c, direct = env
    s.add_input(ys, "2027-02-28", "인력", "보통인부", 1, direct)
    s.add_input(ys, "2026-12-31", "인력", "보통인부", 1, direct)
    assert payment_summary(s, "2027-02")["total"] == 187_000
    assert payment_summary(s, "2026-12")["total"] == 187_000
    with pytest.raises(StoreError):
        s.add_input(ys, "2027-02-29", "인력", "보통인부", 1, direct)


def test_work_date_rejects_timestamp(env):
    s, clock, ys, *_ = env
    with pytest.raises(StoreError):
        s.log_for(ys, "2026-11-12T23:50:00")


# ---------- 인력만 / 작업 없음 ----------
def test_labor_only_day_and_no_work_day(env):
    s, clock, ys, a, b, c, direct = env
    s.add_input(ys, "2026-11-10", "인력", "보통인부", 3, direct)   # 장비 0줄
    s.mark_no_work(ys, "2026-11-11")                                  # 비
    rows = site_inputs(s, "2026-11")
    assert rows[0]["인력"] == 561_000 and rows[0]["장비"] == 0
    cov = log_coverage(s, ys, "2026-11", until="2026-11-11")
    assert "2026-11-11" not in cov["missing"] and "2026-11-01" in cov["missing"]


# ---------- 현장 필수 / 긴급 현장 ----------
def test_input_requires_site_and_hq_site_is_single(env):
    s, clock, ys, a, b, c, direct = env
    with pytest.raises(StoreError):
        s.add_input(None, "2026-11-12", "장비", "6W", 1, a)
    assert s.hq_site() == s.hq_site()


def test_emergency_site_counts_in_month_end(env):
    s, clock, ys, a, b, c, direct = env
    em = s.quick_emergency_site("긴급 수해복구", 36.7, 128.1)
    s.add_input(em, "2026-11-12", "장비", "덤프 25톤", 3, b)
    s.add_input(ys, "2026-11-12", "장비", "덤프 25톤", 2, b)
    summary = payment_summary(s, "2026-11")
    row = summary["rows"][0]
    assert row["payee"] == "B운수" and row["total"] == 5 * 282_000
    assert row["by_site"] == {"긴급 수해복구": 846_000, "요성리 용배수로": 564_000}


# ---------- 두 현장에 나눈 장비 ----------
def test_shared_equipment_paid_once_cost_split(env):
    s, clock, ys, a, b, c, direct = env
    em = s.quick_emergency_site("긴급 복구")
    s.add_shared_input("2026-11-15", "장비", "6W", 1, a, [(ys, "0.5"), (em, "0.5")])
    row = payment_summary(s, "2026-11")["rows"][0]
    assert row["total"] == 680_000                       # 업체에는 1일분 한 번
    assert sorted(row["by_site"].values()) == [340_000, 340_000]


def test_shared_split_rounding_keeps_total(env):
    s, clock, ys, a, b, c, direct = env
    em = s.quick_emergency_site("긴급 복구")
    third = s.quick_emergency_site("마을 안길")
    s.add_shared_input("2026-11-15", "장비", "3W", 1, a,
                       [(ys, "0.4"), (em, "0.3"), (third, "0.3")], unit_price=560_001)
    assert payment_summary(s, "2026-11")["total"] == 560_001


# ---------- 충돌 (0단계 통과 기준) ----------
def test_phone_and_pc_edit_same_record_nothing_lost(env):
    """폰과 PC가 같은 투입 줄을 동시에 고쳐도 어느 값도 사라지지 않는다."""
    s, clock, ys, a, b, c, direct = env
    line = s.add_input(ys, "2026-11-14", "장비", "덤프 25톤", 3, b)
    seen = s.get("input_line", line)["version"]        # 두 기기가 같은 버전을 읽음
    s.device = "phone"
    s.update("input_line", line, seen, {"qty": 4})     # 폰이 먼저 저장
    s.device = "pc"
    with pytest.raises(ConflictError) as err:
        s.update("input_line", line, seen, {"qty": 5})  # PC는 덮어쓰지 못함
    assert s.get("input_line", line)["qty"] == "4"
    conflicts = s.open_conflicts()
    assert len(conflicts) == 1 and '"qty": 5' in conflicts[0]["incoming_json"]
    s.resolve_conflict(err.value.conflict_id, keep="incoming")
    line_now = s.get("input_line", line)
    assert line_now["qty"] == "5" and line_now["amount"] == 5 * 282_000
    assert s.open_conflicts() == []


def test_same_site_name_different_records(env):
    s, *_ = env
    assert s.create_site("요성리 용배수로") != s.create_site("요성리 용배수로")


def test_one_log_per_site_and_day(env):
    s, clock, ys, a, b, c, direct = env
    assert s.log_for(ys, "2026-11-12") == s.log_for(ys, "2026-11-12")


# ---------- 월 마감 ----------
def test_locked_month_needs_reason_and_keeps_history(env):
    s, clock, ys, a, b, c, direct = env
    line = s.add_input(ys, "2026-11-14", "장비", "6W", 1, a)
    s.lock_month("2026-11")
    v = s.get("input_line", line)["version"]
    with pytest.raises(LockedError):
        s.update("input_line", line, v, {"qty": 2})
    with pytest.raises(LockedError):
        s.add_input(ys, "2026-11-20", "인력", "보통인부", 1, direct)
    s.update("input_line", line, v, {"qty": 2}, reason="명세서 확인 결과 2일")
    hist = s.db.execute("SELECT * FROM change_history WHERE row_id=?", (line,)).fetchall()
    assert len(hist) == 1 and hist[0]["reason"] == "명세서 확인 결과 2일"
    s.add_input(ys, "2026-12-01", "인력", "보통인부", 1, direct)   # 다음 달은 자유


# ---------- 금액·단가 ----------
def test_amount_rounding_and_missing_rate(env):
    s, clock, ys, a, b, c, direct = env
    line = s.add_input(ys, "2026-11-12", "자재", "레미콘", "12.5", c, spec="25-21-150")
    assert s.get("input_line", line)["amount"] == 1_312_500
    with pytest.raises(StoreError):
        s.add_input(ys, "2026-11-12", "장비", "펌프카", 1, a)


def test_payee_specific_rate_wins(env):
    s, clock, ys, a, b, c, direct = env
    s.add_rate("장비", "6W", "일", 650_000, payee_id=a, valid_from="2026-11-01")
    line = s.add_input(ys, "2026-11-12", "장비", "6W", 1, a)
    assert s.get("input_line", line)["unit_price"] == 650_000


def test_design_mockup_day_total(env):
    """시안(업무일지 화면) 11/15 합계 4,215,000원과 같아야 한다."""
    s, clock, ys, a, b, c, direct = env
    d = s.create_payee("D건설", "업체")
    s.add_input(ys, "2026-11-15", "인력", "보통인부", 4, direct)
    s.add_input(ys, "2026-11-15", "인력", "형틀목공", 3, d)
    s.add_input(ys, "2026-11-15", "장비", "6W", 1, a)
    s.add_input(ys, "2026-11-15", "장비", "덤프 25톤", 3, b)
    s.add_input(ys, "2026-11-15", "자재", "레미콘", 12, c, spec="25-21-150")
    assert payment_summary(s, "2026-11")["total"] == 4_215_000


# ---------- 배정 자재 (요성리 실제 수치) ----------
def test_yoseong_allocation_design_section(env):
    """설계 단면(벽체 200mm) 기준: 레미콘 25-21-08 설계 176, 배정 180 → 여유 4 ㎥."""
    s, clock, ys, a, b, c, direct = env
    s.add_allocation(ys, "레미콘", "㎥", 176, 180, spec="25-21-08")
    s.add_allocation(ys, "레미콘", "㎥", 40, 41, spec="25-18-08")
    s.add_allocation(ys, "철근", "t", "13.75", "14.163", spec="HD13·HD16")
    s.add_input(ys, "2026-11-12", "자재", "레미콘", 30, c, spec="25-21-08", unit="㎥",
                unit_price=0)   # 관급: 대금은 발주처, 수량만 추적
    status = {(r["item"], r["spec"]): r for r in allocation_status(s, ys)}
    main = status[("레미콘", "25-21-08")]
    assert main["cum_in"] == 30 and main["remaining_need"] == 146 and main["balance"] == 4
    assert status[("철근", "HD13·HD16")]["balance"] == Decimal("0.413")


def test_allocation_shortage_from_remaining_length(env):
    """남은 210 m × 0.703 ㎥/m = 147.63 → 반입 35면 배정 180에 2.63 ㎥ 부족 예상."""
    s, clock, ys, a, b, c, direct = env
    s.add_allocation(ys, "레미콘", "㎥", 176, 180, spec="25-21-08")
    s.add_input(ys, "2026-11-12", "자재", "레미콘", 35, c, spec="25-21-08", unit="㎥",
                unit_price=0)
    need = Decimal("0.703") * 210
    row = allocation_status(s, ys, {("레미콘", "25-21-08"): need})[0]
    assert row["balance"] == Decimal("-2.630") and row["status"] == "부족 예상"


# ---------- 거래명세서 대조 ----------
def test_invoice_matching_never_overwrites_log(env):
    s, clock, ys, a, b, c, direct = env
    s.add_input(ys, "2026-11-14", "장비", "덤프 25톤", 4, b)
    s.add_input(ys, "2026-11-13", "장비", "덤프 15톤", 4, b)
    s.add_invoice(b, "2026-11-14", "장비", "덤프 25톤", 5, 5 * 282_000)   # 차이
    s.add_invoice(b, "2026-11-13", "장비", "덤프 15톤", 4, 880_000)       # 일치
    s.add_invoice(a, "2026-11-08", "장비", "3W", 1, 560_000)              # 일지에 없음
    counts = match_invoices(s, "2026-11")
    assert counts == {"차이": 1, "일치": 1, "일지에없음": 1}
    assert payment_summary(s, "2026-11")["total"] == 4 * 282_000 + 880_000


def test_file_database_survives_reopen(tmp_path: Path):
    db = tmp_path / "jinsung.db"
    s = Store(db)
    site = s.create_site("요성리 용배수로")
    s.db.close()
    assert Store(db).get("site", site)["name"] == "요성리 용배수로"
