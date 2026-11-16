"""1단계(보고) + 온새 제안 8가지 (설계안 5, 5-1, 11장)."""
import sqlite3
from decimal import Decimal as D

import pytest
from openpyxl import load_workbook

from jinsung import Store, alerts, backup, excel_report, invoice_intake, mailer, voice_log, yoseong
from jinsung.seed_rates import load_draft_rates
from jinsung.store import LockedError, StoreError


@pytest.fixture
def world():
    s = Store()
    load_draft_rates(s)
    s.add_rate("자재", "레미콘", "㎥", 98_000, spec="25-21-08")
    y = yoseong.seed(s)
    return {"s": s, **y, "emg": s.quick_emergency_site("점촌 긴급복구"),
            "dump": s.create_payee("대성중기"), "rmc": s.create_payee("가은레미콘"),
            "kim": s.create_payee("김반장", "개인")}


def fill_november(w):
    s = w["s"]
    s.add_input(w["site"], "2026-11-12", "장비", "덤프 25톤", 3, w["dump"])
    s.add_shared_input("2026-11-13", "장비", "6W", 1, w["dump"], [(w["site"], "0.5"), (w["emg"], "0.5")])
    s.add_input(w["site"], "2026-11-13", "인력", "보통인부", 4, w["kim"])
    s.add_input(w["site"], "2026-11-14", "자재", "레미콘", 8, w["rmc"], spec="25-21-08",
                work_type_id=w["base"], sta_from="0", sta_to="30")
    s.add_progress(w["site"], "2026-11-14", w["base"], 30, "m", sta_from="0", sta_to="30")


# ---------- 월말 보고 Excel ----------
def test_report_file_names():
    f = excel_report.report_file_name
    assert f("월말보고", "2026-11") == "월말보고_2026-11.xlsx"
    assert f("월말보고", "2026-11", corrected=True) == "월말보고_2026-11_정정.xlsx"
    assert f("준공정산", "", site="요성리") == "준공정산_요성리.xlsx"
    assert f("사진대지", "2026-11", site="요성리", ext="hwpx") == "사진대지_2026-11_요성리.hwpx"


def test_monthly_excel_sheets_and_formulas(world, tmp_path):
    fill_november(world)
    s = world["s"]
    s.add_invoice(world["dump"], "2026-11-12", "장비", "덤프 25톤", 4, 4 * 282_000)   # 명세서는 4대
    path = excel_report.build_monthly(s, "2026-11", tmp_path)
    assert path.name == "월말보고_2026-11.xlsx"
    wb = load_workbook(path)
    assert wb.sheetnames == ["결제요약", "이체목록", "현장별투입", "출역표", "인력", "장비", "자재", "거래명세서", "자재배정대비"]
    ws = wb["결제요약"]
    assert [c.value for c in ws[5]][:5] == ["받는 곳", "구분", "요성리 용배수로", "점촌 긴급복구", "합계"]
    assert ws["A6"].value == "대성중기" and ws["A6"].font.bold            # 금액 큰 순 + 차이는 굵게
    assert ws["C6"].value.startswith("=SUMIFS('인력'!")                   # 요약은 상세를 더한 수식
    assert ws["I6"].value == "차이"
    assert wb["장비"]["I4"].value == "=ROUND(F4*H4,0)"
    # 일지 값은 명세서로 덮어쓰지 않는다
    assert wb["장비"]["F4"].value == 3 and wb["거래명세서"]["E4"].value == 4 * 282_000


def test_no_equipment_month_and_manpower_only_day(world, tmp_path):
    s = world["s"]
    s.add_input(world["site"], "2026-12-01", "인력", "보통인부", 2, world["kim"])   # 인력만 투입한 날
    wb = load_workbook(excel_report.build_monthly(s, "2026-12", tmp_path))
    assert wb["인력"]["I4"].value == "=ROUND(F4*H4,0)" and wb["장비"]["A4"].value == "합계"


