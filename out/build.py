from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter as CL
from openpyxl.drawing.image import Image as XImg
from openpyxl.comments import Comment

FN="맑은 고딕"
BLUE="0000FF"; GREEN="008000"
thin=Side(style="thin",color="999999"); BOX=Border(left=thin,right=thin,top=thin,bottom=thin)
F_HEAD=PatternFill("solid",fgColor="1F4E78"); F_SEC=PatternFill("solid",fgColor="DDEBF7")
F_IN=PatternFill("solid",fgColor="FFF2CC"); F_TOT=PatternFill("solid",fgColor="E2EFDA"); F_KEY=PatternFill("solid",fgColor="FCE4D6")
wb=Workbook(); wb.remove(wb.active)
A={}  # key -> absolute ref
def ref(ws,r,c): return f"'{ws.title}'!${CL(c)}${r}"
def cell(ws,r,c,v,bold=False,color=None,fill=None,fmt=None,wrap=False,h=None,size=10,border=True,key=None):
    x=ws.cell(r,c,v)
    x.font=Font(name=FN,bold=bold,color=color,size=size)
    if fill: x.fill=fill
    if fmt: x.number_format=fmt
    x.alignment=Alignment(wrap_text=wrap,vertical="center",horizontal=h)
    if border: x.border=BOX
    if key: A[key]=ref(ws,r,c)
    return x
def title(ws,text,sub=None,width=10):
    cell(ws,1,1,text,bold=True,size=14,border=False)
    if sub: cell(ws,2,1,sub,size=9,color="595959",border=False)
def header(ws,r,cols,start=1):
    for i,t in enumerate(cols):
        cell(ws,r,start+i,t,bold=True,color="FFFFFF",fill=F_HEAD,wrap=True,h="center")
def section(ws,r,text,ncol):
    for c in range(1,ncol+1): cell(ws,r,c,None,fill=F_SEC)
    cell(ws,r,1,text,bold=True,fill=F_SEC)
def widths(ws,ws_):
    for i,w in enumerate(ws_): ws.column_dimensions[CL(i+1)].width=w
def R(k): return A[k]
def fmt_for(v):
    return "#,##0.000" if isinstance(v,float) else "#,##0"

# =====================================================================
# 1. 조건
# =====================================================================
S=wb.create_sheet("1.조건")
title(S,"1. 설계조건·입력값 (U형 개거 B1,000×H1,000, 연장 250m)",
      "노란 바탕+파란 글씨 = 입력값(수정 가능) / 검정 = 계산값. 이 시트만 바꾸면 전 시트가 자동 재계산됩니다.")
header(S,4,["구분","항목","값","단위","근거 / 가정"])
r=5
def inp(key,grp,name,val,unit,note,is_in=True,f=None):
    global r
    cell(S,r,1,grp); cell(S,r,2,name)
    if is_in: cell(S,r,3,val,color=BLUE,fill=F_IN,fmt=f or ("#,##0.000" if isinstance(val,float) else None),key=key)
    else: cell(S,r,3,val,fmt=f or "#,##0.000",key=key)
    cell(S,r,4,unit); cell(S,r,5,note,wrap=True)
    r+=1
def sec(t):
    global r
    section(S,r,t,5); r+=1
sec("1. 연장·블록 (신축줄눈 = 타설 블록 경계)")
inp("L","연장","공사연장 L",250,"m","평면도 '용배수로(1.0×1.0) L=250m' (No.0 ~ No.12+10)",f="0.0")
inp("STA","연장","측점 간격",20,"m","종·횡단면도 20m. ※종단도 시점 'No 6' 표기는 No.0 오표기 → No.0으로 정정 적용",f="0")
inp("B","줄눈","신축줄눈 간격",15,"m","배수구조물상세도 '신축줄눈 : 15.0m 간격 설치'",f="0.0")
inp("NJ","줄눈","신축줄눈 개소",f"=ROUNDUP({A['L']}/{A['B']},0)-1","개소","시점·종점 단부 제외 내부 줄눈",False,"0")
inp("NB","블록","타설 블록 수",f"={A['NJ']}+1","블록","줄눈 개소 + 1",False,"0")
inp("LL","블록","마지막 블록 길이",f"={A['L']}-{A['NJ']}*{A['B']}","m","L − 줄눈개소×간격 (No.12+0 ~ No.12+10)",False,"0.0")
inp("NSET","거푸집","거푸집 투입 세트 수",1,"세트","가정: 1세트(1블록분)를 ①기초→②벽체→다음 블록 순으로 전용. 동시 작업구간을 늘리면 수정",f="0")
inp("LSET","거푸집","1세트 길이",f"={A['B']}","m","줄눈 간격(1블록)과 동일. 마지막 10m 블록은 세트 일부만 사용",False,"0.0")
sec("2. 단면 (m) — 기초 1회 타설, 버림 삭제")
inp("WF","단면","기초 타설폭",1.4,"m","지시: 정확히 1,400 (= 벽체 외면 간 거리, 외벽 6012 겹침 조건)")
inp("TF","단면","기초 두께",0.25,"m","지시: 20cm → 25cm, 버림(25-18-08) 대신 1회 타설")
inp("TW","단면","벽체 두께",0.2,"m","도면 200")
inp("HW","단면","벽체 높이(기초 상면 ~ 벽 상단)",1.0,"m","내공 높이 1,000 (1000×1000 개거)")
inp("HH","단면","헌치 크기(내측, 직각이등변)",0.15,"m","도면 150×150")
inp("BIN","단면","내공폭 (검산)",f"={A['WF']}-2*{A['TW']}","m","1.000 이어야 정상",False)
inp("HT","단면","구조물 총높이",f"={A['TF']}+{A['HW']}","m","기초 250 + 벽 1,000",False)
inp("CB","철근","하면 피복 (흙 접촉)",0.075,"m","버림 삭제 → 흙에 직접 타설: KDS 기준 75mm (도면 50 → 75 상향)")
inp("CT","철근","벽체 상단 피복",0.05,"m","가정")
inp("CE","철근","줄눈 단부 피복",0.05,"m","가정 (줄눈에서 철근 단절)")
sec("3. 콘크리트")
inp("CSPEC","콘크리트","레미콘 규격 (단일)","25-21-08","","지시: 21MPa 통일, 25-18-08 삭제",f="@")
inp("CLOSS","콘크리트","레미콘 할증",0.025,"비율","내역서 관급수량 역산(176→180) 기준",f="0.0%")
sec("4. 유로폼 규격 (m)")
inp("FT","유로폼","유로폼 두께(프레임)",0.0635,"m","표준 63.5mm")
inp("PD","유로폼","비계파이프 외경",0.0486,"m","Ø48.6×2.3t")
inp("H3012","유로폼","3012 높이(눕혀서)",0.3,"m","300×1,200 → 기초 측면에 눕혀 사용")
inp("L1200","유로폼","장변 모듈",1.2,"m","3012·헌치폼 길이")
inp("L600","유로폼","보정 모듈",0.6,"m","3006·헌치폼 L600 / 6012·6090 폭")
inp("H6012","유로폼","6012 높이(세워서)",1.2,"m","600×1,200")
inp("H6090","유로폼","6090 높이",0.9,"m","600×900")
sec("5. 거푸집 조립 가정 (현장 관행 — 수정 가능)")
inp("PINSP","부속","웨지핀 간격(이음변)",0.3,"m","이음변 길이 ÷ 간격 올림")
inp("PINMIN","부속","이음 1개소 최소 핀",2,"EA","")
inp("TIEROW","부속","플랫타이 단수",2,"단","벽 높이 1.0m → 2단 (기초상면 +0.30, +0.75)")
inp("TIESP","부속","플랫타이 수평 간격",0.6,"m","600 패널 이음마다 1개 (외벽·내벽 모듈 일치)")
inp("WRF","부속","띠장 줄수 — ①기초 (측당)",1,"줄","")
inp("WRO","부속","띠장 줄수 — ②외벽 (벽당)",2,"줄","플랫타이 단과 일치")
inp("WRI","부속","띠장 줄수 — ②내벽 (벽당)",2,"줄","")
inp("PIPE","부속","비계파이프 정척",6.0,"m","")
inp("PLAP","부속","띠장 이음 겹침",0.3,"m","")
inp("STKSP","부속","①기초 지지말뚝 간격",1.2,"m","측당, 단관 박기")
inp("STKL","부속","말뚝 길이(단관)",1.0,"m","정척 6m 절단")
inp("XTSP","부속","①기초 상단 반생 연결 간격",1.2,"m","양측 폼 벌어짐 방지 (타설 후 절단)")
inp("BRSP","부속","②외벽 경사버팀 간격",1.8,"m","벽당")
inp("BRL","부속","경사버팀 길이(단관)",1.5,"m","정척 6m 절단")
inp("KBSP","부속","②기리바리 간격",1.2,"m","내벽 띠장 사이 압축버팀")
inp("KBROW","부속","②기리바리 단수",2,"단","띠장 2줄과 동일 높이")
inp("BSL","부속","반생 결속 1개소 길이",0.6,"m","2~3회 감기")
inp("BSW","부속","반생(#8, Ø4.19) 단위중량",f"=PI()*0.00419^2/4*7850","kg/m","강 7,850kg/㎥",False,"0.0000")
inp("LR","부속","반복자재 손실률",0.05,"비율","분실·파손",f="0%")
inp("LC","부속","소모자재 손실률",0.03,"비율","",f="0%")
inp("REL","부속","박리제 소요",0.04,"L/㎡","가정 (1L당 약 25㎡)")
sec("6. 철근")
inp("W16","철근","D16 단위중량",1.56,"kg/m","도면 철근재료표")
inp("W13","철근","D13 단위중량",0.995,"kg/m","도면 철근재료표")
inp("D16","철근","D16 공칭지름",0.016,"m","")
inp("D13","철근","D13 공칭지름",0.013,"m","")
inp("SU","철근","U바(D16) 간격",0.2,"m","도면 N=5/m")
inp("SD","철근","배력근(D13) 간격",0.2,"m","도면 N=17 재현 (수평부 7 + 벽 5×2)")
inp("LAPX","철근","D13 겹이음 길이 배수",20,"×d","지시 '20mm'를 20d(=260mm)로 해석 — 확인필요",f="0")
inp("HBL","철근","헌치 보강근 D16 1본 길이",0.736,"m","도면 ③ (536+100+100)")
inp("HBN","철근","헌치 보강근 개수 / U바 1본",2,"EA","도면 N=10/m (양측). 불필요 시 0")
inp("STK13","철근","D13 정척",8,"m","15m 블록 = 8m×2본 1겹이음",f="0")
inp("STKU","철근","U바 정척",7,"m","U바 3.434m × 2본 = 6.868m (손실 최소)",f="0")
inp("STKH","철근","헌치근 정척",7,"m","0.736 × 9본 = 6.624m",f="0")
inp("RLOSS","철근","철근 할증",0.03,"비율","철근재료표 3%",f="0%")
inp("TIEW","철근","결속선 소요",8,"kg/ton","내역서 단산",f="0")
inp("SPFR","철근","기초 스페이서 열수",3,"열","양 벽체 아래 + 중앙",f="0")
inp("SPFS","철근","기초 스페이서 간격",0.8,"m","연장방향")
inp("SPWR","철근","벽체 스페이서 단수(면당)",2,"단","중앙 1단 배근 → 양면 휠스페이서 (피복 100 확보)",f="0")
inp("SPWS","철근","벽체 스페이서 간격",1.0,"m","연장방향")
sec("7. 줄눈 (지수판·신축이음재·실런트)")
inp("WSSPEC","줄눈","지수판 규격","PVC 200×5t","","지시: 200×5t (도면 150×5t → 변경)",f="@")
inp("WSF","줄눈","지수판 소요계수",1.04,"배","내역서 단산 (이음·절단)")
inp("PLYT","줄눈","신축이음 합판 두께",10,"mm","지시: 10mm (도면 12mm → 변경)",f="0")
inp("PLYF","줄눈","합판 가공손실 계수",1.1,"배","지수판 2분할 가공")
inp("PLYU","줄눈","마구리 합판 전용 횟수",1,"회","보수적으로 1회(매 줄눈 신규). 재사용 시 2~3",f="0")
inp("FILT","줄눈","조인트휠러 두께",20,"mm","지시: 20mm",f="0")
inp("FILF","줄눈","조인트휠러 소요계수",1.1,"배","내역서 단산")
inp("SW","줄눈","실런트 폭",0.02,"m","도면 20×25 (수로측)")
inp("SDP","줄눈","실런트 깊이",0.025,"m","")
inp("STOP","줄눈","실런트 벽체 상단 포함 (1=포함)",1,"","벽 상단 노출면 200×2 포함",f="0")
inp("EPD","줄눈","실런트(에폭시) 밀도",1400,"kg/㎥","내역서 단산",f="0")
inp("EPF","줄눈","실런트 소요계수",1.03,"배","내역서 단산")
inp("SHEET","줄눈","합판 1장 면적 (1,220×2,440)",f"=1.22*2.44","㎡","",False)
sec("8. 토공 검토")
inp("BOTW","토공","도면 터파기 저폭 (횡단면도 판독)",2.2,"m","횡단면도 축척 판독 추정치 — 확인필요")
inp("OLDD","토공","기존 바닥 두께 (버림100+바닥200)",0.3,"m","도면")
inp("WORK","토공","거푸집 작업여유 (측당, 폼·띠장 외측)",0.5,"m","말뚝·버팀·작업자 통로")
widths(S,[12,40,14,9,70])
S.freeze_panes="A5"

