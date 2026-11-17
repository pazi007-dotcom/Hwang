"""대표님 보고용 월말 Excel (3장): 월말보고 · 출역표 · 자재.

1. 월말보고: 결제 요청(사람·업체마다 계좌·금액, 원천세·부가세) → 현장별 집계 → 확인할 것.
2. 출역표: 1~31일, 누가·어느 현장에서·얼마나. 사람(장비)마다 소계 줄에 근무일수·지급액·소득세·지방소득세
   (일용근로소득 지급명세서·원천세 신고에 그대로 옮겨 적을 수 있게).
3. 자재: 관급자재(배정량·사용량·남은량·부족량), 사급자재(거래처·품명·수량·단가·금액, 단가를 안 넣었으면 공란).

A4 가로 인쇄, 흑백에서도 읽히게 굵기·선으로 구분. 합계는 수식.
상세 파일(월말상세_YYYY-MM.xlsx: 일자별 줄·거래명세서 대조 등)은 집 PC에 따로 남는다.
"""
from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter as CL

from . import alerts, company, mailer, payout, reports
from .store import Store

FONT = "맑은 고딕"
THIN = Side(style="thin", color="808080")
THICK = Side(style="medium", color="000000")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
WON = '#,##0;[Red]-#,##0;""'
QTY = '#,##0.###;[Red]-#,##0.###;""'
SHADE = PatternFill("solid", fgColor="EEF1F5")
DARK = PatternFill("solid", fgColor="1B2430")
WEEKEND = PatternFill("solid", fgColor="F6F6F6")


def _c(ws, r, c, v=None, *, bold=False, fmt=None, align=None, size=10, border=True, fill=None, color=None,
       wrap=False, top=False):
    cell = ws.cell(r, c, v)
    cell.font = Font(name=FONT, bold=bold, size=size, color=color)
    if fmt:
        cell.number_format = fmt
    cell.alignment = Alignment(horizontal=align, vertical="center", wrap_text=wrap)
    if border:
        cell.border = Border(left=THIN, right=THIN, bottom=THIN, top=THICK if top else THIN)
    if fill:
        cell.fill = fill
    return cell


def _widths(ws, widths):
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[CL(i)].width = w


def _page(ws, landscape=True, title_rows=None):
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.orientation = "landscape" if landscape else "portrait"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_margins.left = ws.page_margins.right = 0.4
    ws.page_margins.top = ws.page_margins.bottom = 0.5
    ws.print_options.horizontalCentered = True
    ws.sheet_view.showGridLines = False
    if title_rows:
        ws.print_title_rows = title_rows


def _title(ws, firm, text, sub, ncol):
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncol)
    _c(ws, 1, 1, f"{firm} · {text}", bold=True, size=15, border=False)
    ws.row_dimensions[1].height = 26
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=ncol)
    _c(ws, 2, 1, sub, size=9, border=False, color="5B6675")


def _section(ws, r, text, ncol):
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=ncol)
    _c(ws, r, 1, text, bold=True, size=12, border=False)
    ws.row_dimensions[r].height = 22


def _head(ws, r, titles):
    for i, t in enumerate(titles, 1):
        _c(ws, r, i, t, bold=True, align="center", fill=SHADE, wrap=True)
    ws.row_dimensions[r].height = 30


def _progress_of(store, site_name):
    from .excel_report import _site_progress
    row = store.db.execute("SELECT id FROM site WHERE name=?", (site_name,)).fetchone()
    return _site_progress(store, row["id"]) if row else None


def _lines(store, month):
    start, end = reports.month_range(month)
    return reports._lines(store, start, end)


def _supply(store) -> dict:
    """(현장, 품명, 규격) → 공급 구분 (도급자관급·관급자관급·사급)."""
    return {(a["site_id"], a["item"], a["spec"]): a["supply"] for a in store.db.execute("SELECT * FROM allocation")}


