"""홈 화면 '오늘 할 일'·경보 (설계안 5-1, 10, 11장).

- 배정 자재 예상 부족: 준공 전에 미리 알린다.
- 원가 경보(제안 7): 공종 원가 집행률이 공정률보다 10%p 이상 앞서면 알린다.
- 설계변경 후보(제안 4): 설계와 실행 수량이 5% 이상 다르면 근거 묶음을 만들어 둔다.
- 단가 갱신 필요(제안 8): 시장 단가와 기준 단가가 벌어지면 알리기만 하고 자동으로 바꾸지 않는다.
"""
from __future__ import annotations

import json
from decimal import Decimal as D

from . import reports, stations
from .store import Store, dec
from .templates import IMPLEMENTED, open_channel

COST_GAP = D("0.10")
CHANGE_GAP = D("0.05")
PRICE_GAP = D("0.03")
_REBAR = {"D16", "D13", "D10", "D19", "D22", "D25"}


def _alloc_key(k: str) -> tuple[str, str]:
    return ("철근", k) if k in _REBAR else ("레미콘", k)


def remaining_need(store: Store, site_id: str) -> dict:
    """남은 구간에 더 필요한 배정 자재량 = 1m당 수량(실행 단면) × 남은 연장."""
    need: dict[tuple[str, str], D] = {}
    for wt in store.db.execute("SELECT * FROM work_type WHERE site_id=?", (site_id,)):
        if int(wt["template_code"]) != 9 or not wt["design_length"]:
            continue
        params = json.loads(wt["exec_params"] or wt["design_params"] or "{}")
        total = dec(wt["design_length"])
        left = total - stations.progress_bar(store, wt["id"])["done_length"]
        for k, v in open_channel.need_for({**params, "length": str(total)}, max(left, D(0))).items():
            key = _alloc_key(k)
            need[key] = need.get(key, D(0)) + v
    if need:
        # 템플릿이 계산하는 종류(레미콘·철근)인데 실행 단면에서 쓰지 않는 규격 → 남은 필요량 0
        for a in store.db.execute("SELECT item, spec FROM allocation WHERE site_id=?"
                                  " AND item IN ('레미콘','철근')", (site_id,)):
            need.setdefault((a["item"], a["spec"]), D(0))
    return need


def allocation_alerts(store: Store, site_id: str) -> list[dict]:
    need = remaining_need(store, site_id)
    out = []
    for a in reports.allocation_status(store, site_id, need or None):
        if not a["tracked"]:
            continue
        used = a["cum_in"] + a["remaining_need"]
        if a["balance"] < 0:
            level, text = "빨강", f"예상 부족 {abs(a['balance']):.1f}{a['unit']}"
        elif used > a["design_qty"]:
            level, text = "주황", f"할증 여유 사용 중 (남은 여유 {a['balance']:.1f}{a['unit']})"
        elif a["cum_in"] == 0 and a["remaining_need"] == 0:
            level, text = "주황", f"배정 {a['alloc_qty']}{a['unit']} 전량 미사용 예정 (감액 대상)"
        else:
            continue
        out.append({**a, "kind": "자재 배정", "level": level,
                    "item": f"{a['item']} {a['spec']}".strip(),
                    "text": f"{a['item']} {a['spec']}: {text}"})
    return out


def cost_alerts(store: Store, site_id: str) -> list[dict]:
    out = []
    for wt in store.db.execute(
            "SELECT * FROM work_type WHERE site_id=? AND exec_budget IS NOT NULL", (site_id,)):
        spent = store.db.execute(
            "SELECT COALESCE(SUM(amount),0) AS a FROM input_line WHERE work_type_id=?",
            (wt["id"],)).fetchone()["a"]
        rate = stations.progress_bar(store, wt["id"])["rate"] or D(0)
        cost_rate = D(spent) / D(wt["exec_budget"])
        if cost_rate - rate >= COST_GAP:
            out.append({"kind": "원가 경보", "level": "빨강", "work_type": wt["name"],
                        "progress": rate, "cost": cost_rate,
                        "text": f"{wt['name']} 공정률 {rate * 100:.0f}%, 원가 집행 {cost_rate * 100:.0f}%"})
    return out


