"""거래명세서·송장 사진 AI 판독 (집 PC 서버에서만 실행. 폰에는 API 키를 두지 않는다).

읽은 값은 그대로 저장하지 않는다. invoice_intake.validate 검산 → 화면 확인 → 등록 순서를 지킨다.
자격 증명은 환경(ANTHROPIC_API_KEY 또는 `ant auth login` 프로필)에서 읽는다.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import re
from pathlib import Path

MODEL = "claude-opus-5-5"
PROMPT = """이 사진은 한국 건설 현장의 거래명세서 또는 레미콘 송장입니다.
아래 JSON 하나만 출력하세요. 사진에서 읽을 수 없는 값은 null 로 두고, 추측해서 채우지 마세요.

{"payee": "공급자(업체) 상호", "work_date": "YYYY-MM-DD (거래일)",
 "lines": [{"kind": "인력|장비|자재|외주", "item": "품목 또는 기종 (예: 레미콘, 덤프 25톤, 6W)",
            "spec": "규격 (예: 25-21-150). 없으면 빈 문자열", "qty": 숫자, "unit_price": 숫자 또는 null,
            "amount": 공급가액(원, 정수)}],
 "total": 합계 공급가액(원, 정수) 또는 null}"""


def read_with_claude(image_path: str) -> dict:
    import anthropic  # 서버에만 설치: pip install anthropic

    path = Path(image_path)
    media_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    data = base64.standard_b64encode(path.read_bytes()).decode("utf-8")
    client = anthropic.Anthropic()
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",          # 안전 분류기가 거절하면 대체 모델로 같은 요청을 다시 실행
        output_config={"effort": "medium"},
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}},
            {"type": "text", "text": PROMPT}]}],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("사진을 판독하지 못했습니다(모델이 요청을 거절). 직접 입력해 주세요.")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("판독 결과가 잘렸습니다. 사진을 나눠서 다시 보내 주세요.")
    text = "".join(b.text for b in response.content if b.type == "text")
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise RuntimeError("판독 결과에서 표를 찾지 못했습니다. 직접 입력해 주세요.")
    parsed = json.loads(m.group(0))
    parsed["lines"] = parsed.get("lines") or []
    return parsed