def test_paid_amount_carries_only_balance_to_next_month(world, tmp_path):
    fill_november(world)
    s = world["s"]
    s.mark_paid(world["dump"], "2026-11", 1_000_000, "2026-12-05")      # 1,526,000 중 일부 지급
    s.add_input(world["site"], "2026-12-02", "장비", "덤프 25톤", 1, world["dump"])
    ws = load_workbook(excel_report.build_monthly(s, "2026-12", tmp_path))["결제요약"]
    head = [c.value for c in ws[5]]
    assert ws.cell(6, head.index("이월 미지급") + 1).value == 526_000


# ---------- 대표이사 전송: 확인 → 전송 → 마감 → 정정 ----------
def test_send_needs_confirmation_and_locks_month(world, tmp_path):
    fill_november(world)
    s = world["s"]
    check = mailer.precheck(s, "2026-11", until="2026-11-14")
    ys = next(x for x in check["sites"] if x["site"] == "요성리 용배수로")
    assert ys["written"] == 3 and "2026-11-09" in ys["missing"]          # 빠진 날짜를 보여 준다
    with pytest.raises(StoreError):
        mailer.send_monthly(s, "2026-11", tmp_path, ["ceo@example.com"], confirmed=False)

    sent = []
    r = mailer.send_monthly(s, "2026-11", tmp_path, ["ceo@example.com"], confirmed=True,
                            transport=sent.append)
    assert r["sent"] == 1 and sent[0]["subject"] == "월말보고 2026-11"
    assert sent[0]["body"].count("\n") == 2 and "3,058,000원" in sent[0]["body"]   # 본문 세 줄
    assert s.is_locked("2026-11")
    with pytest.raises(LockedError):
        s.add_input(world["site"], "2026-11-20", "인력", "보통인부", 1, world["kim"])
    s.add_input(world["site"], "2026-11-20", "인력", "보통인부", 1, world["kim"], reason="누락분")
    r2 = mailer.send_monthly(s, "2026-11", tmp_path, ["ceo@example.com"], confirmed=True,
                             transport=sent.append)
    assert r2["file"].name == "월말보고_2026-11_정정.xlsx" and sent[1]["subject"] == "월말보고 2026-11 정정"


def test_failed_mail_stays_in_outbox_and_retries(world, tmp_path):
    fill_november(world)
    s = world["s"]

    def offline(mail):
        raise ConnectionError("서버 연결 안 됨")

    r = mailer.send_monthly(s, "2026-11", tmp_path, ["ceo@example.com"], confirmed=True, transport=offline)
    assert r["failed"] == 1 and not s.is_locked("2026-11")               # 못 보냈으면 마감하지 않는다
    assert "실패" in s.db.execute("SELECT result FROM report_log").fetchone()["result"]
    sent = []
    assert mailer.flush(s, sent.append) == {"sent": 1, "failed": 0}
    assert s.is_locked("2026-11") and len(sent) == 1


# ---------- 제안 4·7·8 + 배정 자재 ----------
def test_allocation_alerts_for_execution_section(world):
    """실행 단면(버림 삭제·기초 250): 버림 배정 41㎥를 기초 25-21-08로 치환해 쓰면 합계로는 남는다."""
    a = {x["item"]: x for x in alerts.allocation_alerts(world["s"], world["site"])}
    pooled = a["레미콘 25-18-08·25-21-08"]
    assert pooled["level"] == "초록" and pooled["alloc_qty"] == 221
    assert pooled["balance"] == D("221") - D("193.125")                  # 여유 27.9㎥ (참고값)
    assert "참고값" in pooled["text"]
    assert a["철근 D16"]["level"] == "주황" and "할증 여유 사용" in a["철근 D13"]["text"]


def test_without_substitution_2108_alone_is_short():
    s = Store()
    y = yoseong.seed(s)
    s.db.execute("UPDATE allocation SET pool=NULL")                      # 치환이 승인되지 않은 경우
    a = {x["item"]: x for x in alerts.allocation_alerts(s, y["site"])}
    assert a["레미콘 25-21-08"]["balance"] == D("180") - D("193.125")
    assert "전량 미사용" in a["레미콘 25-18-08"]["text"]


