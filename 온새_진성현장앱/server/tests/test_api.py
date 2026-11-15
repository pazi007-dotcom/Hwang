"""집 PC 서버: 화면이 쓰는 요청과 HTTP 너머 동기화."""
import json
import threading
import urllib.request

import pytest

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
