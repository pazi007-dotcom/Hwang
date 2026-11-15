import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.patches import Polygon, Rectangle, Circle
fm.fontManager.addfont("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc")
plt.rcParams["font.family"]="WenQuanYi Zen Hei"
T=63.5; P=48.6
W,TF,TW,HW,H=1400,250,200,1000,150
HT=TF+HW
def base(ax,title):
    ax.set_aspect("equal"); ax.set_title(title,fontsize=13,fontweight="bold")
    ax.axhline(0,color="#8a6d3b",lw=1.2); ax.fill_between([-900,2300],-250,0,color="#e9dfc9",zorder=0)
    ax.set_xlim(-950,2350); ax.set_ylim(-300,1650); ax.axis("off")
def ubar(ax,ls="-"):
    y=75+8
    ax.plot([100,100,1300,1300],[HT-50,y,y,HT-50],color="#c0392b",lw=2,ls=ls)
    for x in range(100,1301,200): ax.add_patch(Circle((x,y+16),11,color="#1f5fa8"))
    for xx in (100,1300):
        for k in range(1,6): ax.add_patch(Circle((xx+(16 if xx==100 else -16),y+200*k),11,color="#1f5fa8"))
fig,axs=plt.subplots(1,2,figsize=(18,8.4))
# ---------- Stage 1
ax=axs[0]; base(ax,"①단계  기초 조립·타설 (양측 3012 거푸집)")
ax.add_patch(Rectangle((0,0),W,TF,fc="#d7d7d7",ec="k",lw=1.2,hatch="..",alpha=.6))
for x0 in (-T,W): ax.add_patch(Rectangle((x0,0),T,300,fc="#f4c542",ec="k"))
for xc in (-T-P/2,W+T+P/2): ax.add_patch(Circle((xc,150),P/2,fc="#555"))
for xs in (-T-P-40,W+T+P+40): ax.plot([xs,xs],[-230,330],color="#555",lw=4)
ax.plot([-T-P,W+T+P],[330,330],color="#7d3c98",lw=1.5,ls="--")
ubar(ax)
for x in (100,700,1300): ax.add_patch(Polygon([[x-30,0],[x+30,0],[x,75]],fc="#7f8c8d"))
ax.plot([700,700],[0,0],"")
ax.annotate("유로폼 3012 (눕혀서, 높이300)\n기초 250 + 상단여유 50",(-T,280),(-900,700),arrowprops=dict(arrowstyle="->"),fontsize=9)
ax.annotate("띠장 비계파이프 1줄/측",(-T-P/2,150),(-900,470),arrowprops=dict(arrowstyle="->"),fontsize=9)
ax.annotate("지지말뚝(단관 L1.0m) @1.2m\n+ 반생 결속",(-T-P-40,-150),(-900,-280),arrowprops=dict(arrowstyle="->"),fontsize=9)
ax.annotate("상단 반생 연결 @1.2m\n(양측 폼 벌어짐 방지)",(700,330),(900,520),arrowprops=dict(arrowstyle="->"),fontsize=9)
ax.annotate("U바 D16 @200 (다리 = 벽체 중심)\n수평부 피복 75 (버림 없음, 흙 접촉)",(1300,900),(1550,1150),arrowprops=dict(arrowstyle="->"),fontsize=9)
ax.annotate("D13 배력근 17본\n(연장방향 20d 겹이음)",(1284,483),(1550,650),arrowprops=dict(arrowstyle="->"),fontsize=9)
ax.annotate("콘크리트 스페이서 75\n3열 @0.8m",(1300,30),(1550,150),arrowprops=dict(arrowstyle="->"),fontsize=9)
ax.text(700,-150,"기초 폭 1,400 (정확히) × 두께 250 · 25-21-08 1회 타설",ha="center",fontsize=10,fontweight="bold")
ax.text(700,1500,"U바 다리·지수판(U자) 상부는 벽체용으로 대기",ha="center",fontsize=9,color="#c0392b")
# ---------- Stage 2
ax=axs[1]; base(ax,"②단계  벽체·헌치 조립·타설 (외벽 6012 세움 / 내벽 헌치150+6090)")
ax.add_patch(Rectangle((0,0),W,TF,fc="#bdbdbd",ec="k"))
for x0 in (0,W-TW): ax.add_patch(Rectangle((x0,TF),TW,HW,fc="#e6e6e6",ec="k",hatch="..",alpha=.6))
ax.add_patch(Polygon([[TW,TF],[TW+H,TF],[TW,TF+H]],fc="#e6e6e6",ec="k",hatch=".."))
ax.add_patch(Polygon([[W-TW,TF],[W-TW-H,TF],[W-TW,TF+H]],fc="#e6e6e6",ec="k",hatch=".."))
# outer 6012
for x0 in (-T,W): ax.add_patch(Rectangle((x0,HT-1200),T,1200,fc="#f4c542",ec="k"))
# haunch forms
import math
for s in (1,-1):
    xa=TW if s==1 else W-TW
    p=[[xa+s*H,TF],[xa,TF+H],[xa+s*(T/math.sqrt(2)),TF+H+T/math.sqrt(2)],[xa+s*(H+T*math.sqrt(2)),TF]]
    ax.add_patch(Polygon(p,fc="#5dade2",ec="k"))
    x0=TW if s==1 else W-TW-T
    ax.add_patch(Rectangle((x0,TF+H),T,900,fc="#f4c542",ec="k"))