def test_design_section_has_small_margin():
    s = Store()
    y = yoseong.seed(s, with_exec=False)                                 # 도면대로 시공하는 경우
    st = {(x["item"], x["spec"]): x for x in
          __import__("jinsung.reports", fromlist=["x"]).allocation_status(
              s, y["site"], alerts.remaining_need(s, y["site"]))}
    assert st[("레미콘", "25-21-08")]["balance"] == D("180") - D("175.625")   # 여유 약 4㎥


def test_design_change_candidates_collect_evidence(world):
    fill_november(world)
    s = world["s"]
    s.add_photo(world["site"], "2026-11-14", "사진/기초타설.jpg", work_type_id=world["base"], stage="중",
                sta_from="10", sta_to="10")
    c = {x["work_type"]: x for x in alerts.design_change_candidates(s, world["site"])}
    base = {d["item"]: d for d in c["개거 기초"]["diffs"]}
    assert base["레미콘 기초 25-21-08"]["diff"] == D("17.5")              # 70 → 87.5 ㎥
    assert base["버림 콘크리트 25-18-08"]["actual"] == 0
    assert "개거 벽체" not in c                                           # 벽체는 설계대로
    ev = c["개거 기초"]["evidence"]
    assert len(ev["photos"]) == 1 and len(ev["inputs"]) == 1 and len(ev["progress"]) == 1


def test_cost_alert_when_spending_runs_ahead(world):
    s = world["s"]
    wt = s.add_work_type(world["site"], 19, "터파기", design_length=250, exec_budget=10_000_000)
    s.add_input(world["site"], "2026-11-12", "장비", "6W", 8, world["dump"], work_type_id=wt)   # 5,440,000
    s.add_progress(world["site"], "2026-11-12", wt, 100, "m", sta_from="0", sta_to="100")       # 40%
    a = alerts.cost_alerts(s, world["site"])
    assert a and a[0]["text"] == "터파기 공정률 40%, 원가 집행 54%"
    s.add_progress(world["site"], "2026-11-13", wt, 50, "m", sta_from="100", sta_to="150")      # 60%
    assert alerts.cost_alerts(s, world["site"]) == []


def test_market_price_only_notifies(world):
    s = world["s"]
    s._insert("market_price", {"kind": "자재", "item": "레미콘", "spec": "25-21-08",
                               "unit_price": 104_000, "as_of": "2026-11-16", "source": "월요일 브리핑"})
    a = [x for x in alerts.rate_alerts(s) if x["kind"] == "단가 갱신"]
    assert len(a) == 1 and "+6.1%" in a[0]["text"]
    assert s.find_rate("자재", "레미콘", "25-21-08", None, "2026-11-20")["unit_price"] == 98_000   # 그대로


def test_home_shows_at_most_three_todos(world):
    h = alerts.home(world["s"], world["site"], "2026-11-15")
    assert h["todo"] == ["오늘 일지 미작성"] and all(a["level"] != "빨강" for a in h["alerts"])


# ---------- 제안 6: 말로 쓰는 일지 ----------
def test_voice_log_fills_draft_then_saves_after_confirm(world):
    s = world["s"]
    d = voice_log.parse("오늘 보통인부 4명, 포크레인 06 한 대, No.3에서 No.5까지 기초 타설", s, world["site"])
    got = {(i["kind"], i["item"]): i["qty"] for i in d["inputs"]}
    assert got == {("인력", "보통인부"): 4, ("장비", "6W"): 1}
    assert d["progress"]["label"] == "No.3 ~ No.5" and d["progress"]["length"] == 40
    assert d["progress"]["work_type"] == "개거 기초" and d["unknown"] == []
    assert s.db.execute("SELECT COUNT(*) FROM input_line").fetchone()[0] == 0     # 아직 저장 안 됨
    r = voice_log.commit(s, world["site"], "2026-11-12", d, {"보통인부": world["kim"], "6W": world["dump"]})
    assert len(r["inputs"]) == 2
    line = dict(s.db.execute("SELECT * FROM input_line WHERE item='6W'").fetchone())
    assert (line["amount"], line["sta_from"], line["sta_to"]) == (680_000, "60", "100")


