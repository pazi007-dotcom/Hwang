"""토공: 평균단면법 (설계안 9-1). V = (A_i + A_{i+1}) / 2 × L."""
from __future__ import annotations

from decimal import Decimal as D

from .store import dec


def average_end_area(sections: list[tuple]) -> dict:
    """sections: [(누가거리 m, 절토·터파기 면적 ㎡, 성토·되메우기 면적 ㎡), ...] 누가거리 순."""
    rows = sorted(((dec(s), dec(c), dec(f)) for s, c, f in sections), key=lambda r: r[0])
    out, cut_sum, fill_sum = [], D(0), D(0)
    for (s0, c0, f0), (s1, c1, f1) in zip(rows, rows[1:]):
        length = s1 - s0
        cut = (c0 + c1) / 2 * length
        fill = (f0 + f1) / 2 * length
        cut_sum += cut
        fill_sum += fill
        out.append({"from": s0, "to": s1, "length": length, "cut": cut, "fill": fill,
                    "cum_cut": cut_sum, "cum_fill": fill_sum})
    return {"segments": out, "cut": cut_sum, "fill": fill_sum, "surplus": cut_sum - fill_sum}


def haul(surplus, dump_capacity_m3="10", swell="1.25") -> dict:
    """잔토 반출(+) 또는 부족토 반입(−)과 덤프 대수."""
    v = dec(surplus)
    loose = abs(v) * dec(swell)
    trips = int(-(-loose // dec(dump_capacity_m3)))
    return {"kind": "잔토 반출" if v > 0 else ("부족토 반입" if v < 0 else "균형"),
            "volume": abs(v), "loose_volume": loose, "dump_trips": trips}
