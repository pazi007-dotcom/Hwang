"""시작 예정일 → 공정별 인력·장비·자재 발주와 확인 체크 (온새 제안).

원리: 시작 예정일에서 거꾸로 세어 '언제까지 무엇을 해 둬야 하는지'를 할 일로 만든다.
- 물량은 물량산출 템플릿(실행 단면)에서 가져온다. 사람이 다시 계산하지 않는다.
- 예정일을 바꾸면 아직 하지 않은 '온새 제안' 할 일만 새 날짜로 다시 만든다(직접 만든 것·끝낸 것은 그대로).
- 타설처럼 반복되는 공정은 블록마다 하루 전 '레미콘 n㎥ 확인'이 생긴다.
- 리드타임과 블록 주기는 가정값이다. 현장에 맞게 고친다.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal as D

from . import intake
from .store import Store, StoreError
from .templates import open_channel

# 시작 며칠 전까지 (가정값)
LEAD = {"착수 서류": 7, "철근 가공": 7, "거푸집·부속": 5, "줄눈재": 5, "장비 예약": 3, "인력 수배": 3,
        "레미콘 통보": 2, "측량": 1, "날씨": 1}
BLOCK_CYCLE_DAYS = 3        # 블록 1개: ①기초 조립·타설 → 양생·탈형 → ②벽체 조립·타설 (가정)
WALL_OFFSET_DAYS = 2        # 기초 타설 뒤 벽체 타설까지


def _d(day: str, delta: int) -> str:
    return (date.fromisoformat(day) + timedelta(days=delta)).isoformat()


def _q(x) -> str:
    return f"{D(str(x)).quantize(D('0.01')).normalize():f}"


def generic(store: Store, site_id: str, start: str) -> list[tuple]:
    """공종 템플릿이 없는 건(긴급·수의·견적)의 기본 체크."""
    return [
        ("인력", "작업 인원·직종 확정, 전날 재확인", -LEAD["인력 수배"], None, None, None),
        ("장비", "장비 기종·대수 예약 (굴삭기·덤프)", -LEAD["장비 예약"], None, None, None),
        ("자재", "자재 물량 확정·발주 (레미콘·와이어메쉬·거푸집 등)", -LEAD["레미콘 통보"], None, None, None),
        ("확인", "날씨 확인 (우천·한파 시 타설 불가)", -LEAD["날씨"], None, None, None),
        ("확인", "착수 전 사진(전) 촬영", 0, None, None, None),
        ("확인", "작업 후 사진(후) 촬영·발주처 확인", 1, None, None, None),
    ]


def channel(wts: list[dict], start: str) -> list[tuple]:
    """현장타설 개거: 준비 발주 + 블록별 타설 전날 레미콘 확인."""
    base = next((w for w in wts if w["params"].get("part") in ("base", "all", None)), wts[0])
    p = {k: v for k, v in base["params"].items() if k != "part"}
    if base["design_length"]:
        p["length"] = base["design_length"]
    r = open_channel.calc(p)
    item = lambda n: open_channel.item(r, n)      # noqa: E731
    wid = base["id"]
    wall = next((w["id"] for w in wts if w["params"].get("part") == "wall"), wid)
    out = [
        ("서류", "착공계·현장대리인·안전관리 서류 확인", -LEAD["착수 서류"], None, None, None),
        ("자재", "철근 가공 발주 (D16 U바·헌치근, D13 배력근)", -LEAD["철근 가공"],
         item("철근 합계(할증 포함)"), "ton", wid),
        ("자재", "유로폼 1세트 임대 (3012·3006·6012·6090·헌치폼)", -LEAD["거푸집·부속"],
         sum(i["qty"] for i in r["items"] if i["group"] == "유로폼 세트" and i["unit"] == "EA"), "매", wid),
        ("자재", "거푸집 부속 (웨지핀·플랫타이·파이프·기리바리)", -LEAD["거푸집·부속"],
         item("플랫타이"), "EA(플랫타이)", wid),
        ("자재", "지수판·조인트휠러·마구리 합판·실런트", -LEAD["줄눈재"], item("지수판"), "m(지수판)", wid),
        ("장비", "굴삭기·덤프·펌프카 예약", -LEAD["장비 예약"], None, None, wid),
        ("인력", "형틀목공·철근공·보통인부 수배", -LEAD["인력 수배"], None, None, wid),
        ("자재", "레미콘 전체 물량 통보 (관급 배정 확인)", -LEAD["레미콘 통보"], item("레미콘 발주"), "㎥", wid),
        ("측량", "BM 확인·규준틀·줄눈 위치(15m) 표시", -LEAD["측량"], None, None, wid),
        ("확인", "용배수관·수문 위치 확정 (벽체 조립 전)", 0, None, None, wall),
    ]
    sec = r["section"]
    for i, length in enumerate(r["blocks"], 1):
        pour = (i - 1) * BLOCK_CYCLE_DAYS + 1
        out.append(("자재", f"블록 {i} 기초 타설 레미콘·날씨 확인", pour - 1, sec["base"] * length, "㎥", wid))
        out.append(("자재", f"블록 {i} 벽체 타설 레미콘·날씨 확인", pour + WALL_OFFSET_DAYS - 1,
                    (sec["wall"] + sec["haunch"]) * length, "㎥", wall))
    return out


def plan(store: Store, site_id: str) -> list[str]:
    site = store.get("site", site_id)
    start = site["planned_start"]
    if not start:
        raise StoreError("시작 예정일을 먼저 넣어 주세요.")
    # 아직 하지 않은 '온새 제안'만 지우고 다시 만든다
    for r in store.db.execute("SELECT id, version FROM site_task WHERE site_id=? AND source='온새 제안'"
                              " AND done=0", (site_id,)).fetchall():
        store.delete("site_task", r["id"], r["version"], reason="시작 예정일 변경으로 다시 계획")
    kept = {r["title"] for r in store.db.execute(
        "SELECT title FROM site_task WHERE site_id=? AND source='온새 제안'", (site_id,))}
    wts = [{"id": w["id"], "design_length": w["design_length"],
            "params": json.loads(w["exec_params"] or w["design_params"] or "{}")}
           for w in store.db.execute("SELECT * FROM work_type WHERE site_id=? AND template_code='9'"
                                     " ORDER BY created_at", (site_id,))]
    rows = channel(wts, start) if wts else generic(store, site_id, start)
    # 접수 체크리스트에 이미 있는 일(착공 서류, 사진(전))은 같은 일을 또 만들지 않는다
    own = [r["title"] for r in store.db.execute(
        "SELECT title FROM site_task WHERE site_id=? AND source!='온새 제안'", (site_id,))]
    same = lambda t: any(k in t and any(k in o for o in own) for k in ("착공", "사진(전)"))  # noqa: E731
    ids = []
    for kind, title, offset, qty, unit, wt in rows:
        if title in kept or same(title):        # 이미 끝낸 일·체크리스트와 같은 일은 다시 만들지 않는다
            continue
        ids.append(intake.add_task(store, site_id, kind, title, due_date=_d(start, offset),
                                   qty=None if qty is None else _q(qty), unit=unit, work_type_id=wt,
                                   source="온새 제안"))
    return ids


def due(store: Store, today: str, days_ahead: int = 2, site_id: str | None = None) -> list[dict]:
    """기한이 지났거나 곧 오는 할 일 (취소·보류 건 제외)."""
    limit = _d(today, days_ahead)
    sql = ("SELECT t.*, s.name AS site_name FROM site_task t JOIN site s ON s.id=t.site_id"
           " WHERE t.done=0 AND t.due_date IS NOT NULL AND t.due_date<=? AND s.status IN ('접수','진행','완공')")
    args = [limit]
    if site_id:
        sql += " AND t.site_id=?"
        args.append(site_id)
    out = []
    for r in store.db.execute(sql + " ORDER BY t.due_date, t.created_at", args):
        gap = (date.fromisoformat(r["due_date"]) - date.fromisoformat(today)).days
        when = "오늘" if gap == 0 else (f"D-{gap}" if gap > 0 else f"{-gap}일 지남")
        qty = f" {r['qty']}{r['unit']}" if r["qty"] else ""
        out.append({**dict(r), "when": when, "level": "빨강" if gap < 0 else "주황",
                    "text": f"[{when}] {r['site_name']} · {r['title']}{qty}"})
    return out


def day_overview(store: Store, work_date: str) -> dict:
    """하루에 여러 현장을 뛴 날: 현장별 투입과, 같은 사람·장비가 하루치를 넘게 잡힌 곳."""
    sites: dict[str, dict] = {}
    load: dict[tuple, D] = {}
    for r in store.db.execute(
            "SELECT l.*, s.name AS site_name, p.name AS payee, p.payee_type FROM input_line l"
            " JOIN work_log w ON w.id=l.log_id JOIN site s ON s.id=w.site_id JOIN payee p ON p.id=l.payee_id"
            " WHERE w.work_date=? ORDER BY s.name", (work_date,)):
        st = sites.setdefault(r["site_name"], {"site": r["site_name"], "lines": 0, "amount": 0})
        st["lines"] += 1
        st["amount"] += r["amount"]
        if r["unit"] in ("일", "인") and (r["kind"] == "장비" or r["payee_type"] == "개인"):
            key = (r["payee"], r["item"], r["kind"])
            load[key] = load.get(key, D(0)) + D(r["qty"])
    warn = [{"payee": k[0], "item": k[1], "total": v,
             "text": f"{k[0]} {k[1]}: 하루에 {v}{'일' if k[2] == '장비' else '공수'} — 대수·인원이 맞는지 확인"}
            for k, v in load.items() if (k[2] == "인력" and v > 1) or (k[2] == "장비" and v != v.to_integral_value() and v > 1)]
    return {"work_date": work_date, "sites": list(sites.values()),
            "total": sum(s["amount"] for s in sites.values()), "warnings": warn}
