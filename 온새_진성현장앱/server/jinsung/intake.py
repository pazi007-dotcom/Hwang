"""공사 건 접수 → 보류 / 취소 / 진행 → 완공 → 민원 (2026-11-16 영주형 지시).

- 긴급·견적·수의·입찰 건이 들어오면 현장 답사 전에 '접수'부터 한다. 접수하는 순간 그날 업무일지에
  [접수] 한 줄이 남는다. 모든 공사의 시작은 업무일지다.
- 보류: 그대로 보관한다(사유 기록). 다시 진행할 수 있다.
- 취소: 돈이 한 푼도 들어가지 않은 건은 파기(삭제, 이력에는 남음). 답사비 등 투입이 있었으면
  지울 수 없고 '취소' 상태로 남긴다 — 연말 집계에서 돈이 빠지면 안 되기 때문이다.
- 진행: 시작 예정일을 넣으면 인력·장비·자재 발주와 확인사항 체크가 날짜와 함께 만들어진다(schedule.py).
- 완공 뒤 민원도 같은 현장에 붙인다. 민원 처리에 들어간 인력·장비는 그 현장의 일지로 들어간다.
"""
from __future__ import annotations

from .store import Store, StoreError, parse_work_date

JOB_TYPES = ("공사", "긴급", "견적", "수의", "입찰", "민원", "기타")  # 공사 = 이미 계약한 공사
_SITE_TYPE = {"공사": "정식", "긴급": "긴급수의", "수의": "긴급수의", "견적": "긴급수의", "입찰": "정식",
              "민원": "보수기타", "기타": "보수기타"}
# 접수하자마자 생기는 필수 확인사항 (구분별)
FIRST_CHECKS = {
    "공사": ["착공계·현장대리인 서류 확인", "도면·내역 받기", "관급자재 배정 확인", "현장 안전 시설 확인"],
    "긴급": ["현장 위치·진입로 확인", "피해 범위 사진(전) 촬영", "발주처 지시 내용·범위 문서(문자)로 받기",
             "필요 장비·인력 즉시 수배"],
    "견적": ["현장 답사", "물량 실측(연장·폭·높이)", "견적서 제출 기한 확인"],
    "수의": ["현장 답사", "계약 금액·공기 확인", "도면·내역 수령", "착수 서류 확인"],
    "입찰": ["공고문 자격 조건 확인", "현장 설명회·답사 일정", "투찰 마감 일시", "내역서 수익성 검토"],
    "민원": ["민원인 연락", "현장 확인·사진", "원인 판단(하자/유지관리)", "처리 결과 통보"],
    "기타": ["현장 확인"],
}


def receive(store: Store, name: str, job_type: str, received_date: str, *, client: str | None = None,
            instructions: str | None = None, contacts: list[dict] | None = None,
            checks: list[str] | None = None, gps_lat=None, gps_lon=None) -> str:
    """접수. 이름과 구분만 있으면 된다. 나머지는 나중에 채운다."""
    if job_type not in JOB_TYPES:
        raise StoreError(f"접수 구분은 {JOB_TYPES} 중 하나입니다.")
    day = parse_work_date(received_date)
    site = store.create_site(name, _SITE_TYPE[job_type], client=client, status="접수",
                             job_type=job_type, received_date=day, instructions=instructions,
                             gps_lat=gps_lat, gps_lon=gps_lon)
    for c in contacts or []:
        add_contact(store, site, **c)
    for title in [*FIRST_CHECKS[job_type], *(checks or [])]:
        add_task(store, site, "확인", title, due_date=day)
    # 접수 즉시 업무일지에 남긴다
    log_id = store.log_for(site, day)
    row = store.get("work_log", log_id)
    text = f"[접수·{job_type}] {name}" + (f" — {instructions}" if instructions else "")
    store.update("work_log", log_id, row["version"], {"note": text})   # 작업 내용(content)은 소장 몫
    return site


def add_contact(store: Store, site_id, name, role=None, phone=None, note=None) -> str:
    return store._insert("contact", {"site_id": site_id, "name": name, "role": role,
                                     "phone": phone, "note": note})


def add_attachment(store: Store, site_id, kind, path, note=None) -> str:
    """도면·내역을 올리면 '검토 대기'가 된다. 검산을 통과한 값만 '온새 승인'으로 바뀐다(설계안 9-1)."""
    return store._insert("attachment", {"site_id": site_id, "kind": kind, "path": path, "note": note,
                                        "review": "검토 대기" if kind in ("도면", "내역") else "해당 없음"})


def add_task(store: Store, site_id, kind, title, *, due_date=None, qty=None, unit=None,
             work_type_id=None, source="직접", note=None) -> str:
    return store._insert("site_task", {
        "site_id": site_id, "kind": kind, "title": title,
        "due_date": parse_work_date(due_date) if due_date else None,
        "qty": None if qty is None else str(qty), "unit": unit, "work_type_id": work_type_id,
        "source": source, "note": note})


