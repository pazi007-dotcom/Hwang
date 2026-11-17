"""공사 건 접수 → 보류/취소/진행 → 완공 → 민원, 시작 예정일 기준 발주·체크."""
import pytest

from jinsung import Store, alerts, intake, schedule, sync, yoseong
from jinsung.seed_rates import load_draft_rates
from jinsung.store import StoreError


@pytest.fixture
def s():
    st = Store()
    load_draft_rates(st)
    return st


def tasks(s, site, where="1=1"):
    return [dict(r) for r in s.db.execute(
        f"SELECT * FROM site_task WHERE site_id=? AND {where} ORDER BY due_date, created_at", (site,))]


def test_receive_writes_log_first_and_makes_checks(s):
    site = intake.receive(s, "점촌 배수로 긴급복구", "긴급", "2026-11-16", client="문경시",
                          instructions="토사 유입 구간 30m 준설", contacts=[
                              {"name": "김주무관", "role": "감독", "phone": "054-000-0000"}],
                          checks=["마을 이장 연락"])
    row = s.get("site", site)
    assert (row["status"], row["job_type"], row["site_type"]) == ("접수", "긴급", "긴급수의")
    log = s.db.execute("SELECT * FROM work_log WHERE site_id=?", (site,)).fetchone()
    assert log["work_date"] == "2026-11-16" and log["note"].startswith("[접수·긴급] 점촌 배수로 긴급복구")
    assert log["content"] is None
    titles = [t["title"] for t in tasks(s, site)]
    assert "피해 사진(전) 찍기" in titles and titles[-1] == "마을 이장 연락"
    assert s.db.execute("SELECT name FROM contact WHERE site_id=?", (site,)).fetchone()["name"] == "김주무관"
    att = intake.add_attachment(s, site, "도면", "진성건설/점촌/도면/평면도.pdf")
    assert s.get("attachment", att)["review"] == "검토 대기"
    assert intake.board(s)["접수"][0]["review_waiting"] == 1


def test_hold_keeps_everything_and_can_resume(s):
    site = intake.receive(s, "모전 농로 포장 견적", "견적", "2026-11-16")
    with pytest.raises(StoreError):
        intake.hold(s, site, "")
    intake.hold(s, site, "발주처 예산 미확정")
    assert intake.board(s)["보류"][0]["reason"] == "발주처 예산 미확정"
    assert schedule.due(s, "2026-11-20") == []                   # 보류 건은 알리지 않는다
    intake.proceed(s, site, "2026-12-01")
    assert s.get("site", site)["status"] == "진행" and len(tasks(s, site)) > 3


def test_cancel_without_cost_is_destroyed(s):
    site = intake.receive(s, "취소될 견적", "견적", "2026-11-16", contacts=[{"name": "박씨"}])
    assert intake.cancel(s, site, "발주 취소") == "파기"
    for table in ("site", "work_log", "site_task", "contact"):
        assert s.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    hist = s.db.execute("SELECT reason FROM change_history WHERE table_name='site'").fetchone()
    assert hist["reason"] == "취소 파기: 발주 취소"               # 파기해도 이력에는 남는다


def test_cancel_with_cost_is_kept_so_money_is_not_lost(s):
    site = intake.receive(s, "답사만 한 건", "수의", "2026-11-16")
    kim = s.create_payee("김반장", "개인")
    s.add_input(site, "2026-11-16", "인력", "보통인부", 1, kim)   # 답사 인건비
    assert intake.cancel(s, site, "계약 무산") == "보관"
    assert s.get("site", site)["status"] == "취소"
    with pytest.raises(StoreError):
        s.add_input(site, "2026-11-17", "인력", "보통인부", 1, kim)
    from jinsung import reports
    assert reports.payment_summary(s, "2026-11")["total"] == 187_000


def test_cancel_destroy_travels_to_other_device(s):
    phone = Store(device="phone")
    site = intake.receive(s, "취소될 긴급", "긴급", "2026-11-16")
    sync.sync(phone, s)
    assert phone.db.execute("SELECT COUNT(*) FROM site").fetchone()[0] == 1
    intake.cancel(s, site, "오접수")
    sync.sync(phone, s)
    assert phone.db.execute("SELECT COUNT(*) FROM site").fetchone()[0] == 0


