"""집 PC 서버: 화면이 쓰는 요청과 HTTP 너머 동기화."""
import json
import threading
import urllib.request

import pytest

from jinsung import intake
from jinsung import Store, sync
from jinsung.api import App, demo_store, serve


@pytest.fixture
def live():
    store = demo_store()
    httpd = serve(store, port=0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield store, f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def call(base, path, body=None):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as res:
            return res.status, res.read(), res.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers


def test_home_and_page(live):
    store, base = live
    code, body, _ = call(base, "/")
    assert code == 200 and "진성현장".encode() in body
    site = json.loads(call(base, "/api/sites")[1])[0]["id"]
    home = json.loads(call(base, f"/api/home?site={site}&today=2026-11-13")[1])
    assert home["month_cost"] == 5_901_000 and home["todo"][0] == "오늘 일지 미작성"
    assert home["bars"][0]["done_length"] == 45


def test_voice_flow_and_errors_in_korean(live):
    store, base = live
    site = json.loads(call(base, "/api/sites")[1])[0]["id"]
    code, body, _ = call(base, "/api/voice/parse", {"site": site, "text": "보통인부 2명, No.3에서 No.4까지 기초"})
    draft = json.loads(body)
    assert code == 200 and draft["inputs"][0]["payee_id"]              # 지난번 받는 곳 추천
    payees = {draft["inputs"][0]["item"]: draft["inputs"][0]["payee_id"]}
    code, body, _ = call(base, "/api/voice/commit",
                         {"site": site, "work_date": "2026-11-13", "draft": draft, "payees": payees})
    assert code == 200
    code, body, _ = call(base, "/api/voice/commit",
                         {"site": site, "work_date": "2026-11-13T09:00", "draft": draft, "payees": payees})
    assert code == 400 and "작업일" in json.loads(body)["error"]
    assert call(base, "/api/nothing")[0] == 404


def test_monthly_download_name(live):
    store, base = live
    code, body, headers = call(base, "/api/report/monthly?month=2026-11")
    assert code == 200 and body[:2] == b"PK"
    assert "%EC%9B%94%EB%A7%90%EB%B3%B4%EA%B3%A0_2026-11.xlsx" in headers["Content-Disposition"]


def test_phone_syncs_over_http(live):
    store, base = live
    phone = Store(device="phone")

    def send(changes):
        return json.loads(call(base, "/api/sync/push", {"changes": changes})[1])

    def fetch(seq):
        return json.loads(call(base, f"/api/sync/pull?since={seq}&device=phone")[1])

    sync.pull(phone, fetch)
    site = phone.db.execute("SELECT id FROM site WHERE site_type='정식'").fetchone()["id"]
    payee = phone.db.execute("SELECT id FROM payee LIMIT 1").fetchone()["id"]
    phone.add_input(site, "2026-11-14", "인력", "보통인부", 3, payee)      # 현장에서 오프라인 입력
    assert sync.push(phone, send) == {"보냄": 2, "충돌": 0}
    assert store.db.execute("SELECT COUNT(*) FROM input_line l JOIN work_log w ON w.id=l.log_id"
                            " WHERE w.work_date='2026-11-14'").fetchone()[0] == 1


def test_token_guard(monkeypatch):
    monkeypatch.setenv("JINSUNG_TOKEN", "비밀값")
    httpd = serve(demo_store(), port=0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    assert call(base, "/api/sites")[0] == 401
    httpd.shutdown()


def test_company_info_and_license_check(tmp_path):
    from jinsung import company
    f = tmp_path / "company.json"
    f.write_text('{"licenses": ["철근콘크리트공사업", "토공사업"], "ceo_email": "ceo@example.com"}', encoding="utf-8")
    assert company.ceo_recipients(f) == ["ceo@example.com"]
    assert company.can_bid(["토공사업"], f)["status"] == "확인 필요"
    assert company.can_bid(["포장공사업"], f) == {"status": "불가", "missing": ["포장공사업"], "note": "면허 없음"}
    assert company.load(tmp_path / "없음.json") == {}


def test_phone_proceed_with_start_date_gets_schedule_back(live):
    """폰에서 접수 건을 '진행 + 시작 예정일'로 바꿔 올리면 서버가 발주·체크를 만들어 내려보낸다."""
    store, base = live
    phone = Store(device="phone")
    send = lambda ch: json.loads(call(base, "/api/sync/push", {"changes": ch})[1])      # noqa: E731
    fetch = lambda seq: json.loads(call(base, f"/api/sync/pull?since={seq}&device=phone")[1])  # noqa: E731
    sync.pull(phone, fetch)
    site = phone.db.execute("SELECT * FROM site WHERE status='접수'").fetchone()
    before = phone.db.execute("SELECT COUNT(*) FROM site_task WHERE site_id=?", (site["id"],)).fetchone()[0]
    phone.update("site", site["id"], site["version"], {"status": "진행", "planned_start": "2026-11-20"})
    sync.push(phone, send)
    sync.pull(phone, fetch)
    rows = phone.db.execute("SELECT title, due_date FROM site_task WHERE site_id=? AND source='온새 제안'"
                            " ORDER BY due_date", (site["id"],)).fetchall()
    assert len(rows) == 6 and before == len(intake.FIRST_CHECKS[site["job_type"]])
    assert (rows[0]["title"], rows[0]["due_date"]) == ("작업 인원·직종 확정, 전날 재확인", "2026-11-17")
