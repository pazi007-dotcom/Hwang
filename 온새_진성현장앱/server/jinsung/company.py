"""회사 정보 (입찰 자격 판정·대표이사 메일 수신처). 실제 값은 config/company.json — 저장소에 올리지 않는다."""
from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULT = Path(__file__).resolve().parent.parent / "config" / "company.json"


def load(path: str | Path | None = None) -> dict:
    p = Path(path or os.environ.get("JINSUNG_COMPANY", DEFAULT))
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def ceo_recipients(path: str | Path | None = None) -> list[str]:
    email = load(path).get("ceo_email")
    return [email] if email else []


def can_bid(required_licenses: list[str], path: str | Path | None = None) -> dict:
    """입찰 자격 1차 판정: 요구 면허를 모두 갖고 있는가. 실적·시공능력은 '확인 필요'로 남긴다."""
    have = set(load(path).get("licenses", []))
    missing = [x for x in required_licenses if x not in have]
    return {"status": "불가" if missing else "확인 필요", "missing": missing,
            "note": "면허 충족. 지역·실적·시공능력평가액은 공고문과 대조 필요" if not missing else "면허 없음"}