def test_planned_start_makes_orders_with_quantities(s):
    y = yoseong.seed(s)
    ids = intake.proceed(s, y["site"], "2026-12-01")
    t = {x["title"]: x for x in tasks(s, y["site"])}
    assert len(ids) == 10 + 2 * 17                               # 준비 10 + 블록 17 × (기초·벽체)
    steel = t["철근 가공 발주 (D16 U바·헌치근, D13 배력근)"]
    assert (steel["due_date"], steel["qty"], steel["unit"]) == ("2026-11-24", "14.26", "ton")
    assert t["레미콘 전체 물량 통보 (관급 배정 확인)"]["qty"] == "198"
    assert t["유로폼 1세트 임대 (3012·3006·6012·6090·헌치폼)"]["qty"] == "152"
    b1, w1, b17 = t["블록 1 기초 타설 레미콘·날씨 확인"], t["블록 1 벽체 타설 레미콘·날씨 확인"], \
        t["블록 17 기초 타설 레미콘·날씨 확인"]
    assert (b1["due_date"], b1["qty"]) == ("2026-12-01", "5.25")
    assert (w1["due_date"], w1["qty"]) == ("2026-12-03", "6.34")
    assert (b17["due_date"], b17["qty"]) == ("2027-01-18", "3.5")  # 마지막 블록은 10m


def test_changing_start_moves_only_unfinished_suggestions(s):
    y = yoseong.seed(s)
    intake.proceed(s, y["site"], "2026-12-01")
    done = next(x for x in tasks(s, y["site"]) if x["title"].startswith("철근 가공"))
    intake.check(s, done["id"], "2026-11-20")
    mine = intake.add_task(s, y["site"], "확인", "마을 방송 요청", due_date="2026-11-30")
    intake.proceed(s, y["site"], "2026-12-08")                   # 일주일 미룸
    t = {x["title"]: x for x in tasks(s, y["site"])}
    assert t["철근 가공 발주 (D16 U바·헌치근, D13 배력근)"]["done_date"] == "2026-11-20"   # 끝낸 일 그대로
    assert t["마을 방송 요청"]["id"] == mine                      # 직접 만든 일 그대로
    assert t["굴삭기·덤프·펌프카 예약"]["due_date"] == "2026-12-04"   # 12/5 토 → 금요일로
    assert len(t) == 44 + 1


def test_due_alerts_on_home(s):
    y = yoseong.seed(s)
    intake.proceed(s, y["site"], "2026-12-01")
    d = schedule.due(s, "2026-11-25")
    assert d[0]["text"].startswith("[1일 지남] 요성리 용배수로 · 착공계") and d[0]["level"] == "빨강"
    assert any(x["when"] == "D-1" and "유로폼" in x["title"] for x in d)
    home = alerts.home(s, y["site"], "2026-11-25")
    assert home["todo"][0] == "오늘 일지 미작성" and home["todo"][1].startswith("[1일 지남]")


def test_complete_then_complaint_stays_on_same_site(s):
    site = intake.receive(s, "산양 수로 보수", "수의", "2026-11-01")
    intake.proceed(s, site, "2026-11-05")
    left = intake.complete(s, site, "2026-11-20")
    assert s.get("site", site)["status"] == "완공" and "답사" in left
    intake.complaint(s, site, "2027-03-02", "벽체 누수 민원", contact={"name": "이장님", "phone": "010-0000-0000"})
    kim = s.create_payee("김반장", "개인")
    s.add_input(site, "2027-03-03", "인력", "보통인부", 1, kim)   # 민원 처리 비용도 같은 현장으로
    log = s.db.execute("SELECT note FROM work_log WHERE site_id=? AND work_date='2027-03-02'",
                       (site,)).fetchone()
    assert log["note"] == "[민원] 벽체 누수 민원"
    assert schedule.due(s, "2027-03-02")[-1]["title"] == "벽체 누수 민원"


def test_several_sites_in_one_day(s):
    """큰 공사 + 긴급 두 건을 오전·오후로 뛴 날."""
    y = yoseong.seed(s)
    a = intake.receive(s, "긴급 A", "긴급", "2026-11-16")
    b = intake.receive(s, "긴급 B", "긴급", "2026-11-16")
    dump, kim = s.create_payee("대성중기"), s.create_payee("김반장", "개인")
    s.add_input(y["site"], "2026-11-16", "인력", "형틀목공", 2, s.create_payee("목수팀"))
    s.add_shared_input("2026-11-16", "장비", "6W", 1, dump, [(a, "0.5"), (b, "0.5")])
    s.add_input(a, "2026-11-16", "인력", "보통인부", "0.5", kim)
    s.add_input(b, "2026-11-16", "인력", "보통인부", "0.5", kim)
    o = schedule.day_overview(s, "2026-11-16")
    assert [x["site"] for x in o["sites"]] == ["긴급 A", "긴급 B", "요성리 용배수로"]
    assert o["total"] == 454_000 + 680_000 + 187_000 and o["warnings"] == []
    s.add_input(y["site"], "2026-11-16", "인력", "보통인부", 1, kim)   # 같은 사람이 하루 2공수?
    assert "김반장 보통인부: 하루에 2.0공수" in schedule.day_overview(s, "2026-11-16")["warnings"][0]["text"]