ys=[TF+300,TF+750]
for y in ys:
    ax.plot([-T-P,TW+T+P],[y,y],color="#7d3c98",lw=1.3); ax.plot([W-TW-T-P,W+T+P],[y,y],color="#7d3c98",lw=1.3)
    for xc in (-T-P/2,TW+T+P/2,W-TW-T-P/2,W+T+P/2): ax.add_patch(Circle((xc,y),P/2,fc="#555"))
    ax.plot([TW+T+P,W-TW-T-P],[y,y],color="#16a085",lw=5)
for s,xw in ((1,-T-P),(-1,W+T+P)):
    ax.plot([xw,xw-s*620],[TF+750,0],color="#555",lw=3); ax.plot([xw-s*660,xw-s*660],[-230,80],color="#555",lw=4)
ax.plot([100,100,1300,1300],[HT-50,83,83,HT-50],color="#c0392b",lw=1.6)
ax.annotate("6012 세워서 (1,200)\n하단 200 = 기초측면 겹침",(-T,150),(-900,300),arrowprops=dict(arrowstyle="->"),fontsize=9)
ax.annotate("헌치폼 150 (눕힘)",(TW+60,TF+60),(400,420),arrowprops=dict(arrowstyle="->"),fontsize=9)
ax.annotate("6090 (높이 900)\n헌치150+900=1,050 → 상단 50 초과\n(타설선 표시)",(TW+T,1250),(380,1430),arrowprops=dict(arrowstyle="->"),fontsize=9)
ax.annotate("플랫타이 2단 @600\n(패널 이음부, 웨지핀 고정)",(TW/2,TF+750),(-900,1150),arrowprops=dict(arrowstyle="->"),fontsize=9)
ax.annotate("기리바리 2단 @1.2m\n(내벽 띠장 사이, L≈0.78m)",(700,TF+300),(800,700),arrowprops=dict(arrowstyle="->"),fontsize=9)
ax.annotate("띠장 파이프 외2·내2줄/벽",(W+T+P/2,TF+750),(1600,1250),arrowprops=dict(arrowstyle="->"),fontsize=9)
ax.annotate("경사버팀(단관1.5m) @1.8m\n+ 말뚝(①단계 말뚝 재사용)",(W+T+P+300,500),(1600,200),arrowprops=dict(arrowstyle="->"),fontsize=9)
ax.text(700,-150,"벽체 200 × H1,000 + 헌치 150×150 일체 타설 (기초 상면 = 시공이음)",ha="center",fontsize=10,fontweight="bold")
plt.tight_layout(); plt.savefig("/home/user/Hwang/out/조립상세_단면.png",dpi=110)

# ---------- elevation / plan of one 15m block
fig,ax=plt.subplots(figsize=(18,5.2)); ax.set_aspect("auto")
L=15000
def strip(y0,h,mods,col,lab):
    x=0
    for m in mods:
        ax.add_patch(Rectangle((x,y0),m,h,fc=col,ec="k",lw=.6)); x+=m
    ax.text(-300,y0+h/2,lab,ha="right",va="center",fontsize=9)
strip(0,300,[1200]*12+[600],"#f9e79f","기초 3012×12 + 3006×1 (측당)")
strip(500,1200,[600]*25,"#f4c542","외벽 6012 세워서 ×25 (측당)")
strip(1900,150,[1200]*12+[600],"#5dade2","내벽 헌치150 L1200×12 + L600×1")
strip(2050,900,[600]*25,"#f4c542","내벽 6090 ×25 (측당)")
for k in range(26):
    x=k*600
    for y in (500+200+300,500+200+750): ax.plot(x,y,"o",color="#7d3c98",ms=4)
ax.axvline(0,color="#c0392b",lw=2); ax.axvline(L,color="#c0392b",lw=2)
ax.text(0,3150,"줄눈(이전 블록 면)\n조인트휠러20 부착",color="#c0392b",fontsize=9)
ax.text(L,3150,"신축줄눈 / 마구리 합판10 + 지수판200×5t",color="#c0392b",fontsize=9,ha="right")
ax.set_xlim(-4200,15500); ax.set_ylim(-300,3600); ax.axis("off")
ax.set_title("일반 블록 1개(15.0m) 패널 배치 전개도 — 측당 수량, 양측(좌·우 벽체) 동일 ×2   ● = 플랫타이 위치(2단, 600 간격)",fontsize=12,fontweight="bold")
plt.tight_layout(); plt.savefig("/home/user/Hwang/out/조립상세_블록전개.png",dpi=100)
