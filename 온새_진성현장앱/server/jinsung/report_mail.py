"""대표님께 가는 월말 보고 메일 (HTML 본문). 메일 앱·휴대폰에서 그대로 보이게 표와 인라인 스타일만 쓴다.

순서: 결제 요청(누구에게 얼마) → 현장별 한 달 집계 → 확인할 것. 숫자는 이체목록·월말 Excel과 같은 계산.
"""
from __future__ import annotations

from datetime import date
from html import escape

from . import company, mailer, payout, reports
from .store import Store

INK, SUB, LINE, HEAD, ACCENT, WARN = "#1b2430", "#5b6675", "#d9dee5", "#f3f5f8", "#1f5fbf", "#b35a00"


def _w(n) -> str:
    return f"{int(n):,}"


def _card(label, value, unit="원", accent=False):
    return (f'<td style="padding:12px 14px;border:1px solid {LINE};border-radius:8px;background:#fff;width:50%">'
            f'<div style="font-size:12px;color:{SUB}">{label}</div>'
            f'<div style="font-size:{20 if accent else 17}px;font-weight:800;color:{ACCENT if accent else INK};'
            f'margin-top:4px;white-space:nowrap">{value}<span style="font-size:12px;font-weight:600;color:{SUB}">'
            f' {unit}</span></div></td>')


def render(store: Store, month: str, sender: str = "현장소장") -> str:
    info = company.load()
    firm = info.get("name") or "진성건설"
    y, m = month[:4], int(month[5:])
    pos = [o for o in payout.month_payouts(store, month) if o["transfer"] > 0]
    pay_sum = sum(o["transfer"] for o in pos)
    gross = reports.payment_summary(store, month)["total"]
    check = mailer.precheck(store, month)
    sites = reports.site_inputs(store, month)
    workers = [o for o in pos if o["group"] == "작업자"]
    equips = [o for o in pos if o["group"] != "작업자"]

    rows = []
    for g in ("작업자", "장비", "자재·외주"):
        gl = [o for o in pos if o["group"] == g]
        if not gl:
            continue
        rows.append(f'<tr><td style="padding:12px 4px 6px;font-size:13px;font-weight:800;color:{INK};'
                    f'border-bottom:2px solid {INK}">{g} {len(gl)}{"명" if g == "작업자" else "곳"}</td>'
                    f'<td style="padding:12px 4px 6px;font-size:13px;font-weight:800;text-align:right;white-space:nowrap;'
                    f'border-bottom:2px solid {INK}">{_w(sum(o["transfer"] for o in gl))}원</td></tr>')
        for o in gl:
            acc = (f'{escape(o["bank"])} {escape(o["account_no"])}'
                   + (f' · 예금주 {escape(o["holder"])}' if o["holder"] and o["holder"] != o["name"] else "")) \
                if o["bank"] else f'<span style="color:{WARN};font-weight:700">계좌 확인 필요</span>'
            calc = [f'{o["work_days"]}일' if g == "작업자" and o["work_days"] else "", f'이달 {_w(o["total"])}']
            if o["income_tax"]:
                calc.append(f'원천세 −{_w(o["income_tax"] + o["local_tax"])}')
            if o["vat"]:
                calc.append(f'부가세 +{_w(o["vat"])}')
            if o["carry"]:
                calc.append(f'이월 {_w(o["carry"])}')
            if o["cash_paid"]:
                calc.append(f'기지급 −{_w(o["cash_paid"])}')
            rows.append(
                f'<tr><td style="padding:9px 4px;border-bottom:1px solid {LINE}">'
                f'<div style="font-size:14px;font-weight:700">{escape(o["name"])}</div>'
                f'<div style="font-size:13px;margin-top:2px">{acc}</div>'
                f'<div style="font-size:12px;color:{SUB};margin-top:2px">{" · ".join(c for c in calc if c)}</div></td>'
                f'<td style="padding:9px 4px;border-bottom:1px solid {LINE};text-align:right;vertical-align:top;'
                f'white-space:nowrap;font-size:15px;font-weight:800">{_w(o["transfer"])}</td></tr>')
    pay_table = (f'<table cellspacing="0" cellpadding="0" style="width:100%;border-collapse:collapse">{"".join(rows)}'
                 f'<tr><td style="padding:12px 4px;font-size:14px;font-weight:800">합계 '
                 f'<span style="font-size:12px;font-weight:400;color:{SUB}">(일지 금액 {_w(gross)}원)</span></td>'
                 f'<td style="padding:12px 4px;text-align:right;white-space:nowrap;font-size:17px;font-weight:800;'
                 f'color:{ACCENT}">{_w(pay_sum)}원</td></tr></table>')

    srows = "".join(
        f'<tr><td style="padding:9px 4px;border-bottom:1px solid {LINE}">'
        f'<div style="font-size:14px;font-weight:700">{escape(x["site"])}</div>'
        f'<div style="font-size:12px;color:{SUB};margin-top:2px">'
        + " · ".join(f"{k} {_w(x.get(k, 0))}" for k in ("인력", "장비", "자재", "외주") if x.get(k)) +
        f'</div></td><td style="padding:9px 4px;border-bottom:1px solid {LINE};text-align:right;vertical-align:top;'
        f'white-space:nowrap;font-size:15px;font-weight:800">{_w(x["합계"])}</td></tr>' for x in sites)
    site_table = f'<table cellspacing="0" cellpadding="0" style="width:100%;border-collapse:collapse">{srows}</table>'

    notes = []
    no_acc = [o["name"] for o in pos if not o["bank"]]
    if no_acc:
        notes.append(f"계좌 확인 필요: {', '.join(map(escape, no_acc))}")
    for x in check["sites"]:
        if x.get("type") != "정식":
            continue
        miss = [d for d in x["missing"] if date.fromisoformat(d).weekday() < 5]   # 평일만
        if miss:
            notes.append(f'{escape(x["site"])} 평일인데 일지 없는 날 {len(miss)}일: '
                         + ", ".join(f"{int(d[5:7])}/{int(d[8:])}" for d in miss))
    if check["diffs"]:
        notes.append(f'거래명세서와 차이 {check["diffs"]}건 (Excel 「거래명세서」 시트)')
    tax = sum(o["income_tax"] + o["local_tax"] for o in pos)
    if tax:
        notes.append(f"일용 원천세 {_w(tax)}원 (소득세 {_w(sum(o['income_tax'] for o in pos))} · 지방소득세 "
                     f"{_w(sum(o['local_tax'] for o in pos))}) → 다음 달 10일까지 신고·납부")
    note_html = "".join(f'<li style="margin:3px 0">{n}</li>' for n in notes) or '<li>없음</li>'

    sec = lambda t: (f'<div style="font-size:15px;font-weight:800;color:{INK};margin:26px 0 8px;'
                     f'padding-left:8px;border-left:4px solid {ACCENT}">{t}</div>')
    return f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{y}년 {m}월 월말보고</title></head>
