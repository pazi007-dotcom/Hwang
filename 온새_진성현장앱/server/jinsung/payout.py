"""이체 목록: 받는 사람·업체 1곳 = 이체 1건 (폰 lib/payout.dart 와 같은 계산).

- 작업자(지급 방식 '일용'): 하루 일당(여러 현장이면 합)에서 15만원 넘는 부분 × 2.7%를 소득세로.
  하루씩 더해 10원 미만 버림, 1,000원 미만이면 떼지 않음(소액부징수). 지방소득세 = 소득세의 10%(10원 미만 버림).
- '부가세별도': 이달 금액의 10%를 더해 보낸다.
- 보낼 돈 = 이달 금액 + 이월 − 소득세 − 지방소득세 + 부가세 − 이달 청구분으로 이미 보낸 돈.
"""
from __future__ import annotations

from collections import defaultdict

from . import reports
from .store import Store

PAY_RULES = ("일용", "부가세별도", "그대로")


def daily_income_tax(pay: int) -> int:
    return 0 if pay <= 150000 else (pay - 150000) * 27 // 1000


def settled_paid(store: Store, payee_id: str, month: str, before: bool = False) -> int:
    """일지 금액 기준으로 정산된 액수 = 보낸 돈 + 뗀 세금 − 더한 부가세."""
    op = "<" if before else "="
    return store.db.execute(
        f"SELECT COALESCE(SUM(amount + COALESCE(deduct,0) - COALESCE(vat,0)),0) AS a FROM payment"
        f" WHERE payee_id=? AND month {op} ?", (payee_id, month)).fetchone()["a"]


def month_payouts(store: Store, month: str) -> list[dict]:
    start, end = reports.month_range(month)
    totals: dict[str, int] = defaultdict(int)
    daily: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    kinds: dict[str, set] = defaultdict(set)
    for r in reports._lines(store, start, end):
        totals[r["payee_id"]] += r["amount"]
        kinds[r["payee_id"]].add(r["kind"])
        if r["kind"] == "인력":
            daily[r["payee_id"]][r["work_date"]] += r["amount"]
    ids = set(totals)
    for r in store.db.execute("SELECT DISTINCT payee_id FROM payment WHERE month <= ?", (month,)):
        ids.add(r["payee_id"])
    out = []
    for pid in ids:
        p = store.get("payee", pid)
        billed_before = store.db.execute(
            "SELECT COALESCE(SUM(l.amount),0) AS a FROM input_line l JOIN work_log w ON w.id=l.log_id"
            " WHERE l.payee_id=? AND w.work_date < ?", (pid, start)).fetchone()["a"]
        carry = billed_before - settled_paid(store, pid, month, before=True)
        cash = store.db.execute("SELECT COALESCE(SUM(amount),0) AS a FROM payment WHERE payee_id=? AND month=?",
                                (pid, month)).fetchone()["a"]
        total = totals.get(pid, 0)
        rule = p.get("pay_rule") or ("일용" if p["payee_type"] == "개인" else "그대로")
        tax = local = vat = 0
        if rule == "일용":
            tax = sum(daily_income_tax(v) for v in daily[pid].values()) // 10 * 10
            if tax < 1000:
                tax = 0
            local = tax // 10 // 10 * 10
        elif rule == "부가세별도":
            vat = total // 10
        if total == 0 and carry == 0 and cash == 0:
            continue
        k = kinds.get(pid, set())
        group = "작업자" if "인력" in k else "장비" if "장비" in k else "자재·외주"
        out.append({
            "payee_id": pid, "name": p["name"], "group": group, "rule": rule,
            "bank": p.get("bank") or "", "account_no": p.get("account_no") or "",
            "holder": p.get("holder") or "", "total": total, "carry": carry, "work_days": len(daily[pid]),
            "income_tax": tax, "local_tax": local, "vat": vat, "cash_paid": cash,
            "transfer": total + carry - tax - local + vat - cash,
        })
    order = ["작업자", "장비", "자재·외주"]
    out.sort(key=lambda o: (order.index(o["group"]), -o["transfer"], o["name"]))
    return out
