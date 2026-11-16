const { chromium } = require('playwright');
const OUT = process.argv[2]; let n = 0; const notes = [];
(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ permissions: ['clipboard-read', 'clipboard-write'], viewport: { width: 360, height: 800 }, timezoneId: 'Asia/Seoul', locale: 'ko-KR' });
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
    await tap('tab', '명부');
    const reg = async (kind, payee, item, price, bank, acc) => {
      await tap('button', '+ 작업자·장비 등록');
      if (kind !== '인력') await clickText(kind);
      await type(kind === '인력' ? '이름 (한 사람씩 — 일당·세금이 사람별)' : '업체', payee);
      await type(kind === '인력' ? '직종 (보통인부, 형틀목공 …)' : '기종 (6W, 덤프 25톤 …)', item);
      await type('단가 (원)', price);
      if (bank) { await type('은행 (월말 이체용)', bank); await type('계좌번호', acc); }
      await tap('button', '저장', true); await p.waitForTimeout(500);
    };
    await reg('인력', '김반장', '보통인부', 187000, '농협', '351-1111-2222-33');
    await reg('인력', '이영수', '보통인부', 187000, '국민', '9876-01-234567');
    await reg('인력', '박목수', '형틀목공', 230000);
    await reg('장비', '대성중기', '6W', 680000, '기업', '123-456789-01-011');
    await shot('명부 (사람마다 따로)');
    await tap('button', '+ 접수'); await type('공사 이름', '요성리 용배수로 개체공사');
    await tap('button', '구분'); await clickText('공사'); await tap('button', '접수', true); await p.waitForTimeout(800);
    await tap('tab', '일지'); await p.waitForTimeout(700);
    await tap('button', '오늘 나온 사람·장비 고르기'); await p.waitForTimeout(700);
    for (const name of ['김반장 · 보통인부', '이영수 · 보통인부', '박목수 · 형틀목공', '대성중기 · 6W']) { await clickText(name, false); await p.waitForTimeout(250); }
    await tap('button', '고른 것 넣기'); await p.waitForTimeout(900);
    await tap('tab', '결제 요청'); await p.waitForTimeout(1000); await shot('결제 탭 위 (보낼 돈)');
    await scroll(450); await shot('작업자 사람별');
    await scroll(-3000);
    await tap('button', '대표님께 보고 메일 보내기'); await p.waitForTimeout(700); await shot('보내기 확인창');
    await tap('button', '보내기', true); await p.waitForTimeout(1200); await shot('보낸 뒤 (집 PC 대기)');
  } catch (e) { notes.push('!! 막힘: ' + e.message); await shot('막힌 화면'); }
  notes.push('페이지 오류: ' + JSON.stringify(errs)); console.log(notes.join('\n')); await b.close();
})();