# ───────────────────────── 1. 월말보고 ─────────────────────────
def _sheet_report(wb, store, month, firm, check):
    ws = wb.active
    ws.title = "월말보고"
    N = 11
    _widths(ws, [9, 14, 9, 19, 14, 7, 13, 11, 11, 12, 14])
    y, m = month[:4], int(month[5:])
    _title(ws, firm, f"{y}년 {m}월 월말보고 · 결제 요청",
           f"대상 {check['period']} · 현장소장 → 대표님 · 업무일지 기준 (고칠 내용은 앱에서 고친 뒤 다시 만듭니다)", N)
    pos = [o for o in payout.month_payouts(store, month) if o["transfer"] > 0 or o["total"]]
    gross = reports.payment_summary(store, month)["total"]

    # 요약 칸
    r = 4
    first_pay_row = 9
    labels = [("결제하실 돈", None), ("이달 투입 (일지)", gross),
              ("작업자", f'{sum(1 for o in pos if o["group"] == "작업자")}명'),
              ("장비·자재 업체", f'{sum(1 for o in pos if o["group"] != "작업자")}곳')]
    spans = [(1, 3), (4, 5), (6, 8), (9, 11)]
    for (label, val), (c1, c2) in zip(labels, spans):
        ws.merge_cells(start_row=r, start_column=c1, end_row=r, end_column=c2)
        ws.merge_cells(start_row=r + 1, start_column=c1, end_row=r + 1, end_column=c2)
        _c(ws, r, c1, label, size=9, color="5B6675", fill=SHADE)
        for c in range(c1 + 1, c2 + 1):
            _c(ws, r, c, fill=SHADE)
            _c(ws, r + 1, c)
        cell = _c(ws, r + 1, c1, val, bold=True, size=14, fmt=WON if isinstance(val, int) else None)
        if label == "결제하실 돈":
            cell.font = Font(name=FONT, bold=True, size=15, color="1F5FBF")
            pay_cell = cell
    ws.row_dimensions[r + 1].height = 28

    # 1. 결제 요청
    _section(ws, 7, "1. 결제 요청 — 누구에게 얼마", N)
    _head(ws, 8, ["구분", "받는 곳", "은행", "계좌번호", "예금주", "출역일", "이달 금액", "원천세\n(소득+지방)",
                  "부가세", "이월·기지급", "결제하실 돈"])
    r = first_pay_row
    sub_rows = []
    for g in ("작업자", "장비", "자재·외주"):
        gl = [o for o in pos if o["group"] == g]
        if not gl:
            continue
        g_first = r
        for i, o in enumerate(gl):
            top = i == 0
            _c(ws, r, 1, g if i == 0 else None, bold=True, align="center", top=top)
            _c(ws, r, 2, o["name"], bold=True, top=top)
            _c(ws, r, 3, o["bank"] or "계좌 확인", bold=not o["bank"], color=None if o["bank"] else "B35A00", top=top)
            _c(ws, r, 4, o["account_no"], top=top)
            _c(ws, r, 5, o["holder"] or (o["name"] if o["bank"] else None), top=top)
            _c(ws, r, 6, f'{o["work_days"]}일' if o["work_days"] else None, align="center", top=top)
            _c(ws, r, 7, o["total"], fmt=WON, top=top)
            _c(ws, r, 8, -(o["income_tax"] + o["local_tax"]) or None, fmt=WON, top=top)
            _c(ws, r, 9, o["vat"] or None, fmt=WON, top=top)
            _c(ws, r, 10, (o["carry"] - o["cash_paid"]) or None, fmt=WON, top=top)
            _c(ws, r, 11, f"=G{r}+H{r}+I{r}+J{r}", fmt=WON, bold=True, top=top)
            r += 1
        _c(ws, r, 1, None, fill=SHADE)
        _c(ws, r, 2, f"{g} 소계 {len(gl)}{'명' if g == '작업자' else '곳'}", bold=True, fill=SHADE)
        for c in range(3, 7):
            _c(ws, r, c, fill=SHADE)
        for c in range(7, 12):
            _c(ws, r, c, f"=SUM({CL(c)}{g_first}:{CL(c)}{r - 1})", fmt=WON, bold=True, fill=SHADE)
        sub_rows.append(r)
        r += 1
    _c(ws, r, 1, "합계", bold=True, align="center", top=True)
    for c in range(2, 7):
        _c(ws, r, c, top=True)
    for c in range(7, 12):
        _c(ws, r, c, "=" + "+".join(f"{CL(c)}{x}" for x in sub_rows) if sub_rows else 0, fmt=WON, bold=True,
           top=True, color="1F5FBF" if c == 11 else None)
    pay_cell.value = f"=K{r}"
    pay_cell.number_format = WON
    total_row = r
    r += 1
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=N)
    _c(ws, r, 1, "작업자는 사람마다 따로: 하루 일당 15만원 초과분 × 2.7% 소득세, 그 10% 지방소득세(10원 미만 버림, "
                 "1,000원 미만 안 뗌). 날짜·현장별 근거는 「출역표」 시트.", size=8, border=False, color="5B6675",
       wrap=True)
    ws.row_dimensions[r].height = 24

    # 2. 현장별 집계
    r += 2
    _section(ws, r, "2. 현장별 한 달 집계", N)
    r += 1
    sites = reports.site_inputs(store, month)
    days = defaultdict(set)
    for ln in _lines(store, month):
        days[ln["site_name"]].add(ln["work_date"])
    _head(ws, r, ["", "현장", "", "", "작업일", "", "인력", "장비", "자재", "외주", "합계"])
    for a, b in ((2, 4), (5, 6)):
        ws.merge_cells(start_row=r, start_column=a, end_row=r, end_column=b)
    r += 1
    s_first = r
    for x in sites:
        _c(ws, r, 1)
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=4)
        _c(ws, r, 2, x["site"], bold=True)
        _c(ws, r, 3)
        _c(ws, r, 4)
        ws.merge_cells(start_row=r, start_column=5, end_row=r, end_column=6)
        prog = _progress_of(store, x["site"])
        _c(ws, r, 5, f'{len(days[x["site"]])}일' + (f' · 공정 {prog:.0%}' if prog is not None else ''), align="center", size=9)
        _c(ws, r, 6)
        for c, k in zip(range(7, 11), ("인력", "장비", "자재", "외주")):
            _c(ws, r, c, x.get(k, 0) or None, fmt=WON)
        _c(ws, r, 11, f"=SUM(G{r}:J{r})", fmt=WON, bold=True)
        r += 1
    _c(ws, r, 1, "합계", bold=True, align="center", top=True)
    for c in range(2, 7):
        _c(ws, r, c, top=True)
    for c in range(7, 12):
        _c(ws, r, c, f"=SUM({CL(c)}{s_first}:{CL(c)}{r - 1})" if sites else 0, fmt=WON, bold=True, top=True)
    r += 1
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=N)
    _c(ws, r, 1, f'=IF(G{total_row}=K{r - 1},"검산: 결제 요청 이달 금액 = 현장별 합계 (일치)","검산 차이 — 확인 필요")',
       size=8, border=False, color="5B6675")

    # 3. 확인할 것
    r += 2
    _section(ws, r, "3. 확인할 것", N)
    notes = []
    no_acc = [o["name"] for o in pos if o["transfer"] > 0 and not o["bank"]]
    if no_acc:
        notes.append(f"계좌 확인 필요: {', '.join(no_acc)}")
    for x in check["sites"]:
        if x.get("type") != "정식":
            continue
        miss = [d for d in x["missing"] if date.fromisoformat(d).weekday() < 5]
        if miss:
            notes.append(f"{x['site']} 평일인데 일지 없는 날 {len(miss)}일: "
                         + ", ".join(f"{int(d[5:7])}/{int(d[8:])}" for d in miss))
    if check["diffs"]:
        notes.append(f"거래명세서와 차이 {check['diffs']}건")
    tax = sum(o["income_tax"] + o["local_tax"] for o in pos)
    if tax:
        notes.append(f"일용 원천세 {tax:,}원 (소득세 {sum(o['income_tax'] for o in pos):,} · 지방소득세 "
                     f"{sum(o['local_tax'] for o in pos):,}) → 다음 달 10일까지 신고·납부. 사람별 내역은 「출역표」")
    short = [a for a in _gov_rows(store, month) if a["short"] > 0]
    if short:
        notes.append("관급자재 부족 예상: " + ", ".join(f"{a['site']} {a['item']} {a['short']:g}{a['unit']}" for a in short))
    for n in notes or ["없음"]:
        r += 1
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=N)
        _c(ws, r, 1, "· " + n, border=False, wrap=True)
        ws.row_dimensions[r].height = 18 if len(n) < 90 else 30
    _page(ws, landscape=False, title_rows=None)
    ws.page_setup.fitToHeight = 1
    return pos


