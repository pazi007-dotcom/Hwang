"""1. 농로 콘크리트 포장: 연장 × 폭 × 두께."""
from decimal import Decimal as D


def calc(p: dict) -> dict:
    L, W, T = D(str(p["length"])), D(str(p["width"])), D(str(p["thickness"]))
    area = L * W
    items = [
        {"name": "레미콘", "spec": p.get("concrete", "25-21-08"), "unit": "㎥", "qty": area * T,
         "formula": f"{L}m × {W}m × {T}m"},
        {"name": "비닐", "spec": "", "unit": "㎡", "qty": area, "formula": f"{L}m × {W}m"},
    ]
    if p.get("wire_mesh"):
        items.append({"name": "와이어메시", "spec": "", "unit": "㎡", "qty": area,
                      "formula": f"{L}m × {W}m"})
    if p.get("base_t"):
        items.append({"name": "보조기층", "spec": "", "unit": "㎥", "qty": area * D(str(p["base_t"])),
                      "formula": f"{L}m × {W}m × {p['base_t']}m"})
    return {"items": items, "checks": []}