# =====================================================================
# 7. 철근 (block sheet references lines/lap)
# =====================================================================
RB=wb.create_sheet("7.철근")
title(RB,"7. 철근 — U바 D16 벽체 중앙 1단 + 헌치근 D16 + 배력근 D13 (연장방향 겹이음)",
      "버림 삭제로 기초가 흙에 직접 접하므로 하면 피복 75mm 적용. 수량은 「3.블록·줄눈」 블록별 산출 합계 연동.")
header(RB,4,["구분","항목","값","단위","산식 / 비고"])
rr=5
def rb(key,grp,name,f,unit,note,fm="#,##0.000"):
    global rr
    cell(RB,rr,1,grp); cell(RB,rr,2,name); cell(RB,rr,3,f,fmt=fm,key=key); cell(RB,rr,4,unit); cell(RB,rr,5,note,wrap=True); rr+=1
def rbsec(t):
    global rr
    section(RB,rr,t,5); rr+=1
rbsec("[A] U바 D16 주력근 — 다리는 각 벽체 두께 중앙(외면에서 100)")
rb("UY","U바","수평부 중심높이 (기초 하면 기준)",f"={R('CB')}+{R('D16')}/2","m","하면 피복 75 + d/2")
rb("UH","U바","수평부 길이 (벽체 중심 ~ 중심)",f"={R('WF')}-{R('TW')}","m","1.400 − 0.200 = 1.200")
rb("ULEG","U바","다리 길이 (1개)",f"={R('HT')}-{R('CT')}-{R('UY')}","m","총높이 − 상단피복 − 수평부 높이")
rb("ULEN","U바","U바 1본 길이",f"={R('UH')}+2*{R('ULEG')}","m","도면 3.500(1.3+1.1×2) → 3.434")
rb("UN","U바","총 본수",None,"본","「3.블록·줄눈」 블록별 (블록길이−2×단부피복)÷간격+1 합계","#,##0")
rb("ULT","U바","총 길이",None,"m","")
rb("UWT","U바","중량",None,"ton","")
rbsec("[B] 헌치 보강근 D16 — 도면 ③ 유지")
rb("HN","헌치근","총 본수",None,"본","U바 1본당 양측 2본","#,##0")
rb("HLT","헌치근","총 길이",None,"m","")
rb("HWT","헌치근","중량",None,"ton","")
rbsec("[C] 배력근 D13 — 연장방향, 줄눈에서 단절, 블록 내 겹이음")
rb("NLH","D13","수평부(기초) 본수",f"=INT({R('UH')}/{R('SD')}+0.0001)+1","본","1.2÷0.2+1 = 7 (U바 수평부 위)","0")
rb("NLV","D13","벽체 다리당 본수",f"=INT({R('ULEG')}/{R('SD')}+0.0001)","본","1.117÷0.2 → 5 (U바 다리 내측)","0")
rb("NL","D13","단면당 라인 수",f"={R('NLH')}+2*{R('NLV')}","본","17본 (도면 N=17 일치)","0")
rb("LAP","D13","겹이음 길이",f"={R('LAPX')}*{R('D13')}","m","20d (확인필요)")
rb("D13LT","D13","총 길이 (겹이음 포함)",None,"m","「3.블록·줄눈」 합계")
rb("D13LAPN","D13","겹이음 개소",None,"개소","","#,##0")
rb("D13WT","D13","중량",None,"ton","")
rbsec("[D] 집계")
rr0=rr
header(RB,rr,["구분","정미 (ton)","할증","소요 (ton) = 관급 발주","내역서 관급(ton) / 차이"]); rr+=1
def rbrow(k,name,f,cmp):
    global rr
    cell(RB,rr,1,name); cell(RB,rr,2,f,fmt="0.000",key=k+"N"); cell(RB,rr,3,f"={R('RLOSS')}",fmt="0%")
    cell(RB,rr,4,f"={CL(2)}{rr}*(1+{CL(3)}{rr})",fmt="0.000",key=k+"S",fill=F_KEY); cell(RB,rr,5,cmp); rr+=1
rbrow("RD16","D16 (U바+헌치근)",f"={R('UWT').split('!')[1]}+{R('HWT').split('!')[1]}","내역서 9.785")
rbrow("RD13","D13 (배력근)",f"={R('D13WT').split('!')[1]}","내역서 4.378")
cell(RB,rr,1,"합계",bold=True,fill=F_TOT); cell(RB,rr,2,f"=B{rr-2}+B{rr-1}",fmt="0.000",bold=True,fill=F_TOT,key="RTN")
cell(RB,rr,3,None,fill=F_TOT); cell(RB,rr,4,f"=D{rr-2}+D{rr-1}",fmt="0.000",bold=True,fill=F_TOT,key="RTS"); cell(RB,rr,5,"내역서 14.163",fill=F_TOT); rr+=1
cell(RB,rr,1,"결속선 #20"); cell(RB,rr,2,f"={R('RTN').split('!')[1]}*{R('TIEW')}",fmt="0.0",key="TIEKG"); cell(RB,rr,3,None); cell(RB,rr,4,f"=B{rr}",fmt="0.0"); cell(RB,rr,5,"kg (8kg/ton)"); rr+=2
rbsec("[E] 정척 절단계획 (가공장 발주 참고 — 할증 3%와 비교)")
header(RB,rr,["철근","가공길이(m)","정척(m) / 1본당 채취","필요 정척 본수","정척 중량(ton) / 손실률"]); rr+=1
EROW=rr
cell(RB,rr,1,"D16 U바"); cell(RB,rr,2,f"={R('ULEN').split('!')[1]}",fmt="0.000")
cell(RB,rr,3,f"={R('STKU')}&\"m / \"&INT({R('STKU')}/B{rr})&\"본\""); cell(RB,rr,4,f"=ROUNDUP({R('UN').split('!')[1]}/INT({R('STKU')}/B{rr}),0)",fmt="#,##0",key="CUTU")
cell(RB,rr,5,f"=D{rr}*{R('STKU')}*{R('W16')}/1000",fmt="0.000",key="CUTUW"); rr+=1
cell(RB,rr,1,"D16 헌치근"); cell(RB,rr,2,f"={R('HBL')}",fmt="0.000")
cell(RB,rr,3,f"={R('STKH')}&\"m / \"&INT({R('STKH')}/B{rr})&\"본\""); cell(RB,rr,4,f"=ROUNDUP({R('HN').split('!')[1]}/INT({R('STKH')}/B{rr}),0)",fmt="#,##0",key="CUTH")
cell(RB,rr,5,f"=D{rr}*{R('STKH')}*{R('W16')}/1000",fmt="0.000",key="CUTHW"); rr+=1
cell(RB,rr,1,"D13 배력근"); cell(RB,rr,2,"블록별 산출")
cell(RB,rr,3,f"={R('STK13')}&\"m 정척\""); cell(RB,rr,4,None,fmt="#,##0",key="CUT13")
cell(RB,rr,5,f"=D{rr}*{R('STK13')}*{R('W13')}/1000",fmt="0.000",key="CUT13W"); rr+=1
cell(RB,rr,1,"D16 정척 합계 / 손실률",bold=True); cell(RB,rr,2,None); cell(RB,rr,3,None)
cell(RB,rr,4,f"=E{EROW}+E{EROW+1}",fmt="0.000",bold=True); cell(RB,rr,5,f"=D{rr}/{R('RD16N').split('!')[1]}-1",fmt="0.0%"); rr+=1
cell(RB,rr,1,"D13 정척 합계 / 손실률",bold=True); cell(RB,rr,2,None); cell(RB,rr,3,None)
cell(RB,rr,4,f"=E{EROW+2}",fmt="0.000",bold=True); cell(RB,rr,5,f"=D{rr}/{R('RD13N').split('!')[1]}-1",fmt="0.0%"); rr+=1
cell(RB,rr,1,"※ D13은 마지막 블록 짧은 토막(2.16m 등)을 정척 1본에서 여러 개 채취하는 것으로 계산. 정척 손실률이 3%를 넘으면 잔재 재활용 또는 발주 정척 조정 검토.",border=False,size=9); rr+=2
rbsec("[F] 스페이서 (버림 없음 → 고임 필수)")
rb("SPF","스페이서","기초 콘크리트 스페이서 75mm",None,"EA","「3.블록·줄눈」 합계 (3열 @0.8m)","#,##0")
rb("SPW","스페이서","벽체 휠스페이서 100mm",None,"EA","양 벽 × 양면 × 2단 @1.0m","#,##0")
widths(RB,[18,34,22,22,55])