def test_voice_log_variants_and_unknowns(world):
    s = world["s"]
    d = voice_log.parse("덤프 25톤 두 대, 06W 반일, 레미콘 25-21-08 12루베 반입", s, world["site"])
    got = {i["item"]: i["qty"] for i in d["inputs"]}
    assert got == {"덤프 25톤": 2, "6W": D("0.5"), "레미콘": 12}
    d2 = voice_log.parse("철근공 3명, 펌프카 한 대", s, world["site"])
    assert "기준 정보에 없는 직종: 철근공" in d2["unknown"] and "기준 단가 없음: 펌프카" in d2["unknown"]
    with pytest.raises(ValueError):
        voice_log.commit(s, world["site"], "2026-11-12", d2, {})


# ---------- 제안 5: 송장·명세서 사진 ----------
def reader(_path):
    return {"payee": "대성 중기", "work_date": "2026-11-12", "total": 1_410_000,
            "lines": [{"kind": "장비", "item": "덤프 25톤", "spec": "", "qty": 5, "unit_price": 282_000,
                       "amount": 1_410_000}]}


def test_invoice_photo_is_checked_confirmed_then_matched(world):
    fill_november(world)
    s = world["s"]
    draft = invoice_intake.intake(s, "명세서/대성중기_1112.jpg", reader)
    assert draft["problems"] == [] and draft["known_payee"]
    with pytest.raises(StoreError):
        invoice_intake.register(s, draft["parsed"], confirmed=False)
    r = invoice_intake.register(s, draft["parsed"], confirmed=True)
    assert list(r["status"].values()) == ["차이"]                        # 명세서 5대, 일지 3대
    line = s.db.execute("SELECT qty FROM input_line WHERE item='덤프 25톤'").fetchone()
    assert line["qty"] == "3"                                            # 일지는 그대로
    s.mark_invoice_error(r["invoice_ids"][0])                            # '명세서 오류'로 해소
    assert alerts.home(s, world["site"], "2026-11-14")["todo"] == []


def test_invoice_validation_catches_bad_read(world):
    bad = reader("")
    bad["total"] = 1_500_000
    bad["lines"][0]["qty"] = 4
    assert len(invoice_intake.validate(bad)) == 2
    with pytest.raises(StoreError):
        invoice_intake.register(world["s"], {**reader(""), "payee": "처음 보는 업체"}, confirmed=True)


def test_invoice_missing_in_log_can_be_added(world):
    s = world["s"]
    r = invoice_intake.register(s, reader(""), confirmed=True)
    inv = r["invoice_ids"][0]
    assert r["status"][inv] == "일지에없음"
    invoice_intake.add_missing_to_log(s, inv, world["site"])
    assert s.get("invoice", inv)["status"] == "일치"
    assert str(invoice_intake.archive_path("D:/", "요성리", "2026-11-12", "a.jpg")).endswith(
        "진성건설/요성리/거래명세서/2026-11/a.jpg")


# ---------- 백업 3곳 ----------
def test_backup_three_places_one_missing(world, tmp_path):
    fill_november(world)
    a, b = tmp_path / "집PC", tmp_path / "외장"
    a.mkdir(), b.mkdir()
    res = backup.backup(world["s"], [a, b, tmp_path / "없는폴더"], "2026-11-15")
    assert [r["ok"] for r in res] == [True, True, False]
    chk = backup.restore_check(a / "진성현장_2026-11-15.db")
    assert chk == {"integrity": "ok", "sites": 2, "logs": 4, "lines": 5}
    for day in range(16, 20):
        backup.backup(world["s"], [a], f"2026-11-{day}", keep=3)
    assert len(list(a.glob("*.db"))) == 3


def test_attendance_sheet_and_yearly_report(world, tmp_path):
    fill_november(world)
    s = world["s"]
    s.add_input(world["site"], "2026-10-20", "인력", "보통인부", 1, world["kim"])
    wb = load_workbook(excel_report.build_monthly(s, "2026-11", tmp_path))
    ws = wb["출역표"]
    head = [c.value for c in ws[3]]
    rows = {(r[0], r[1]): r for r in ws.iter_rows(min_row=4, values_only=True) if r[0]}
    kim = rows[("김반장", "보통인부")]
    assert kim[head.index("13")] == 4 and kim[head.index("일수")].startswith("=COUNT(")
    dump = rows[("대성중기", "6W")]
    assert dump[head.index("13")] == 1          # 두 현장 0.5 + 0.5 = 1
    path = excel_report.build_yearly(s, "2026", tmp_path)
    assert path.name == "연말보고_2026.xlsx"
    y = load_workbook(path)
    assert y.sheetnames == ["사람장비별", "현장별"]
    vals = {(r[0], r[4]): r for r in y["사람장비별"].iter_rows(min_row=4, values_only=True) if r[0]}
    q = vals[("김반장", "수량")]
    assert (q[4 + 10], q[4 + 11]) == (1, 4)     # 10월 1공수, 11월 4공수 (F열=1월)


