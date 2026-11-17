// 현장 시뮬레이션 공용: 날짜 바꾸기(다음 날 아침 앱 다시 열기), 누르기, 입력, 화면 글자 읽기
const { chromium } = require('playwright');
async function start(width = 360) {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width, height: 800 }, timezoneId: 'Asia/Seoul', locale: 'ko-KR',
    permissions: ['clipboard-read', 'clipboard-write', 'geolocation'], geolocation: { latitude: 36.6359, longitude: 128.1534 } });
  const p = await ctx.newPage(); const errs = []; p.on('pageerror', e => errs.push(String(e)));
  await p.addInitScript(() => {
    const D = Date; window.__simNow = new D('2026-11-02T07:30:00+09:00').getTime(); let base = D.now();
    globalThis.Date = class extends D { constructor(...a) { super(...(a.length ? a : [window.__simNow + (D.now() - base)])); }
      static now() { return window.__simNow + (D.now() - base); } };
    window.__setNow = (iso) => { window.__simNow = new D(iso).getTime(); base = D.now(); };
  });
  await p.goto('http://127.0.0.1:8791/'); await p.waitForTimeout(5000);
  await p.evaluate(() => document.querySelector('flt-semantics-placeholder')?.click()); await p.waitForTimeout(800);
  const S = { b, p, errs };
  S.scroll = async (dy) => { await p.mouse.move(180, 450); await p.mouse.wheel(0, dy); await p.waitForTimeout(250); };
  S.find = async (role, name, exact = false) => { for (let i = 0; i < 30; i++) { const l = p.getByRole(role, { name, exact }); if (await l.count() > 0) { try { await l.last().scrollIntoViewIfNeeded({ timeout: 800 }); } catch {} return l.last(); } await S.scroll(i < 14 ? 350 : -350); } throw new Error(`못 찾음: ${role} "${name}"`); };
  S.tap = async (role, name, exact) => { await (await S.find(role, name, exact)).click(); await p.waitForTimeout(450); };
  S.fill = async (getL, text) => { let v; for (let k = 0; k < 4; k++) { const l = await getL(); await l.click({ timeout: 5000 }); await p.waitForTimeout(250); await p.keyboard.press('Control+A'); await p.waitForTimeout(80); await p.keyboard.type(String(text)); await p.waitForTimeout(150);
      v = await p.evaluate(() => document.activeElement && document.activeElement.value); if (v === undefined || v === null || v.trim() === String(text)) return; }
    throw new Error(`입력이 안 됨: ${text} (칸 값: ${v})`); };
  S.type = async (name, text) => S.fill(() => S.find('textbox', name), text);
  S.text = async (t, exact = false) => { for (let i = 0; i < 30; i++) { const o = await p.evaluate(([t, exact]) => {
      const host = document.querySelector('flt-semantics-host') || document.body;
      return [...host.querySelectorAll('*')].filter(e => { const own = (e.getAttribute('aria-label') || [...e.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join('') || '').trim();
          return own && (exact ? own === t : own.includes(t)); })
        .map(e => { const r = e.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2, r.width, r.height]; })
        .filter(x => x[2] > 0 && x[3] > 0 && x[1] > 60 && x[1] < 740).sort((a, b) => a[2] * a[3] - b[2] * b[3])[0]; }, [t, exact]);
      if (o) return o; await S.scroll(i < 14 ? 350 : -350); } throw new Error('글자 못 찾음: ' + t); };
  S.click = async (t, exact = true) => { const o = await S.text(t, exact); await p.mouse.click(o[0], o[1]); await p.waitForTimeout(450); };
  S.has = async (t) => p.evaluate((t) => [...document.querySelectorAll('flt-semantics')].some(e => (e.getAttribute('aria-label') || e.textContent || '').includes(t)), t);
  S.all = async () => p.evaluate(() => [...new Set([...document.querySelectorAll('flt-semantics')].map(e => (e.getAttribute('aria-label') || '').trim()).filter(Boolean))]);
  S.day = async (iso) => { // 다음 날 아침: 폰을 껐다가 앱을 다시 연다
    await p.evaluate((iso) => window.__setNow(iso), iso);
    await p.evaluate(() => { Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true }); document.dispatchEvent(new Event('visibilitychange')); });
    await p.waitForTimeout(150);
    await p.evaluate(() => { Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true }); document.dispatchEvent(new Event('visibilitychange')); window.dispatchEvent(new Event('focus')); });
    await p.waitForTimeout(700);
  };
  S.top = async () => { await S.scroll(-6000); };
  return S;
}
module.exports = { start };