# =====================================================================
# 3. 블록·줄눈 (per block simulation)
# =====================================================================
BK=wb.create_sheet("3.블록·줄눈")
title(BK,"3. 타설 블록별 산출 (신축줄눈 15.0m 간격 = 블록 경계, 블록마다 ①기초 → ②벽체 2회 타설)",
      "시점 No.0 기준(종단도 'No 6' 오표기 정정). 각 블록은 이전 블록 줄눈면(조인트휠러 부착)에 붙여 타설하고 종점측에 마구리 합판을 설치합니다.")
cols=["블록","시점거리(m)","종점거리(m)","시점 측점","종점 측점","길이(m)","종점측 구분",
      "①기초 콘크리트(㎥)","②벽체+헌치 콘크리트(㎥)","①기초 거푸집(㎡)","②벽체 거푸집(㎡)",
      "U바 D16(본)","D13 라인당 정척수","D13 라인길이(m,겹이음포함)","D13 총길이(m)","D13 겹이음(개소)",
      "플랫타이(EA)","마구리 개소(①·② 각)","기초 스페이서(EA)","벽체 스페이서(EA)"]
header(BK,4,cols)
NBV=17
stf=lambda c: f"\"No.\"&INT({c}/{R('STA')})&IF(MOD({c},{R('STA')})>0.0001,\"+\"&TEXT(MOD({c},{R('STA')}),\"0.0\"),\"\")"
for i in range(1,NBV+1):
    r=4+i
    cell(BK,r,1,i,h="center")
    cell(BK,r,2,f"=(A{r}-1)*{R('B')}",fmt="0.0")
    cell(BK,r,6,f"=IF(A{r}<{R('NB')},{R('B')},{R('LL')})",fmt="0.0")
    cell(BK,r,3,f"=B{r}+F{r}",fmt="0.0")
    cell(BK,r,4,f"={stf('B'+str(r))}",h="center"); cell(BK,r,5,f"={stf('C'+str(r))}",h="center")
    cell(BK,r,7,f"=IF(A{r}<{R('NB')},\"신축줄눈 #\"&A{r},\"공사종점(단부)\")")
    cell(BK,r,8,f"={R('WF')}*{R('TF')}*F{r}",fmt="0.000")
    cell(BK,r,9,f"=(2*{R('TW')}*{R('HW')}+{R('HH')}^2)*F{r}",fmt="0.000")
    cell(BK,r,10,f"=2*{R('TF')}*F{r}",fmt="0.00")
    cell(BK,r,11,f"=(2*{R('HW')}+2*({R('HW')}-{R('HH')})+2*SQRT(2)*{R('HH')})*F{r}",fmt="0.00")
    cell(BK,r,12,f"=INT((F{r}-2*{R('CE')})/{R('SU')}+0.0001)+1",fmt="0")
    cell(BK,r,13,f"=ROUNDUP((F{r}-2*{R('CE')}-{R('LAP')})/({R('STK13')}-{R('LAP')}),0)",fmt="0")
    cell(BK,r,14,f"=F{r}-2*{R('CE')}+(M{r}-1)*{R('LAP')}",fmt="0.000")
    cell(BK,r,15,f"=N{r}*{R('NL')}",fmt="0.00")
    cell(BK,r,16,f"=(M{r}-1)*{R('NL')}",fmt="0")
    cell(BK,r,17,f"=(INT(F{r}/{R('TIESP')}+0.0001)+1)*{R('TIEROW')}*2",fmt="0")
    cell(BK,r,18,f"=IF(A{r}=1,2,1)",fmt="0")
    cell(BK,r,19,f"={R('SPFR')}*(ROUNDUP((F{r}-2*{R('CE')})/{R('SPFS')},0)+1)",fmt="0")
    cell(BK,r,20,f"=2*2*{R('SPWR')}*(ROUNDUP((F{r}-2*{R('CE')})/{R('SPWS')},0)+1)",fmt="0")
TR=5+NBV
cell(BK,TR,1,"합계",bold=True,fill=F_TOT)
for c in range(2,21): cell(BK,TR,c,None,fill=F_TOT)
for c,fm in [(6,"0.0"),(8,"0.000"),(9,"0.000"),(10,"0.00"),(11,"0.00"),(12,"#,##0"),(15,"#,##0.00"),(16,"#,##0"),(17,"#,##0"),(18,"0"),(19,"#,##0"),(20,"#,##0")]:
    cell(BK,TR,c,f"=SUM({CL(c)}5:{CL(c)}{TR-1})",fmt=fm,bold=True,fill=F_TOT)
cell(BK,TR+1,1,"검산",bold=True)
cell(BK,TR+1,2,f"=IF(ABS(F{TR}-{R('L')})<0.001,\"블록 길이 합 = 공사연장 OK\",\"블록 행 수 조정 필요 (블록 수 \"&{R('NB')}&\")\")",border=False)
cell(BK,TR+2,1,"※ 마구리 개소: 1블록은 시점 단부+종점측 2개소, 이후 블록은 종점측 1개소 (시점측은 이전 블록의 줄눈면 이용) → 총 = 줄눈 16 + 시·종점 단부 2 = 18개소 × ①기초·②벽체 각 1회.",border=False,size=9)
A["BK_TR"]=TR
for k,c in [("BK_L",6),("BK_CF",8),("BK_CW",9),("BK_FF",10),("BK_FW",11),("BK_U",12),("BK_D13",15),("BK_LAPN",16),("BK_TIE",17),("BK_END",18),("BK_SPF",19),("BK_SPW",20)]:
    A[k]=ref(BK,TR,c)
widths(BK,[6,9,9,11,11,7,15,10,10,10,10,8,9,11,11,9,9,9,9,9])
BK.freeze_panes="B5"; BK.row_dimensions[4].height=45
# fill rebar dependent cells
def setc(key,f):
    sh,addr=A[key].split("!"); ws=wb[sh.strip("'")]; ws[addr.replace("$","")].value=f
setc("UN",f"={A['BK_U']}"); setc("ULT",f"={R('UN')}*{R('ULEN')}"); setc("UWT",f"={R('ULT')}*{R('W16')}/1000")
setc("HN",f"={R('UN')}*{R('HBN')}"); setc("HLT",f"={R('HN')}*{R('HBL')}"); setc("HWT",f"={R('HLT')}*{R('W16')}/1000")
setc("D13LT",f"={A['BK_D13']}"); setc("D13LAPN",f"={A['BK_LAPN']}"); setc("D13WT",f"={R('D13LT')}*{R('W13')}/1000")
setc("SPF",f"={A['BK_SPF']}"); setc("SPW",f"={A['BK_SPW']}")
# D13 cutting: per general block lines×bars + last block: 8m + remainder pieces
setc("CUT13",f"=({R('NB')}-1)*{R('NL')}*'3.블록·줄눈'!$M$5+{R('NL')}*(INT(('3.블록·줄눈'!$N${TR-1})/{R('STK13')}))+ROUNDUP({R('NL')}/MAX(1,INT({R('STK13')}/MAX(0.001,MOD('3.블록·줄눈'!$N${TR-1},{R('STK13')})))),0)")

# =====================================================================
# 4. 콘크리트
# =====================================================================
CC=wb.create_sheet("4.콘크리트")
title(CC,"4. 콘크리트 — 25-21-08 단일 규격 (버림 삭제, 기초 250 1회 타설)","단면적 = m당 체적. 타설은 블록마다 ①기초 → ②벽체+헌치 2회.")
header(CC,4,["부위","산식","단면적(㎡)","총량(㎥)","블록당(15m)(㎥)","타설 횟수","비고"])
rows=[("① 기초","폭 1.400 × 두께 0.250",f"={R('WF')}*{R('TF')}",A["BK_CF"],"1회 타설 (버림 대체)"),
      ("② 벽체 (양측)","2 × 0.200 × 1.000",f"=2*{R('TW')}*{R('HW')}",None,"기초 상면 = 수평 시공이음"),
      ("② 헌치 (양측)","2 × ½ × 0.15²",f"={R('HH')}^2",None,"벽체와 일체 타설")]
r=5
for n,fx,a,tot,note in rows:
    cell(CC,r,1,n); cell(CC,r,2,fx); cell(CC,r,3,a,fmt="0.0000")
    cell(CC,r,4,f"=C{r}*{R('L')}",fmt="0.000"); cell(CC,r,5,f"=C{r}*{R('B')}",fmt="0.000")
    cell(CC,r,6,f"={R('NB')}",fmt="0"); cell(CC,r,7,note); r+=1
cell(CC,r,1,"합계",bold=True,fill=F_TOT); cell(CC,r,2,None,fill=F_TOT)
for c in (3,4,5): cell(CC,r,c,f"=SUM({CL(c)}5:{CL(c)}{r-1})",fmt="0.000",bold=True,fill=F_TOT)
A["CNET"]=ref(CC,r,4); cell(CC,r,6,f"=2*{R('NB')}",fmt="0",fill=F_TOT); cell(CC,r,7,"①17회 + ②17회 = 34회 타설",fill=F_TOT)
r+=1
cell(CC,r,1,"검산: 블록 합계"); cell(CC,r,4,f"={A['BK_CF']}+{A['BK_CW']}",fmt="0.000"); cell(CC,r,7,"「3.블록·줄눈」 합계와 일치해야 함"); r+=2
header(CC,r,["레미콘","정미(㎥)","할증","소요(㎥)","발주(올림,㎥)","내역서 관급(㎥)","비고"]); r+=1
cell(CC,r,1,"=" + R('CSPEC')); cell(CC,r,2,f"={A['CNET']}",fmt="0.000"); cell(CC,r,3,f"={R('CLOSS')}",fmt="0.0%")
cell(CC,r,4,f"=B{r}*(1+C{r})",fmt="0.000"); cell(CC,r,5,f"=ROUNDUP(D{r},0)",fmt="0",key="CORD",fill=F_KEY); cell(CC,r,6,180); cell(CC,r,7,"관급 발주 변경 필요"); r+=1
cell(CC,r,1,"25-18-08"); cell(CC,r,2,0); cell(CC,r,3,None); cell(CC,r,4,0); cell(CC,r,5,0); cell(CC,r,6,41); cell(CC,r,7,"삭제 (21MPa 통일, 버림 없음)"); r+=2
cell(CC,r,1,"※ 블록당 ①기초 5.25㎥ / ②벽체 6.34㎥ 소량 타설 → 레미콘 배차 최소단위·펌프카 운용 계획 필요. 줄눈(20mm) 공간 체적(약 0.25㎥)은 무시.",border=False,size=9)
widths(CC,[16,24,12,12,14,12,36])

