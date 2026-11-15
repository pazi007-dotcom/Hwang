"""대표이사 직접 전송 (설계안 5장 '안전장치', 5-1 '대표이사 보고 파일명').

- 보내기 전에 대상 기간·일지 수·빠진 날짜를 확인 창에 보여 준다(precheck).
- 자동으로 보내지 않는다. 영주형이 확인(confirmed=True)한 뒤에만 보낸다.
- 실패하면 보낼 함에 남기고, 연결되면 다시 보낸다. 성공·실패는 보고 이력에 남는다.
- 전송에 성공한 달은 마감(잠금)된다. 마감된 달을 다시 보내면 '_정정' 파일이 된다.
- 메일 비밀번호는 집 PC 서버의 환경 변수에만 둔다. 폰과 저장소에는 두지 않는다.
"""
from __future__ import annotations

import json
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path
from typing import Callable

from . import excel_report, reports
from .store import Store, StoreError, new_id


def precheck(store: Store, month: str, until: str | None = None) -> dict:
    start, end = reports.month_range(month)
    sites = []
    for s in store.db.execute("SELECT * FROM site WHERE site_type IN ('정식','긴급수의') ORDER BY name"):
        if s["end_date"] and s["end_date"] < start:
            continue
        cov = reports.log_coverage(store, s["id"], month, until)
        if cov["written"] or s["site_type"] == "정식":
            sites.append({"site": s["name"], "written": cov["written"], "missing": cov["missing"]})
    summary = reports.payment_summary(store, month)
    diff = store.db.execute(
        "SELECT COUNT(*) AS n FROM invoice WHERE work_date BETWEEN ? AND ? AND status IN"
        " ('차이','일지에없음')", (start, end)).fetchone()["n"]
    return {"month": month, "period": f"{start} ~ {until or end}", "sites": sites,
            "total": summary["total"], "payees": summary["payee_count"], "diffs": diff,
            "conflicts": len(store.open_conflicts()), "corrected": store.is_locked(month)}


def compose(store: Store, month: str) -> dict:
    """제목은 파일명과 같은 형식, 본문은 세 줄."""
    reports.match_invoices(store, month)
    check = precheck(store, month)
    per_site = " / ".join(f"{s['site']} {s['합계']:,}원" for s in reports.site_inputs(store, month))
    subject = f"월말보고 {month}" + (" 정정" if check["corrected"] else "")
    body = "\n".join([
        f"1. 이달 결제 합계: {check['total']:,}원 (받는 곳 {check['payees']}곳)",
        f"2. 현장별 투입: {per_site or '없음'}",
        f"3. 확인이 필요한 차이: {check['diffs']}건",
    ])
    return {"subject": subject, "body": body, "corrected": check["corrected"]}


def send_monthly(store: Store, month: str, out_dir, recipients: list[str], *, confirmed: bool,
                 transport: Callable[[dict], None] | None = None) -> dict:
    if not confirmed:
        raise StoreError("확인 창에서 내용을 확인한 뒤 보냅니다(자동 전송 안 함).")
    if store.open_conflicts():
        raise StoreError("충돌 검토가 남아 있습니다. 먼저 골라 주세요.")
    mail = compose(store, month)
    path = excel_report.build_monthly(store, month, out_dir, corrected=mail["corrected"])
    report_id = store._insert("report_log", {
        "report_type": "월말보고", "period": month, "file_name": path.name,
        "sent_to": ", ".join(recipients), "result": "대기"})
    outbox_id = new_id()
    with store.db:
        store.db.execute(
            "INSERT INTO mail_outbox (id, subject, body, recipients, attachments, report_id, created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (outbox_id, mail["subject"], mail["body"], json.dumps(recipients),
             json.dumps([str(path)]), report_id, store._now()))
    result = flush(store, transport) if transport else {"sent": 0, "failed": 0}
    return {"file": path, "outbox_id": outbox_id, **result}


def flush(store: Store, transport: Callable[[dict], None]) -> dict:
    """보낼 함 비우기. 실패한 것은 남겨 두었다가 다음에 다시 시도한다."""
    sent = failed = 0
    for m in store.db.execute("SELECT * FROM mail_outbox WHERE status != '전송됨' ORDER BY created_at"
                              ).fetchall():
        mail = {"subject": m["subject"], "body": m["body"],
                "recipients": json.loads(m["recipients"]), "attachments": json.loads(m["attachments"])}
        try:
            transport(mail)
        except Exception as exc:  # noqa: BLE001 — 실패 사유를 남기고 다음 메일로
            failed += 1
            with store.db:
                store.db.execute("UPDATE mail_outbox SET status='실패', tries=tries+1, last_error=?"
                                 " WHERE id=?", (str(exc), m["id"]))
                store.db.execute("UPDATE report_log SET result=? WHERE id=?",
                                 (f"실패: {exc}", m["report_id"]))
            continue
        sent += 1
        now = store._now()
        with store.db:
            store.db.execute("UPDATE mail_outbox SET status='전송됨', tries=tries+1, sent_at=?,"
                             " last_error=NULL WHERE id=?", (now, m["id"]))
            store.db.execute("UPDATE report_log SET result='전송됨', sent_at=? WHERE id=?",
                             (now, m["report_id"]))
        rep = store.db.execute("SELECT * FROM report_log WHERE id=?", (m["report_id"],)).fetchone()
        if rep and rep["report_type"] == "월말보고":
            store.lock_month(rep["period"])        # 보낸 달은 마감
    return {"sent": sent, "failed": failed}


def smtp_transport(host: str | None = None, port: int | None = None, user: str | None = None,
                   password: str | None = None) -> Callable[[dict], None]:
    """집 PC 서버용. 값은 환경 변수(JINSUNG_SMTP_HOST/PORT/USER/PASSWORD)에서 읽는다."""
    host = host or os.environ["JINSUNG_SMTP_HOST"]
    port = port or int(os.environ.get("JINSUNG_SMTP_PORT", "587"))
    user = user or os.environ["JINSUNG_SMTP_USER"]
    password = password or os.environ["JINSUNG_SMTP_PASSWORD"]

    def send(mail: dict) -> None:
        msg = EmailMessage()
        msg["Subject"], msg["From"], msg["To"] = mail["subject"], user, ", ".join(mail["recipients"])
        msg.set_content(mail["body"])
        for a in mail["attachments"]:
            p = Path(a)
            msg.add_attachment(p.read_bytes(), maintype="application",
                               subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               filename=p.name)
        with smtplib.SMTP(host, port, timeout=30) as smtp:
            smtp.starttls()
            smtp.login(user, password)
            smtp.send_message(msg)
    return send