def design_change_candidates(store: Store, site_id: str) -> list[dict]:
    """설계 단면과 실행 단면의 물량 차이 5% 이상 → 설계변경 검토 자료(측점별 기록 묶음)."""
    out = []
    for wt in store.db.execute("SELECT * FROM work_type WHERE site_id=?", (site_id,)):
        code = int(wt["template_code"])
        if code not in IMPLEMENTED or not wt["exec_params"]:
            continue
        base = {"length": wt["design_length"]} if wt["design_length"] else {}
        design = IMPLEMENTED[code]({**json.loads(wt["design_params"] or "{}"), **base})
        actual = IMPLEMENTED[code]({**json.loads(wt["exec_params"]), **base})
        dq = {(i["name"], i["spec"]): i for i in design["items"] if i.get("use", "시공") == "시공"}
        aq = {(i["name"], i["spec"]): i for i in actual["items"] if i.get("use", "시공") == "시공"}
        diffs = []
        for key in sorted(set(dq) | set(aq)):
            d = dq[key]["qty"] if key in dq else D(0)
            a = aq[key]["qty"] if key in aq else D(0)
            if d == a:
                continue
            ratio = None if d == 0 else (a - d) / d
            if ratio is None or abs(ratio) >= CHANGE_GAP:
                unit = (aq.get(key) or dq[key])["unit"]
                diffs.append({"item": " ".join(k for k in key if k), "unit": unit, "design": d,
                              "actual": a, "diff": a - d, "ratio": ratio})
        if diffs:
            bar = stations.progress_bar(store, wt["id"])
            total = wt["design_length"] or "0"
            out.append({"kind": "설계변경 후보", "level": "주황", "work_type": wt["name"],
                        "diffs": diffs, "progress": bar,
                        "evidence": stations.records_at(store, site_id, 0, total),
                        "text": f"{wt['name']}: 설계와 실행 수량 차이 {len(diffs)}항목 (5% 이상)"})
    return out


def rate_alerts(store: Store) -> list[dict]:
    out = []
    for m in store.db.execute(
            "SELECT * FROM market_price m WHERE as_of = (SELECT MAX(as_of) FROM market_price"
            " WHERE kind=m.kind AND item=m.item AND spec=m.spec)"):
        r = store.find_rate(m["kind"], m["item"], m["spec"], None, m["as_of"])
        if r is None:
            continue
        gap = (D(m["unit_price"]) - D(r["unit_price"])) / D(r["unit_price"])
        if abs(gap) >= PRICE_GAP:
            name = f"{m['item']} {m['spec']}".strip()
            out.append({"kind": "단가 갱신", "level": "주황", "item": name, "gap": gap,
                        "ours": r["unit_price"], "market": m["unit_price"],
                        "text": f"{name} 단가 갱신이 필요합니다 (기준 {r['unit_price']:,}원 → 시장 "
                                f"{m['unit_price']:,}원, {gap * 100:+.1f}%)"})
    drafts = store.db.execute("SELECT COUNT(*) AS n FROM rate WHERE is_draft=1").fetchone()["n"]
    if drafts:
        out.append({"kind": "초안 단가", "level": "주황", "count": drafts,
                    "text": f"초안 단가 {drafts}건 — 실제 단가로 확인해 주세요"})
    return out


def home(store: Store, site_id: str, today: str) -> dict:
    """홈 화면 카드: 오늘 할 일(많아야 3줄) + 경보 전체."""
    todo = []
    has_log = store.db.execute("SELECT 1 FROM work_log WHERE site_id=? AND work_date=?",
                               (site_id, today)).fetchone()
    if not has_log:
        todo.append("오늘 일지 미작성")
    n_conf = len(store.open_conflicts())
    if n_conf:
        todo.append(f"충돌 검토 {n_conf}건")
    n_diff = store.db.execute("SELECT COUNT(*) AS n FROM invoice WHERE status IN ('차이','일지에없음')"
                              ).fetchone()["n"]
    if n_diff:
        todo.append(f"거래명세서 확인 {n_diff}건")
    alerts = (allocation_alerts(store, site_id) + cost_alerts(store, site_id)
              + design_change_candidates(store, site_id) + rate_alerts(store))
    alerts.sort(key=lambda a: a["level"] != "빨강")
    return {"todo": todo[:3], "alerts": alerts}
