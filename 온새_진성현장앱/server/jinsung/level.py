"""스마트 야장 계산 (설계안 7장). 읽은 값만 저장하고 기계고·지반고는 항상 다시 계산한다.

기계고 HI = BM + BS,  지반고 = HI − FS,  이기점: 새 HI = (HI − TP의 FS) + 새 BS.
"""
from __future__ import annotations

from decimal import Decimal as D

from .store import Store, StoreError, dec, parse_work_date


def start_run(store: Store, site_id, work_date, bm_name, bm_elev, backsight, assumed=False) -> str:
    run = store._insert("level_run", {
        "site_id": site_id, "work_date": parse_work_date(work_date), "bm_name": bm_name,
        "bm_elev": str(dec(bm_elev)), "bm_assumed": int(assumed)})
    _read(store, run, "BS", backsight)
    return run


def _read(store, run_id, kind, value, sta_m=None, offset_m=0, value2=None) -> str:
    seq = store.db.execute("SELECT COALESCE(MAX(seq),0)+1 AS n FROM level_reading WHERE run_id=?",
                           (run_id,)).fetchone()["n"]
    return store._insert("level_reading", {
        "run_id": run_id, "seq": seq, "kind": kind,
        "sta_m": None if sta_m is None else str(dec(sta_m)), "offset_m": str(dec(offset_m)),
        "value": str(dec(value)), "value2": None if value2 is None else str(dec(value2))})


def foresight(store, run_id, sta_m, value, offset_m=0) -> str:
    return _read(store, run_id, "FS", value, sta_m, offset_m)


def turning_point(store, run_id, fs, new_bs) -> str:
    return _read(store, run_id, "TP", fs, value2=new_bs)


def close(store, run_id, fs_on_bm) -> str:
    return _read(store, run_id, "CLOSE", fs_on_bm)


def plan_elev(store: Store, site_id, sta_m) -> D | None:
    """계획고: 그 측점 값이 있으면 그대로, 없으면 앞뒤 측점 사이를 누가거리로 보간."""
    rows = [(dec(r["sta_m"]), dec(r["plan_elev"])) for r in store.db.execute(
        "SELECT sta_m, plan_elev FROM station WHERE site_id=? AND plan_elev IS NOT NULL", (site_id,))]
    rows.sort()
    s = dec(sta_m)
    for (s0, e0), (s1, e1) in zip(rows, rows[1:]):
        if s0 <= s <= s1:
            return e0 + (e1 - e0) * (s - s0) / (s1 - s0)
    for s0, e0 in rows:
        if s0 == s:
            return e0
    return None


def compute(store: Store, run_id: str, tolerance_mm_per_sqrt_km="10") -> dict:
    run = store.get("level_run", run_id)
    rows = store.db.execute("SELECT * FROM level_reading WHERE run_id=? ORDER BY seq", (run_id,)).fetchall()
    bm = dec(run["bm_elev"])
    hi, points, closure, stas = None, [], None, []
    for r in rows:
        v = dec(r["value"])
        if r["kind"] == "BS":
            hi = bm + v
        elif hi is None:
            raise StoreError("후시(BS)를 먼저 입력해 주세요.")
        elif r["kind"] == "TP":
            hi = hi - v + dec(r["value2"])
        elif r["kind"] == "FS":
            ground = hi - v
            plan = plan_elev(store, run["site_id"], r["sta_m"]) if dec(r["offset_m"]) == 0 else None
            diff = None if plan is None else ground - plan
            points.append({
                "sta_m": dec(r["sta_m"]), "offset_m": dec(r["offset_m"]), "fs": v, "hi": hi,
                "ground": ground, "plan": plan, "diff": diff,
                "work": None if diff is None else ("절토" if diff > 0 else ("성토" if diff < 0 else "계획고")),
                "depth": None if diff is None else abs(diff)})
            stas.append(dec(r["sta_m"]))
        elif r["kind"] == "CLOSE":
            err = (hi - v) - bm
            dist_km = (max(stas) - min(stas)) * 2 / 1000 if stas else D(0)
            allow = dec(tolerance_mm_per_sqrt_km) / 1000 * dist_km.sqrt()
            closure = {"error": err, "allow": allow, "ok": abs(err) <= allow}
    return {"bm": bm, "assumed": bool(run["bm_assumed"]), "points": points, "closure": closure}


def grade_plan(start_elev, end_elev, length, stations) -> list[dict]:
    """시점·종점 계획고로 모든 측점의 계획고를 누가거리로 계산."""
    e0, e1, L = dec(start_elev), dec(end_elev), dec(length)
    g = (e1 - e0) / L
    return [{"sta_m": dec(s), "plan": e0 + g * dec(s), "grade_pct": g * 100} for s in stations]


def check_flow(profile: list[tuple]) -> list[dict]:
    """수로는 물이 흘러야 한다: 하류로 갈수록 계획고가 낮아지지 않는 구간(역구배·수평)을 찾는다."""
    rows = sorted((dec(s), dec(e)) for s, e in profile)
    bad = []
    for (s0, e0), (s1, e1) in zip(rows, rows[1:]):
        if e1 >= e0:
            bad.append({"from": s0, "to": s1, "rise": e1 - e0,
                        "kind": "역구배" if e1 > e0 else "수평"})
    return bad
