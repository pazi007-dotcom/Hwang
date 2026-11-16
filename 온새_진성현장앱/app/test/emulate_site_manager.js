const { chromium } = require('playwright');
const OUT = process.argv[2];
let n = 0; const notes = [];
(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 412, height: 915 }, deviceScaleFactor: 1, timezoneId: 'Asia/Seoul', locale: 'ko-KR' });
  const p = await ctx.newPage();
  const errs = []; p.on('pageerror', e => errs.push(String(e)));
  await p.addInitScript(() => { const f = new Date('2026-11-16T08:30:00+09:00').getTime(); const D = Date;
    globalThis.Date = class extends D { constructor(...a) { super(...(a.length ? a : [f])); } static now() { return f; } }; });
  await p.goto('http://127.0.0.1:8791/'); await p.waitForTimeout(5000);
  await p.evaluate(() => document.querySelector('flt-semantics-placeholder')?.click()); await p.waitForTimeout(1000);
  const shot = async (what) => { n++; const f = `${OUT}/s${String(n).padStart(2,'0')}.png`; await p.screenshot({ path: f }); notes.push(`[화면 ${n}] ${what}`); };
  const note = (s) => notes.push('   ' + s);
  const scroll = async (dy) => { await p.mouse.move(206, 500); await p.mouse.wheel(0, dy); await p.waitForTimeout(400); };
  async function find(role, name, exact = false) {
    for (let i = 0; i < 25; i++) {
      const loc = p.getByRole(role, { name, exact });
      if (await loc.count() > 0) { const l = loc.first(); try { await l.scrollIntoViewIfNeeded({ timeout: 1000 }); } catch {} return l; }
      await scroll(i < 12 ? 300 : -300);
    }
    throw new Error(`못 찾음: ${role} "${name}"`);
  }
  async function top() { for (let i = 0; i < 8; i++) await scroll(-800); }
  async function tap(role, name, exact) { const l = await find(role, name, exact); await l.click(); await p.waitForTimeout(600); }
  async function type(name, text) { const l = await find('textbox', name); await l.click(); await p.keyboard.press('Control+A'); await p.keyboard.type(String(text)); await p.waitForTimeout(200); }
  async function readAll() { return await p.evaluate(() => [...document.querySelectorAll('flt-semantics')].map(e => e.getAttribute('aria-label') || '').filter(Boolean)); }
  async function snack() { const t = await p.evaluate(() => [...document.querySelectorAll('flt-semantics')].map(e => (e.getAttribute('aria-label')||e.textContent||'').trim()).filter(x => /저장|접수했|겹침|거부|없습니다|넣어|적어/.test(x))); return t.slice(-3).join(' | '); }

  try {
    await shot('앱 처음 열기 (빈 폰)');
    // ── 1. 요성리 등록
    await tap('button', '+ 접수');
    await type('공사 이름', '요성리 용배수로 개체공사');
    await shot('+ 접수 창');
    // 구분을 '입찰'로
    await tap('button', '구분'); await p.waitForTimeout(400);
    { const o = await p.evaluate(() => [...document.querySelectorAll('flt-semantics')].filter(e => (e.getAttribute('aria-label')||e.textContent||'').trim() === '공사').map(e => { const r = e.getBoundingClientRect(); return [r.x + r.width/2, r.y + r.height/2, r.width]; }).filter(x => x[2] > 0).pop()); await p.mouse.click(o[0], o[1]); }
    await p.waitForTimeout(400);
    await type('지시사항·확인사항', '개거 1.0×1.0 L=250m, 기초 250 1회 타설');
    await tap('button', '접수', true);
    await p.waitForTimeout(800); await shot('요성리 접수 후 홈'); note('알림: ' + await snack());

    // ── 2. 일지 탭
    await tap('tab', '일지'); await p.waitForTimeout(800);
    { const o = await p.evaluate(() => [...document.querySelectorAll('flt-semantics')].filter(e => (e.getAttribute('aria-label')||e.textContent||'').trim() === '맑음').map(e => { const r = e.getBoundingClientRect(); return [r.x + r.width/2, r.y + r.height/2, r.width]; }).filter(x => x[2] > 0).pop()); await p.mouse.click(o[0], o[1]); await p.waitForTimeout(700); }
    await shot('일지 탭 처음 (날씨 맑음 선택)');
    const line = async (kind, item, payee, qty, unit, price, spec) => {
      await top();
      await tap('button', kind, true);
      await type(kind === '인력' ? '직종 (보통인부, 형틀목공 …)' : kind === '장비' ? '장비 (6W, 덤프 25톤 …)' : kind === '자재' ? '자재 (레미콘, 와이어메쉬 …)' : '외주 내용', item);
      if (spec) await type('규격 (25-21-08 등, 선택)', spec);
      await type(kind === '인력' ? '받는 사람 (이름 또는 팀)' : '받는 업체', payee);
      await type('수량 (반일 0.5)', qty);
      if (unit) await type('단위', unit);
      if (price !== null) await type('단가 (원)', price);
      await tap('button', '저장', true);
      await p.waitForTimeout(700);
      const s = await snack(); note(`${kind} ${item} ${qty}${unit||''} ${payee} ${price ?? '(단가 추천)'} → ${s || '알림 없음'}`);
      return s;
    };
    await line('인력', '형틀목공', '박목수 팀', 2, null, 230000);
    await line('인력', '보통인부', '김반장', 1, null, 187000);
    await line('인력', '보통인부', '이영수', 1, null, null);   // 같은 직종: 단가가 남아 있어야 함
    await line('장비', '6W', '대성중기', 1, null, 680000);
    await line('장비', '펌프카', '문경펌프', 1, null, 750000);
    await line('자재', '레미콘', '가은레미콘', 6, null, 98000, '25-21-08');
    await scroll(1200); await shot('요성리 투입 6줄 입력 후 목록');
    // 작업 내용
    await type('오늘 한 일', 'No.3~No.5 기초 타설 6㎥, 벽체 거푸집 조립');
    await tap('button', '내용 저장'); note('작업 내용 → ' + await snack());
    await scroll(1500); await shot('작업 내용 칸 확인');
    await shot('작업 내용 저장');

    // ── 3. 오후 긴급
    await tap('button', '+ 접수');
    await type('공사 이름', '점촌 배수로 긴급복구');
    await type('지시사항·확인사항', '토사 유입 30m 준설, 오후 착수');
    await type('연락처 이름', '문경시 김주무관'); await type('전화번호', '054-550-0000');
    await tap('button', '접수', true); await p.waitForTimeout(800);
    note('긴급 접수 → ' + await snack());
    await tap('tab', '일지'); await p.waitForTimeout(800);
    await shot('긴급 현장 일지 (현장이 바뀌었는지)');
    const s1 = await line('인력', '보통인부', '김반장', 0.5, null, null);
    await shot('김반장 0.5 저장 시도 → 겹침 경고?');
    if (await p.getByRole('button', { name: '그대로 저장' }).count() > 0) { await p.getByRole('button', { name: '그대로 저장' }).click(); await p.waitForTimeout(700); note('겹침 경고 → 그대로 저장 → ' + await snack()); }
    await line('장비', '덤프 25톤', '한빛운수', 3, '대', 282000);
    await scroll(1200); await shot('긴급 현장 투입');

    // ── 4. 요성리 김반장을 0.5 로 고치기
    await top();
    await tap('button', '현장'); await p.waitForTimeout(600);
    const opts = await p.evaluate(() => [...document.querySelectorAll('flt-semantics')].filter(e => /요성리/.test(e.getAttribute('aria-label')||e.textContent||'')).map(e => { const r = e.getBoundingClientRect(); return [r.x + r.width/2, r.y + r.height/2, r.width]; }));
    const o = opts.filter(x => x[2] > 0).pop(); await p.mouse.click(o[0], o[1]); await p.waitForTimeout(900);
    const kim = await find('button', '김반장');
    note('요성리 줄 목록에서 김반장 줄 찾음');
    await kim.click(); await p.waitForTimeout(800); await shot('줄 고치기 화면');
    await type('수량', '0.5'); await tap('button', '고친 내용 저장'); await p.waitForTimeout(700);
    note('김반장 0.5로 고침 → ' + await snack());
    await scroll(1200); await shot('요성리 고친 뒤');

    // ── 5. 결제 탭
    await tap('tab', '결제'); await p.waitForTimeout(1000); await shot('결제 탭');
    await scroll(700); await shot('결제 탭 아래');
    await scroll(900); await shot('현장별 한 달 집계');
    // ── 6. 홈
    await tap('tab', '홈'); await p.waitForTimeout(800); await shot('홈');
  } catch (e) { notes.push('!! 막힘: ' + e.message); await shot('막힌 화면'); }
  notes.push('페이지 오류: ' + JSON.stringify(errs));
  console.log(notes.join('\n'));
  await b.close();
})();