def check(store: Store, task_id: str, done_date: str, done: bool = True) -> None:
    row = store.get("site_task", task_id)
    store.update("site_task", task_id, row["version"],
                 {"done": int(done), "done_date": parse_work_date(done_date) if done else None})


def _set_status(store: Store, site_id: str, status: str, **more) -> None:
    row = store.get("site", site_id)
    store.update("site", site_id, row["version"], {"status": status, **more})


def hold(store: Store, site_id: str, reason: str) -> None:
    if not reason or not reason.strip():
        raise StoreError("보류 사유를 적어 주세요.")
    _set_status(store, site_id, "보류", status_reason=reason.strip())


def proceed(store: Store, site_id: str, planned_start: str | None = None) -> list[str]:
    """진행. 시작 예정일이 있으면 발주·체크 일정을 만든다."""
    from . import schedule
    start = parse_work_date(planned_start) if planned_start else None
    _set_status(store, site_id, "진행", status_reason=None, planned_start=start)
    return schedule.plan(store, site_id) if start else []


def complete(store: Store, site_id: str, end_date: str) -> list[str]:
    """완공. 끝나지 않은 체크가 있으면 알려 준다(막지는 않는다)."""
    _set_status(store, site_id, "완공", end_date=parse_work_date(end_date))
    return [r["title"] for r in store.db.execute(
        "SELECT title FROM site_task WHERE site_id=? AND done=0 ORDER BY due_date", (site_id,))]


def complaint(store: Store, site_id: str, received_date: str, title: str, *, contact: dict | None = None,
              note: str | None = None) -> str:
    """완공 뒤 민원. 같은 현장에 붙이고 그날 일지에도 남긴다."""
    day = parse_work_date(received_date)
    if contact:
        add_contact(store, site_id, **{"role": "민원인", **contact})
    task = add_task(store, site_id, "민원", title, due_date=day, note=note)
    log_id = store.log_for(site_id, day)
    row = store.get("work_log", log_id)
    text = "; ".join(x for x in [row["note"], f"[민원] {title}"] if x)
    store.update("work_log", log_id, row["version"], {"note": text})
    return task


def cancel(store: Store, site_id: str, reason: str) -> str:
    """취소. 투입(돈)이 없으면 파기하고 '파기'를, 있으면 '취소'로 남기고 '보관'을 돌려준다."""
    if not reason or not reason.strip():
        raise StoreError("취소 사유를 적어 주세요.")
    site = store.get("site", site_id)
    spent = store.db.execute(
        "SELECT COUNT(*) AS n FROM input_line l JOIN work_log w ON w.id=l.log_id WHERE w.site_id=?",
        (site_id,)).fetchone()["n"]
    locked = any(store.is_locked(r["work_date"][:7]) for r in store.db.execute(
        "SELECT work_date FROM work_log WHERE site_id=?", (site_id,)))
    if spent or locked:
        _set_status(store, site_id, "취소", status_reason=reason.strip())
        return "보관"
    why = f"취소 파기: {reason.strip()}"
    for table, col in (("site_task", "site_id"), ("contact", "site_id"), ("attachment", "site_id"),
                       ("photo", "site_id"), ("progress", None), ("work_log", "site_id"),
                       ("work_type", "site_id"), ("station", "site_id"), ("allocation", "site_id")):
        if table == "progress":
            rows = store.db.execute("SELECT p.id, p.version FROM progress p JOIN work_log w ON w.id=p.log_id"
                                    " WHERE w.site_id=?", (site_id,)).fetchall()
        else:
            rows = store.db.execute(f"SELECT id, version FROM {table} WHERE {col}=?", (site_id,)).fetchall()
        for r in rows:
            store.delete(table, r["id"], r["version"], reason=why)
    store.delete("site", site_id, store.get("site", site_id)["version"], reason=why)
    return "파기"


def board(store: Store) -> dict:
    """접수함: 상태별 공사 건 목록."""
    out = {k: [] for k in ("접수", "보류", "진행", "완공", "취소")}
    for s in store.db.execute("SELECT * FROM site WHERE site_type != '본사공통' ORDER BY created_at DESC"):
        open_tasks = store.db.execute("SELECT COUNT(*) AS n FROM site_task WHERE site_id=? AND done=0",
                                      (s["id"],)).fetchone()["n"]
        waiting = store.db.execute("SELECT COUNT(*) AS n FROM attachment WHERE site_id=? AND"
                                   " review IN ('검토 대기','확인 필요')", (s["id"],)).fetchone()["n"]
        out[s["status"]].append({"id": s["id"], "name": s["name"], "job_type": s["job_type"],
                                 "received_date": s["received_date"], "planned_start": s["planned_start"],
                                 "reason": s["status_reason"], "open_tasks": open_tasks,
                                 "review_waiting": waiting})
    return out