# =====================================================================
# 5. 거푸집
# =====================================================================
FW=wb.create_sheet("5.거푸집")
title(FW,"5. 거푸집(유로폼) — 공정별 조립 시뮬레이션 기준 (기초 양측 + 벽체 외·내벽 양측)",
      "① 기초: 3012 눕혀 양측 → 타설 → 탈형 / ② 외벽 6012 세워 양측(하단 200 기초 겹침) + 내벽 헌치150 눕힘 + 6090 양측 → 타설 → 탈형 → 다음 블록")
r=4; section(FW,r,"A. 접촉면적 (콘크리트와 닿는 면, 전체 연장) — 내역 수량 기준",8); r+=1
header(FW,r,["공정","폼","접촉높이(m)","면수","㎡/m","총 접촉면적(㎡)","단계","비고"]); r+=1
fa=r
data=[("① 기초 측면 (좌·우)","3012 눕힘",f"={R('TF')}",2,"①","타설높이 250 (폼 300)"),
      ("② 외벽 (좌벽 외면·우벽 외면)","6012 세움",f"={R('HW')}",2,"②","기초 상면 위 1.0m (하단 0.2m는 기초 겹침 → 비접촉)"),
      ("② 내벽 직면부 (좌·우)","6090",f"={R('HW')}-{R('HH')}",2,"②","1.0 − 헌치 0.15"),
      ("② 헌치 경사면 (좌·우)","헌치폼150 눕힘",f"=SQRT(2)*{R('HH')}",2,"②","√2 × 0.15")]
for n,fm_,h,s,stg,note in data:
    cell(FW,r,1,n); cell(FW,r,2,fm_); cell(FW,r,3,h,fmt="0.0000"); cell(FW,r,4,s)
    cell(FW,r,5,f"=C{r}*D{r}",fmt="0.0000"); cell(FW,r,6,f"=E{r}*{R('L')}",fmt="#,##0.00"); cell(FW,r,7,stg,h="center"); cell(FW,r,8,note); r+=1
cell(FW,r,1,"합계 (유로폼)",bold=True,fill=F_TOT)
for c in range(2,9): cell(FW,r,c,None,fill=F_TOT)
cell(FW,r,5,f"=SUM(E{fa}:E{r-1})",fmt="0.0000",bold=True,fill=F_TOT); cell(FW,r,6,f"=SUM(F{fa}:F{r-1})",fmt="#,##0.00",bold=True,fill=F_KEY,key="FAREA")
A["FA1"]=ref(FW,fa,6); A["FA2"]=f"SUM('5.거푸집'!$F${fa+1}:$F${fa+3})"; r+=1
cell(FW,r,1,"검산: 블록 합계"); cell(FW,r,6,f"={A['BK_FF']}+{A['BK_FW']}",fmt="#,##0.00"); r+=1
cell(FW,r,1,"내역서 비교"); cell(FW,r,2,"보통 1,130 + 간단(버림) 50 = 1,180㎡"); cell(FW,r,6,f"={R('FAREA')}-1180",fmt="#,##0.00;[Red]-#,##0.00"); cell(FW,r,8,"버림 삭제로 간단 폼 소멸, 기초 측면은 양측 산정"); r+=1
cell(FW,r,1,"마구리(단부) 거푸집은 합판 t10 → 「8.줄눈」에서 산출 (유로폼 아님)",border=False,size=9); r+=2

section(FW,r,"B. 투입 세트 패널 수량 (1세트 = 1블록 15.0m, 블록마다 전용) — 측(면)당 × 면수",9); r+=1
header(FW,r,["단계·부위","패널","규격(mm)","배치 방향","측당 매수","면수","세트당(EA)","반입(EA) ×세트수","배치 산식"]); r+=1
pb=r
n1200=f"INT({R('LSET')}/{R('L1200')}+0.0001)"
rem=f"({R('LSET')}-{n1200}*{R('L1200')})"
panels=[("① 기초 좌·우","유로폼 3012","300×1,200","눕힘(장변=연장)",f"={n1200}",2,"세트길이 ÷ 1.2 정수"),
        ("① 기초 좌·우","유로폼 3006 (보정)","300×600","눕힘",f"=IF({rem}>0.001,ROUNDUP({rem}/{R('L600')},0),0)",2,"잔여 0.6m 보정"),
        ("② 외벽 좌·우","유로폼 6012","600×1,200","세움(높이 1.2)",f"=ROUNDUP({R('LSET')}/{R('L600')},0)",2,"세트길이 ÷ 0.6"),
        ("② 내벽 좌·우 하부","헌치폼 150 L1200","150×150×1,200","눕힘",f"={n1200}",2,"헌치 경사면"),
        ("② 내벽 좌·우 하부","헌치폼 150 L600 (보정)","150×150×600","눕힘",f"=IF({rem}>0.001,ROUNDUP({rem}/{R('L600')},0),0)",2,"잔여 보정"),
        ("② 내벽 좌·우 상부","유로폼 6090","600×900","세움(높이 0.9)",f"=ROUNDUP({R('LSET')}/{R('L600')},0)",2,"헌치폼 위 적층")]
keys=["P3012","P3006","P6012","PH12","PH06","P6090"]
for (st_,nm,sz,dr,f,sides,note),k in zip(panels,keys):
    cell(FW,r,1,st_); cell(FW,r,2,nm); cell(FW,r,3,sz); cell(FW,r,4,dr); cell(FW,r,5,f,fmt="0",key=k+"S"); cell(FW,r,6,sides)
    cell(FW,r,7,f"=E{r}*F{r}",fmt="0"); cell(FW,r,8,f"=G{r}*{R('NSET')}",fmt="0",key=k,fill=F_KEY); cell(FW,r,9,note); r+=1
cell(FW,r,1,"합계",bold=True,fill=F_TOT)
for c in range(2,10): cell(FW,r,c,None,fill=F_TOT)
cell(FW,r,7,f"=SUM(G{pb}:G{r-1})",fmt="0",bold=True,fill=F_TOT); cell(FW,r,8,f"=SUM(H{pb}:H{r-1})",fmt="0",bold=True,fill=F_TOT); r+=1
cell(FW,r,1,"※ 패널은 종류별 별개 자재 → 단계 간 공용 불가(합산). 3012는 ①단계 후 회수되어 다음 블록 기초로 이동, 6012·6090·헌치폼은 ②단계 전용.",border=False,size=9); r+=1
cell(FW,r,1,"※ 마지막 블록(10.0m)은 세트 일부 사용: 3012 8+3006 1(10.2m), 6012·6090 17매(10.2m) — 종점 단부 쪽으로 0.2m 돌출 허용.",border=False,size=9); r+=2

section(FW,r,"C. 조립 높이·치수 검토",5); r+=1
header(FW,r,["검토 항목","값(m)","기준","판정","조치"]); r+=1
chk=[("기초폼 3012 높이 − 기초두께 (상단 여유)",f"={R('H3012')}-{R('TF')}",">=0",f"=IF(B{{r}}>=0,\"OK\",\"NG\")","상단 50 여유, 타설면 레벨 표시"),
     ("외벽 6012 하단 겹침 = 1.2 − 벽높이",f"={R('H6012')}-{R('HW')}","< 기초두께",f"=IF(B{{r}}<{R('TF')},\"OK\",\"NG\")","겹침 200, 폼 하단은 바닥에서 50 위 → 고임목"),
     ("내벽 헌치150 + 6090 − 벽높이 (상단 초과)",f"={R('HH')}+{R('H6090')}-{R('HW')}","0 이상",f"=IF(B{{r}}>=0,\"OK(초과 \"&TEXT(B{{r}}*1000,\"0\")&\"mm)\",\"부족\")","내벽 타설선 표시 (외벽 상단 = 마감 기준)"),
     ("기초폭 = 벽체 외면 간 거리",f"={R('WF')}-(2*{R('TW')}+{R('BIN')})","= 0",f"=IF(ABS(B{{r}})<0.0001,\"일치\",\"불일치\")","기초폭 1,400 정밀 시공 필수 (외벽폼 밀착)"),
     ("기리바리 길이 (내벽 띠장 사이)",f"={R('BIN')}-2*({R('FT')}+{R('PD')})","",'="참고"',"조절식 또는 각재 절단 ≈ 0.78m"),
     ("기초 지지말뚝 위치 (기초 외면에서)",f"={R('FT')}+{R('PD')}","",'="참고"',"폼+띠장 바로 외측")]
for n,f,crit,j,act in chk:
    cell(FW,r,1,n); cell(FW,r,2,f,fmt="0.000"); cell(FW,r,3,crit); cell(FW,r,4,j.replace("{r}",str(r))); cell(FW,r,5,act); r+=1
widths(FW,[30,22,16,16,12,14,12,16,28])

# =====================================================================
# 6. 거푸집 부속
# =====================================================================
AC=wb.create_sheet("6.거푸집부속")
title(AC,"6. 거푸집 부속자재 — 반복자재는 ①기초·②벽체 단계 중 큰 값 1회만 (중복 산출 금지)",
      "근거: 외벽 6012가 기초 측면을 200 겹치므로 ②벽체 조립 전에 ①기초 폼을 반드시 탈형 → 웨지핀·파이프·말뚝이 ②단계로 그대로 전용됩니다.")
r=4; section(AC,r,"A. 반복자재 (세트 반입 수량)",9); r+=1
header(AC,r,["자재","규격","단위","①기초 단계","②벽체 단계","반입 기준 = MAX","손실률","반입 수량 (×세트)","산정 근거"]); r+=1
pinjf=lambda length: f"MAX({R('PINMIN')},ROUNDUP({length}/{R('PINSP')},0))"
nf=f"({R('P3012S')}+{R('P3006S')})"
pin1=f"=2*({nf}-1)*{pinjf(R('H3012'))}"
pin2=(f"=2*({R('P6012S')}-1)*{pinjf(R('H6012'))}"
      f"+2*({R('P6090S')}-1)*{pinjf(R('H6090'))}"
      f"+2*{R('P6090S')}*{R('PINMIN')}"
      f"+2*({R('PH12S')}+{R('PH06S')}-1)*{R('PINMIN')}"
      f"+{R('TIEROW')}*2*2*2")
