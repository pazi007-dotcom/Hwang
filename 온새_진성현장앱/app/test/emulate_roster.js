const { chromium } = require('playwright');
const OUT = process.argv[2]; let n = 0; const notes = [];
(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 412, height: 915 }, timezoneId: 'Asia/Seoul', locale: 'ko-KR' });
  const p = await ctx.newPage(); const errs = []; p.on('pageerror', e => errs.push(String(e)));
  await p.addInitScript(() => { const f = new Date('2026-11-16T08:30:00+09:00').getTime(); const D = Date;
    globalThis.Date = class extends D { constructor(...a) { super(...(a.length ? a : [f])); } static now() { return f; } }; });
  await p.goto('http://127.0.0.1:8791/'); await p.waitForTimeout(5000);
  await p.evaluate(() => document.querySelector('flt-semantics-placeholder')?.click()); await p.waitForTimeout(1000);
  const shot = async (w) => { n++; await p.screenshot({ path: `${OUT}/r${String(n).padStart(2,'0')}.png` }); notes.push(`[화면 ${n}] ${w}`); };
  const scroll = async (dy) => { await p.mouse.move(206, 500); await p.mouse.wheel(0, dy); await p.waitForTimeout(350); };
  async function find(role, name, exact = false) { for (let i = 0; i < 25; i++) { const l = p.getByRole(role, { name, exact }); if (await l.count() > 0) { try { await l.first().scrollIntoViewIfNeeded({ timeout: 1000 }); } catch {} return l.first(); } await scroll(i < 12 ? 300 : -300); } throw new Error(`못 찾음: ${role} "${name}"`); }
  async function clickText(t, exact = true) { const o = await p.evaluate(([t, exact]) => [...document.querySelectorAll('flt-semantics')].filter(e => { const s = (e.getAttribute('aria-label')||e.textContent||'').trim(); return exact ? s === t : s.includes(t); }).map(e => { const r = e.getBoundingClientRect(); return [r.x + r.width/2, r.y + r.height/2, r.width, r.height]; }).filter(x => x[2] > 0 && x[3] > 0).pop(), [t, exact]); if (!o) throw new Error('글자 못 찾음: ' + t); await p.mouse.click(o[0], o[1]); await p.waitForTimeout(600); }
  async function tap(role, name, exact) { await (await find(role, name, exact)).click(); await p.waitForTimeout(600); }
  async function type(name, text) { const l = await find('textbox', name); await l.click(); await p.keyboard.press('Control+A'); await p.keyboard.type(String(text)); await p.waitForTimeout(150); }
  try {
    // 1. 명부 등록
    await tap('tab', '명부'); await shot('명부 탭 (빈 상태)');
    const reg = async (kind, payee, item, unit, price, phone) => {
      await tap('button', '+ 작업자·장비 등록');
      if (kind !== '인력') await clickText(kind);
      await type(kind === '인력' ? '이름 (또는 팀)' : '업체', payee);
      await type(kind === '인력' ? '직종 (보통인부, 형틀목공 …)' : kind === '장비' ? '기종 (6W, 덤프 25톤 …)' : '항목', item);
      if (unit) await type('단위', unit);
      await type('단가 (원)', price);
      if (phone) await type('연락처 (선택)', phone);
      await tap('button', '저장', true); await p.waitForTimeout(500);
      notes.push(`   등록: ${kind} ${payee} ${item} ${price}`);
    };
    await reg('인력', '김반장', '보통인부', null, 187000, '010-1111-2222');
    await reg('인력', '이영수', '보통인부', null, 187000);
    await reg('인력', '박목수 팀', '형틀목공', null, 230000);
    await reg('장비', '대성중기', '6W', null, 680000);
    await reg('장비', '한빛운수', '덤프 25톤', '대', 282000);
    await shot('명부 5칸 등록 후');
    // 2. 현장 접수
    await tap('button', '+ 접수'); await type('공사 이름', '요성리 용배수로 개체공사');
    await tap('button', '구분'); await clickText('공사'); await tap('button', '접수', true); await p.waitForTimeout(800);
    // 3. 일지: 명부에서 고르기
    await tap('tab', '일지'); await p.waitForTimeout(700);
    await tap('button', '오늘 나온 사람·장비 고르기'); await p.waitForTimeout(700);
    await shot('명부에서 고르기 창');
    for (const name of ['김반장 · 보통인부', '이영수 · 보통인부', '박목수 팀 · 형틀목공', '대성중기 · 6W']) {
      const cb = p.locator(`flt-semantics[role="checkbox"]`); 
      const idx = await p.evaluate((name) => { const all = [...document.querySelectorAll('flt-semantics')]; const lab = all.find(e => (e.getAttribute('aria-label')||e.textContent||'').includes(name)); if (!lab) return null; const r = lab.getBoundingClientRect(); return [r.y + r.height/2]; }, name);
      // 같은 줄의 체크박스(왼쪽) 누르기
      await clickText(name, false); await p.waitForTimeout(300);
    }
    // 박목수 팀 수량 2
    const q = p.getByRole('textbox', { name: '인' });
    const cnt = await q.count(); notes.push(`   수량 칸 ${cnt}개 열림`);
    if (cnt >= 3) { await q.nth(2).click(); await p.keyboard.press('Control+A'); await p.keyboard.type('2'); }
    await shot('4명·대 체크, 박목수 팀 2');
    await tap('button', '고른 것 넣기'); await p.waitForTimeout(900);
    await scroll(1600); await shot('일지에 들어간 줄');
    // 4. 출역표
    await tap('tab', '명부'); await p.waitForTimeout(700);
    await clickText('김반장', false); await p.waitForTimeout(900); await shot('김반장 출역표');
    await scroll(800); await shot('김반장 출역표 아래 (날짜별·연간)');
    await p.keyboard.press('Escape'); await p.waitForTimeout(500);
    await p.goBack().catch(() => {}); await p.waitForTimeout(800);
    await tap('tab', '결제 요청'); await p.waitForTimeout(800); await scroll(3000); await shot('결제 탭 아래 (년 누계)');
    await scroll(-600); await shot('결제 탭 년 누계 위');
  } catch (e) { notes.push('!! 막힘: ' + e.message); await shot('막힌 화면'); }
  notes.push('페이지 오류: ' + JSON.stringify(errs)); console.log(notes.join('\n')); await b.close();
})();