<body style="margin:0;background:#eef1f5;font-family:'Pretendard','맑은 고딕','Malgun Gothic',sans-serif;color:{INK}">
<div style="max-width:760px;margin:0 auto;padding:12px 8px">
<div style="background:{INK};color:#fff;border-radius:10px 10px 0 0;padding:20px 22px">
<div style="font-size:13px;opacity:.75">{escape(firm)} · 월말보고</div>
<div style="font-size:21px;font-weight:800;margin-top:4px">{y}년 {m}월 결제 요청<br><span style="font-size:15px;font-weight:600;opacity:.85">한 달 집계</span></div>
<div style="font-size:13px;opacity:.75;margin-top:6px">대상 {check["period"]} · {escape(sender)} → 대표님</div>
</div>
<div style="background:#fff;border-radius:0 0 10px 10px;padding:14px 16px 22px">
<table cellspacing="6" cellpadding="0" style="width:100%;border-collapse:separate">
<tr>{_card("결제하실 돈", _w(pay_sum), accent=True)}{_card("이달 투입 (일지)", _w(gross))}</tr>
<tr>{_card("작업자", len(workers), "명")}{_card("장비·자재", len(equips), "곳")}</tr></table>
{sec("1. 결제 요청 — 누구에게 얼마")}
{pay_table}
<div style="font-size:12px;color:{SUB};margin-top:8px">작업자는 사람마다 따로, 하루 일당 15만원 초과분 × 2.7% 소득세와 그 10% 지방소득세를 뗀 금액입니다. 날짜별 근거는 첨부 Excel 「출역표」, 계좌·금액은 「이체목록」 시트.</div>
{sec("2. 현장별 한 달 집계")}
{site_table}
{sec("3. 확인할 것")}
<ul style="margin:0;padding-left:20px;font-size:13px;color:{INK}">{note_html}</ul>
<div style="margin-top:28px;padding-top:12px;border-top:1px solid {LINE};font-size:12px;color:{SUB}">
진성현장 앱의 업무일지에서 만든 보고입니다. 숫자는 일지 기준이며, 고칠 내용은 앱에서 고친 뒤 다시 보냅니다.<br>
첨부: 월말보고_{month}.xlsx (결제요약 · 이체목록 · 현장별투입 · 출역표 · 인력 · 장비 · 자재 · 거래명세서)</div>
</div></div></body></html>"""