ppr=f"ROUNDUP(({R('LSET')}-{R('PLAP')})/({R('PIPE')}-{R('PLAP')}),0)"
stk1=f"2*(ROUNDUP({R('LSET')}/{R('STKSP')},0)+1)"
br2=f"2*(ROUNDUP({R('LSET')}/{R('BRSP')},0)+1)"
kb2=f"{R('KBROW')}*(ROUNDUP({R('LSET')}/{R('KBSP')},0)+1)"
items=[("PIN","폼핀 (웨지핀 세트)","핀+쐐기","EA",pin1,pin2,"①: 3012·3006 맞댐 (측당 12개소×2핀)×2측 / ②: 6012 세로이음 4핀, 6090 세로이음 3핀, 6090↔헌치폼 적층 2핀/매, 헌치폼 맞댐 2핀, 단부 플랫타이 고정핀"),
       ("PIPE6","비계파이프 (띠장)","Ø48.6×2.3t, 6m","본",f"={R('WRF')}*2*{ppr}",f"=({R('WRO')}+{R('WRI')})*2*{ppr}","①: 1줄×2측 / ②: (외2+내2)줄×2벽, 줄당 6m 3본(겹침 0.3)"),
       ("STK","지지말뚝 / 버팀 말뚝","단관 L=1.0m","EA",f"={stk1}",f"={br2}","①: 기초폼 외측 @1.2m 양측 / ②: 경사버팀 하단 말뚝 (①말뚝 회수 재사용)"),
       ("BRC","경사버팀","단관 L=1.5m","EA",0,f"={br2}","②: 외벽 띠장 → 지반, @1.8m 양벽"),
       ("CLP","클램프 (자재형)","Ø48.6용","EA",0,f"=2*{br2}","②: 경사버팀 상·하단 각 1"),
       ("KB","기리바리 (내벽 가로버팀)","조절식/각재 L≈0.78m","EA",0,f"={kb2}","②: 내벽 띠장 사이 2단 @1.2m (①기초는 상단 반생 연결로 대체)")]
a0=r
for k,nm,spec,u,f1,f2,note in items:
    cell(AC,r,1,nm); cell(AC,r,2,spec); cell(AC,r,3,u); cell(AC,r,4,f1,fmt="#,##0"); cell(AC,r,5,f2,fmt="#,##0")
    cell(AC,r,6,f"=MAX(D{r},E{r})",fmt="#,##0"); cell(AC,r,7,f"={R('LR')}",fmt="0%")
    cell(AC,r,8,f"=ROUNDUP(F{r}*(1+G{r}),0)*{R('NSET')}",fmt="#,##0",fill=F_KEY,key=k); cell(AC,r,9,note,wrap=True); r+=1
cell(AC,r,1,"단관 절단용 6m 파이프 환산",bold=True); cell(AC,r,2,"말뚝 6본/정척, 버팀 4본/정척"); cell(AC,r,3,"본")
for c in (4,5,6,7): cell(AC,r,c,None)
cell(AC,r,8,f"=ROUNDUP({R('STK')}/INT({R('PIPE')}/{R('STKL')}),0)+ROUNDUP({R('BRC')}/INT({R('PIPE')}/{R('BRL')}),0)",fmt="#,##0",key="PIPECUT",fill=F_KEY)
cell(AC,r,9,"띠장용 6m와 별도 (절단 단관은 띠장 전용 불가)"); r+=1
cell(AC,r,1,"비계파이프 6m 총 반입",bold=True,fill=F_TOT)
for c in range(2,8): cell(AC,r,c,None,fill=F_TOT)
cell(AC,r,8,f"={R('PIPE6')}+{R('PIPECUT')}",fmt="#,##0",bold=True,fill=F_TOT,key="PIPETOT"); cell(AC,r,9,"띠장 + 단관 절단분",fill=F_TOT); r+=2

section(AC,r,"B. 소모자재 (매 블록 소멸 → 블록별 합산)",9); r+=1
header(AC,r,["자재","규격","단위","일반블록 1개 (15m)","마지막블록 (10m)","전체 정미 = 일반×(블록수−1)+마지막","손실률","소요 수량","산정 근거"]); r+=1
LB=R('B'); LLs=R('LL')
def per(Lx):
    tie=f"(INT({Lx}/{R('TIESP')}+0.0001)+1)*{R('TIEROW')}*2"
    stk=f"2*(ROUNDUP({Lx}/{R('STKSP')},0)+1)"
    xt=f"(ROUNDUP({Lx}/{R('XTSP')},0)+1)"
    kb=f"{R('KBROW')}*(ROUNDUP({Lx}/{R('KBSP')},0)+1)"
    bs=(f"({stk}*{R('BSL')}+{xt}*({R('WF')}+2*({R('FT')}+{R('PD')})+{R('BSL')})"
        f"+{tie}*2*{R('BSL')}+{kb}*2*{R('BSL')}+2*({R('WRF')}*2+({R('WRO')}+{R('WRI')})*2)*{R('BSL')})*{R('BSW')}")
    return tie,bs
t1,b1=per(LB); t2,b2=per(LLs)
cons=[("TIE","플랫타이","벽두께 200용","EA",f"={t1}",f"={t2}","2단 × 600 이음마다 × 양벽 (외벽↔내벽 관통, 매립·절단)","0"),
      ("BS","반생 (소둔철선 #8)","Ø4.19mm","kg",f"={b1}",f"={b2}","①말뚝 결속 + ①기초 상단 연결선(1.4m+여유) + ②플랫타이 양단 띠장 결속 + ②기리바리 양단 + 띠장 이음","0.0")]
for k,nm,spec,u,f1,f2,note,fm in cons:
    cell(AC,r,1,nm); cell(AC,r,2,spec); cell(AC,r,3,u); cell(AC,r,4,f1,fmt=fm); cell(AC,r,5,f2,fmt=fm)
    cell(AC,r,6,f"=D{r}*({R('NB')}-1)+E{r}",fmt="#,##0.0",key=k+"N"); cell(AC,r,7,f"={R('LC')}",fmt="0%")
    cell(AC,r,8,f"=ROUNDUP(F{r}*(1+G{r}),0)",fmt="#,##0",fill=F_KEY,key=k); cell(AC,r,9,note,wrap=True); r+=1
cell(AC,r,1,"검산: 플랫타이 블록표 합계"); cell(AC,r,6,f"={A['BK_TIE']}",fmt="#,##0"); r+=1
cell(AC,r,1,"박리제"); cell(AC,r,2,"유성/수성"); cell(AC,r,3,"L"); cell(AC,r,4,None); cell(AC,r,5,None)
cell(AC,r,6,f"={R('FAREA')}*{R('REL')}",fmt="#,##0.0"); cell(AC,r,7,f"={R('LC')}",fmt="0%"); cell(AC,r,8,f"=ROUNDUP(F{r}*(1+G{r}),0)",fmt="#,##0",fill=F_KEY,key="REL_Q"); cell(AC,r,9,"접촉면적 × 0.04L/㎡ (가정)"); r+=2
cell(AC,r,1,"※ 반복자재 중복 금지 원칙: 웨지핀·파이프·말뚝은 ①단계에서 쓴 것을 탈형 후 ②단계에 그대로 사용 → 두 단계 중 큰 값만 반입. ①과 ②를 서로 다른 블록에서 동시에 진행하면(병행) 합산이 필요하므로 「1.조건」 세트 수로 조정.",border=False,size=9)
widths(AC,[26,20,6,14,14,18,8,14,70])

# =====================================================================
# 8. 줄눈
# =====================================================================
JT=wb.create_sheet("8.줄눈")
title(JT,"8. 신축줄눈 — 지수판 PVC 200×5t · 합판 t10 · 조인트휠러 t20 · 실런트 20×25 (설치간격 15.0m)",
      "모든 줄눈 자재는 같은 위치(신축줄눈)에 1조로 설치. 지수판은 ①기초 단계에 U자로 세워 설치하고 상부 다리는 ②벽체에서 매립.")
r=4; section(JT,r,"A. 줄눈 1개소당 수량 (단면 기하 산출)",6); r+=1
header(JT,r,["항목","①기초부","②벽체+헌치부","1개소 합계","단위","산식"]); r+=1
jrows=[("JWS","지수판 연장",f"={R('WF')}-{R('TW')}",f"=2*({R('HT')}-{R('CT')}-{R('TF')}/2)","m","수평 1.2(기초 중앙) + 수직 2×(1.25−0.05−0.125). 도면 3.4 → 3.35"),
       ("JSEC","줄눈 단면적 (합판·휠러)",f"={R('WF')}*{R('TF')}",f"=2*{R('TW')}*{R('HW')}+{R('HH')}^2","㎡","기초 0.35 + 벽 0.4 + 헌치 0.0225"),
       ("JSL","실런트 연장 (수로측)",f"={R('BIN')}-2*{R('HH')}",f"=2*SQRT(2)*{R('HH')}+2*({R('HW')}-{R('HH')})+{R('STOP')}*2*{R('TW')}","m","바닥 0.7 + 헌치 0.424 + 내벽 1.7 + 상단 0.4")]
for k,n,f1,f2,u,note in jrows:
    cell(JT,r,1,n); cell(JT,r,2,f1,fmt="0.0000"); cell(JT,r,3,f2,fmt="0.0000"); cell(JT,r,4,f"=B{r}+C{r}",fmt="0.0000",key=k,bold=True); cell(JT,r,5,u); cell(JT,r,6,note); r+=1
r+=1
section(JT,r,"B. 설치 위치·간격표 (15.0m 간격, 측점 No.0 기준)",9); r+=1
header(JT,r,["No","거리(m)","측점","지수판 200×5t (m)","합판 t10 마구리 (㎡)","조인트휠러 t20 (㎡)","실런트 (m)","설치 단계","비고"]); r+=1
j0=r
for i in range(1,17):
    cell(JT,r,1,i,h="center"); cell(JT,r,2,f"=A{r}*{R('B')}",fmt="0.0"); cell(JT,r,3,f"={stf('B'+str(r))}",h="center")
    cell(JT,r,4,f"={R('JWS')}",fmt="0.000"); cell(JT,r,5,f"={R('JSEC')}",fmt="0.0000"); cell(JT,r,6,f"={R('JSEC')}",fmt="0.0000"); cell(JT,r,7,f"={R('JSL')}",fmt="0.000")
    cell(JT,r,8,"①지수판·기초마구리 → ②벽체마구리 → 다음블록 휠러 → 양생후 실런트",size=8); cell(JT,r,9,f"=\"블록\"&A{r}&\" | 블록\"&(A{r}+1)",size=9); r+=1
