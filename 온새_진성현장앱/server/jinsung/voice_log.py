"""말로 쓰는 일지 (설계안 11장 제안 6).

"오늘 보통인부 4명, 포크레인 06 한 대, No.3에서 No.5까지 기초 타설" → 일지 칸 초안.
폰 안에서 규칙으로 풀기 때문에 인터넷이 없어도 된다. 저장은 화면 확인 뒤(commit)에만 한다.
"""
from __future__ import annotations

import re
from decimal import Decimal as D

from .stations import format_sta, parse_sta
from .store import Store

_NUM = {"한": 1, "두": 2, "세": 3, "네": 4, "다섯": 5, "여섯": 6, "일곱": 7, "여덟": 8,
        "아홉": 9, "열": 10, "하나": 1, "둘": 2, "셋": 3, "넷": 4, "반": D("0.5")}
_QTY = r"(\d+(?:\.\d+)?|" + "|".join(sorted(_NUM, key=len, reverse=True)) + r")"
# 현장에서 부르는 이름 → 기준 정보의 항목 이름
EQUIP_ALIASES = [
    (r"(?:포크레인|포크레인|굴삭기|백호우?)\s*(?:0?2|공이)(?:\s*[lL])?", "2L"),
    (r"(?:포크레인|굴삭기|백호우?)\s*(?:0?3|공삼)(?:\s*[wW])?", "3W"),
    (r"(?:포크레인|굴삭기|백호우?)\s*(?:0?6|공육)(?:\s*[wW])?", "6W"),
    (r"\b0?2\s*[lL]\b", "2L"), (r"\b0?3\s*[wW]\b", "3W"), (r"\b0?6\s*[wW]\b", "6W"),
    (r"덤프\s*(\d+(?:\.\d+)?)\s*톤", r"덤프 \1톤"), (r"(\d+(?:\.\d+)?)\s*톤\s*덤프", r"덤프 \1톤"),
    (r"펌프카", "펌프카"),
]
_STA = r"(?:no|넘버|측점)\s*\.?\s*\d+(?:\s*\+\s*\d+(?:\.\d+)?)?"
_RANGE = re.compile(rf"({_STA})\s*(?:에서|부터|~|-|–)\s*({_STA})\s*(?:까지)?", re.I)


def _num(tok: str) -> D:
    return D(str(_NUM[tok])) if tok in _NUM else D(tok)


def parse(text: str, store: Store, site_id: str) -> dict:
    site = store.get("site", site_id)
    iv, shift = site["sta_interval"], site["sta_label_shift"]
    rest = text
    inputs, unknown = [], []

    # 장비 (별칭을 먼저 표준 이름으로 바꾼 뒤 수량을 찾는다)
    for pat, name in EQUIP_ALIASES:
        for m in list(re.finditer(pat + rf"\s*{_QTY}?\s*(대|일|반일)?", rest)):
            item = m.expand(name) if "\\" in name else name
            g = m.groups()
            qty_tok, unit_tok = g[-2], g[-1]
            qty = D("0.5") if unit_tok == "반일" else (_num(qty_tok) if qty_tok else D(1))
            inputs.append({"kind": "장비", "item": item, "qty": qty})
            rest = rest.replace(m.group(0), " ", 1)

    # 인력: 기준 정보에 등록된 직종 이름 + 인원
    trades = [r["item"] for r in store.db.execute("SELECT DISTINCT item FROM rate WHERE kind='인력'")]
    for t in sorted(trades, key=len, reverse=True):
        m = re.search(re.escape(t) + rf"\s*{_QTY}\s*(?:명|인|사람)", rest)
        if m:
            inputs.append({"kind": "인력", "item": t, "qty": _num(m.group(1))})
            rest = rest.replace(m.group(0), " ", 1)
    for m in re.finditer(rf"([가-힣]+(?:공|인부))\s*{_QTY}\s*(?:명|인|사람)", rest):
        unknown.append(f"기준 정보에 없는 직종: {m.group(1)}")

    # 자재: 레미콘 규격 + 수량
    m = re.search(r"레미콘\s*(\d+-\d+-\d+)?\s*(\d+(?:\.\d+)?)\s*(?:루베|㎥|m3|입방)", rest)
    if m:
        inputs.append({"kind": "자재", "item": "레미콘", "spec": m.group(1) or "", "qty": D(m.group(2))})
        rest = rest.replace(m.group(0), " ", 1)

    # 측점 구간 + 공종
    progress = None
    m = _RANGE.search(rest)
    if m:
        a, b = parse_sta(m.group(1), iv, shift), parse_sta(m.group(2), iv, shift)
        if b < a:
            a, b = b, a
        wts = store.db.execute("SELECT id, name FROM work_type WHERE site_id=?", (site_id,)).fetchall()
        tail = rest[m.end():]
        wt = next((w for w in wts if any(tok and tok in tail for tok in w["name"].split())), None)
        if wt is None and len(wts) == 1:
            wt = wts[0]
        progress = {"sta_from": a, "sta_to": b, "length": b - a,
                    "label": f"{format_sta(a, iv)} ~ {format_sta(b, iv)}",
                    "work_type_id": wt["id"] if wt else None,
                    "work_type": wt["name"] if wt else None}
        if wt is None:
            unknown.append("공종을 골라 주세요")

    # 단가·업체는 기준 정보에서 채운다. 없으면 '확인 필요'
    for i in inputs:
        i.setdefault("spec", "")
        rate = store.find_rate(i["kind"], i["item"], i["spec"], None, "9999-12-31")
        i["unit_price"] = rate["unit_price"] if rate else None
        i["unit"] = rate["unit"] if rate else None
        if rate is None:
            unknown.append(f"기준 단가 없음: {i['item']} {i['spec']}".strip())
    return {"text": text, "inputs": inputs, "progress": progress, "unknown": unknown,
            "tbm": "TBM" in text.upper() or "티비엠" in text}


def commit(store: Store, site_id: str, work_date: str, draft: dict, payees: dict[str, str]) -> dict:
    """화면에서 확인한 초안을 저장한다. payees: {항목: 받는 곳 id} (화면에서 고른 값)."""
    if draft["unknown"]:
        raise ValueError("확인이 필요한 항목이 남아 있습니다: " + "; ".join(draft["unknown"]))
    ids = []
    p = draft["progress"]
    for i in draft["inputs"]:
        ids.append(store.add_input(
            site_id, work_date, i["kind"], i["item"], i["qty"], payees[i["item"]], spec=i["spec"],
            work_type_id=p["work_type_id"] if p else None,
            sta_from=str(p["sta_from"]) if p else None, sta_to=str(p["sta_to"]) if p else None))
    prog_id = None
    if p:
        prog_id = store.add_progress(site_id, work_date, p["work_type_id"], p["length"], "m",
                                     sta_from=str(p["sta_from"]), sta_to=str(p["sta_to"]))
    log_id = store.log_for(site_id, work_date)
    row = store.get("work_log", log_id)
    store.update("work_log", log_id, row["version"], {"content": draft["text"], "tbm": int(draft["tbm"])})
    return {"log_id": log_id, "inputs": ids, "progress": prog_id}