# ───────────────────────── 2. 출역표 ─────────────────────────
def _sheet_attendance(wb, store, month, firm):
    ws = wb.create_sheet("출역표")
    y, m = int(month[:4]), int(month[5:])
    ndays = calendar.monthrange(y, m)[1]
    D0 = 5                           # 1일 열
    cD = D0 + ndays                  # 일수
    cQ, cP, cA, cT, cL = cD + 1, cD + 2, cD + 3, cD + 4, cD + 5   # 수량·단가·금액·소득세·지방소득세
    N = cL
    _widths(ws, [7, 12, 10, 24] + [4.2] * ndays + [5, 7, 9, 11, 9, 9])
    _title(ws, firm, f"{y}년 {m}월 출역표 (1일~{ndays}일)",
           "칸 숫자 = 그날 그 현장에서의 공수(인)·일수(대). 굵은 줄(두 현장 이상이면 「계」 줄) = 그 사람의 한 달: "
           "근무일수·지급액·소득세·지방소득세 → 일용근로소득 지급명세서·원천세 신고용.", N)
    yo = "월화수목금토일"
    titles = ["구분", "이름·업체", "직종·기종", "현장"] + [str(d) for d in range(1, ndays + 1)] + \
             ["일수", "공수\n·수량", "단가", "금액", "소득세", "지방\n소득세"]
    _head(ws, 4, titles)
    for d in range(1, ndays + 1):
        wd = date(y, m, d).weekday()
        _c(ws, 5, D0 + d - 1, yo[wd], align="center", size=8, fill=WEEKEND if wd >= 5 else SHADE,
           bold=wd >= 5)
        if wd >= 5:
            ws.cell(4, D0 + d - 1).fill = WEEKEND
    for c in list(range(1, D0)) + list(range(cD, N + 1)):
        _c(ws, 5, c, fill=SHADE)
    ws.freeze_panes = ws.cell(6, D0)
    ws.print_title_rows = "4:5"

    # (받는 곳, 종류, 항목) → 현장 → 날짜 → 수량, 금액
    grid = defaultdict(lambda: defaultdict(lambda: defaultdict(Decimal)))
    money = defaultdict(lambda: defaultdict(int))
    price = defaultdict(lambda: defaultdict(set))
    unit = {}
    names = {}
    for ln in _lines(store, month):
        if ln["kind"] not in ("인력", "장비"):
            continue
        key = (ln["payee_id"], ln["kind"], ln["item"])
        names[key] = ln["payee_name"]
        unit[key] = ln["unit"]
        grid[key][ln["site_name"]][int(ln["work_date"][8:])] += Decimal(str(ln["qty"]))
        money[key][ln["site_name"]] += ln["amount"]
        price[key][ln["site_name"]].add(ln["unit_price"])
    po = {o["payee_id"]: o for o in payout.month_payouts(store, month)}
    order = sorted(grid, key=lambda k: (0 if k[1] == "인력" else 1, names[k], k[2]))
    r = 6
    last_payee = None
    span = f"{CL(D0)}{{r}}:{CL(D0 + ndays - 1)}{{r}}"

    def tax_cells(row, key, fill=None):
        pid, kind, _ = key
        o = po.get(pid)
        ok = kind == "인력" and o and o["rule"] == "일용" and pid != last_payee
        _c(ws, row, cT, o["income_tax"] if ok else None, fmt=WON, bold=True, fill=fill)
        _c(ws, row, cL, o["local_tax"] if ok else None, fmt=WON, bold=True, fill=fill)

    for key in order:
        pid, kind, item = key
        sites = sorted(grid[key])
        multi = len(sites) > 1
        group = "작업자" if kind == "인력" else "장비"
        site_rows = []
        for i, site in enumerate(sites):
            top = i == 0
            # 현장이 하나면 이 줄이 곧 그 사람의 한 달 줄(구분 칸을 채움 → 합계·신고에 쓰임)
            _c(ws, r, 1, group if not multi else None, align="center", top=top)
            _c(ws, r, 2, names[key] if top else None, bold=True, top=top)
            _c(ws, r, 3, item if top else None, top=top)
            _c(ws, r, 4, site, top=top, size=9)
            for d in range(1, ndays + 1):
                q = grid[key][site].get(d)
                wd = date(y, m, d).weekday()
                _c(ws, r, D0 + d - 1, float(q) if q else None, fmt=QTY, align="center", size=9, top=top,
                   fill=WEEKEND if wd >= 5 else None, bold=not multi)
            _c(ws, r, cD, f"=COUNT({span.format(r=r)})", align="center", top=top, bold=not multi)
            _c(ws, r, cQ, f"=SUM({span.format(r=r)})", fmt=QTY, align="center", top=top, bold=not multi)
            ps = price[key][site]
            _c(ws, r, cP, next(iter(ps)) if len(ps) == 1 else "여러 단가", fmt=WON, top=top, size=9)
            _c(ws, r, cA, money[key][site], fmt=WON, top=top, bold=not multi)
            if multi:
                _c(ws, r, cT, None, top=top)
                _c(ws, r, cL, None, top=top)
            else:
                tax_cells(r, key)
            site_rows.append(r)
            r += 1
        if multi:
            # 하루에 두 현장이면 날짜 칸은 합계 (그날 공수)
            _c(ws, r, 1, group, align="center", fill=SHADE)
            _c(ws, r, 2, f"{names[key]} 계", bold=True, fill=SHADE)
            _c(ws, r, 3, f"{len(sites)}개 현장", fill=SHADE, size=9)
            _c(ws, r, 4, unit[key], fill=SHADE, size=9, align="center")
            for d in range(1, ndays + 1):
                col = CL(D0 + d - 1)
                _c(ws, r, D0 + d - 1, f'=IF(SUM({col}{site_rows[0]}:{col}{site_rows[-1]})=0,"",'
                                      f'SUM({col}{site_rows[0]}:{col}{site_rows[-1]}))',
                   fmt=QTY, align="center", size=9, bold=True, fill=SHADE)
            _c(ws, r, cD, f"=COUNT({span.format(r=r)})", align="center", bold=True, fill=SHADE)
            _c(ws, r, cQ, f"=SUM({CL(cQ)}{site_rows[0]}:{CL(cQ)}{site_rows[-1]})", fmt=QTY, align="center",
               bold=True, fill=SHADE)
            _c(ws, r, cP, fill=SHADE)
            _c(ws, r, cA, f"=SUM({CL(cA)}{site_rows[0]}:{CL(cA)}{site_rows[-1]})", fmt=WON, bold=True, fill=SHADE)
            tax_cells(r, key, SHADE)
            r += 1
        last_payee = pid
    _c(ws, r, 1, "합계", bold=True, align="center", top=True)
    for c in range(2, cA):
        _c(ws, r, c, top=True)
    for c in (cA, cT, cL):   # 구분 칸이 채워진 줄 = 사람·장비 1개의 한 달 줄
        _c(ws, r, c, f'=SUMIF($A$6:$A${r - 1},"?*",{CL(c)}6:{CL(c)}{r - 1})', fmt=WON, bold=True, top=True)
    _page(ws, landscape=True, title_rows="4:5")
    return r