for n,d in (("시점 단부","0"),("종점 단부",f"={R('L')}")):
    cell(JT,r,1,n); cell(JT,r,2,d,fmt="0.0"); cell(JT,r,3,f"={stf('B'+str(r))}",h="center"); cell(JT,r,4,0); cell(JT,r,5,f"={R('JSEC')}",fmt="0.0000"); cell(JT,r,6,0); cell(JT,r,7,0)
    cell(JT,r,8,"마구리 합판만 (줄눈 아님)",size=8); cell(JT,r,9,"기존 수로 접속부 현장 확인",size=9); r+=1
cell(JT,r,1,"합계",bold=True,fill=F_TOT); cell(JT,r,2,None,fill=F_TOT); cell(JT,r,3,f"={R('NJ')}&\"개소+단부2\"",fill=F_TOT)
for c in (4,5,6,7): cell(JT,r,c,f"=SUM({CL(c)}{j0}:{CL(c)}{r-1})",fmt="0.000",bold=True,fill=F_TOT)
cell(JT,r,8,None,fill=F_TOT); cell(JT,r,9,None,fill=F_TOT)
JTOT=r; r+=1
cell(JT,r,1,f"=IF(COUNT(A{j0}:A{j0+15})={R('NJ')},\"줄눈 개소 일치\",\"줄눈 행 수 조정 필요\")",border=False); r+=2
section(JT,r,"C. 자재 집계",7); r+=1
header(JT,r,["자재","규격","단위","정미","소요계수","소요량","비고"]); r+=1
jm=[("WS","PVC 지수판","=" + R('WSSPEC'),"m",f"=D{JTOT}",f"={R('WSF')}","줄눈 16개소, 개소당 U자 1본 연속 (현장 이음 금지 권장)","0.0"),
    ("PLY","합판(내수) 마구리 겸 신축이음 거푸집",f"=\"t=\"&{R('PLYT')}&\"mm\"","㎡",f"=E{JTOT}",f"={R('PLYF')}/{R('PLYU')}","①기초·②벽체 각 마구리, 지수판 끼움 2분할","0.00"),
    ("FIL","조인트휠러",f"=\"t=\"&{R('FILT')}&\"mm\"","㎡",f"=F{JTOT}",f"={R('FILF')}","줄눈 단면 전체 (①기초부 0.35 + ②벽체부 0.4225)","0.00"),
    ("SEALM","실런트 연장","20×25","m",f"=G{JTOT}",1,"수로측 내면 + 벽 상단","0.0"),
    ("SEAL","실런트(에폭시)","20×25","kg",f"=G{JTOT}",f"={R('SW')}*{R('SDP')}*{R('EPD')}*{R('EPF')}","정미=연장(m), 계수=kg/m","0.0")]
for k,n,s,u,f,fac,note,fm in jm:
    cell(JT,r,1,n); cell(JT,r,2,s); cell(JT,r,3,u); cell(JT,r,4,f,fmt=fm); cell(JT,r,5,fac,fmt="0.000")
    cell(JT,r,6,f"=D{r}*E{r}",fmt=fm,fill=F_KEY,key=k); cell(JT,r,7,note); r+=1
cell(JT,r,1,"합판 장수 (1,220×2,440)"); cell(JT,r,2,None); cell(JT,r,3,"장"); cell(JT,r,4,None); cell(JT,r,5,None)
cell(JT,r,6,f"=ROUNDUP({R('PLY')}/{R('SHEET')},0)",fmt="0",fill=F_KEY,key="PLYSH"); cell(JT,r,7,"재단: 기초 1.4×0.3 / 벽 0.2×1.05 ×2 / 헌치 삼각 보강"); r+=1
cell(JT,r,1,"조인트휠러 장수 (1×2m 기준)"); cell(JT,r,2,None); cell(JT,r,3,"장"); cell(JT,r,4,None); cell(JT,r,5,None)
cell(JT,r,6,f"=ROUNDUP({R('FIL')}/2,0)",fmt="0",fill=F_KEY,key="FILSH"); cell(JT,r,7,"규격 판 크기는 납품업체 확인"); r+=2
section(JT,r,"D. 줄눈 1개소 설치 순서 (입체 시뮬레이션)",7); r+=1
steps=["1) 블록 n ①기초 조립 시: 종점측에 합판 t10 마구리(지수판 위치에서 상·하 2분할) 설치 → 지수판 200×5t를 U자로 끼움 (수평부 = 기초 두께 중앙 0.125, 수직 다리는 벽체 상단 −50까지 대기, 철근에 결속 고정)",
       "2) 기초 타설 → 기초 마구리 탈형 (지수판 수평부 매립 완료, 다리는 노출 대기 → 손상 주의)",
       "3) 블록 n ②벽체 조립 시: 지수판 다리를 벽체 두께 중앙에 맞춰 합판 마구리(벽 2개소 + 헌치) 설치 → 벽체 타설 → 탈형",
       "4) 블록 n+1 ①기초 조립 시: 블록 n 줄눈면(기초부)에 조인트휠러 t20 부착 → 지수판 반대쪽 100이 블록 n+1 기초에 매립",
       "5) 블록 n+1 ②벽체 조립 시: 블록 n 줄눈면(벽체·헌치부)에 조인트휠러 부착 → 수로측 25mm는 실런트 홈으로 비워 둠 (홈 형성용 목재 스트립)",
       "6) 양생 후 실런트 홈 청소·프라이머 → 실런트 20×25 충전 (수로측 내면 + 벽 상단)"]
for s_ in steps:
    JT.merge_cells(start_row=r,start_column=1,end_row=r,end_column=7); cell(JT,r,1,s_,wrap=True); JT.row_dimensions[r].height=32; r+=1
widths(JT,[22,14,14,16,16,16,22,30,16])

# =====================================================================
# 9. 토공
# =====================================================================
EW=wb.create_sheet("9.토공")
title(EW,"9. 토공 — 횡단면도 단면적 (평균단면적법) + 기초 변경 보정",
      "횡단면도는 No.0~No.11만 수록. No.12·No.12+10은 1차 산출(내역 기준) 값 유지 — 확인필요.")
header(EW,4,["측점","누가거리(m)","구간거리(m)","터파기 단면적(㎡)","되메우기 단면적(㎡)","터파기 체적(㎥)","되메우기 체적(㎥)","지반고(m)","계획고(m)","성토고(m)"])
ed=[("No.0",0,1.8,1.3,100,100),("No.1",20,1.8,1.7,99.3,99.47),("No.2",40,0.8,1.0,98.77,98.94),("No.3",60,0.8,0.9,98.16,98.41),
    ("No.4",80,1.2,1.5,97.63,97.88),("No.5",100,1.9,1.6,97.35,97.35),("No.6",120,1.3,1.5,97.05,97.12),("No.7",140,1.3,1.5,96.69,96.9),
    ("No.8",160,1.5,1.5,96.54,96.67),("No.9",180,1.9,1.6,96.36,96.45),("No.10",200,2.0,1.6,96.23,96.23),("No.11",220,1.8,1.5,96.15,96.15),
    ("No.12",240,1.9,1.6,96.0,96.06),("No.12+10",250,1.4,1.4,95.86,95.98)]
r=5
for i,(s,d,a1,a2,g,p) in enumerate(ed):
    cell(EW,r,1,s); cell(EW,r,2,d,color=BLUE); cell(EW,r,4,a1,color=BLUE,fmt="0.00"); cell(EW,r,5,a2,color=BLUE,fmt="0.00")
    cell(EW,r,8,g,color=BLUE,fmt="0.00"); cell(EW,r,9,p,color=BLUE,fmt="0.00"); cell(EW,r,10,f"=I{r}-H{r}",fmt="0.00")
    if i==0:
        cell(EW,r,3,None); cell(EW,r,6,None); cell(EW,r,7,None)
    else:
        cell(EW,r,3,f"=B{r}-B{r-1}",fmt="0.0"); cell(EW,r,6,f"=(D{r-1}+D{r})/2*C{r}",fmt="0.00"); cell(EW,r,7,f"=(E{r-1}+E{r})/2*C{r}",fmt="0.00")
    r+=1
cell(EW,r,1,"합계 (도면 기준)",bold=True,fill=F_TOT)
for c in range(2,11): cell(EW,r,c,None,fill=F_TOT)
cell(EW,r,6,f"=SUM(F5:F{r-1})",fmt="0.00",bold=True,fill=F_TOT); cell(EW,r,7,f"=SUM(G5:G{r-1})",fmt="0.00",bold=True,fill=F_TOT); ET=r; r+=2
header(EW,r,["보정 항목","값","단위","산식 / 비고"]); r+=1
cell(EW,r,1,"바닥 두께 변화 (터파기 깊이 감소)"); cell(EW,r,2,f"={R('OLDD')}-{R('TF')}",fmt="0.000"); cell(EW,r,3,"m"); cell(EW,r,4,"버림100+바닥200 → 기초250 : 50mm 얕아짐"); D1=r; r+=1
cell(EW,r,1,"터파기 감소량"); cell(EW,r,2,f"=-B{D1}*{R('BOTW')}*{R('L')}",fmt="0.00"); cell(EW,r,3,"㎥"); cell(EW,r,4,"감소 깊이 × 도면 터파기 저폭 × 연장"); D2=r; r+=1
cell(EW,r,1,"구조물 체적 변화"); cell(EW,r,2,f"=({R('WF')}*{R('TF')})-(0.16+1.4*0.2)",fmt="0.0000"); cell(EW,r,3,"㎡/m"); cell(EW,r,4,"신 기초 0.35 − (버림 1.6×0.1 + 바닥 1.4×0.2)"); D3=r; r+=1
cell(EW,r,1,"되메우기 변화량"); cell(EW,r,2,f"=B{D2}-B{D3}*{R('L')}",fmt="0.00"); cell(EW,r,3,"㎥"); cell(EW,r,4,"Δ터파기 − Δ구조물체적"); D4=r; r+=1
cell(EW,r,1,"보정 후 터파기",bold=True,fill=F_KEY); cell(EW,r,2,f"=F{ET}+B{D2}",fmt="0.00",bold=True,fill=F_KEY,key="EXC"); cell(EW,r,3,"㎥"); cell(EW,r,4,"내역서 382㎥"); r+=1
cell(EW,r,1,"보정 후 되메우기",bold=True,fill=F_KEY); cell(EW,r,2,f"=G{ET}+B{D4}",fmt="0.00",bold=True,fill=F_KEY,key="BF"); cell(EW,r,3,"㎥"); cell(EW,r,4,"내역서 363㎥"); r+=1
cell(EW,r,1,f"=IF(B{r}>=0,\"잔토(사토)\",\"부족토(유용·반입)\")"); cell(EW,r,2,f"=B{r-2}-B{r-1}",fmt="0.00;[Red]-0.00"); cell(EW,r,3,"㎥"); cell(EW,r,4,"터파기 − 되메우기. 계획고가 지반고보다 높은 구간(성토고) 되메우기 포함 → 음수면 토사 부족"); r+=2
header(EW,r,["작업여유폭 검토","값","단위","판정 / 조치"]); r+=1
cell(EW,r,1,"필요 터파기 저폭"); cell(EW,r,2,f"={R('WF')}+2*({R('FT')}+{R('PD')}+{R('WORK')})",fmt="0.000"); cell(EW,r,3,"m"); cell(EW,r,4,"기초폭 + 양측(폼 + 띠장 + 작업·말뚝·경사버팀 여유)"); W1=r; r+=1
cell(EW,r,1,"도면 터파기 저폭(판독)"); cell(EW,r,2,f"={R('BOTW')}",fmt="0.000"); cell(EW,r,3,"m"); cell(EW,r,4,f"=IF(B{W1}>B{r},\"부족 \"&TEXT(B{W1}-B{r},\"0.00\")&\"m → 양측 폼 조립 공간 확보 위해 터파기 확폭 검토(설계변경 사유)\",\"OK\")"); r+=1
widths(EW,[30,14,12,60,14,14,14,10,10,10])

