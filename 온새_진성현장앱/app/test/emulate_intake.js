const { chromium } = require('playwright');
const OUT = process.argv[2]; let n = 0; const notes = [];
(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ permissions: ['clipboard-read', 'clipboard-write', 'geolocation'], geolocation: { latitude: 36.72381, longitude: 128.11654 }, viewport: { width: 360, height: 800 }, timezoneId: 'Asia/Seoul', locale: 'ko-KR' });
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
    await tap('button', '+ 접수'); await p.waitForTimeout(600); await shot('접수 창 (공사)');
    await clickText('긴급'); await p.waitForTimeout(400);
    await type('공사 이름', '점촌 배수로 긴급복구');
    await type('공사 위치 (주소·마을·도로명 등)', '점촌동 123-4 앞 도로');
    await tap('button', '지금 위치'); await p.waitForTimeout(2500);
    await type('연락처 이름', '박주무관'); await type('전화번호', '054-550-6000');
    await clickText('피해 사진(전) 찍기', false); await p.waitForTimeout(300);
    await shot('접수 창 (긴급, 위치·체크)');
    await scroll(600); await shot('접수 창 아래');
    await tap('button', '접수', true); await p.waitForTimeout(1000); await shot('접수 뒤 홈');
    await tap('tab', '명부'); await tap('button', '+ 작업자·장비 등록'); await p.waitForTimeout(600); await shot('명부 등록 (인력)');
    await clickText('장비'); await p.waitForTimeout(400); await shot('명부 등록 (장비)');
    await p.keyboard.press('Escape'); await p.waitForTimeout(500);
    await tap('tab', '일지'); await p.waitForTimeout(700);
    await type('항목 (보통인부, 6W, 레미콘 …)', '보통인부').catch(e => notes.push('항목칸: ' + e.message));
    await shot('일지');
  } catch (e) { notes.push('!! 막힘: ' + e.message); await shot('막힌 화면'); }
  notes.push('페이지 오류: ' + JSON.stringify(errs)); console.log(notes.join('\n')); await b.close();
})();