# ───────────────────────── 3. 자재 ─────────────────────────
def _gov_rows(store, month):
    start, end = reports.month_range(month)
    out = []
    for s in store.db.execute("SELECT DISTINCT s.id, s.name FROM site s JOIN allocation a ON a.site_id=s.id"
                              " WHERE a.supply != '사급' ORDER BY s.name").fetchall():
        need = alerts.remaining_need(store, s["id"])
        for a in reports.allocation_status(store, s["id"], need or None):
            if a["supply"] == "사급":
                continue
            month_use = sum((Decimal(str(x["qty"])) for x in store.db.execute(
                "SELECT l.qty FROM input_line l JOIN work_log w ON w.id=l.log_id WHERE w.site_id=? AND l.kind='자재'"
                " AND l.item=? AND l.spec=? AND w.work_date BETWEEN ? AND ?",
                (s["id"], a["item"], a["spec"], start, end))), Decimal(0))
            left = a["alloc_qty"] - a["cum_in"]
            short = max(a["remaining_need"] - left, Decimal(0))
            out.append({"site": s["name"], "item": a["item"], "spec": a["spec"], "unit": a["unit"],
                        "supply": a["supply"], "alloc": a["alloc_qty"], "month": month_use, "cum": a["cum_in"],
                        "left": left, "need": a["remaining_need"], "short": float(short)})
    return out


