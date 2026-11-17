// 접수 → 진행 → 공정 → 완공, 공사 5건(겹치는 기간 포함) · 2026-11-02 ~ 2027-01-04 · 월말 보고 2번
const { start } = require('./lib.js');
const OUT = process.argv[2]; const log = []; let n = 0; const fs = require('fs');
const say = (s) => { log.push(s); console.log(s); fs.writeFileSync(OUT + '/log.txt', log.join('\n')); };
// ── 기대값(손 계산): 날짜·현장·사람·수량·단가 ──
const P = { 김반장: 187000, 이영수: 187000, 박목수: 230000, 정목수: 230000, 대성중기: 680000, 한빛운수: 282000, 가은레미콘: 98000 };
const KIND = { 김반장: '인력', 이영수: '인력', 박목수: '인력', 정목수: '인력', 대성중기: '장비', 한빛운수: '장비', 가은레미콘: '자재' };
const plan = []; const add = (date, site, who, qty) => plan.push({ date, site, who, qty, amt: Math.round(qty * P[who]) });
function expect(month) { // 받는 곳별 이달 금액·원천세·부가세 → 결제하실 돈
  const rows = plan.filter(x => x.date.startsWith(month)); const by = {};
  for (const x of rows) { const b = (by[x.who] ||= { total: 0, days: {} }); b.total += x.amt; if (KIND[x.who] === '인력') b.days[x.date] = (b.days[x.date] || 0) + x.amt; }
  let send = 0, gross = 0; const out = {};
  for (const [w, b] of Object.entries(by)) {
    let tax = 0, local = 0, vat = 0;
    if (KIND[w] === '인력') { tax = Object.values(b.days).reduce((a, d) => a + (d <= 150000 ? 0 : Math.floor((d - 150000) * 27 / 1000)), 0); tax = Math.floor(tax / 10) * 10; if (tax < 1000) tax = 0; local = Math.floor(tax / 10 / 10) * 10; }
    if (w === '대성중기') vat = Math.floor(b.total / 10);
    out[w] = { total: b.total, pay: b.total - tax - local + vat }; send += out[w].pay; gross += b.total;
  }
  return { send, gross, by: out };
}
const won = (n) => n.toLocaleString('en-US');
(async () => {
  const S = await start(360); const { p } = S;
  const shot = async (w) => { n++; await p.screenshot({ path: `${OUT}/s${String(n).padStart(2, '0')}.png` }); say(`   📷 ${n}. ${w}`); };
  let today = '';
  const okIfAsked = async () => { for (const b of ['그대로 저장']) { if (await p.getByRole('button', { name: b, exact: true }).count()) { say(`   ⚠ ${today} 겹침 경고창 → 그대로 저장`); await p.getByRole('button', { name: b, exact: true }).last().click(); await p.waitForTimeout(400); } } };
  const confirm = async (label = '확인') => { await p.getByRole('button', { name: label, exact: true }).last().click(); await p.waitForTimeout(600); };
  const pickSite = async (name) => { await S.top(); await p.getByRole('button', { name: /현장/ }).first().click(); await p.waitForTimeout(500); await S.click(name, false); await p.waitForTimeout(700); };
  const pick = async (labels, qty = {}) => {
    await S.tap('button', '오늘 나온 사람·장비 고르기'); await p.waitForTimeout(500);
    for (const l of labels) { await S.click(l, false); await p.waitForTimeout(150); }
    for (const [k, v] of Object.entries(qty)) { const [u, i] = k.split('#'); const f = p.getByRole('textbox', { name: u, exact: true }); await S.fill(async () => (i === undefined ? f.last() : f.nth(+i)), v); }
    await S.tap('button', '고른 것 넣기'); await p.waitForTimeout(600); await okIfAsked();
  };
  const content = async (t) => { await S.type('오늘 한 일', t); await S.tap('button', '내용 저장'); };
  const weather = async (w) => { await S.top(); await S.click(w); };
  const copyYesterday = async () => { await S.top(); await S.tap('button', '어제와 같이'); await p.waitForTimeout(500); await S.tap('button', '고른 줄 복사'); await p.waitForTimeout(600); await okIfAsked(); };
  const progress = async (from, to) => { await S.type('시공 측점 시작', from); await S.type('시공 측점 끝', to); await S.tap('button', '시공 연장 저장'); };
  const act = async (a, text) => { await S.tap('tab', '홈'); await S.top(); await S.tap('button', a, true); await p.waitForTimeout(400); if (text !== undefined) { await S.fill(async () => p.getByRole('textbox').last(), text); } await confirm(); };
  const receive = async (type, name, addr, cname, cphone, check) => {
    await S.top(); await S.tap('button', '+ 접수'); await S.click(type); await S.type('공사 이름', name);
    if (addr) { await S.type('공사 위치 (주소·마을·도로명 등)', addr); await S.tap('button', '지금 위치'); await p.waitForTimeout(1200); }
    if (cname) { await S.type('연락처 이름', cname); await S.type('전화번호', cphone); }
    if (check) await S.click(check, false);
    await S.tap('button', '접수', true); await p.waitForTimeout(800);
  };
  const tasksToday = async () => { // 홈 「발주·체크」에서 오늘·지난 것 체크
    await S.tap('tab', '홈'); await S.top(); const done = [];
    for (let k = 0; k < 15; k++) {
      let lab = (await S.labels()).find(t => /^(오늘|\d+일 지남)\n/.test(t));
      if (!lab) { await S.scroll(450); lab = (await S.labels()).find(t => /^(오늘|\d+일 지남)\n/.test(t)); }
      if (!lab) break;
      await S.click(lab, true); done.push(lab.replace(/\n/, ' ')); await p.waitForTimeout(500); await S.top();
    }
    if (done.length) say(`   ☑ ${today} 발주·체크 ${done.length}건: ${done.join(' / ')}`);
  };
  const regRoster = async (kind, payee, item, price, extra = {}) => {
    await S.tap('button', '+ 작업자·장비 등록'); if (kind !== '인력') await S.click(kind);
    await S.type(kind === '인력' ? '이름 (한 사람씩 — 일당·세금이 사람별)' : '업체', payee);
    await S.type(kind === '인력' ? '직종 (보통인부, 형틀목공 …)' : kind === '장비' ? '기종 (6W, 덤프 25톤 …)' : '항목', item);
    if (extra.spec) await S.type('규격 (선택)', extra.spec);
    if (extra.supply) { await S.click(extra.supply); await S.type('배정량', extra.alloc); }
    await S.type(kind === '인력' ? '일당 (원)' : kind === '장비' ? '단가 (원, 위에서 고른 단위당)' : '단가 (원, 모르면 비움)', price);
    if (extra.bank) { await S.type('은행 (월말 이체용)', extra.bank); await S.type('계좌번호', extra.acc); }
    await S.tap('button', '저장', true); await p.waitForTimeout(500);
  };
  const sync = async () => { await S.tap('tab', '동기화'); await S.tap('button', '지금 맞추기'); await p.waitForTimeout(1500); };
  const day = async (iso) => { await S.day(iso); today = iso.slice(5, 10).replace('-', '/'); };
  const readPay = async () => { await S.top(); const t = (await S.all()).find(x => /결제하실 돈/.test(x)) || ''; const m = t.match(/결제하실 돈\s*([\d,]+)/); return m ? +m[1].replace(/,/g, '') : null; };
  const A = '요성리 용배수로 개체공사', B = '점촌 배수로 막힘 긴급', C = '불정동 옹벽 보수', D = '산양면 배수로 정비 입찰', E = '오미리 배수구 막힘 민원';
  const crewA = ['김반장 · 보통인부', '이영수 · 보통인부', '박목수 · 형틀목공', '정목수 · 형틀목공', '대성중기 · 6W'];
  const sta = (m) => { const no = Math.floor(m / 20), r = +(m - no * 20).toFixed(2); return r ? `No.${no}+${r}` : `No.${no}`; };
  let staA = 0, staC = 0; const pourA = { '11-13': 5.5, '11-20': 6, '11-27': 6.5, '12-04': 5, '12-11': 6, '12-18': 6.5 };
  const rainA = new Set(['11-19', '12-14']);
  const workDays = []; for (let t = Date.UTC(2026, 10, 9); t <= Date.UTC(2026, 11, 18); t += 864e5) { const d = new Date(t); if (d.getUTCDay() % 6) workDays.push(d.toISOString().slice(5, 10)); }
  const aDays = workDays.filter(d => !rainA.has(d));
  const overlap = new Set(['12-07', '12-08', '12-09', '12-10', '12-11']);
  try {
    // ════ 11/2 (월) 요성리 낙찰 → 접수·공종·진행, 명부 ════
    await day('2026-11-02T07:30:00+09:00'); say('■ 11/2 요성리 접수 → 공종(U형 개거 250m) → 진행(시작 11/9)');
    await receive('공사', A, '문경읍 요성리 일원', '문경시 김주무관', '054-550-6100', '도면·내역 받기');
    await S.tap('tab', '홈'); await S.tap('button', '+ 공종 추가'); await S.type('설계 연장 (m)', '250'); await S.tap('button', '추가', true); await p.waitForTimeout(600);
    await act('진행', '2026-11-09');
    await S.tap('tab', '명부');
    await regRoster('인력', '김반장', '보통인부', 187000, { bank: '농협', acc: '351-1111-2222-33' });
    await regRoster('인력', '이영수', '보통인부', 187000, { bank: '국민', acc: '9876-01-234567' });
    await regRoster('인력', '박목수', '형틀목공', 230000);
    await regRoster('인력', '정목수', '형틀목공', 230000, { bank: '신한', acc: '110-222-333444' });
    await regRoster('장비', '대성중기', '6W', 680000, { bank: '기업', acc: '123-456789-01-011' });
    await regRoster('자재', '가은레미콘', '레미콘', 98000, { spec: '25-21-08', bank: '농협', acc: '301-0000-1111-21', supply: '관급 (우리가 구매)', alloc: '34' });
    await S.tap('tab', '동기화'); await S.type('주소 (Tailscale)', 'http://127.0.0.1:8766'); await S.tap('button', '지금 맞추기'); await p.waitForTimeout(2000);
    await S.tap('tab', '홈'); await S.top(); await shot('11/2 요성리 홈 (공정률·발주 일정 내려옴)');
    // ════ 날마다 ════
    for (let t = Date.UTC(2026, 10, 3); t <= Date.UTC(2026, 11, 18); t += 864e5) {
      const dd = new Date(t).toISOString().slice(5, 10); const wd = new Date(t).getUTCDay(); if (wd === 0 || wd === 6) continue;
      await sync(); await day(`2026-${dd}T07:20:00+09:00`); const D_ = `2026-${dd}`;
      await pickSite(A); await tasksToday();
      // ── 그날 생기는 일 ──
      if (dd === '11-10') { say('■ 11/10 07:50 긴급 전화 → 오전 긴급 처리 → 완공, 오후 요성리');
        await receive('긴급', B, '점촌동 중앙시장 앞', '점촌동 행정복지센터', '054-550-8600', '피해 사진(전) 찍기');
        await S.tap('tab', '일지'); await weather('맑음'); await pick(['김반장 · 보통인부'], { '인': '0.5' }); add(D_, B, '김반장', 0.5);
        await S.click('장비'); await S.type('장비 (6W, 덤프 25톤 …)', '덤프 25톤'); await S.type('받는 업체', '한빛운수'); await S.type('수량 (반일 0.5)', '3'); await S.type('단위', '대'); await S.type('단가 (원)', '282000'); await S.tap('button', '저장', true); await okIfAsked(); add(D_, B, '한빛운수', 3);
        await content('시장 앞 배수로 준설 30m, 덤프 3대 반출'); await act('완공', D_); await shot('긴급 완공'); await pickSite(A); }
      if (dd === '11-12') { say('■ 11/12 불정동 옹벽 견적 접수'); await receive('견적', C, '불정동 마을회관 뒤', '불정동 이장', '010-3333-4444', '답사·실측'); await pickSite(A); }
      if (dd === '11-16') { say('■ 11/16 견적 보류 / 산양면 입찰 접수');
        await pickSite(C); await act('보류', '발주처 예산 확정 대기');
        await receive('입찰', D, '산양면 현리 일원', null, null, '공고 자격 확인'); await pickSite(A); }
      if (dd === '11-27') { say('■ 11/27 산양면 입찰 낙찰 실패 → 취소'); await pickSite(D); await act('취소', '낙찰 실패 (2순위)'); say('   취소 뒤 현장 목록에 남음: ' + (await S.has(D))); await pickSite(A); }
      if (dd === '12-01') { // 지난달 보고
        say('■ 12/1 07:40 현장 — 11월 보고'); await S.tap('tab', '결제 요청'); await p.waitForTimeout(800);
        for (const [bank, acc] of [['농협', '352-0000-1234-53'], ['대구', '505-10-123456-7']]) { await S.tap('button', '계좌 넣기'); await S.type('은행', bank); await S.type('계좌번호', acc); await S.tap('button', '저장', true); await p.waitForTimeout(700); }
        const eq = await S.text('대성중기', false); const ys = await p.getByRole('button', { name: '계좌·방식' }).evaluateAll((els) => els.map(e => { const r = e.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; }));
        const tgt = ys.filter(([x, y]) => y > eq[1]).sort((a, b) => a[1] - b[1])[0]; await p.mouse.click(tgt[0], tgt[1]); await p.waitForTimeout(600);
        await S.click('부가세 10% 더해서'); await S.tap('button', '저장', true); await p.waitForTimeout(700);
        const exp = expect('2026-11'); const got = await readPay(); say(`   11월 결제하실 돈: 앱 ${won(got)} / 손 계산 ${won(exp.send)} ${got === exp.send ? '✔' : '✘ 다름'}`);
        await S.top(); await S.tap('button', '대표님께 보고 메일 보내기'); await S.tap('button', '보내기', true); await p.waitForTimeout(3000); await S.top();
        say('   보낸 뒤: ' + (await S.all()).filter(x => /보냄|대기|못/.test(x)).map(x => x.replace(/\s+/g, ' ')).join(' | ')); await shot('12/1 11월 보고 보냄');
        say('■ 12/1 불정동 견적 → 진행(시작 12/7), 공종 옹벽 30m'); await pickSite(C); await act('진행', '2026-12-07');
        await S.tap('button', '+ 공종 추가'); await S.click('기타'); await S.type('공종 이름', '옹벽 보수'); await S.type('설계 연장 (m)', '30'); await S.tap('button', '추가', true); await p.waitForTimeout(500); await pickSite(A); }
      if (dd === '12-02') { say('■ 12/2 오미리 민원 접수'); await receive('민원', E, '오미리 버스정류장 옆', '오미리 주민', '010-5555-6666', '민원인 연락'); await pickSite(A); }
      if (dd === '12-03') { say('■ 12/3 민원 처리(김반장 오전) → 완공');
        await pickSite(E); await S.tap('tab', '일지'); await weather('맑음'); await pick(['김반장 · 보통인부'], { '인': '0.5' }); add(D_, E, '김반장', 0.5); await content('배수구 토사 제거, 덮개 교체');
        await tasksToday(); await act('완공', D_); await pickSite(A); }
      if (dd === '12-10') { say('■ 12/10 사장님 11월 결제 끝냈다고 연락 → 결제 끝남'); await S.tap('tab', '결제 요청'); await S.top(); await S.tap('button', '결제 끝남'); await confirm('결제 끝남'); say('   11월 남은 돈: ' + (await readPay())); await pickSite(A); }
      // ── 불정동(C) 시공 12/7~12/11: 요성리와 겹침 ──
      if (overlap.has(dd)) {
        await pickSite(C); await S.tap('tab', '일지'); await weather('맑음');
        await pick(['김반장 · 보통인부', '박목수 · 형틀목공', '정목수 · 형틀목공', '대성중기 · 6W'], { '인#0': '0.5', '일': '0.5' });
        add(D_, C, '김반장', 0.5); add(D_, C, '박목수', 1); add(D_, C, '정목수', 1); add(D_, C, '대성중기', 0.5);
        if (dd === '12-07') { await S.click('장비'); await S.type('장비 (6W, 덤프 25톤 …)', '덤프 25톤'); await S.type('받는 업체', '한빛운수'); await S.type('수량 (반일 0.5)', '1'); await S.type('단위', '대'); await S.type('단가 (원)', '282000'); await S.tap('button', '저장', true); await okIfAsked(); add(D_, C, '한빛운수', 1); }
        await content(`옹벽 보수 ${staC}~${staC + 6}m`); await progress(sta(staC), sta(staC + 6)); staC += 6;
        if (dd === '12-07') await shot('12/7 불정동 (겹치는 날)');
        if (dd === '12-11') { await act('완공', D_); say('   불정동 완공'); }
        await pickSite(A);
      }
      // ── 요성리(A) ──
      if (dd < '11-09') continue;                     // 시작 전: 발주·체크만
      if (dd === '11-20') { say('■ 11/20 일지 못 씀 (23일 밤에)'); continue; }
      await S.tap('tab', '일지');
      if (rainA.has(dd)) { await weather('비'); await S.tap('button', '작업 없음(비 등)'); say(`■ ${today} 비 — 작업 없음`); continue; }
      const half = overlap.has(dd) || dd === '11-10' || dd === '12-03';
      const firstAfterBreak = dd === '11-09' || dd === '11-11' || dd === '12-04' || dd === '12-15';
      if (overlap.has(dd)) { await pick(['김반장 · 보통인부', '이영수 · 보통인부', '대성중기 · 6W'], { '인#0': '0.5', '일': '0.5' });
        add(D_, A, '김반장', 0.5); add(D_, A, '이영수', 1); add(D_, A, '대성중기', 0.5);
      } else if (half) { await pick(crewA, { '인#0': '0.5' }); add(D_, A, '김반장', 0.5); for (const w of ['이영수', '박목수', '정목수', '대성중기']) add(D_, A, w, 1);
      } else if (firstAfterBreak) { await pick(crewA); for (const w of ['김반장', '이영수', '박목수', '정목수', '대성중기']) add(D_, A, w, 1);
      } else { await copyYesterday(); for (const w of ['김반장', '이영수', '박목수', '정목수', '대성중기']) add(D_, A, w, 1); }
      if (pourA[dd]) { await pick(['가은레미콘 · 레미콘'], { '㎥': pourA[dd] }); add(D_, A, '가은레미콘', pourA[dd]); }
      await weather('맑음');
      const step = aDays.indexOf(dd) === aDays.length - 1 ? 250 - staA : 9; const to = Math.min(250, staA + step);
      await content(`U형 개거 ${sta(staA)}~${sta(to)}`); await progress(sta(staA), sta(to)); staA = to;
      if (dd === '11-23') { // 밤에 밀린 20일
        await day('2026-11-23T19:30:00+09:00'); await S.tap('tab', '일지'); await S.top(); await S.tap('button', '2026-11-23'); await S.click('11월 20일', false); await confirm('확인');
        say('■ 11/23 밤 밀린 11/20 입력: 날짜 ' + ((await S.has('2026-11-20')) ? '20일로 바뀜' : '안 바뀜!'));
        await pick(crewA); for (const w of ['김반장', '이영수', '박목수', '정목수', '대성중기']) add('2026-11-20', A, w, 1);
        await pick(['가은레미콘 · 레미콘'], { '㎥': pourA['11-20'] }); add('2026-11-20', A, '가은레미콘', pourA['11-20']);
        await weather('맑음'); const to2 = staA + 9; await content(`U형 개거 ${sta(staA)}~${sta(to2)} (밀린 일지)`); await progress(sta(staA), sta(to2)); staA = to2; }
      if (dd === '12-18') { await S.tap('tab', '홈'); await S.top(); await shot('12/18 요성리 공정률'); await act('완공', D_); say(`■ 12/18 요성리 완공 · 시공 ${staA}m`); }
    }
    // ════ 1/4 (월) 12월 보고 ════
    await sync(); await day('2027-01-04T07:40:00+09:00'); say('■ 2027-01-04 07:40 — 12월 보고');
    await S.tap('tab', '결제 요청'); await p.waitForTimeout(800); await S.top(); say('   화면 월: ' + ((await S.has('2026-12')) ? '2026-12' : '다른 달!'));
    const exp12 = expect('2026-12'); const got12 = await readPay(); say(`   12월 결제하실 돈: 앱 ${won(got12)} / 손 계산 ${won(exp12.send)} ${got12 === exp12.send ? '✔' : '✘ 다름'}`);
    await shot('1/4 12월 결제 요청'); await S.tap('button', '대표님께 보고 메일 보내기'); await S.tap('button', '보내기', true); await p.waitForTimeout(3000); await S.top();
    say('   보낸 뒤: ' + (await S.all()).filter(x => /보냄|대기|못/.test(x)).map(x => x.replace(/\s+/g, ' ')).join(' | '));
    await S.scroll(6000); await shot('2026년 누계'); say('   연 누계 화면: ' + (await S.all()).filter(x => /김반장 · 보통인부|2026년 누계/.test(x)).map(x => x.replace(/\s+/g, ' ')).slice(0, 3).join(' | '));
    await S.tap('tab', '명부'); await S.click('김반장', false); await p.waitForTimeout(800); await S.tap('button', '◀'); await p.waitForTimeout(600); await shot('김반장 12월 출역표');
    // 기대값 저장
    fs.writeFileSync(OUT + '/expect.json', JSON.stringify({ nov: expect('2026-11'), dec: expect('2026-12'), plan }, null, 1));
  } catch (e) { say('!! 막힘: ' + e.message); await shot('막힌 화면'); }
  say('페이지 오류: ' + JSON.stringify(S.errs)); await S.b.close();
})();
