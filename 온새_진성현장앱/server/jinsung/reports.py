"""집계 (설계안 5-1장). 모든 보고는 '작업일'로만 묶고, 투입 기록 줄을 더할 뿐이다."""
from __future__ import annotations

import calendar
from collections import defaultdict
from decimal import Decimal

from .store import KINDS, Store, dec


def month_range(month: str) -> tuple[str, str]:
    y, m = (int(x) for x in month.split("-"))
    last = calendar.monthrange(y, m)[1]
    return f"{y:04d}-{m:02d}-01", f"{y:04d}-{m:02d}-{last:02d}"


def _lines(store: Store, start: str, end: str):
    return store.db.execute(
        "SELECT l.*, w.work_date, w.site_id, s.name AS site_name, p.name AS payee_name"
        " FROM input_line l JOIN work_log w ON w.id = l.log_id"
        " JOIN site s ON s.id = w.site_id JOIN payee p ON p.id = l.payee_id"
        " WHERE w.work_date BETWEEN ? AND ?"
        " ORDER BY w.work_date, s.name, l.kind", (start, end)).fetchall()


def payment_summary(store: Store, month: str) -> dict:
    """결제요약: 받는 곳 1곳 = 한 줄. 현장별 금액은 가로로, 합계는 하나."""
    start, end = month_range(month)
    by_payee: dict[str, dict] = {}
    for r in _lines(store, start, end):
        p = by_payee.setdefault(r["payee_id"], {
            "payee_id": r["payee_id"], "payee": r["payee_name"], "kinds": set(),
            "by_site": defaultdict(int), "total": 0})
        p["kinds"].add(r["kind"])
        p["by_site"][r["site_name"]] += r["amount"]
        p["total"] += r["amount"]
    rows = sorted(by_payee.values(), key=lambda p: (-p["total"], p["payee"]))
    for p in rows:
        p["kinds"] = "·".join(k for k in KINDS if k in p["kinds"])
        p["by_site"] = dict(p["by_site"])
    total = sum(p["total"] for p in rows)
    sites = {s for p in rows for s in p["by_site"]}
    return {"month": month, "total": total, "payee_count": len(rows),
            "site_count": len(sites), "rows": rows}


def site_inputs(store: Store, month: str) -> list[dict]:
    """현장별투입: 현장 1곳 = 한 줄. 인력·장비·자재·외주·합계."""
    start, end = month_range(month)
    by_site: dict[str, dict] = {}
    for r in _lines(store, start, end):
        s = by_site.setdefault(r["site_id"], {"site": r["site_name"], **{k: 0 for k in KINDS}})
        s[r["kind"]] += r["amount"]
    out = []
    for s in by_site.values():
        s["합계"] = sum(s[k] for k in KINDS)
        out.append(s)
    return sorted(out, key=lambda s: -s["합계"])


def daily_lines(store: Store, month: str, kind: str) -> list[dict]:
    """인력·장비·자재 시트의 상세 줄."""
    start, end = month_range(month)
    return [dict(r) for r in _lines(store, start, end) if r["kind"] == kind]


def log_coverage(store: Store, site_id: str, month: str, until: str | None = None) -> dict:
    """일지 작성 확인: 착공~기준일 사이 일지가 없는 날(미작성)을 알려 준다."""
    from datetime import date, timedelta
    start, end = month_range(month)
    site = store.get("site", site_id)
    if site.get("start_date") and site["start_date"] > start:
        start = site["start_date"]
    if until and until < end:
        end = until
    have = {r["work_date"] for r in store.db.execute(
        "SELECT work_date FROM work_log WHERE site_id=? AND work_date BETWEEN ? AND ?",
        (site_id, start, end))}
    d, last, missing = date.fromisoformat(start), date.fromisoformat(end), []
    while d <= last:
        if d.isoformat() not in have:
            missing.append(d.isoformat())
        d += timedelta(days=1)
    return {"written": len(have), "missing": missing}


def allocation_status(store: Store, site_id: str,
                      remaining_need: dict[tuple[str, str], object] | None = None) -> list[dict]:
    """배정 자재: 배정량 / 누계 반입 / 남은 시공 필요량 / 예상 과부족.

    누계 반입은 업무일지의 자재 줄에서만 읽는다(값의 주인 = 업무일지).
    남은 필요량은 물량산출(1m당 수량 × 남은 연장)에서 넘겨받는다. 없으면 설계 수량 − 누계 반입.
    예상 과부족 = 배정량 − (누계 반입 + 남은 필요량). 음수면 부족.
    """
    remaining_need = remaining_need or {}
    out = []
    for a in store.db.execute("SELECT * FROM allocation WHERE site_id=? ORDER BY item, spec",
                              (site_id,)):
        cum = store.db.execute(
            "SELECT l.qty FROM input_line l JOIN work_log w ON w.id=l.log_id"
            " WHERE w.site_id=? AND l.kind='자재' AND l.item=? AND l.spec=?",
            (site_id, a["item"], a["spec"])).fetchall()
        cum_in = sum((dec(r["qty"]) for r in cum), Decimal(0))
        key = (a["item"], a["spec"])
        if key in remaining_need:
            need = dec(remaining_need[key])
        else:
            need = max(dec(a["design_qty"]) - cum_in, Decimal(0))
        alloc = dec(a["alloc_qty"])
        balance = alloc - (cum_in + need)
        out.append({
            "item": a["item"], "spec": a["spec"], "unit": a["unit"], "supply": a["supply"],
            "design_qty": dec(a["design_qty"]), "alloc_qty": alloc,
            "cum_in": cum_in, "remaining_need": need, "balance": balance,
            "status": "부족 예상" if balance < 0 else "여유",
            "tracked": a["supply"] != "관급자관급", "pool": a["pool"]})
    return out


def match_invoices(store: Store, month: str) -> dict:
    """거래명세서 ↔ 일지 대조. 같은 날·같은 업체·같은 기종(품목) 줄의 합과 비교한다.
    어느 쪽 값도 고치지 않고 상태만 표시한다. '명세서오류'로 표시된 것은 건드리지 않는다."""
    start, end = month_range(month)
    counts = defaultdict(int)
    invoices = store.db.execute(
        "SELECT * FROM invoice WHERE work_date BETWEEN ? AND ?", (start, end)).fetchall()
    for inv in invoices:
        if inv["status"] == "명세서오류":
            counts["명세서오류"] += 1
            continue
        rows = store.db.execute(
            "SELECT l.amount, l.qty FROM input_line l JOIN work_log w ON w.id=l.log_id"
            " WHERE w.work_date=? AND l.payee_id=? AND l.item=? AND l.spec=?",
            (inv["work_date"], inv["payee_id"], inv["item"], inv["spec"])).fetchall()
        if not rows:
            status = "일지에없음"
        else:
            status = "일치" if sum(r["amount"] for r in rows) == inv["amount"] else "차이"
        with store.db:
            store.db.execute("UPDATE invoice SET status=? WHERE id=?", (status, inv["id"]))
        counts[status] += 1
    return dict(counts)
