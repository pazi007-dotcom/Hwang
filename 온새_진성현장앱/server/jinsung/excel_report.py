"""월말 보고 Excel (설계안 5-1 '월말 보고 Excel 시트 구성').

- 결제가 첫 번째: 결제요약 → 현장별투입 → 인력 → 장비 → 자재 → (외주) → 거래명세서 → 자재배정대비.
- 요약의 모든 합계는 상세 시트 줄을 더한 수식(SUMIFS)이다. 요약과 상세가 어긋날 수 없다.
- 파일은 언제든 원본 데이터에서 다시 만든다. 파일명: 월말보고_2026-11.xlsx (정정본은 _정정).
- A4 흑백 인쇄 기준: 색 대신 굵기·선, 머리글 반복, 매크로 없음.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, Side
from openpyxl.utils import get_column_letter as CL

from . import alerts, reports
from .stations import progress_bar
from .store import KINDS, Store

FONT = "맑은 고딕"
THIN = Side(style="thin", color="000000")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
WON = '#,##0;[Red]-#,##0;"-"'
QTY = "#,##0.###"
DETAIL_COLS = ["날짜", "현장", "받는 곳", "항목", "규격", "수량", "단위", "단가", "금액", "명세서 대조"]
DETAIL_W = [12, 20, 18, 14, 12, 9, 6, 12, 14, 12]


def report_file_name(kind: str, period: str, site: str | None = None, corrected: bool = False,
                     ext: str = "xlsx") -> str:
    """종류_기간[_현장][_정정].확장자 — 띄어쓰기·버전·시각 없음."""
    parts = [kind, period] if period else [kind]
    if site:
        parts.append(site.replace(" ", ""))
    if corrected:
        parts.append("정정")
    return "_".join(parts) + "." + ext


def _c(ws, row, col, value, bold=False, fmt=None, align=None, size=10, border=True, wrap=False):
    cell = ws.cell(row, col, value)
    cell.font = Font(name=FONT, bold=bold, size=size)
    if fmt:
        cell.number_format = fmt
    cell.alignment = Alignment(horizontal=align, vertical="center", wrap_text=wrap)
    if border:
        cell.border = BOX
    return cell


def _header(ws, row, titles, widths=None):
    for i, t in enumerate(titles, 1):
        _c(ws, row, i, t, bold=True, align="center", wrap=True)
        if widths:
            ws.column_dimensions[CL(i)].width = widths[i - 1]
    ws.print_title_rows = f"{row}:{row}"
    ws.freeze_panes = ws.cell(row + 1, 1)


def _page(ws, landscape=True):
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.orientation = "landscape" if landscape else "portrait"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_options.horizontalCentered = True
    ws.sheet_view.showGridLines = False


def _invoice_status(store: Store, month: str) -> dict:
    """(작업일, 받는 곳, 항목, 규격) → 대조 상태."""
    start, end = reports.month_range(month)
    return {(r["work_date"], r["payee_id"], r["item"], r["spec"]): r["status"]
            for r in store.db.execute("SELECT * FROM invoice WHERE work_date BETWEEN ? AND ?",
                                      (start, end))}


def _carry_over(store: Store, payee_id: str, month: str) -> int:
    """이월 미지급 = 이전 달까지의 투입 합계 − 이전 달 청구분에 대한 지급."""
    start, _ = reports.month_range(month)
    billed = store.db.execute(
        "SELECT COALESCE(SUM(l.amount),0) AS a FROM input_line l JOIN work_log w ON w.id=l.log_id"
        " WHERE l.payee_id=? AND w.work_date < ?", (payee_id, start)).fetchone()["a"]
    paid = store.db.execute(
        "SELECT COALESCE(SUM(amount),0) AS a FROM payment WHERE payee_id=? AND month < ?",
        (payee_id, month)).fetchone()["a"]
    return billed - paid


def _site_progress(store: Store, site_id: str):
    done = total = 0
    for wt in store.db.execute("SELECT id FROM work_type WHERE site_id=? AND design_length IS NOT NULL",
                               (site_id,)):
        bar = progress_bar(store, wt["id"])
        done += bar["done_length"]
        total += bar["design_length"]
    return float(done / total) if total else None


def build_monthly(store: Store, month: str, out_dir: str | Path, corrected: bool = False) -> Path:
    reports.match_invoices(store, month)
    summary = reports.payment_summary(store, month)
    inv_status = _invoice_status(store, month)
    start, end = reports.month_range(month)
    wb = Workbook()
    wb.remove(wb.active)
    sheets = {name: wb.create_sheet(name) for name in ["결제요약", "현장별투입", "인력", "장비", "자재"]}
    has_sub = bool(reports.daily_lines(store, month, "외주"))
    if has_sub:
        sheets["외주"] = wb.create_sheet("외주")
    detail_names = [k for k in KINDS if k in sheets]

    # ---------- 상세 (인력·장비·자재·외주): 날짜·줄 1건 = 한 줄 ----------
    last_row = {}
    for kind in detail_names:
        ws = sheets[kind]
        _c(ws, 1, 1, f"{month} {kind} 투입 상세", bold=True, size=13, border=False)
        _header(ws, 3, DETAIL_COLS, DETAIL_W)
        r = 4
        for ln in reports.daily_lines(store, month, kind):
            status = inv_status.get((ln["work_date"], ln["payee_id"], ln["item"], ln["spec"]), "없음")
            _c(ws, r, 1, ln["work_date"], align="center")
            _c(ws, r, 2, ln["site_name"])
            _c(ws, r, 3, ln["payee_name"])
            _c(ws, r, 4, ln["item"])
            _c(ws, r, 5, ln["spec"])
            _c(ws, r, 6, float(ln["qty"]), fmt=QTY)
            _c(ws, r, 7, ln["unit"], align="center")
            _c(ws, r, 8, ln["unit_price"], fmt=WON)
            natural = round(float(ln["qty"]) * ln["unit_price"])
            # 두 현장으로 나눈 줄의 끝전처럼 수량×단가와 다른 금액은 값 그대로 적는다
            _c(ws, r, 9, f"=ROUND(F{r}*H{r},0)" if natural == ln["amount"] else ln["amount"], fmt=WON)
            _c(ws, r, 10, status, align="center", bold=status in ("차이", "일지에없음"))
            r += 1
        last_row[kind] = max(r - 1, 4)
        _c(ws, r, 1, "합계", bold=True, align="center")
        for col in range(2, 11):
            _c(ws, r, col, None, bold=True)
        _c(ws, r, 9, f"=SUM(I4:I{last_row[kind]})", bold=True, fmt=WON)
        _page(ws)

    def sumifs(kinds, crit):
        """상세 시트들의 금액을 조건으로 더하는 수식 조각. crit: [(열 문자, 조건 셀)]"""
        parts = []
        for kind in kinds:
            n = last_row[kind]
            cond = ",".join(f"'{kind}'!${col}$4:${col}${n},{ref}" for col, ref in crit)
            parts.append(f"SUMIFS('{kind}'!$I$4:$I${n},{cond})")
        return "+".join(parts)

    # ---------- 결제요약: 받는 곳 1곳 = 한 줄 ----------
    ws = sheets["결제요약"]
    site_names = sorted({s for p in summary["rows"] for s in p["by_site"]})
    n_site = len(site_names)
    c_total, c_carry, c_paid, c_due, c_inv, c_state = (3 + n_site + i for i in range(6))
    _c(ws, 1, 1, f"월말보고 {month}" + (" (정정)" if corrected else ""), bold=True, size=14, border=False)
    first, last = 6, 5 + max(len(summary["rows"]), 1)
    diff_count = sum(1 for s in inv_status.values() if s in ("차이", "일지에없음"))
    _c(ws, 2, 1, f'="{int(month[5:])}월 결제 합계 "&TEXT({CL(c_total)}{last + 1},"#,##0")&"원 · 받는 곳 "'
                 f'&COUNTA(A{first}:A{last})&"곳 · 차이 {diff_count}건"', bold=True, size=12, border=False)
    drafts = store.db.execute("SELECT COUNT(*) AS n FROM rate WHERE is_draft=1").fetchone()["n"]
    note = "이 파일은 진성현장 앱의 기록에서 만든 결과물입니다. 고칠 내용은 앱에서 고친 뒤 다시 만듭니다."
    if drafts:
        note += f" ※ 초안 단가 {drafts}건 포함 — 실제 단가 확인 전."
    _c(ws, 3, 1, note, size=9, border=False)
    titles = ["받는 곳", "구분", *site_names, "합계", "이월 미지급", "이달 지급", "미지급 잔액",
              "명세서 대조", "지급 상태"]
    _header(ws, 5, titles, [20, 12, *([15] * n_site), 15, 14, 14, 15, 12, 11])
    for i, p in enumerate(summary["rows"]):
        r = first + i
        statuses = {s for (d, pid, _, _), s in inv_status.items() if pid == p["payee_id"]}
        if statuses & {"차이", "일지에없음"}:
            inv = "차이"
        elif statuses:
            inv = "일치"
        else:
            inv = "없음"
        bold = inv == "차이"
        _c(ws, r, 1, p["payee"], bold=bold)
        _c(ws, r, 2, p["kinds"], align="center")
        for j, site in enumerate(site_names):
            col = 3 + j
            _c(ws, r, col, "=" + sumifs(detail_names, [("C", f"$A{r}"), ("B", f"{CL(col)}$5")]),
               fmt=WON, bold=bold)
        _c(ws, r, c_total, f"=SUM({CL(3)}{r}:{CL(2 + n_site)}{r})" if n_site else 0, fmt=WON, bold=True)
        _c(ws, r, c_carry, _carry_over(store, p["payee_id"], month), fmt=WON)
        paid = store.db.execute("SELECT COALESCE(SUM(amount),0) AS a FROM payment WHERE payee_id=?"
                                " AND month=?", (p["payee_id"], month)).fetchone()["a"]
        _c(ws, r, c_paid, paid, fmt=WON)
        _c(ws, r, c_due, f"={CL(c_total)}{r}+{CL(c_carry)}{r}-{CL(c_paid)}{r}", fmt=WON, bold=True)
        _c(ws, r, c_inv, inv, align="center", bold=bold)
        _c(ws, r, c_state, f'=IF({CL(c_due)}{r}<=0,"지급 완료",IF({CL(c_paid)}{r}>0,"일부 지급","미지급"))',
           align="center")
    r = last + 1
    _c(ws, r, 1, "합계", bold=True, align="center")
    _c(ws, r, 2, None)
    for col in range(3, c_due + 1):
        _c(ws, r, col, f"=SUM({CL(col)}{first}:{CL(col)}{last})", fmt=WON, bold=True)
    _c(ws, r, c_inv, None)
    _c(ws, r, c_state, None)
    _c(ws, r + 1, 1, "검산(상세 시트 합)", size=9, border=False)
    _c(ws, r + 1, c_total, "=" + "+".join(f"'{k}'!I{last_row[k] + 1}" for k in detail_names),
       fmt=WON, size=9, border=False)
    _page(ws)

    # ---------- 현장별투입: 현장 1곳 = 한 줄 ----------
    ws = sheets["현장별투입"]
    _c(ws, 1, 1, f"{month} 현장별 투입", bold=True, size=13, border=False)
    cols = ["현장", *[f"{k}비" for k in KINDS], "이달 합계", "누계", "공정률", "도급액", "도급액 대비"]
    _header(ws, 3, cols, [22, 14, 14, 14, 14, 15, 15, 9, 15, 11])
    site_rows = store.db.execute(
        "SELECT DISTINCT s.* FROM site s JOIN work_log w ON w.site_id=s.id JOIN input_line l"
        " ON l.log_id=w.id WHERE w.work_date BETWEEN ? AND ? ORDER BY s.name", (start, end)).fetchall()
    r = 4
    for s in site_rows:
        _c(ws, r, 1, s["name"])
        for j, kind in enumerate(KINDS):
            f = "=" + sumifs([kind], [("B", f"$A{r}")]) if kind in last_row else 0
            _c(ws, r, 2 + j, f, fmt=WON)
        _c(ws, r, 6, f"=SUM(B{r}:E{r})", fmt=WON, bold=True)
        cum = store.db.execute(
            "SELECT COALESCE(SUM(l.amount),0) AS a FROM input_line l JOIN work_log w ON w.id=l.log_id"
            " WHERE w.site_id=? AND w.work_date<=?", (s["id"], end)).fetchone()["a"]
        _c(ws, r, 7, cum, fmt=WON)
        _c(ws, r, 8, _site_progress(store, s["id"]), fmt="0%", align="center")
        _c(ws, r, 9, s["contract_amount"], fmt=WON)
        _c(ws, r, 10, f'=IF(N(I{r})>0,G{r}/I{r},"")', fmt="0.0%", align="center")
        r += 1
    _c(ws, r, 1, "합계", bold=True, align="center")
    for col in range(2, 8):
        _c(ws, r, col, f"=SUM({CL(col)}4:{CL(col)}{max(r - 1, 4)})", fmt=WON, bold=True)
    for col in (8, 9, 10):
        _c(ws, r, col, None)
    _page(ws)

    # ---------- 거래명세서: 명세서 1장 = 한 줄 ----------
    ws = wb.create_sheet("거래명세서")
    _c(ws, 1, 1, f"{month} 거래명세서 대조 (일지 값을 덮어쓰지 않음)", bold=True, size=13, border=False)
    _header(ws, 3, ["업체", "날짜", "품목·기종", "규격", "명세서 금액", "일지 금액", "차이", "상태", "사진"],
            [20, 12, 14, 12, 15, 15, 13, 12, 40])
    r = 4
    for inv in store.db.execute(
            "SELECT i.*, p.name AS payee FROM invoice i JOIN payee p ON p.id=i.payee_id"
            " WHERE i.work_date BETWEEN ? AND ? ORDER BY i.work_date, p.name", (start, end)):
        log_amt = store.db.execute(
            "SELECT COALESCE(SUM(l.amount),0) AS a FROM input_line l JOIN work_log w ON w.id=l.log_id"
            " WHERE w.work_date=? AND l.payee_id=? AND l.item=? AND l.spec=?",
            (inv["work_date"], inv["payee_id"], inv["item"], inv["spec"])).fetchone()["a"]
        bold = inv["status"] in ("차이", "일지에없음")
        _c(ws, r, 1, inv["payee"], bold=bold)
        _c(ws, r, 2, inv["work_date"], align="center")
        _c(ws, r, 3, inv["item"])
        _c(ws, r, 4, inv["spec"])
        _c(ws, r, 5, inv["amount"], fmt=WON)
        _c(ws, r, 6, log_amt, fmt=WON)
        _c(ws, r, 7, f"=E{r}-F{r}", fmt=WON, bold=bold)
        _c(ws, r, 8, inv["status"], align="center", bold=bold)
        cell = _c(ws, r, 9, inv["photo_path"])
        if inv["photo_path"]:
            cell.hyperlink = inv["photo_path"]
        r += 1
    _page(ws)

    # ---------- 출역표: 사람·장비 1줄 × 1~31일 (공수·일수), 결제 근거 ----------
    ws = wb.create_sheet("출역표", 2)
    last_day = int(end[-2:])
    _c(ws, 1, 1, f"{month} 출역표 (사람·장비별 날짜별 수량, 두 현장 이상인 날은 합계)", bold=True, size=13, border=False)
    head = ["받는 곳", "항목", "단위", *[str(d) for d in range(1, last_day + 1)], "합계", "일수", "금액"]
    _header(ws, 3, head, [16, 12, 5, *([4.2] * last_day), 7, 5, 13])
    grid: dict[tuple, dict] = {}
    for kind in KINDS:
        if kind in ("자재",):
            continue
        for ln in reports.daily_lines(store, month, kind):
            key = (ln["payee_name"], ln["item"], ln["unit"])
            g = grid.setdefault(key, {"days": defaultdict(float), "amount": 0})
            g["days"][int(ln["work_date"][-2:])] += float(ln["qty"])
            g["amount"] += ln["amount"]
    r = 4
    for (payee, item, unit), g in sorted(grid.items(), key=lambda kv: (-kv[1]["amount"], kv[0])):
        _c(ws, r, 1, payee)
        _c(ws, r, 2, item)
        _c(ws, r, 3, unit, align="center")
        for d in range(1, last_day + 1):
            v = g["days"].get(d)
            _c(ws, r, 3 + d, v if v else None, fmt="0.##", align="center")
        a, z = CL(4), CL(3 + last_day)
        _c(ws, r, 4 + last_day, f"=SUM({a}{r}:{z}{r})", fmt="0.##", bold=True, align="center")
        _c(ws, r, 5 + last_day, f"=COUNT({a}{r}:{z}{r})", align="center")
        _c(ws, r, 6 + last_day, g["amount"], fmt=WON)
        r += 1
    _page(ws)

    # ---------- 자재배정대비: 현장·품목 1건 = 한 줄 ----------
    ws = wb.create_sheet("자재배정대비")
    _c(ws, 1, 1, "내역 배정 자재 대비 (누계 기준)", bold=True, size=13, border=False)
    _header(ws, 3, ["현장", "품목", "규격", "단위", "설계 수량", "배정량", "누계 반입", "남은 시공 필요량",
                    "예상 과부족", "상태"], [22, 12, 12, 6, 12, 12, 12, 15, 13, 14])
    r = 4
    for s in store.db.execute("SELECT DISTINCT s.id, s.name FROM site s JOIN allocation a"
                              " ON a.site_id=s.id ORDER BY s.name").fetchall():
        need = alerts.remaining_need(store, s["id"])
        for a in reports.allocation_status(store, s["id"], need or None):
            _c(ws, r, 1, s["name"])
            _c(ws, r, 2, a["item"])
            _c(ws, r, 3, a["spec"])
            _c(ws, r, 4, a["unit"], align="center")
            _c(ws, r, 5, float(a["design_qty"]), fmt=QTY)
            _c(ws, r, 6, float(a["alloc_qty"]), fmt=QTY)
            _c(ws, r, 7, float(a["cum_in"]), fmt=QTY)
            _c(ws, r, 8, float(a["remaining_need"]), fmt=QTY)
            _c(ws, r, 9, f"=F{r}-(G{r}+H{r})", fmt='#,##0.###;[Red]-#,##0.###;0', bold=True)
            _c(ws, r, 10, f'=IF(I{r}<0,"부족 예상",IF(G{r}+H{r}>E{r},"할증 여유 사용","여유"))',
               align="center", bold=a["balance"] < 0)
            r += 1
    _page(ws)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / report_file_name("월말보고", month, corrected=corrected)
    wb.save(path)
    return path


def build_yearly(store: Store, year: str, out_dir: str | Path) -> Path:
    """연말 보고: 사람·장비별 월별(수량·금액), 현장별 월별 금액. 파일명 연말보고_2026.xlsx"""
    wb = Workbook()
    wb.remove(wb.active)
    rows = store.db.execute(
        "SELECT l.*, w.work_date, s.name AS site_name, p.name AS payee_name FROM input_line l"
        " JOIN work_log w ON w.id=l.log_id JOIN site s ON s.id=w.site_id JOIN payee p ON p.id=l.payee_id"
        " WHERE substr(w.work_date,1,4)=?", (year,)).fetchall()
    months = [f"{m}월" for m in range(1, 13)]

    ws = wb.create_sheet("사람장비별")
    _c(ws, 1, 1, f"{year}년 사람·장비별 집계 (위 줄 수량, 아래 줄 금액)", bold=True, size=13, border=False)
    _header(ws, 3, ["받는 곳", "구분", "항목", "단위", "", *months, "합계"], [16, 6, 12, 5, 5, *([11] * 12), 13])
    agg: dict[tuple, dict] = {}
    for ln in rows:
        key = (ln["payee_name"], ln["kind"], ln["item"], ln["unit"])
        g = agg.setdefault(key, {"q": defaultdict(float), "a": defaultdict(int)})
        m = int(ln["work_date"][5:7])
        g["q"][m] += float(ln["qty"])
        g["a"][m] += ln["amount"]
    r = 4
    for (payee, kind, item, unit), g in sorted(agg.items(), key=lambda kv: -sum(kv[1]["a"].values())):
        for i, (lab, src, fmt) in enumerate((("수량", g["q"], "0.##"), ("금액", g["a"], WON))):
            _c(ws, r, 1, payee if i == 0 else None, bold=i == 0)
            _c(ws, r, 2, kind if i == 0 else None)
            _c(ws, r, 3, item if i == 0 else None)
            _c(ws, r, 4, unit if i == 0 else "원", align="center")
            _c(ws, r, 5, lab, align="center")
            for m in range(1, 13):
                _c(ws, r, 5 + m, src.get(m) or None, fmt=fmt)
            _c(ws, r, 18, f"=SUM({CL(6)}{r}:{CL(17)}{r})", fmt=fmt, bold=True)
            r += 1
    _c(ws, r, 1, "금액 합계", bold=True)
    for m in range(1, 14):
        col = 5 + m
        _c(ws, r, col, f'=SUMIF($E$4:$E${r - 1},"금액",{CL(col)}4:{CL(col)}{r - 1})', fmt=WON, bold=True)
    _page(ws)

    ws = wb.create_sheet("현장별")
    _c(ws, 1, 1, f"{year}년 현장별 월별 투입", bold=True, size=13, border=False)
    _header(ws, 3, ["현장", *months, "합계"], [24, *([12] * 12), 14])
    site: dict[str, dict] = {}
    for ln in rows:
        site.setdefault(ln["site_name"], defaultdict(int))[int(ln["work_date"][5:7])] += ln["amount"]
    r = 4
    for name, g in sorted(site.items(), key=lambda kv: -sum(kv[1].values())):
        _c(ws, r, 1, name)
        for m in range(1, 13):
            _c(ws, r, 1 + m, g.get(m) or None, fmt=WON)
        _c(ws, r, 14, f"=SUM(B{r}:M{r})", fmt=WON, bold=True)
        r += 1
    _c(ws, r, 1, "합계", bold=True)
    for col in range(2, 15):
        _c(ws, r, col, f"=SUM({CL(col)}4:{CL(col)}{r - 1})", fmt=WON, bold=True)
    _page(ws)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / report_file_name("연말보고", year)
    wb.save(path)
    return path
