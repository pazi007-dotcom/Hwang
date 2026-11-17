"""실제 SMTP 전송 코드를 가짜 메일 서버(aiosmtpd)로 끝까지 통과시킨다.
보고 HTML 본문 + 글자 본문 + Excel 첨부, 한글 제목, 로그인, 실패 → 보낼 함 → 다시 보냄."""
import email
from email import policy

import pytest

aiosmtpd = pytest.importorskip("aiosmtpd")
from aiosmtpd.controller import Controller          # noqa: E402
from aiosmtpd.smtp import AuthResult, LoginPassword  # noqa: E402

from jinsung import Store, api, mailer, sync        # noqa: E402
from jinsung.seed_rates import load_draft_rates     # noqa: E402


class Box:
    def __init__(self):
        self.got = []

    async def handle_DATA(self, server, session, envelope):
        self.got.append((envelope.rcpt_tos, envelope.content))
        return "250 OK"


def auth(server, session, envelope, mechanism, data):
    ok = isinstance(data, LoginPassword) and data.login == b"jinsung@example.com" and data.password == b"app-pw"
    return AuthResult(success=ok)


@pytest.fixture
def smtp():
    box = Box()
    c = Controller(box, hostname="127.0.0.1", port=8026, authenticator=auth, auth_require_tls=False)
    c.start()
    yield box
    c.stop()


def world():
    s = Store()
    load_draft_rates(s)
    site = s.quick_emergency_site("요성리")
    kim = s.create_payee("김반장", "개인")
    s.add_input(site, "2026-11-12", "인력", "보통인부", 1, kim, unit_price=187000)
    return s


def test_report_mail_goes_through_real_smtp(smtp, tmp_path):
    s = world()
    send = mailer.smtp_transport("127.0.0.1", 8026, "jinsung@example.com", "app-pw", tls="none")
    r = mailer.send_monthly(s, "2026-11", tmp_path, ["ceo@example.com"], confirmed=True, transport=send)
    assert r["sent"] == 1 and len(smtp.got) == 1
    rcpt, raw = smtp.got[0]
    assert rcpt == ["ceo@example.com"]
    msg = email.message_from_bytes(raw, policy=policy.default)
    assert msg["Subject"] == "월말보고 2026-11"
    assert msg.get_body(("html",)).get_content().count("결제 요청") >= 1
    assert "1. 결제 요청" in msg.get_body(("plain",)).get_content()
    files = [p.get_filename() for p in msg.iter_attachments()]
    assert files == ["월말보고_2026-11.xlsx"]
    assert s.is_locked("2026-11")


def test_wrong_password_stays_in_outbox_then_retries(smtp, tmp_path):
    s = world()
    bad = mailer.smtp_transport("127.0.0.1", 8026, "jinsung@example.com", "틀림", tls="none")
    r = mailer.send_monthly(s, "2026-11", tmp_path, ["ceo@example.com"], confirmed=True, transport=bad)
    assert r["failed"] == 1 and not smtp.got
    st = mailer.status(s)
    assert st["waiting"] == 1 and st["outbox"][0]["status"] == "실패" and st["outbox"][0]["last_error"]
    good = mailer.smtp_transport("127.0.0.1", 8026, "jinsung@example.com", "app-pw", tls="none")
    assert mailer.flush(s, good) == {"sent": 1, "failed": 0}
    assert len(smtp.got) == 1 and mailer.status(s)["waiting"] == 0


def test_phone_request_waits_then_goes_when_mail_works_again(smtp, tmp_path):
    """폰이 보낸 요청 → 메일 서버 문제로 실패(보낼 함) → 다음 맞추기 때 자동으로 다시 보내고 폰 상태도 '전송됨'."""
    s = world()
    app = api.App(s, tmp_path, transport=mailer.smtp_transport("127.0.0.1", 8026, "jinsung@example.com", "틀림", tls="none"),
                  recipients=["ceo@example.com"])
    phone = Store(device="phone")
    sync.pull(phone, lambda since: sync.changes_since(s, since, exclude_device="phone"))
    phone._insert("pay_request", {"month": "2026-11", "amount": 1, "payee_count": 1,
                                  "requested_at": "2026-12-01T07:40:00+09:00", "status": "보낼 요청"})
    sync.push(phone, app.sync_push)
    assert s.db.execute("SELECT status FROM pay_request").fetchone()["status"] == "실패"
    app.transport = mailer.smtp_transport("127.0.0.1", 8026, "jinsung@example.com", "app-pw", tls="none")
    phone._insert("site", {"name": "다음 날 접수", "site_type": "긴급수의", "status": "접수"})   # 아무 변경이나 맞추기
    sync.push(phone, app.sync_push)
    assert len(smtp.got) == 1
    q = s.db.execute("SELECT status, result FROM pay_request").fetchone()
    assert q["status"] == "전송됨"                     # 폰에도 다음 맞추기 때 '보냄'으로
    sync.pull(phone, lambda since: sync.changes_since(s, since, exclude_device="phone"))
    assert phone.db.execute("SELECT status FROM pay_request").fetchone()["status"] == "전송됨"
