"""측점 = 모든 기록의 주소 (설계안 11장 제안 1).

측점은 누가거리(m)로 저장하고, 화면·문서에는 'No.2+10' 형식으로 보여 준다.
도면 표기가 실제와 다르면(요성리 종단도: 시점이 'No 6'으로 표기 → 실제 No.0)
현장의 sta_label_shift 로 한 번만 치환 규칙을 정한다.
"""
from __future__ import annotations

import re
from decimal import Decimal

from .store import StoreError, dec

_PAT = re.compile(r"^\s*(?:no|넘버|측점)?\s*\.?\s*(\d+)\s*(?:\+\s*(\d+(?:\.\d+)?))?\s*$", re.I)


def parse_sta(text, interval=20, label_shift: int = 0) -> Decimal:
    """'No.2+10', 'NO.0+5.8', 'no 3', '2+10' → 누가거리(m). 숫자+'m'는 누가거리 그대로."""
    s = str(text).strip()
    if s.lower().endswith("m"):
        return dec(s[:-1])
    m = _PAT.match(s)
    if not m:
        raise StoreError(f"측점 형식이 아닙니다: {text!r} (예: No.2+10)")
    no = int(m.group(1)) + label_shift
    plus = dec(m.group(2) or 0)
    iv = dec(interval)
    if no < 0:
        raise StoreError(f"측점 치환 후 음수가 됩니다: {text!r}")
    if plus >= iv:
        raise StoreError(f"+값이 측점 간격({iv}m) 이상입니다: {text!r}")
    return no * iv + plus


def format_sta(meters, interval=20) -> str:
    m, iv = dec(meters), dec(interval)
    no = int(m // iv)
    plus = m - no * iv
    if plus == 0:
        return f"No.{no}"
    text = f"{plus:.1f}".rstrip("0").rstrip(".")
    return f"No.{no}+{text}"


def span(sta_from, sta_to) -> Decimal:
    a, b = dec(sta_from), dec(sta_to)
    if b < a:
        raise StoreError("측점 구간의 끝이 시작보다 앞입니다.")
    return b - a


def merge_ranges(ranges) -> list[tuple[Decimal, Decimal]]:
    """겹치거나 이어진 구간을 합친다. 같은 구간을 두 번 적어도 연장이 두 번 잡히지 않는다."""
    rs = sorted((dec(a), dec(b)) for a, b in ranges if a is not None and b is not None)
    out: list[tuple[Decimal, Decimal]] = []
    for a, b in rs:
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def covered_length(ranges) -> Decimal:
    return sum((b - a for a, b in merge_ranges(ranges)), Decimal(0))


def gaps(ranges, start, end) -> list[tuple[Decimal, Decimal]]:
    """아직 시공하지 않은 구간."""
    out, cur = [], dec(start)
    for a, b in merge_ranges(ranges):
        if a > cur:
            out.append((cur, min(a, dec(end))))
        cur = max(cur, b)
    if cur < dec(end):
        out.append((cur, dec(end)))
    return [(a, b) for a, b in out if b > a]


def progress_bar(store, work_type_id: str) -> dict:
    """공정 막대 지도: 공종 하나의 시공 구간·미시공 구간·공정률."""
    wt = store.get("work_type", work_type_id)
    site = store.get("site", wt["site_id"])
    iv = site["sta_interval"]
    rows = store.db.execute(
        "SELECT sta_from, sta_to FROM progress WHERE work_type_id=? AND sta_from IS NOT NULL",
        (work_type_id,)).fetchall()
    ranges = [(r["sta_from"], r["sta_to"]) for r in rows]
    done = covered_length(ranges)
    total = dec(wt["design_length"]) if wt["design_length"] else None
    return {
        "work_type": wt["name"],
        "done": [(format_sta(a, iv), format_sta(b, iv)) for a, b in merge_ranges(ranges)],
        "todo": [(format_sta(a, iv), format_sta(b, iv)) for a, b in gaps(ranges, 0, total)] if total else [],
        "done_length": done, "design_length": total,
        "rate": (done / total) if total else None,
    }


def records_at(store, site_id: str, sta_from, sta_to) -> dict:
    """한 측점 구간의 모든 기록(일지 투입·시공 실적·사진·야장)을 한 번에 모은다."""
    a, b = dec(sta_from), dec(sta_to)

    def hit(row):
        if row["sta_from"] is None:
            return False
        lo, hi = dec(row["sta_from"]), dec(row["sta_to"] or row["sta_from"])
        return lo <= b and hi >= a

    def pick(sql):
        return [dict(r) for r in store.db.execute(sql, (site_id,)) if hit(r)]

    readings = [dict(r) for r in store.db.execute(
        "SELECT r.*, n.work_date FROM level_reading r JOIN level_run n ON n.id=r.run_id"
        " WHERE n.site_id=? AND r.kind='FS'", (site_id,))
        if r["sta_m"] is not None and a <= dec(r["sta_m"]) <= b]
    return {
        "inputs": pick("SELECT l.*, w.work_date FROM input_line l JOIN work_log w ON w.id=l.log_id"
                       " WHERE w.site_id=?"),
        "progress": pick("SELECT p.*, w.work_date FROM progress p JOIN work_log w ON w.id=p.log_id"
                         " WHERE w.site_id=?"),
        "photos": pick("SELECT * FROM photo WHERE site_id=?"),
        "level": readings,
    }