# =====================================================================
# 2. 공정시뮬레이션
# =====================================================================
PS=wb.create_sheet("2.공정시뮬레이션")
title(PS,"2. 공정별 시공 시뮬레이션 — 블록(15m) 1개 기준 입체 단계 (17블록 반복)",
      "각 단계에서 '새로 투입'되는 자재와 '이전 단계에서 회수·전용'되는 자재를 구분 → 반복자재 중복 산출 방지의 근거")
header(PS,4,["단계","공정","작업 내용 (순서)","신규 투입 자재 (블록당)","전용·회수","체크포인트"])
B15=lambda k: R(k)
ps=[("0","준비·측량","줄눈 위치(15m) 및 측점 표시, 용배수관 15개소·수문 1개소 위치 확정","규준틀","-","시점 No.0 기준 (종단도 No 6 오표기 정정). 관 관통부는 ②단계 전 확정(슬리브/박스아웃)"),
    ("1","터파기·바닥정리","저폭 = 기초폭 + 양측 작업여유, 바닥 다짐·평탄(버림 없음 → 바닥 레벨 ±10mm 관리)","-","-","「9.토공」 작업여유폭 검토 참조"),
    ("①-a","기초 거푸집","3012 눕혀 좌·우 양측 조립(측당 12+3006 1), 웨지핀 결속, 띠장 1줄/측, 지지말뚝 @1.2m, 상단 반생 연결 @1.2m",
     f"=\"3012 \"&{R('P3012')}&\"매, 3006 \"&{R('P3006')}&\"매, 웨지핀 \"&'6.거푸집부속'!$D$6&\"EA, 띠장 \"&'6.거푸집부속'!$D$7&\"본, 말뚝 \"&'6.거푸집부속'!$D$8&\"EA\"",
     "세트 반입분 사용","기초폭 1,400 정확히 (외벽 6012 밀착 조건)"),
    ("①-b","철근 조립","스페이서 75 설치 → U바 D16 @200 (다리 = 벽체 중심) → D13 수평 7본 + 벽 5×2본 (8m 정척 20d 겹이음) → 헌치근 D16 → 결속",
     f"=\"U바 \"&'3.블록·줄눈'!$L$5&\"본, D13 \"&TEXT('3.블록·줄눈'!$O$5,\"0\")&\"m, 스페이서 \"&'3.블록·줄눈'!$S$5&\"EA\"","-","U바 다리 1.1m 자립 → 상단 임시 띠장으로 수직 고정"),
    ("①-c","줄눈(기초부)","종점측 합판 마구리 + 지수판 U자 설치 / 시점측 이전 블록 면에 조인트휠러 기초부 부착",
     f"=\"합판 \"&TEXT('8.줄눈'!$B$7,\"0.00\")&\"㎡, 지수판 \"&TEXT({R('JWS')},\"0.00\")&\"m, 휠러 \"&TEXT('8.줄눈'!$B$7,\"0.00\")&\"㎡\"","-","지수판 중심 = 줄눈면, 양쪽 100씩"),
    ("①-d","기초 타설","25-21-08 1회 타설 (두께 250), 상면 시공이음 거친면 처리",f"=TEXT('3.블록·줄눈'!$H$5,\"0.00\")&\"㎥\"","-","U바·지수판 다리 보호"),
    ("①-e","기초 탈형","3012·3006·웨지핀·띠장·말뚝 회수 (외벽 6012가 기초 측면을 200 겹치므로 탈형 필수)","-","핀·파이프·말뚝 → ②단계 전용 / 3012 → 다음 블록","탈형 시기: 측면 거푸집 존치기간 준수"),
    ("②-a","외벽 거푸집","6012 세워 좌·우 외면 양측 (측당 25매), 하단 200을 기초 측면에 밀착, 하단 고임",f"=\"6012 \"&{R('P6012')}&\"매\"","-","폼 상단 = 벽체 상단 마감선"),
    ("②-b","내벽 거푸집","헌치폼 150 눕혀 기초 상면 모서리 설치 → 6090 적층 (좌·우 내면)",f"=\"헌치폼 \"&({R('PH12')}+{R('PH06')})&\"매, 6090 \"&{R('P6090')}&\"매\"","-","내벽 폼 50 높음 → 타설선 표시"),
    ("②-c","폼 고정","플랫타이 2단 @600 (외↔내 관통, 웨지핀), 띠장 외2·내2줄/벽, 기리바리 2단 @1.2m, 외벽 경사버팀 @1.8m + 말뚝",
     f"=\"플랫타이 \"&'3.블록·줄눈'!$Q$5&\"EA (소모)\"","웨지핀·띠장·말뚝 ①단계분 전용 + 추가분","「6.거푸집부속」 MAX 원칙"),
    ("②-d","줄눈(벽체부)","지수판 다리 위치 맞춰 벽체·헌치 마구리 합판 / 이전 블록 벽면 조인트휠러",
     f"=\"합판·휠러 각 \"&TEXT('8.줄눈'!$C$7,\"0.000\")&\"㎡\"","-","실런트 홈 25mm 확보"),
    ("②-e","벽체 타설","벽체+헌치 일체 타설 (다짐: 벽 200 협소 → 소형 바이브레이터)",f"=TEXT('3.블록·줄눈'!$I$5,\"0.00\")&\"㎥\"","-","타설 높이 1.0m, 좌·우 교대 타설로 편압 방지"),
    ("②-f","벽체 탈형·이동","유로폼·부속 회수 → 다음 블록으로 이동 (17회 전용)","-","전 자재 회수","플랫타이 노출부 절단"),
    ("3","마감","양생 → 실런트 20×25 충전 (수로측 내면+벽 상단)","실런트","-","줄눈 16개소 전부"),
    ("4","되메우기","양측 균등 되메우기·다짐","-","-","편토압 방지 (한쪽만 되메우기 금지)")]
r=5
for row in ps:
    for c,v in enumerate(row,1): cell(PS,r,c,v,wrap=True,fill=(F_SEC if row[0].startswith("①") else (F_IN if row[0].startswith("②") else None)))
    PS.row_dimensions[r].height=48; r+=1
r+=1
cell(PS,r,1,"공정 흐름: 블록1 ①기초 → ①탈형 → ②벽체 → ②탈형 → 블록2 ①기초 … (1세트 순환). 기초 거푸집과 벽체 거푸집은 종류가 달라 패널은 각각 필요하지만, 웨지핀·파이프·말뚝은 공용 → 큰 값 1회 반입.",border=False,size=9)
r+=1
PS.add_image(XImg("/home/user/Hwang/out/조립상세_단면.png"),f"A{r+1}")
img2=XImg("/home/user/Hwang/out/조립상세_블록전개.png"); PS.add_image(img2,f"A{r+48}")
widths(PS,[7,14,52,40,26,34])

# =====================================================================
# 0. 공종별 자재 총괄 (summary)
# =====================================================================
SM=wb.create_sheet("0.공종별자재총괄",0)
title(SM,"문경읍 요성리 용배수로 개체공사 — U형 개거 1,000×1,000 L=250m · 공종별 필요자재 총괄 (3차)",
      "반복 = 세트 반입 수량(블록마다 전용) / 소모 = 사용 후 소멸(전체 합산) / 시공 = 시공·발주 수량. 모든 값은 하위 시트 수식 연동.")
