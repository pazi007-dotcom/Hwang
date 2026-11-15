"""저장 규칙 (설계안 3장 '날짜 오류를 막는 규칙', '중복·충돌을 막는 규칙', 5-1장).

규칙 요약
1. 작업일(work_date)은 사용자가 정한 날짜만 쓴다. 기록 시각·전송 시각에서 다시 뽑지 않는다.
2. 모든 투입은 반드시 하나의 현장에 속한다. 현장이 없으면 저장하지 않는다.
3. 투입은 인력·장비·자재·외주의 '줄'로 따로 저장한다. 장비 줄이 0개인 날도 정상.
4. 같은 기록을 두 기기가 동시에 고치면 덮어쓰지 않고 '충돌'로 남긴다.
5. 마감된 달의 기록은 사유 없이는 고칠 수 없고, 고치면 이력이 남는다.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Callable, Iterable

KST = timezone(timedelta(hours=9))
SCHEMA = Path(__file__).with_name("schema.sql")
KINDS = ("인력", "장비", "자재", "외주")
# 동기화하는 테이블 (기기끼리 주고받는 기록). 이력·충돌·보낼 함은 기기별로 둔다.
SYNCED = ("site", "payee", "rate", "work_type", "station", "work_log", "input_line",
          "progress", "allocation", "invoice", "photo", "level_run", "level_reading",
          "payment", "market_price", "approval", "report_log")


class StoreError(Exception):
    """사용자에게 그대로 보여 줄 수 있는 저장 오류."""


class ConflictError(StoreError):
    def __init__(self, conflict_id: str):
        super().__init__("다른 기기에서 먼저 고친 기록입니다. 충돌 검토에서 골라 주세요.")
        self.conflict_id = conflict_id


class LockedError(StoreError):
    pass


def new_id() -> str:
    return str(uuid.uuid4())


def kst_now() -> datetime:
    return datetime.now(KST)


def parse_work_date(value: str | date) -> str:
    """작업일을 'YYYY-MM-DD'로 확인한다. 시각이 붙은 값은 받지 않는다."""
    if isinstance(value, datetime):
        raise StoreError("작업일에는 시각을 넣지 않습니다. 날짜만 넣어 주세요.")
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    if len(text) != 10:
        raise StoreError(f"작업일 형식이 아닙니다: {value!r} (예: 2026-11-12)")
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise StoreError(f"없는 날짜입니다: {value!r}") from exc


def dec(value) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception as exc:  # noqa: BLE001
        raise StoreError(f"숫자가 아닙니다: {value!r}") from exc


def won(qty, unit_price) -> int:
    return int((dec(qty) * dec(unit_price)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


class Store:
    def __init__(self, path: str | Path = ":memory:", device: str = "pc",
                 clock: Callable[[], datetime] = kst_now):
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA.read_text(encoding="utf-8"))
        self.device = device
        self.clock = clock

    # ---------- 공통 ----------
    def _now(self) -> str:
        return self.clock().astimezone(KST).isoformat(timespec="seconds")

    def _insert(self, table: str, values: dict) -> str:
        values = dict(values)
        values.setdefault("id", new_id())
        now = self._now()
        values.setdefault("created_at", now)
        values.setdefault("updated_at", now)
        cols = ", ".join(values)
        marks = ", ".join("?" for _ in values)
        with self.db:
            self.db.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", list(values.values()))
            self._log_change(table, values["id"], "추가", None, values)
        return values["id"]

    def _log_change(self, table, row_id, op, base_version, data, reason=None, device=None):
        """동기화용 변경 기록. 호출하는 쪽의 트랜잭션 안에서 쓴다."""
        if table not in SYNCED and op != "마감":
            return
        self.db.execute(
            "INSERT INTO change_log (table_name, row_id, op, base_version, data_json, reason,"
            " device, at) VALUES (?,?,?,?,?,?,?,?)",
            (table, row_id, op, base_version,
             json.dumps(data, ensure_ascii=False) if data is not None else None,
             reason, device or self.device, self._now()))

    def get(self, table: str, row_id: str) -> dict:
        row = self.db.execute(f"SELECT * FROM {table} WHERE id = ?", (row_id,)).fetchone()
        if row is None:
            raise StoreError(f"{table}에 없는 기록입니다: {row_id}")
        return dict(row)

    def _history(self, table, row_id, action, before, after, reason):
        self.db.execute(
            "INSERT INTO change_history (id, table_name, row_id, action, before_json, after_json,"
            " reason, device, changed_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (new_id(), table, row_id, action,
             json.dumps(before, ensure_ascii=False) if before else None,
             json.dumps(after, ensure_ascii=False) if after else None,
             reason, self.device, self._now()))

    # ---------- 현장 ----------
    def create_site(self, name: str, site_type: str = "정식", **fields) -> str:
        if not name or not name.strip():
            raise StoreError("현장 이름을 넣어 주세요.")
        return self._insert("site", {"name": name.strip(), "site_type": site_type, **fields})

    def quick_emergency_site(self, name: str, gps_lat: float | None = None,
                             gps_lon: float | None = None) -> str:
        """긴급 현장 10초 생성: 이름과 위치만. 발주처·금액은 나중에."""
        return self.create_site(name, "긴급수의", gps_lat=gps_lat, gps_lon=gps_lon)

    def hq_site(self) -> str:
        """어디에도 속하지 않는 비용을 넣는 '본사·공통' 현장 (하나만 존재)."""
        row = self.db.execute("SELECT id FROM site WHERE site_type = '본사공통'").fetchone()
        return row["id"] if row else self.create_site("본사·공통", "본사공통")

    # ---------- 받는 곳·단가 ----------
    def create_payee(self, name: str, payee_type: str = "업체") -> str:
        return self._insert("payee", {"name": name, "payee_type": payee_type})

    def add_rate(self, kind, item, unit, unit_price, spec="", payee_id=None,
                 valid_from="2026-01-01", is_draft=False) -> str:
        if kind not in KINDS:
            raise StoreError(f"종류는 {KINDS} 중 하나입니다.")
        return self._insert("rate", {
            "kind": kind, "item": item, "spec": spec, "unit": unit,
            "unit_price": int(unit_price), "payee_id": payee_id,
            "valid_from": parse_work_date(valid_from), "is_draft": int(is_draft)})

    def find_rate(self, kind, item, spec, payee_id, work_date) -> dict | None:
        """업체 전용 단가 → 공통 단가 순. 작업일 기준으로 가장 최근 적용분."""
        rows = self.db.execute(
            "SELECT * FROM rate WHERE kind=? AND item=? AND spec=? AND valid_from<=?"
            " AND (payee_id=? OR payee_id IS NULL)"
            " ORDER BY (payee_id IS NULL), valid_from DESC LIMIT 1",
            (kind, item, spec, work_date, payee_id)).fetchone()
        return dict(rows) if rows else None

    # ---------- 일지·투입 ----------
    def log_for(self, site_id: str | None, work_date, reason: str | None = None) -> str:
        """현장+작업일의 일지를 찾거나 만든다. 현장 없이 저장하지 않는다.
        마감된 달에 기록을 더하려면 사유가 있어야 한다."""
        if not site_id:
            raise StoreError("현장을 골라 주세요. 어디에도 속하지 않으면 '본사·공통'을 고릅니다.")
        self.get("site", site_id)
        wd = parse_work_date(work_date)
        self._check_unlocked(wd, reason=reason, creating=True)
        row = self.db.execute("SELECT id FROM work_log WHERE site_id=? AND work_date=?",
                              (site_id, wd)).fetchone()
        if row:
            return row["id"]
        return self._insert("work_log", {"site_id": site_id, "work_date": wd})

    def mark_no_work(self, site_id, work_date, weather="비") -> str:
        log_id = self.log_for(site_id, work_date)
        row = self.get("work_log", log_id)
        self.update("work_log", log_id, row["version"], {"no_work": 1, "weather": weather})
        return log_id

    def add_input(self, site_id, work_date, kind, item, qty, payee_id, *, spec="",
                  unit=None, unit_price=None, work_type_id=None, sta_from=None,
                  sta_to=None, share_group=None, reason=None, amount=None) -> str:
        if kind not in KINDS:
            raise StoreError(f"종류는 {KINDS} 중 하나입니다.")
        if dec(qty) <= 0:
            raise StoreError("수량은 0보다 커야 합니다.")
        log_id = self.log_for(site_id, work_date, reason=reason)
        wd = self.get("work_log", log_id)["work_date"]
        if unit_price is None or unit is None:
            rate = self.find_rate(kind, item, spec, payee_id, wd)
            if rate is None:
                raise StoreError(f"기준 단가가 없습니다: {kind} {item} {spec}".strip())
            unit_price = rate["unit_price"] if unit_price is None else unit_price
            unit = rate["unit"] if unit is None else unit
        values = {
            "log_id": log_id, "kind": kind, "item": item, "spec": spec,
            "qty": str(dec(qty)), "unit": unit, "unit_price": int(unit_price),
            "amount": won(qty, unit_price) if amount is None else int(amount),
            "payee_id": payee_id,
            "work_type_id": work_type_id, "sta_from": sta_from, "sta_to": sta_to,
            "share_group": share_group}
        line_id = self._insert("input_line", values)
        if self.is_locked(wd[:7]):
            with self.db:
                self._history("input_line", line_id, "마감 후 추가", None, values, reason)
        return line_id

    def add_shared_input(self, work_date, kind, item, qty_total, payee_id,
                         splits: Iterable[tuple[str, object]], *, spec="",
                         unit=None, unit_price=None) -> list[str]:
        """하루에 두 현장을 오간 장비·인력. 결제는 한 번(총액 그대로), 원가는 현장별로 나눔.

        splits: [(site_id, 비율 또는 수량), ...] — 합이 qty_total이 되어야 한다.
        끝전은 마지막 현장에 붙여 현장별 금액의 합이 총액과 정확히 같게 한다.
        """
        splits = [(s, dec(q)) for s, q in splits]
        total = dec(qty_total)
        if sum(q for _, q in splits) != total:
            raise StoreError("나눈 수량의 합이 전체 수량과 다릅니다.")
        wd = parse_work_date(work_date)
        if unit_price is None or unit is None:
            rate = self.find_rate(kind, item, spec, payee_id, wd)
            if rate is None:
                raise StoreError(f"기준 단가가 없습니다: {kind} {item}")
            unit_price = rate["unit_price"] if unit_price is None else unit_price
            unit = rate["unit"] if unit is None else unit
        total_amount = won(total, unit_price)
        group = new_id()
        ids, used = [], 0
        for i, (site_id, q) in enumerate(splits):
            last = i == len(splits) - 1
            amount = total_amount - used if last else won(q, unit_price)
            used += amount
            ids.append(self.add_input(site_id, wd, kind, item, q, payee_id, spec=spec,
                                      unit=unit, unit_price=unit_price, share_group=group,
                                      amount=amount))
        return ids

    # ---------- 수정·삭제 (충돌·마감) ----------
    def _month_of_row(self, table, row) -> str | None:
        if table == "work_log":
            return row["work_date"][:7]
        if table in ("input_line", "progress"):
            return self.get("work_log", row["log_id"])["work_date"][:7]
        if table in ("invoice", "photo", "level_run"):
            return row["work_date"][:7]
        return None

    def is_locked(self, month: str) -> bool:
        return self.db.execute("SELECT 1 FROM month_lock WHERE month=?", (month,)).fetchone() is not None

    def _check_unlocked(self, work_date: str, reason, creating=False):
        if self.is_locked(work_date[:7]) and not reason:
            what = "추가" if creating else "수정"
            raise LockedError(f"{work_date[:7]}은 월말 보고를 보내 마감된 달입니다. "
                              f"{what}하려면 사유를 넣어 주세요(정정 보고서 대상).")

    def lock_month(self, month: str):
        datetime.strptime(month, "%Y-%m")
        with self.db:
            cur = self.db.execute(
                "INSERT OR IGNORE INTO month_lock (month, locked_at) VALUES (?,?)",
                (month, self._now()))
            if cur.rowcount:
                self._log_change("month_lock", month, "마감", None, {"month": month})

    def update(self, table: str, row_id: str, base_version: int, changes: dict,
               reason: str | None = None) -> int:
        """기기가 읽어 갔던 version(base_version)과 지금 version이 다르면 덮어쓰지 않는다."""
        current = self.get(table, row_id)
        if current["version"] != base_version:
            cid = new_id()
            with self.db:
                self.db.execute(
                    "INSERT INTO conflict (id, table_name, row_id, base_version, current_json,"
                    " incoming_json, device, created_at) VALUES (?,?,?,?,?,?,?,?)",
                    (cid, table, row_id, base_version,
                     json.dumps(current, ensure_ascii=False),
                     json.dumps(changes, ensure_ascii=False), self.device, self._now()))
            raise ConflictError(cid)
        month = self._month_of_row(table, current)
        if month:
            self._check_unlocked(month + "-01", reason)
        changes = dict(changes)
        if "work_date" in changes:
            changes["work_date"] = parse_work_date(changes["work_date"])
            self._check_unlocked(changes["work_date"], reason)
        if table == "input_line" and ({"qty", "unit_price"} & changes.keys()):
            qty = changes.get("qty", current["qty"])
            price = changes.get("unit_price", current["unit_price"])
            changes["qty"] = str(dec(qty))
            changes["amount"] = won(qty, price)
        for key in ("id", "version", "created_at", "updated_at"):
            changes.pop(key, None)
        new_version = base_version + 1
        sets = ", ".join(f"{k}=?" for k in changes)
        with self.db:
            self.db.execute(
                f"UPDATE {table} SET {sets}{', ' if sets else ''}version=?, updated_at=?"
                " WHERE id=? AND version=?",
                [*changes.values(), new_version, self._now(), row_id, base_version])
            self._log_change(table, row_id, "수정", base_version, changes, reason)
            if month and (self.is_locked(month) or reason):
                self._history(table, row_id, "수정", current, changes, reason)
        return new_version

    def delete(self, table: str, row_id: str, base_version: int, reason: str | None = None):
        current = self.get(table, row_id)
        if current["version"] != base_version:
            raise ConflictError(self._record_conflict_for_delete(table, current, base_version))
        month = self._month_of_row(table, current)
        if month:
            self._check_unlocked(month + "-01", reason)
        with self.db:
            self.db.execute(f"DELETE FROM {table} WHERE id=?", (row_id,))
            self._log_change(table, row_id, "삭제", base_version, None, reason)
            self._history(table, row_id, "삭제", current, None, reason)

    def _record_conflict_for_delete(self, table, current, base_version):
        cid = new_id()
        with self.db:
            self.db.execute(
                "INSERT INTO conflict (id, table_name, row_id, base_version, current_json,"
                " incoming_json, device, created_at) VALUES (?,?,?,?,?,?,?,?)",
                (cid, table, current["id"], base_version,
                 json.dumps(current, ensure_ascii=False), json.dumps({"삭제": True}),
                 self.device, self._now()))
        return cid

    def open_conflicts(self) -> list[dict]:
        return [dict(r) for r in self.db.execute(
            "SELECT * FROM conflict WHERE resolved=0 ORDER BY created_at")]

    def resolve_conflict(self, conflict_id: str, keep: str):
        """keep='current'(먼저 저장된 값 유지) 또는 'incoming'(이 기기 값 적용)."""
        c = dict(self.db.execute("SELECT * FROM conflict WHERE id=?", (conflict_id,)).fetchone())
        if keep == "incoming":
            row = self.get(c["table_name"], c["row_id"])
            self.update(c["table_name"], c["row_id"], row["version"],
                        json.loads(c["incoming_json"]), reason="충돌 검토에서 선택")
        elif keep != "current":
            raise StoreError("keep은 'current' 또는 'incoming'입니다.")
        with self.db:
            self.db.execute("UPDATE conflict SET resolved=1 WHERE id=?", (conflict_id,))

    # ---------- 공종·실적·배정·명세서 ----------
    def add_work_type(self, site_id, template_code, name, design_length=None,
                      design_params: dict | None = None, exec_params: dict | None = None,
                      exec_budget: int | None = None) -> str:
        return self._insert("work_type", {
            "site_id": site_id, "template_code": template_code, "name": name,
            "design_length": None if design_length is None else str(dec(design_length)),
            "design_params": json.dumps(design_params, ensure_ascii=False) if design_params else None,
            "exec_params": json.dumps(exec_params, ensure_ascii=False) if exec_params else None,
            "exec_budget": exec_budget})

    def add_station(self, site_id, sta_m, label, plan_elev=None, ground_elev=None) -> str:
        return self._insert("station", {
            "site_id": site_id, "sta_m": str(dec(sta_m)), "label": label,
            "plan_elev": None if plan_elev is None else str(dec(plan_elev)),
            "ground_elev": None if ground_elev is None else str(dec(ground_elev))})

    def add_photo(self, site_id, work_date, path, *, taken_at=None, work_type_id=None,
                  stage=None, sta_from=None, sta_to=None, gps_lat=None, gps_lon=None,
                  caption=None) -> str:
        self.get("site", site_id)
        return self._insert("photo", {
            "site_id": site_id, "work_date": parse_work_date(work_date), "path": path,
            "taken_at": taken_at, "work_type_id": work_type_id, "stage": stage,
            "sta_from": sta_from, "sta_to": sta_to, "gps_lat": gps_lat, "gps_lon": gps_lon,
            "caption": caption})

    def mark_paid(self, payee_id, month, amount, paid_date) -> str:
        datetime.strptime(month, "%Y-%m")
        return self._insert("payment", {"payee_id": payee_id, "month": month,
                                        "amount": int(amount),
                                        "paid_date": parse_work_date(paid_date)})

    def mark_invoice_error(self, invoice_id: str) -> None:
        """'명세서 오류'로 표시하면 차이가 해소된다(일지 값은 그대로)."""
        row = self.get("invoice", invoice_id)
        self.update("invoice", invoice_id, row["version"], {"status": "명세서오류"},
                    reason="명세서 오류로 표시")

    def add_progress(self, site_id, work_date, work_type_id, qty, unit,
                     sta_from=None, sta_to=None) -> str:
        log_id = self.log_for(site_id, work_date)
        return self._insert("progress", {"log_id": log_id, "work_type_id": work_type_id,
                                         "qty": str(dec(qty)), "unit": unit,
                                         "sta_from": sta_from, "sta_to": sta_to})

    def add_allocation(self, site_id, item, unit, design_qty, alloc_qty,
                       supply="도급자관급", spec="") -> str:
        return self._insert("allocation", {
            "site_id": site_id, "item": item, "spec": spec, "unit": unit,
            "design_qty": str(dec(design_qty)), "alloc_qty": str(dec(alloc_qty)),
            "supply": supply})

    def add_invoice(self, payee_id, work_date, kind, item, qty, amount, spec="",
                    photo_path=None) -> str:
        return self._insert("invoice", {
            "payee_id": payee_id, "work_date": parse_work_date(work_date), "kind": kind,
            "item": item, "spec": spec, "qty": str(dec(qty)), "amount": int(amount),
            "photo_path": photo_path})
