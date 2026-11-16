"""집 PC 서버 (설계안 2장, 12장). 표준 라이브러리만 쓴다 — 설치할 것이 없다.

실행:  python -m jinsung.api --db D:/진성현장/jinsung.db            (집 PC)
       python -m jinsung.api --demo                                   (요성리 예시 자료로 둘러보기)

접속 범위: 기본은 이 PC(127.0.0.1)만. 폰에서 쓰려면 Tailscale 주소로 --host 를 주고,
환경 변수 JINSUNG_TOKEN 을 정해 두면 그 값을 아는 기기만 들어온다. 공유기 포트는 열지 않는다.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
import threading
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import alerts, excel_report, intake, mailer, reports, schedule, stations, sync, voice_log
from .store import Store, StoreError
from .templates import IMPLEMENTED

WEB = Path(__file__).with_name("web")


def _json(obj) -> bytes:
    def default(o):
        if isinstance(o, Decimal):
            return float(o) if o != o.to_integral_value() else int(o)
        if isinstance(o, (set, tuple)):
            return list(o)
        if isinstance(o, Path):
            return str(o)
        raise TypeError(type(o))
    return json.dumps(obj, ensure_ascii=False, default=default).encode("utf-8")


class App:
    """요청 하나를 처리하는 순수 함수 모음 (HTTP 없이도 테스트할 수 있게)."""

    def __init__(self, store: Store, out_dir: str | Path | None = None):
        self.store = store
        self.out_dir = Path(out_dir or tempfile.mkdtemp(prefix="jinsung_"))
        self.lock = threading.Lock()

    # ---- 읽기 ----
    def sites(self, **_):
        return [dict(r) for r in self.store.db.execute(
            "SELECT id, name, site_type, client, contract_amount, status, job_type FROM site"
            " WHERE status != '취소' ORDER BY (status='진행') DESC, created_at")]

    # ---- 접수함 ----
    def board(self, **_):
        return intake.board(self.store)

    def job(self, site, **_):
        s = self.store
        q = lambda sql: [dict(r) for r in s.db.execute(sql, (site,))]   # noqa: E731
        return {"site": s.get("site", site),
                "contacts": q("SELECT * FROM contact WHERE site_id=? ORDER BY created_at"),
                "attachments": q("SELECT * FROM attachment WHERE site_id=? ORDER BY created_at"),
                "tasks": q("SELECT * FROM site_task WHERE site_id=? ORDER BY done, due_date, created_at")}

    def receive(self, name, job_type, received_date, client=None, instructions=None,
                contact_name=None, contact_phone=None, contact_role=None, **_):
        contacts = [{"name": contact_name, "phone": contact_phone, "role": contact_role}] if contact_name else []
        return {"site": intake.receive(self.store, name, job_type, received_date, client=client or None,
                                       instructions=instructions or None, contacts=contacts)}

    def job_status(self, site, action, reason=None, date=None, **_):
        s = self.store
        if action == "보류":
            intake.hold(s, site, reason or "")
            return {"status": "보류"}
        if action == "취소":
            return {"status": intake.cancel(s, site, reason or "")}
        if action == "진행":
            return {"status": "진행", "tasks": len(intake.proceed(s, site, date or None))}
        if action == "완공":
            return {"status": "완공", "left": intake.complete(s, site, date)}
        raise ValueError("action 은 보류·취소·진행·완공 중 하나입니다.")

    def task_check(self, task, date, done=True, **_):
        intake.check(self.store, task, date, bool(done))
        return {"ok": True}

    def task_add(self, site, kind, title, due_date=None, **_):
        return {"task": intake.add_task(self.store, site, kind, title, due_date=due_date or None)}

    def complaint(self, site, date, title, **_):
        return {"task": intake.complaint(self.store, site, date, title)}

    def day(self, date, **_):
        return schedule.day_overview(self.store, date)

    def payees(self, **_):
        return [dict(r) for r in self.store.db.execute("SELECT id, name, payee_type FROM payee ORDER BY name")]

    def home(self, site, today, **_):
        s = self.store
        month = today[:7]
        bars = [stations.progress_bar(s, r["id"]) for r in s.db.execute(
            "SELECT id FROM work_type WHERE site_id=? AND design_length IS NOT NULL ORDER BY created_at",
            (site,))]
        cost = s.db.execute(
            "SELECT COALESCE(SUM(l.amount),0) AS a FROM input_line l JOIN work_log w ON w.id=l.log_id"
            " WHERE w.site_id=? AND substr(w.work_date,1,7)=?", (site, month)).fetchone()["a"]
        logs = [dict(r) for r in s.db.execute(
            "SELECT w.work_date, w.content, w.no_work, COALESCE(SUM(l.amount),0) AS amount,"
            " COUNT(l.id) AS lines FROM work_log w LEFT JOIN input_line l ON l.log_id=w.id"
            " WHERE w.site_id=? GROUP BY w.id ORDER BY w.work_date DESC LIMIT 7", (site,))]
        return {"site": s.get("site", site), "month_cost": cost, "bars": bars, "logs": logs,
                "locked": s.is_locked(month), **alerts.home(s, site, today)}

    def quantities(self, work_type, **_):
        wt = self.store.get("work_type", work_type)
        code = int(wt["template_code"])
        if code not in IMPLEMENTED:
            return {"name": wt["name"], "opened": False, "design": [], "exec": []}
        base = {"length": wt["design_length"]} if wt["design_length"] else {}
        design = IMPLEMENTED[code]({**json.loads(wt["design_params"] or "{}"), **base})
        actual = IMPLEMENTED[code]({**json.loads(wt["exec_params"] or wt["design_params"] or "{}"), **base})
        return {"name": wt["name"], "opened": True, "design": design["items"], "exec": actual["items"],
                "checks": actual["checks"]}

    def work_types(self, site, **_):
        return [dict(r) for r in self.store.db.execute(
            "SELECT id, name, template_code, design_length FROM work_type WHERE site_id=?", (site,))]

    def precheck(self, month, until=None, **_):
        return mailer.precheck(self.store, month, until)

    def monthly_file(self, month, **_) -> Path:
        return excel_report.build_monthly(self.store, month, self.out_dir,
                                          corrected=self.store.is_locked(month))

    # ---- 쓰기 ----
    def voice_parse(self, site, text, **_):
        return voice_log.parse(text, self.store, site)

    def voice_commit(self, site, work_date, draft, payees, **_):
        return voice_log.commit(self.store, site, work_date, draft, payees)

    def no_work(self, site, work_date, weather="비", **_):
        return {"log_id": self.store.mark_no_work(site, work_date, weather)}

    def sync_push(self, changes, **_):
        results = [sync.apply_change(self.store, c) for c in changes]
        # 폰에서 '진행 + 시작 예정일'이 올라오면 발주·체크 일정을 만든다(물량 계산은 서버 몫)
        touched = {c["row_id"] for c, r in zip(changes, results)
                   if c["table_name"] == "site" and r["status"] == "적용" and c["op"] != "삭제"
                   and ("planned_start" in (c["data_json"] or "") or c["op"] == "추가")}
        for site_id in touched:
            row = self.store.db.execute("SELECT status, planned_start FROM site WHERE id=?",
                                        (site_id,)).fetchone()
            if row and row["status"] == "진행" and row["planned_start"]:
                schedule.plan(self.store, site_id)
        return results

    def sync_pull(self, since, device, **_):
        return sync.changes_since(self.store, int(since), exclude_device=device)


GET = {"/api/sites": "sites", "/api/payees": "payees", "/api/home": "home",
       "/api/quantities": "quantities", "/api/work_types": "work_types",
       "/api/precheck": "precheck", "/api/sync/pull": "sync_pull",
       "/api/board": "board", "/api/job": "job", "/api/day": "day"}
POST = {"/api/voice/parse": "voice_parse", "/api/voice/commit": "voice_commit",
        "/api/no_work": "no_work", "/api/sync/push": "sync_push", "/api/receive": "receive",
        "/api/job/status": "job_status", "/api/task/check": "task_check", "/api/task/add": "task_add",
        "/api/complaint": "complaint"}


def make_handler(app: App, token: str | None):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # 조용히
            pass

        def _send(self, code, body: bytes, ctype="application/json; charset=utf-8", extra=None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _allowed(self) -> bool:
            return not token or self.headers.get("X-Jinsung-Token") == token

        def _run(self, name, args):
            try:
                with app.lock:
                    result = getattr(app, name)(**args)
                self._send(200, _json(result))
            except (StoreError, ValueError, NotImplementedError) as exc:
                self._send(400, _json({"error": str(exc)}))
            except (KeyError, TypeError) as exc:
                self._send(400, _json({"error": f"요청 값이 빠졌거나 잘못됐습니다: {exc}"}))

        def do_GET(self):
            url = urlparse(self.path)
            args = {k: v[0] for k, v in parse_qs(url.query).items()}
            if url.path in ("/", "/index.html"):
                return self._send(200, (WEB / "index.html").read_bytes(), "text/html; charset=utf-8")
            if not self._allowed():
                return self._send(401, _json({"error": "허용되지 않은 기기입니다."}))
            if url.path in ("/api/report/monthly", "/api/report/yearly"):
                try:
                    with app.lock:
                        path = (app.monthly_file(**args) if url.path.endswith("monthly")
                                else excel_report.build_yearly(app.store, args["year"], app.out_dir))
                except (StoreError, ValueError, KeyError) as exc:
                    return self._send(400, _json({"error": str(exc)}))
                from urllib.parse import quote
                return self._send(200, path.read_bytes(),
                                  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                  {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(path.name)}"})
            if url.path in GET:
                return self._run(GET[url.path], args)
            self._send(404, _json({"error": "없는 주소입니다."}))

        def do_POST(self):
            url = urlparse(self.path)
            if not self._allowed():
                return self._send(401, _json({"error": "허용되지 않은 기기입니다."}))
            if url.path not in POST:
                return self._send(404, _json({"error": "없는 주소입니다."}))
            try:
                args = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            except json.JSONDecodeError:
                return self._send(400, _json({"error": "JSON 형식이 아닙니다."}))
            self._run(POST[url.path], args)
    return Handler


def demo_store() -> Store:
    """요성리 예시 자료 (단가·업체·금액은 모두 예시)."""
    from . import yoseong
    from .seed_rates import load_draft_rates
    s = Store(check_same_thread=False)
    load_draft_rates(s)
    s.add_rate("자재", "레미콘", "㎥", 98_000, spec="25-21-08", is_draft=True)
    y = yoseong.seed(s)
    dump, rmc, kim = s.create_payee("대성중기(예시)"), s.create_payee("가은레미콘(예시)"), \
        s.create_payee("직영 인부(예시)", "직영")
    for day, a, b in (("2026-11-10", 0, 15), ("2026-11-11", 15, 30), ("2026-11-12", 30, 45)):
        s.add_input(y["site"], day, "인력", "보통인부", 4, kim, work_type_id=y["base"])
        s.add_input(y["site"], day, "장비", "6W", 1, dump, work_type_id=y["base"])
        s.add_input(y["site"], day, "자재", "레미콘", "5.5", rmc, spec="25-21-08",
                    work_type_id=y["base"], sta_from=str(a), sta_to=str(b))
        s.add_progress(y["site"], day, y["base"], b - a, "m", sta_from=str(a), sta_to=str(b))
    intake.proceed(s, y["site"], "2026-11-10")
    intake.receive(s, "점촌 배수로 긴급복구(예시)", "긴급", "2026-11-13", client="문경시",
                   instructions="토사 유입 구간 약 30m 준설",
                   contacts=[{"name": "담당 주무관(예시)", "role": "감독", "phone": "054-000-0000"}])
    held = intake.receive(s, "모전 농로 포장 견적(예시)", "견적", "2026-11-11")
    intake.hold(s, held, "발주처 예산 미확정")
    s.add_invoice(dump, "2026-11-12", "장비", "6W", 1, 700_000)
    reports.match_invoices(s, "2026-11")
    return s


def serve(store: Store, host="127.0.0.1", port=8765, out_dir=None):
    app = App(store, out_dir)
    httpd = ThreadingHTTPServer((host, port), make_handler(app, os.environ.get("JINSUNG_TOKEN")))
    return httpd


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="jinsung.db")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()
    st = demo_store() if a.demo else Store(a.db, check_same_thread=False)
    server = serve(st, a.host, a.port)
    print(f"진성현장 서버: http://{a.host}:{a.port}  (끝내려면 Ctrl+C)")
    server.serve_forever()