# ---------- 이체 목록: 사람마다 한 건, 일당 원천세, 부가세 별도 (폰과 같은 숫자) ----------
def test_payout_list_per_person_matches_phone(world, tmp_path):
    from datetime import date, timedelta
    from jinsung import payout
    s, site, emg = world["s"], world["site"], world["emg"]
    lee = s.create_payee("이영수", "개인")
    pk1, pk2 = s.create_payee("박목수", "개인"), s.create_payee("정목수", "개인")
    dump = world["dump"]
    s.update("payee", dump, s.get("payee", dump)["version"],
             {"bank": "국민", "account_no": "123-45-678", "holder": "대성중기(주)", "pay_rule": "부가세별도"})
    s.update("payee", world["kim"], s.get("payee", world["kim"])["version"], {"bank": "농협", "account_no": "351-1111-2222-33"})
    days = [d for d in (date(2026, 11, 2) + timedelta(i) for i in range(29)) if d.weekday() < 5 and d.day != 10]
    assert len(days) == 20
    for d in days:
        ds = d.isoformat()
        s.add_input(site, ds, "인력", "보통인부", 1, world["kim"], unit_price=187000)
        s.add_input(site, ds, "인력", "보통인부", 1, lee, unit_price=187000)
        s.add_input(site, ds, "인력", "형틀목공", 1, pk1, unit_price=230000)
        s.add_input(site, ds, "인력", "형틀목공", 1, pk2, unit_price=230000)
        s.add_input(site, ds, "장비", "6W", 1, dump, unit_price=680000)
    s.add_input(emg, "2026-11-10", "인력", "보통인부", "0.5", lee, unit_price=187000)
    s.add_input(site, "2026-11-10", "인력", "보통인부", "0.5", lee, unit_price=187000)
    s.add_input(site, "2026-11-10", "인력", "보통인부", 1, world["kim"], unit_price=187000)
    po = {o["name"]: o for o in payout.month_payouts(s, "2026-11")}
    assert [po["김반장"][k] for k in ("total", "work_days", "income_tax", "local_tax", "transfer")] == \
        [3927000, 21, 20970, 2090, 3903940]
    assert po["이영수"]["income_tax"] == 20970                 # 0.5+0.5 같은 날 = 하루 일당
    assert po["박목수"]["transfer"] == 4552480 and po["박목수"]["bank"] == ""
    assert (po["대성중기"]["vat"], po["대성중기"]["transfer"]) == (1360000, 14960000)
    # 보냄 기록 → 12월 이월 0
    s.mark_paid(world["kim"], "2026-11", 3903940, "2026-12-05", deduct=23060)
    s.mark_paid(dump, "2026-11", 14960000, "2026-12-05", vat=1360000)
    po = {o["name"]: o for o in payout.month_payouts(s, "2026-11")}
    assert po["김반장"]["transfer"] == 0 and po["대성중기"]["transfer"] == 0
    dec = {o["name"]: o for o in payout.month_payouts(s, "2026-12")}
    assert "김반장" not in dec and "대성중기" not in dec
    wb = load_workbook(excel_report.build_monthly(s, "2026-11", tmp_path))
    assert wb.sheetnames[:2] == ["결제요약", "이체목록"]
    rows = {r[1]: r for r in wb["이체목록"].iter_rows(min_row=5, values_only=True) if r[0] in ("작업자", "장비", "자재·외주")}
    assert rows["김반장"][2:4] == ("농협", "351-1111-2222-33") and rows["박목수"][2] == "계좌 없음"
    assert rows["김반장"][11].startswith("=F")
