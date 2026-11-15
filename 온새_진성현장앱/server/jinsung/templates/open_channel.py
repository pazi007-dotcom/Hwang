"""9. 현장타설 개거(U형). 공정 순서대로 계산한다 (설계안 8장 '검산 원칙').

단계: ①기초(양측 거푸집) → 탈형 → ②벽체·헌치(외벽 양측 + 내벽 양측) → 다음 블록.
- 거푸집 '도면 기준'(접촉면적)과 '실제 조립 기준'(패널 장수)을 따로 낸다.
- 반복자재(웨지핀·파이프·말뚝)는 ①→② 전용이므로 두 단계 중 큰 값 1회만 센다.
- 소모자재(플랫타이·반생·줄눈재)는 블록마다 더한다.

치수는 모두 m. 검증 사례: 요성리 용배수로(1.0×1.0, L=250m) — tests/test_templates.py.
"""
from __future__ import annotations

import math
from decimal import Decimal as D

DEFAULTS = {
    "inner_w": "1.0", "wall_h": "1.0", "wall_t": "0.2", "base_t": "0.2", "base_w": None,
    "haunch": "0.15", "lean_t": "0.1", "lean_w": None,          # 버림. lean_t=0 이면 없음
    "length": "250", "joint_spacing": "15",
    "concrete": "25-21-08", "lean_concrete": "25-18-08", "concrete_loss": "0.025",
    # 철근
    "ubar_spacing": "0.2", "ubar_d": "0.016", "ubar_w": "1.56", "ubar_at_center": True,
    "dist_spacing": "0.2", "dist_d": "0.013", "dist_w": "0.995", "lap_factor": "20",
    "dist_stock": "8", "haunch_bar_len": "0.736", "haunch_bars_per_ubar": 2,
    "cover_bottom": "0.05", "cover_top": "0.05", "cover_end": "0.05", "rebar_loss": "0.03",
    # 거푸집 조립 (실제 조립 기준)
    "base_form_h": "0.3", "outer_form_h": "1.2", "inner_form_h": "0.9",
    "long_module": "1.2", "short_module": "0.6", "form_t": "0.0635", "pipe_d": "0.0486",
    "pin_spacing": "0.3", "pin_min": 2, "tie_rows": 2, "tie_spacing": "0.6",
    "waler_base": 1, "waler_outer": 2, "waler_inner": 2, "pipe_len": "6", "pipe_lap": "0.3",
    "stake_spacing": "1.2", "brace_spacing": "1.8", "strut_spacing": "1.2", "strut_rows": 2,
    # 줄눈
    "waterstop_w": "0.2", "sealant_top": True,
    # 공종을 기초/벽체로 나눠 관리할 때: "all" | "base"(①기초+철근) | "wall"(②벽체·헌치)
    "part": "all",
}


def _d(v) -> D:
    return D(str(v))


def _ceil(x: D) -> int:
    return int(math.ceil(float(x) - 1e-9))


def _floor(x: D) -> int:
    return int(math.floor(float(x) + 1e-9))


def blocks(length: D, spacing: D) -> list[D]:
    """신축줄눈 간격으로 나눈 타설 블록 길이."""
    n_joint = _ceil(length / spacing) - 1
    out = [spacing] * n_joint
    out.append(length - spacing * n_joint)
    return out


def section(p: dict) -> dict:
    """단면적(㎡ = 1m당 ㎥)과 거푸집 접촉 길이(㎡/m)."""
    q = {**DEFAULTS, **p}
    iw, h, tw, tb, hh = (_d(q[k]) for k in ("inner_w", "wall_h", "wall_t", "base_t", "haunch"))
    bw = _d(q["base_w"]) if q["base_w"] else iw + 2 * tw
    lt = _d(q["lean_t"])
    lw = _d(q["lean_w"]) if q["lean_w"] else bw + D("0.2")
    sqrt2 = D(2).sqrt()
    return {
        "base_w": bw, "base": bw * tb, "wall": 2 * tw * h, "haunch": hh * hh,
        "body": bw * tb + 2 * tw * h + hh * hh,
        "lean": lw * lt if lt > 0 else D(0),
        "form_base": 2 * tb, "form_outer": 2 * h, "form_inner": 2 * (h - hh),
        "form_haunch": 2 * sqrt2 * hh,
        "form_lean": 2 * lt if lt > 0 else D(0),
        "total_h": tb + h,
    }