def _sheet_material(wb, store, month, firm):
    ws = wb.create_sheet("자재")
    N = 11
    _widths(ws, [10, 24, 13, 13, 6, 10, 9, 9, 10, 12, 12])
    y, m = month[:4], int(month[5:])
    _title(ws, firm, f"{y}년 {m}월 자재", "관급자재: 배정량 대비 사용·남은·부족.  사급자재: 거래처별 구입 (단가를 안 넣은 줄은 금액 공란).", N)

    _section(ws, 4, "1. 관급자재 (배정량 대비)", N)
    _head(ws, 5, ["공급", "현장", "품명", "규격", "단위", "배정량", "이달 사용", "누계 사용", "남은량",
                  "남은 공사\n필요량", "부족량"])
    r = 6
    gov = _gov_rows(store, month)
    for a in gov:
        _c(ws, r, 1, a["supply"], size=8, align="center")
        _c(ws, r, 2, a["site"], size=9)
        _c(ws, r, 3, a["item"], bold=True)
        _c(ws, r, 4, a["spec"], size=9)
        _c(ws, r, 5, a["unit"], align="center")
        _c(ws, r, 6, float(a["alloc"]), fmt=QTY)
        _c(ws, r, 7, float(a["month"]), fmt=QTY)
        _c(ws, r, 8, float(a["cum"]), fmt=QTY)
        _c(ws, r, 9, f"=F{r}-H{r}", fmt=QTY, bold=True)
        _c(ws, r, 10, float(a["need"]), fmt=QTY)
        _c(ws, r, 11, f"=MAX(J{r}-I{r},0)", fmt=QTY, bold=True, color="B35A00" if a["short"] > 0 else None)
        r += 1
    if not gov:
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=N)
        _c(ws, r, 1, "이 달 관급자재 배정이 없습니다.", size=9, border=False, color="5B6675")
        r += 1
    r += 1
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=N)
    _c(ws, r, 1, "남은량 = 배정량 − 누계 사용.  부족량 = 남은 공사 필요량 − 남은량 (0보다 크면 추가 배정 요청 필요).",
       size=8, border=False, color="5B6675")

    r += 2
    _section(ws, r, "2. 사급자재 (거래처·금액)", N)
    r += 1
    _head(ws, r, ["날짜", "현장", "거래처", "품명", "단위", "규격", "수량", "", "단가", "금액", "비고"])
    r += 1
    sup = _supply(store)
    rows = [ln for ln in _lines(store, month) if ln["kind"] == "자재"
            and sup.get((ln["site_id"], ln["item"], ln["spec"]), "사급") == "사급"]
    rows.sort(key=lambda ln: (ln["payee_name"], ln["work_date"]))
    first = r
    by_vendor = defaultdict(lambda: [0, 0, False])
    for ln in rows:
        _c(ws, r, 1, f'{int(ln["work_date"][5:7])}/{int(ln["work_date"][8:])}', align="center")
        _c(ws, r, 2, ln["site_name"], size=9)
        _c(ws, r, 3, ln["payee_name"], bold=True)
        _c(ws, r, 4, ln["item"])
        _c(ws, r, 5, ln["unit"], align="center")
        _c(ws, r, 6, ln["spec"], size=9)
        _c(ws, r, 7, float(ln["qty"]), fmt=QTY)
        _c(ws, r, 8)
        priced = bool(ln["unit_price"])
        _c(ws, r, 9, ln["unit_price"] if priced else None, fmt=WON)
        _c(ws, r, 10, ln["amount"] if priced else None, fmt=WON)
        _c(ws, r, 11, None if priced else "단가 미입력", size=8, color="B35A00")
        v = by_vendor[ln["payee_name"]]
        v[0] += 1
        v[1] += ln["amount"] if priced else 0
        v[2] = v[2] or not priced
        r += 1
    if not rows:
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=N)
        _c(ws, r, 1, "이 달 사급자재 구입이 없습니다.", size=9, border=False, color="5B6675")
        r += 1
    else:
        _c(ws, r, 1, "합계", bold=True, align="center", top=True)
        for c in range(2, 10):
            _c(ws, r, c, top=True)
        _c(ws, r, 10, f"=SUM(J{first}:J{r - 1})", fmt=WON, bold=True, top=True)
        _c(ws, r, 11, top=True)
        r += 2
        _section(ws, r, "거래처별", N)
        r += 1
        _head(ws, r, ["", "거래처", "", "건수", "", "", "", "", "", "금액", "비고"])
        r += 1
        for name, (n, amt, missing) in sorted(by_vendor.items()):
            for c in range(1, N + 1):
                _c(ws, r, c)
            ws.cell(r, 2).value = name
            ws.cell(r, 2).font = Font(name=FONT, bold=True, size=10)
            ws.cell(r, 4).value = n
            _c(ws, r, 10, f'=SUMIF($C${first}:$C${first + len(rows) - 1},B{r},$J${first}:$J${first + len(rows) - 1})',
               fmt=WON, bold=True)
            _c(ws, r, 11, "단가 미입력 있음" if missing else None, size=8, color="B35A00")
            r += 1
    _page(ws, landscape=False)


def _firm_line(info: dict) -> str:
    """보고서 아래 회사 정보 한 줄 (사업자등록증 기준, config/company.json)."""
    parts = [info.get("name"), f"대표 {info['ceo']}" if info.get("ceo") else None,
             f"사업자 {info['business_no']}" if info.get("business_no") else None, info.get("address")]
    return " · ".join(p for p in parts if p)


def build_report(store: Store, month: str, out_dir: str | Path, corrected: bool = False) -> Path:
    from .excel_report import report_file_name
    info = company.load()
    firm = info.get("name") or "진성건설"
    check = mailer.precheck(store, month)
    wb = Workbook()
    _sheet_report(wb, store, month, firm, check)
    _sheet_attendance(wb, store, month, firm)
    _sheet_material(wb, store, month, firm)
    line = _firm_line(info)
    for ws in wb.worksheets:                     # 인쇄할 때 쪽마다 아래에 회사 정보
        ws.oddFooter.left.text = line
        ws.oddFooter.left.size = 8
        ws.oddFooter.right.text = "&P / &N"
        ws.oddFooter.right.size = 8
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / report_file_name("월말보고", month, corrected=corrected)
    wb.save(path)
    return path
