"""송장·거래명세서 사진 자동 입력 (설계안 5-1 '거래명세서 사진 받기', 11장 제안 5).

흐름: 사진 → 읽기(reader) → 사람이 확인 → 명세서 등록 → 일지와 자동 대조.
- 명세서는 일지 값을 덮어쓰지 않는다. 다르면 '차이'로만 표시한다.
- 짝이 없는 명세서는 '일지에 없는 투입'으로 알리고, 버튼 하나로 그날 일지에 추가한다.
- reader 는 갈아 끼울 수 있다. 서버에서는 AI 판독(invoice_reader.read_with_claude)을 쓴다.
"""
from __future__ import annotations

from decimal import Decimal as D
from pathlib import Path
from typing import Callable

from . import reports
from .store import KINDS, Store, StoreError, dec, parse_work_date

REQUIRED = ("payee", "work_date", "lines")


def validate(parsed: dict) -> list[str]:
    """읽은 값 검산. 통과하지 못한 항목은 사람에게 넘긴다."""
    problems = [f"빠진 값: {k}" for k in REQUIRED if not parsed.get(k)]
    if problems:
        return problems
    try:
        parse_work_date(parsed["work_date"])
    except StoreError as exc:
        problems.append(str(exc))
    total = 0
    for n, ln in enumerate(parsed["lines"], 1):
        if ln.get("kind") not in KINDS:
            problems.append(f"{n}번째 줄 종류 확인: {ln.get('kind')!r}")
        try:
            if dec(ln["qty"]) <= 0 or int(ln["amount"]) <= 0:
                problems.append(f"{n}번째 줄 수량·금액 확인")
            if ln.get("unit_price") and abs(int(dec(ln["qty"]) * dec(ln["unit_price"])) - int(ln["amount"])) > 1:
                problems.append(f"{n}번째 줄 수량×단가≠금액")
            total += int(ln["amount"])
        except (KeyError, StoreError, ValueError):
            problems.append(f"{n}번째 줄을 읽지 못함")
    if parsed.get("total") is not None and int(parsed["total"]) != total:
        problems.append(f"줄 합계 {total:,}원 ≠ 명세서 합계 {int(parsed['total']):,}원")
    return problems


def find_payee(store: Store, name: str) -> str | None:
    key = name.replace(" ", "").replace("(주)", "").replace("주식회사", "")
    for r in store.db.execute("SELECT id, name FROM payee"):
        if r["name"].replace(" ", "").replace("(주)", "").replace("주식회사", "") == key:
            return r["id"]
    return None


def register(store: Store, parsed: dict, *, confirmed: bool, create_payee: bool = False) -> dict:
    """사람이 확인한(confirmed) 판독 결과만 등록한다."""
    if not confirmed:
        raise StoreError("읽은 내용을 화면에서 확인한 뒤 저장합니다.")
    problems = validate(parsed)
    if problems:
        raise StoreError("확인 필요: " + "; ".join(problems))
    payee_id = find_payee(store, parsed["payee"])
    if payee_id is None:
        if not create_payee:
            raise StoreError(f"등록되지 않은 업체입니다: {parsed['payee']} (새 업체로 등록할지 확인)")
        payee_id = store.create_payee(parsed["payee"])
    ids = [store.add_invoice(payee_id, parsed["work_date"], ln["kind"], ln["item"], ln["qty"],
                             ln["amount"], spec=ln.get("spec", ""), photo_path=parsed.get("photo_path"))
           for ln in parsed["lines"]]
    reports.match_invoices(store, parsed["work_date"][:7])
    return {"invoice_ids": ids,
            "status": {i: store.get("invoice", i)["status"] for i in ids}}


def add_missing_to_log(store: Store, invoice_id: str, site_id: str, reason: str | None = None) -> str:
    """'일지에 없는 투입' → 그날 일지에 추가(값의 주인은 여전히 일지)."""
    inv = store.get("invoice", invoice_id)
    if inv["status"] != "일지에없음":
        raise StoreError("일지에 없는 명세서만 추가할 수 있습니다.")
    qty = dec(inv["qty"])
    unit_price = int((D(inv["amount"]) / qty).to_integral_value())
    rate = store.find_rate(inv["kind"], inv["item"], inv["spec"], inv["payee_id"], inv["work_date"])
    line = store.add_input(site_id, inv["work_date"], inv["kind"], inv["item"], qty, inv["payee_id"],
                           spec=inv["spec"], unit=rate["unit"] if rate else "식",
                           unit_price=unit_price, amount=inv["amount"],
                           reason=reason or "거래명세서로 추가")
    reports.match_invoices(store, inv["work_date"][:7])
    return line


def archive_path(root: str | Path, site_name: str, work_date: str, file_name: str) -> Path:
    """원본 사진 보관 위치: 진성건설/현장명/거래명세서/2026-11/"""
    return Path(root) / "진성건설" / site_name / "거래명세서" / work_date[:7] / file_name


def intake(store: Store, image_path: str, reader: Callable[[str], dict]) -> dict:
    """사진 한 장을 읽어 '확인 화면'에 보여 줄 초안을 만든다. 저장하지 않는다."""
    parsed = reader(image_path)
    parsed["photo_path"] = image_path
    payee_id = find_payee(store, parsed.get("payee") or "")
    return {"parsed": parsed, "problems": validate(parsed), "known_payee": payee_id is not None}