def _panels(L: D, long_m: D, short_m: D) -> tuple[int, int]:
    n = _floor(L / long_m)
    rem = L - n * long_m
    return n, (_ceil(rem / short_m) if rem > D("0.001") else 0)


def calc(p: dict) -> dict:
    q = {**DEFAULTS, **p}
    s = section(q)
    L, sp = _d(q["length"]), _d(q["joint_spacing"])
    blk = blocks(L, sp)
    n_joint, set_len = len(blk) - 1, max(blk)
    iw, h, tw, tb, hh = (_d(q[k]) for k in ("inner_w", "wall_h", "wall_t", "base_t", "haunch"))
    bw = s["base_w"]
    items: list[dict] = []
    checks: list[dict] = []

    def add(group, name, qty, unit, formula, spec="", use="시공", stage=""):
        items.append({"group": group, "name": name, "spec": spec, "unit": unit,
                      "qty": qty, "formula": formula, "use": use, "stage": stage})

    # ---------- 콘크리트 ----------
    loss = 1 + _d(q["concrete_loss"])
    add("콘크리트", "레미콘 기초", s["base"] * L, "㎥", f"{bw}×{tb}×{L}", q["concrete"], stage="①")
    add("콘크리트", "레미콘 벽체+헌치", (s["wall"] + s["haunch"]) * L, "㎥",
        f"(2×{tw}×{h} + {hh}²)×{L}", q["concrete"], stage="②")
    add("콘크리트", "레미콘 발주", D(_ceil(s["body"] * L * loss)), "㎥",
        f"{s['body'] * L}㎥ × {loss} 올림", q["concrete"])
    if s["lean"] > 0:
        add("콘크리트", "버림 콘크리트", s["lean"] * L, "㎥", f"{s['lean']}㎡×{L}", q["lean_concrete"],
            stage="버림")

    # ---------- 거푸집: 도면 기준(접촉면적) ----------
    add("거푸집", "기초 측면 (양측)", s["form_base"] * L, "㎡", f"2×{tb}×{L}", stage="①")
    add("거푸집", "외벽 (양측)", s["form_outer"] * L, "㎡", f"2×{h}×{L}", stage="②")
    add("거푸집", "내벽 직면 (양측)", s["form_inner"] * L, "㎡", f"2×({h}−{hh})×{L}", stage="②")
    add("거푸집", "헌치 경사면 (양측)", s["form_haunch"] * L, "㎡", f"2×√2×{hh}×{L}", stage="②")
    form_area = (s["form_base"] + s["form_outer"] + s["form_inner"] + s["form_haunch"]) * L
    add("거푸집", "유로폼 접촉면적 합계", form_area, "㎡", "기초 양측 + 외벽 + 내벽 + 헌치")

    # ---------- 거푸집: 실제 조립 기준(1세트 = 가장 긴 블록) ----------
    lm, sm = _d(q["long_module"]), _d(q["short_module"])
    n_long, n_short = _panels(set_len, lm, sm)
    n_600 = _ceil(set_len / sm)
    fb, fo, fi = _d(q["base_form_h"]), _d(q["outer_form_h"]), _d(q["inner_form_h"])
    add("유로폼 세트", "3012 (기초, 눕힘)", D(n_long * 2), "EA", f"{n_long}매 × 양측", use="반복", stage="①")
    add("유로폼 세트", "3006 (기초 보정)", D(n_short * 2), "EA", f"{n_short}매 × 양측", use="반복", stage="①")
    add("유로폼 세트", "6012 (외벽, 세움)", D(n_600 * 2), "EA", f"{n_600}매 × 양측", use="반복", stage="②")
    add("유로폼 세트", "헌치폼 150 L1200", D(n_long * 2), "EA", f"{n_long}매 × 양측", use="반복", stage="②")
    add("유로폼 세트", "헌치폼 150 L600", D(n_short * 2), "EA", f"{n_short}매 × 양측", use="반복", stage="②")
    add("유로폼 세트", "6090 (내벽)", D(n_600 * 2), "EA", f"{n_600}매 × 양측", use="반복", stage="②")
    add("유로폼 세트", "외벽 패널 전체 연장 환산(측당)", D(_ceil(L / sm)), "장",
        f"{L}m ÷ {sm}m (전용 전 총 장수)", use="참고")

    checks += [
        {"name": "기초폼 높이 ≥ 기초 두께", "ok": fb >= tb, "value": fb - tb,
         "note": f"상단 여유 {(fb - tb) * 1000:.0f}mm"},
        {"name": "외벽폼 하단 겹침 < 기초 두께", "ok": D(0) <= fo - h < tb, "value": fo - h,
         "note": f"기초 측면 겹침 {(fo - h) * 1000:.0f}mm → ②조립 전 ①탈형 필수"},
        {"name": "내벽 헌치폼+폼 ≥ 벽 높이", "ok": hh + fi >= h, "value": hh + fi - h,
         "note": f"내벽 폼 {(hh + fi - h) * 1000:.0f}mm 초과 → 타설선 표시"},
        {"name": "기초폭 = 벽체 외면 간 거리", "ok": bw == iw + 2 * tw, "value": bw - (iw + 2 * tw),
         "note": "외벽폼이 기초 측면에 밀착하려면 일치해야 함"},
    ]

    # ---------- 부속: 반복자재는 ①·② 중 큰 값 ----------
    ps, pmin = _d(q["pin_spacing"]), int(q["pin_min"])

    def pins(edge: D) -> int:
        return max(pmin, _ceil(edge / ps))

    rows_t = int(q["tie_rows"])
    pin1 = 2 * (n_long + n_short - 1) * pins(fb)
    pin2 = (2 * (n_600 - 1) * pins(fo) + 2 * (n_600 - 1) * pins(fi) + 2 * n_600 * pmin
            + 2 * (n_long + n_short - 1) * pmin + rows_t * 8)
    per_row = _ceil((set_len - _d(q["pipe_lap"])) / (_d(q["pipe_len"]) - _d(q["pipe_lap"])))
    pipe1 = int(q["waler_base"]) * 2 * per_row
    pipe2 = (int(q["waler_outer"]) + int(q["waler_inner"])) * 2 * per_row
    stake1 = 2 * (_ceil(set_len / _d(q["stake_spacing"])) + 1)
    brace2 = 2 * (_ceil(set_len / _d(q["brace_spacing"])) + 1)
    strut2 = int(q["strut_rows"]) * (_ceil(set_len / _d(q["strut_spacing"])) + 1)
    for name, a, b, unit in (("폼핀(웨지핀)", pin1, pin2, "EA"), ("비계파이프 6m(띠장)", pipe1, pipe2, "본"),
                             ("말뚝(단관 1.0m)", stake1, brace2, "EA")):
        add("부속(반복)", name, D(max(a, b)), unit, f"①{a} / ②{b} → 큰 값 1회", use="반복", stage="①→②")
    add("부속(반복)", "경사버팀(단관 1.5m)", D(brace2), "EA", "외벽 양측", use="반복", stage="②")
    add("부속(반복)", "기리바리", D(strut2), "EA",
        f"{q['strut_rows']}단, L≈{iw - 2 * (_d(q['form_t']) + _d(q['pipe_d'])):.2f}m", use="반복", stage="②")

    ts = _d(q["tie_spacing"])
    ties = sum((_floor(b / ts) + 1) * rows_t * 2 for b in blk)
    add("부속(소모)", "플랫타이", D(ties), "EA", f"{rows_t}단 × {ts}m 간격 × 양벽, 블록별 합", use="소모", stage="②")

    # ---------- 철근 ----------
    ce = _d(q["cover_end"])
    us = _d(q["ubar_spacing"])
    n_u = sum(_floor((b - 2 * ce) / us) + 1 for b in blk)
    uy = _d(q["cover_bottom"]) + _d(q["ubar_d"]) / 2
    if q["ubar_at_center"]:
        u_h = bw - tw                                   # 다리 = 각 벽체 두께 중앙
    else:
        u_h = bw - 2 * _d(q["cover_bottom"])
    leg = s["total_h"] - _d(q["cover_top"]) - uy
    u_len = u_h + 2 * leg
    u_ton = n_u * u_len * _d(q["ubar_w"]) / 1000
    add("철근", "D16 U바", u_ton, "ton", f"{n_u}본 × {u_len}m × {q['ubar_w']}kg/m", stage="①")
    h_n = n_u * int(q["haunch_bars_per_ubar"])
    h_ton = h_n * _d(q["haunch_bar_len"]) * _d(q["ubar_w"]) / 1000
    add("철근", "D16 헌치근", h_ton, "ton", f"{h_n}본 × {q['haunch_bar_len']}m", stage="①")
    ds = _d(q["dist_spacing"])
    lines = _floor(u_h / ds) + 1 + 2 * _floor(leg / ds)
    lap = _d(q["lap_factor"]) * _d(q["dist_d"])
    stock = _d(q["dist_stock"])
    d_len, laps = D(0), 0
    for b in blk:
        net = b - 2 * ce
        bars = max(1, _ceil((net - lap) / (stock - lap)))
        d_len += (net + (bars - 1) * lap) * lines
        laps += (bars - 1) * lines
    d_ton = d_len * _d(q["dist_w"]) / 1000
    add("철근", "D13 배력근", d_ton, "ton", f"{lines}본 × 블록별(겹이음 {lap}m × {laps}개소) = {d_len}m",
        stage="①")
    rl = 1 + _d(q["rebar_loss"])
    add("철근", "철근 합계(할증 포함)", (u_ton + h_ton + d_ton) * rl, "ton", f"정미 × {rl}")

    # ---------- 줄눈 ----------
    ws = (bw - tw) + 2 * (s["total_h"] - _d(q["cover_top"]) - tb / 2)
    sec = s["body"]
    seal = (iw - 2 * hh) + 2 * D(2).sqrt() * hh + 2 * (h - hh) + (2 * tw if q["sealant_top"] else 0)
    add("줄눈", "지수판", ws * n_joint, "m", f"{ws}m × {n_joint}개소", f"PVC {_d(q['waterstop_w']) * 1000:.0f}×5t",
        use="소모")
    add("줄눈", "마구리 합판", sec * (n_joint + 2), "㎡", f"{sec}㎡ × (줄눈 {n_joint} + 시·종점 2)", use="소모")
    add("줄눈", "조인트휠러", sec * n_joint, "㎡", f"{sec}㎡ × {n_joint}개소", use="소모")
    add("줄눈", "실런트", seal * n_joint, "m", f"{seal:.3f}m × {n_joint}개소", use="소모")

    part = q["part"]
    per_m = {}
    if part in ("all", "base"):            # 철근은 ①기초 단계에 전부 조립한다
        per_m = {q["concrete"]: s["base"], "D16": (u_ton + h_ton) / L, "D13": d_ton / L}
        if s["lean"] > 0:
            per_m[q["lean_concrete"]] = s["lean"]
    if part in ("all", "wall"):
        per_m[q["concrete"]] = per_m.get(q["concrete"], D(0)) + s["wall"] + s["haunch"]
    if part != "all":
        keep = ("①", "버림") if part == "base" else ("②",)
        items = [i for i in items if i["stage"] in keep]
    return {"items": items, "checks": checks, "section": s, "blocks": blk, "joints": n_joint,
            "per_m": per_m, "form_area": form_area, "ubar_count": n_u, "dist_length": d_len,
            "ties": ties, "pins": (pin1, pin2)}


def need_for(p: dict, remaining_length) -> dict:
    """남은 연장에 더 필요한 배정 자재량 (자재 배정 대비의 '남은 시공 필요량')."""
    r = calc({**p})
    return {k: v * _d(remaining_length) for k, v in r["per_m"].items()}


def item(result: dict, name: str) -> D:
    return next(i["qty"] for i in result["items"] if i["name"] == name)
