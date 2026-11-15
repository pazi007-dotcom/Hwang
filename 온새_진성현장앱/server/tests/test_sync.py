"""0단계 통과 기준: 폰과 PC에서 같은 현장을 만들고 동시에 고쳐도 자료가 사라지지 않음."""
import pytest

from jinsung import Store
from jinsung.sync import sync


@pytest.fixture
def pair():
    pc, phone = Store(device="pc"), Store(device="phone")
    site = pc.create_site("요성리 용배수로")
    p = pc.create_payee("대성중기")
    pc.add_rate("장비", "덤프 25톤", "대", 282_000)
    sync(phone, pc)
    return pc, phone, site, p


def rows(store, table):
    return {r["id"]: dict(r) for r in store.db.execute(f"SELECT * FROM {table}")}


def test_first_sync_copies_everything(pair):
    pc, phone, site, p = pair
    assert rows(phone, "site") == rows(pc, "site")
    assert rows(phone, "rate") == rows(pc, "rate")


def test_offline_input_reaches_pc(pair):
    pc, phone, site, p = pair
    phone.add_input(site, "2026-11-12", "장비", "덤프 25톤", 3, p)   # 산골, 인터넷 없음
    assert rows(pc, "input_line") == {}
    r = sync(phone, pc)
    assert r["보냄"] == 2 and r["충돌"] == 0                         # 일지 1 + 투입 1
    assert rows(pc, "input_line") == rows(phone, "input_line")
    assert sync(phone, pc) == {"보냄": 0, "받음": 0, "충돌": 0}      # 두 번 해도 그대로


def test_both_edit_same_line_keeps_both_values(pair):
    pc, phone, site, p = pair
    line = phone.add_input(site, "2026-11-12", "장비", "덤프 25톤", 3, p)
    sync(phone, pc)
    pc.update("input_line", line, 1, {"qty": "4"})       # PC에서 4대로
    phone.update("input_line", line, 1, {"qty": "5"})    # 같은 때 폰에서 5대로
    r = sync(phone, pc)
    assert r["충돌"] == 1
    # 자동으로 덮어쓰지 않는다: 양쪽 모두 먼저 저장된 값(4), 폰 값(5)은 충돌 검토에 남는다
    assert pc.get("input_line", line)["qty"] == "4"
    assert phone.get("input_line", line)["qty"] == "4"
    c = phone.open_conflicts()
    assert len(c) == 1 and '"qty": "5"' in c[0]["incoming_json"]
    # 영주형이 폰 값을 고르면 양쪽에 반영된다
    phone.resolve_conflict(c[0]["id"], "incoming")
    sync(phone, pc)
    assert pc.get("input_line", line)["qty"] == "5"
    assert pc.get("input_line", line)["amount"] == 5 * 282_000
    assert rows(pc, "input_line") == rows(phone, "input_line")


def test_both_create_same_day_log_merges_into_one(pair):
    pc, phone, site, p = pair
    pc.add_input(site, "2026-11-13", "장비", "덤프 25톤", 1, p)
    phone.add_input(site, "2026-11-13", "장비", "덤프 25톤", 2, p)
    sync(phone, pc)
    for s in (pc, phone):
        assert len(rows(s, "work_log")) == 1                 # 일지는 하나
        qty = sorted(r["qty"] for r in rows(s, "input_line").values())
        assert qty == ["1", "2"]                             # 투입 두 줄은 모두 남음
        log_id = next(iter(rows(s, "work_log")))
        assert all(r["log_id"] == log_id for r in rows(s, "input_line").values())


def test_delete_vs_edit_is_conflict_not_loss(pair):
    pc, phone, site, p = pair
    line = phone.add_input(site, "2026-11-12", "장비", "덤프 25톤", 3, p)
    sync(phone, pc)
    pc.update("input_line", line, 1, {"qty": "4"})
    phone.delete("input_line", line, 1, reason="잘못 입력")
    r = sync(phone, pc)
    assert r["충돌"] == 1
    assert pc.get("input_line", line)["qty"] == "4"
    assert phone.get("input_line", line)["qty"] == "4"       # 되살아남, 삭제 의사는 충돌 검토에


def test_month_lock_travels(pair):
    pc, phone, site, p = pair
    pc.lock_month("2026-11")
    sync(phone, pc)
    assert phone.is_locked("2026-11")


def test_three_devices_converge(pair):
    pc, phone, site, p = pair
    tablet = Store(device="tablet")
    sync(tablet, pc)
    phone.add_input(site, "2026-11-12", "장비", "덤프 25톤", 3, p)
    tablet.add_input(site, "2026-11-14", "장비", "덤프 25톤", 1, p)
    sync(phone, pc); sync(tablet, pc); sync(phone, pc)
    assert rows(pc, "input_line") == rows(phone, "input_line") == rows(tablet, "input_line")