header(SM,4,["공종","단계","자재명","규격","단위","정미 / 세트","반입·소요량","사용구분","산정 근거 / 비고"])
def g(k): return f"={R(k)}"
sm=[("1. 콘크리트공",None),
    ("콘크리트","①기초","레미콘","=" + R('CSPEC'),"㎥",f"={R('L')}*{R('WF')}*{R('TF')}",None,"시공","기초 1,400×250, 1회 타설 17회"),
    ("콘크리트","②벽체·헌치","레미콘","=" + R('CSPEC'),"㎥",f"={R('L')}*(2*{R('TW')}*{R('HW')}+{R('HH')}^2)",None,"시공","벽체 200×1,000 양측 + 헌치 150, 17회"),
    ("콘크리트","관급 발주","레미콘 합계","=" + R('CSPEC'),"㎥",f"={R('CNET')}",g("CORD"),"시공","할증 2.5% 올림. 25-18-08 삭제(내역 41㎥ → 0)"),
    ("2. 거푸집공 — 유로폼 패널 (종류별 별개 → 합산)",None),
    ("거푸집","①기초","유로폼 3012","300×1,200 (눕힘)","EA",f"={R('P3012')}",g("P3012"),"반복","좌·우 양측 각 12매"),
    ("거푸집","①기초","유로폼 3006","300×600 (보정)","EA",f"={R('P3006')}",g("P3006"),"반복","양측 각 1매"),
    ("거푸집","②외벽","유로폼 6012","600×1,200 (세움)","EA",f"={R('P6012')}",g("P6012"),"반복","좌·우 외면 각 25매, 하단 200 기초 겹침"),
    ("거푸집","②내벽","헌치폼 150","150×150×1,200 (눕힘)","EA",f"={R('PH12')}",g("PH12"),"반복","좌·우 내면 각 12매"),
    ("거푸집","②내벽","헌치폼 150","150×150×600 (보정)","EA",f"={R('PH06')}",g("PH06"),"반복","각 1매"),
    ("거푸집","②내벽","유로폼 6090","600×900","EA",f"={R('P6090')}",g("P6090"),"반복","좌·우 내면 각 25매, 헌치폼 위"),
    ("거푸집","전체","유로폼 접촉면적 (내역 수량)","-","㎡",g("FAREA"),g("FAREA"),"시공","①기초 양측 125 + ②외벽 500 + 내벽 425 + 헌치 106.07"),
    ("3. 거푸집 부속 — 반복자재 (①·② 공용, 큰 값 1회)",None),
    ("부속","①→②","폼핀(웨지핀 세트)","핀+쐐기","EA","='6.거푸집부속'!$F$6",g("PIN"),"반복","=\"①기초 \"&'6.거푸집부속'!$D$6&\" / ②벽체 \"&'6.거푸집부속'!$E$6&\" → 큰 값 1회\""),
    ("부속","①→②","비계파이프 (띠장)","Ø48.6×2.3t 6m","본","='6.거푸집부속'!$F$7",g("PIPE6"),"반복","=\"①기초 \"&'6.거푸집부속'!$D$7&\" / ②벽체 \"&'6.거푸집부속'!$E$7&\" → 큰 값 1회\""),
    ("부속","①→②","지지·버팀 말뚝","단관 L1.0m","EA","='6.거푸집부속'!$F$8",g("STK"),"반복","=\"①기초 \"&'6.거푸집부속'!$D$8&\" / ②벽체 \"&'6.거푸집부속'!$E$8&\" → 큰 값 1회\""),
    ("부속","②","경사버팀","단관 L1.5m","EA","='6.거푸집부속'!$F$9",g("BRC"),"반복","외벽 @1.8m"),
    ("부속","②","단관 절단용 파이프","Ø48.6 6m","본",None,g("PIPECUT"),"반복","말뚝·버팀 절단분 (띠장과 별도)"),
    ("부속","②","클램프(자재형)","Ø48.6","EA","='6.거푸집부속'!$F$10",g("CLP"),"반복","경사버팀 상·하단"),
    ("부속","②","기리바리","조절식/각재 L≈0.78m","EA","='6.거푸집부속'!$F$11",g("KB"),"반복","내벽 2단 @1.2m"),
    ("4. 거푸집 부속 — 소모자재",None),
    ("부속","②","플랫타이","벽두께 200용","EA",g("TIEN"),g("TIE"),"소모","2단 @600 양벽, 블록별 합산"),
    ("부속","①+②","반생(소둔철선 #8)","Ø4.19mm","kg",g("BSN"),g("BS"),"소모","결속 후 절단"),
    ("부속","①+②","박리제","-","L",None,g("REL_Q"),"소모","접촉면 도포"),
    ("5. 철근공",None),
    ("철근","①","이형철근 D16 — U바 (주력근)","SD400, L=3.434m","ton",g("UWT"),f"={R('UWT')}*(1+{R('RLOSS')})","시공",f"=\"벽체 가운데 1단 @200, \"&{R('UN')}&\"본\""),
    ("철근","①","이형철근 D16 — 헌치근","SD400, L=0.736m","ton",g("HWT"),f"={R('HWT')}*(1+{R('RLOSS')})","시공","도면 ③ 유지"),
    ("철근","①","이형철근 D13 — 배력근","SD400","ton",g("D13WT"),f"={R('D13WT')}*(1+{R('RLOSS')})","시공","17본, 연장방향 20d 겹이음"),
    ("철근","합계","철근 합계 (관급)","SD400","ton",g("RTN"),g("RTS"),"시공","할증 3%"),
    ("철근","①","콘크리트 스페이서","75mm","EA",g("SPF"),f"=ROUNDUP({R('SPF')}*(1+{R('LC')}),0)","소모","버림 없음 → 필수"),
    ("철근","①","휠 스페이서","피복 100","EA",g("SPW"),f"=ROUNDUP({R('SPW')}*(1+{R('LC')}),0)","소모","중앙 1단 위치 고정"),
    ("철근","①","결속선","#20 0.9mm","kg",g("TIEKG"),f"=ROUNDUP({R('TIEKG')},0)","소모","8kg/ton"),
    ("6. 신축줄눈공 — 15.0m 간격 16개소 (No.0+15 ~ No.12+0)",None),
    ("줄눈","①→②","PVC 지수판","=" + R('WSSPEC'),"m",f"={R('JWS')}*{R('NJ')}",g("WS"),"소모",f"=\"개소당 \"&TEXT({R('JWS')},\"0.00\")&\"m U자 연속, 15m 간격\""),
    ("줄눈","①·②","합판 마구리(신축이음)",f"=\"t=\"&{R('PLYT')}&\"mm\"","㎡",f"='8.줄눈'!$E${JTOT}",g("PLY"),"소모",f"=\"줄눈 16 + 시·종점 2 = 18개소, \"&{R('PLYSH')}&\"장\""),
    ("줄눈","①·②","조인트휠러",f"=\"t=\"&{R('FILT')}&\"mm\"","㎡",f"='8.줄눈'!$F${JTOT}",g("FIL"),"소모","줄눈 단면 전체, 15m 간격"),
    ("줄눈","마감","실런트(에폭시)","20×25","kg",g("SEALM"),g("SEAL"),"소모","정미칸 = 연장(m), 15m 간격"),
    ("7. 토공",None),
    ("토공","1","터파기","-","㎥",None,g("EXC"),"시공","도면 단면 − 기초 변경 보정"),
    ("토공","4","되메우기","-","㎥",None,g("BF"),"시공",""),
    ("8. 제외",None),
    ("용배수관·수문","-","현장 조정 사항 — 산출 제외","-","-",None,None,"-","위치는 ②벽체 조립 전 확정 필요 (관통 슬리브)")]
r=5
for row in sm:
    if row[1] is None:
        section(SM,r,row[0],9); r+=1; continue
    for c,v in enumerate(row,1):
        fm=None
        if c in (6,7): fm="#,##0.000" if row[4] in ("㎥","ton","㎡","m","kg","L") else "#,##0"
        cell(SM,r,c,v,fmt=fm,fill=(F_KEY if c==7 and v is not None else None),wrap=(c==9))
    r+=1
r+=1
cell(SM,r,1,"【설치간격】 신축줄눈·지수판·합판 마구리·조인트휠러·실런트 = 모두 15.0m 간격 동일 위치 1조 (16개소) — 「8.줄눈」 측점표",border=False,bold=True); r+=1
cell(SM,r,1,"【조립상세】 ①기초 3012 눕혀 양측 → 탈형 → ②외벽 6012 세워 양측(기초 200 겹침) + 내벽 헌치150 눕힘 + 6090 양측 — 「2.공정시뮬레이션」 그림",border=False,bold=True); r+=1
cell(SM,r,1,"【중복 금지】 웨지핀·파이프·말뚝은 ①→② 전용이므로 MAX 1회 / 패널은 종류가 달라 각각 / 플랫타이·반생·합판·휠러는 소모성 전량",border=False,bold=True)
widths(SM,[12,10,28,22,6,13,13,9,48]); SM.freeze_panes="A5"

# =====================================================================
# 10. 검토사항
# =====================================================================
CK=wb.create_sheet("10.확인필요")
title(CK,"10. 확인 필요 사항 · 해석 가정")
header(CK,3,["No","항목","내용","영향 / 조치"])
ck=[("종단도 시점","종단면도 3매 모두 시점 측점이 'No 6'으로 표기 → No.0 오표기로 정정. 종단도 'U형개거 500×500, L=102.21m' 문구도 실제(1,000×1,000, L=250m)와 불일치.","측점·줄눈 위치는 No.0 기준 15m 간격으로 산정"),
    ("D13 겹이음 '20mm'","철근 겹이음 20mm는 성립하지 않아 20d(=260mm)로 해석. KDS 인장 겹이음(D13 약 400mm 이상)과 비교 시 감독 확인 권장.","「1.조건」 겹이음 배수만 수정 → 자동 반영"),
    ("하면 피복 75mm","버림 삭제로 흙에 직접 타설 → 피복 75mm 적용(도면 50). U바 다리 길이 1.117m.","U바 3.434m (도면 3.5m)"),
    ("합판 t10 역할","합판을 줄눈 마구리(단부 거푸집) 겸 신축이음재 거푸집으로, 조인트휠러 t20을 줄눈 단면 전체 충전재로 해석. 합판을 줄눈 내 존치(매립)하는 방식이면 줄눈폭 30mm(10+20)가 되므로 확인 필요.","합판 18개소×0.7725㎡"),
    ("내벽 폼 높이","헌치150 + 6090(900) = 1,050 > 벽높이 1,000 → 내벽 폼이 50mm 높음. 외벽 6012 상단이 마감선.","내벽 타설선 표시"),
    ("작업여유폭","기초 양측 거푸집 + 띠장 + 말뚝·경사버팀 → 필요 저폭 약 2.62m. 횡단면도 판독 저폭 약 2.2m.","터파기 확폭 시 토공량 증가 (설계변경 검토)"),
    ("부속자재 가정치","웨지핀 간격 300, 플랫타이 2단×600, 띠장 줄수, 말뚝 @1.2, 경사버팀 @1.8, 기리바리 2단 @1.2, 반생 0.6m/개소는 현장 관행 가정.","「1.조건」 5번에서 수정"),
    ("세트 수","1세트(15m)로 17블록 순환. ①기초와 ②벽체를 다른 블록에서 병행하면 반복자재 합산 필요.","공기 단축 시 세트 수 2"),
    ("헌치 보강근","U바를 벽체 중앙에 둔 상태에서도 도면 ③ 헌치근(L=736) 유지.","불필요 시 「1.조건」 개수 0"),
    ("시공이음 지수","기초 상면(벽체 하단) 수평 시공이음에 별도 지수재 없음 — 용수로 누수 우려 시 수평 지수판/지수재 검토.","필요 시 250m×2열 추가"),
    ("토공","횡단면도는 No.0~No.11만 수록, No.12·12+10은 1차 값. 기초 변경으로 터파기 약 27.5㎥ 감소 보정.","「9.토공」"),
    ("관급자재 변경","레미콘 25-21-08 증가·25-18-08 삭제, 철근 D16/D13 변경, 지수판 150→200, 합판 12→10, 휠러 t20.","설계변경·관급 조달 요청"),
    ("용배수관·수문","현장 조정 사항으로 산출 제외 (평면도: 용배수관 15개소, 수문 1개소).","벽체 관통 위치는 ②단계 전 확정")]
for i,(a,b,c) in enumerate(ck,4):
    cell(CK,i,1,i-3,h="center"); cell(CK,i,2,a); cell(CK,i,3,b,wrap=True); cell(CK,i,4,c,wrap=True); CK.row_dimensions[i].height=45
widths(CK,[5,18,80,40])

order=["0.공종별자재총괄","1.조건","2.공정시뮬레이션","3.블록·줄눈","4.콘크리트","5.거푸집","6.거푸집부속","7.철근","8.줄눈","9.토공","10.확인필요"]
wb._sheets=[wb[n] for n in order]
for ws in wb.worksheets: ws.sheet_view.showGridLines=False
wb.save("/home/user/Hwang/out/용배수로_물량산출_v3.xlsx")
print("saved")
