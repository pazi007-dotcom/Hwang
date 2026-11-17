// 소장 한 달: 2026-11-02 ~ 11-30 현장 입력 → 12-01 아침 대표님께 보고. 하루하루 폰에서 누르는 그대로.
const { start } = require('./lib.js');
const OUT = process.argv[2]; const log = []; let n = 0;
const say = (s) => { log.push(s); console.log(s); };
(async () => {
  const S = await start(360); const { p } = S;
  const shot = async (w) => { n++; await p.screenshot({ path: `${OUT}/s${String(n).padStart(2, '0')}.png` }); say(`   📷 ${n}. ${w}`); };
  const pickSite = async (name) => { await S.top(); await p.getByRole('button', { name: /현장/ }).first().click().catch(async () => { await S.click('현장', false); }); await p.waitForTimeout(500); await S.click(name, false); await p.waitForTimeout(600); };
  let today = '';
  const okIfAsked = async () => { for (const b of ['그대로 저장', '확인']) { if (await p.getByRole('button', { name: b, exact: true }).count()) {
      if (b === '그대로 저장') { const txt = await p.evaluate(() => [...document.querySelectorAll('flt-semantics')].map(e => e.getAttribute('aria-label') || '').filter(t => /공수|겹|하루/.test(t)).join(' / ')); say(`   ⚠ ${today} 경고창: ${txt.slice(0, 160)}`); }
      await p.getByRole('button', { name: b, exact: true }).last().click(); await p.waitForTimeout(400); } } };
  const syncNight = async () => { await S.tap('tab', '동기화'); await S.tap('button', '지금 맞추기'); await p.waitForTimeout(1500); };
  const pick = async (labels, qty = {}) => {
    await S.tap('button', '오늘 나온 사람·장비 고르기'); await p.waitForTimeout(500);
    for (const l of labels) { await S.click(l, false); await p.waitForTimeout(200); }
    for (const [k, v] of Object.entries(qty)) { const [unitLabel, i] = k.split('#'); const f = p.getByRole('textbox', { name: unitLabel, exact: true }); await S.fill(async () => (i === undefined ? f.last() : f.nth(+i)), v); }
    await S.tap('button', '고른 것 넣기'); await p.waitForTimeout(600); await okIfAsked();
  };
  const content = async (t) => { await S.type('오늘 한 일', t); await S.tap('button', '내용 저장'); };
  const weather = async (w) => { await S.top(); await S.click(w); };
  const copyYesterday = async () => { await S.top(); await S.tap('button', '어제와 같이'); await p.waitForTimeout(500); await S.tap('button', '고른 줄 복사'); await p.waitForTimeout(600); await okIfAsked(); };
  const regRoster = async (kind, payee, item, price, extra = {}) => {
    await S.tap('button', '+ 작업자·장비 등록');
    if (kind !== '인력') await S.click(kind);
    await S.type(kind === '인력' ? '이름 (한 사람씩 — 일당·세금이 사람별)' : '업체', payee);
    await S.type(kind === '인력' ? '직종 (보통인부, 형틀목공 …)' : kind === '장비' ? '기종 (6W, 덤프 25톤 …)' : '항목', item);
    if (extra.spec) await S.type('규격 (선택)', extra.spec);
    if (extra.unit) await S.type('단위 (㎥, 톤, 개 …)', extra.unit);
    if (extra.supply) { await S.click(extra.supply); await S.type('배정량', extra.alloc); }
    await S.type(kind === '인력' ? '일당 (원)' : kind === '장비' ? '단가 (원, 위에서 고른 단위당)' : '단가 (원, 모르면 비움)', price);
    if (extra.bank) { await S.type('은행 (월말 이체용)', extra.bank); await S.type('계좌번호', extra.acc); }
    await S.tap('button', '저장', true); await p.waitForTimeout(500);
  };
  const days = []; for (let d = 2; d <= 30; d++) { const dt = new Date(Date.UTC(2026, 10, d)); const wd = dt.getUTCDay(); if (wd !== 0 && wd !== 6) days.push(d); }
  const iso = (d, hh = '07:30') => `2026-11-${String(d).padStart(2, '0')}T${hh}:00+09:00`;
  const work = { 2: '터파기 No.0~No.2', 3: '터파기·버림 No.2~No.4', 4: '기초 거푸집 No.0~No.2', 5: '기초 철근 No.0~No.2', 6: '기초 타설 No.0~No.2 (레미콘 5.5㎥)',
    10: '기초 거푸집 No.2~No.4', 11: '벽체 철근 No.0~No.2', 12: '벽체 거푸집 No.0~No.2', 13: '벽체 타설 No.0~No.2 (레미콘 6㎥)', 16: '거푸집 해체·정리', 17: '기초 철근 No.4~No.6',
    18: '기초 거푸집 No.4~No.6', 19: '지수판·신축줄눈 설치', 20: '기초 타설 No.2~No.6 (레미콘 6.5㎥)', 23: '벽체 철근 No.2~No.4', 24: '벽체 거푸집 No.2~No.4', 25: '벽체 거푸집 No.4~No.6',
    26: '되메우기 No.0~No.4', 27: '벽체 타설 No.2~No.6 (레미콘 5㎥)', 30: '되메우기·정리 No.4~No.6' };
  const pour = { 6: 5.5, 13: 6, 20: 6.5, 27: 5 };
  const crew = ['김반장 · 보통인부', '이영수 · 보통인부', '박목수 · 형틀목공', '정목수 · 형틀목공', '대성중기 · 6W'];
  try {
    // ── 11/2 (월) 아침: 낙찰된 요성리 접수, 명부 등록, 첫 일지
    say('■ 11/2(월) 07:30 사무실 — 요성리 접수, 명부 등록');
    await S.tap('button', '+ 접수'); await S.click('공사'); await S.type('공사 이름', '요성리 용배수로 개체공사');
    await S.type('공사 위치 (주소·마을·도로명 등)', '문경읍 요성리 일원'); await S.tap('button', '지금 위치'); await p.waitForTimeout(1500);
    await S.type('연락처 이름', '문경시 김주무관'); await S.type('전화번호', '054-550-6100');
    await S.click('도면·내역 받기', false); await shot('요성리 접수');
    await S.tap('button', '접수', true); await p.waitForTimeout(800);
    await S.tap('button', '진행', true); await p.waitForTimeout(400); await S.tap('button', '확인', true); await p.waitForTimeout(600);
    await S.tap('tab', '명부');
    await regRoster('인력', '김반장', '보통인부', 187000, { bank: '농협', acc: '351-1111-2222-33' });
    await regRoster('인력', '이영수', '보통인부', 187000, { bank: '국민', acc: '9876-01-234567' });
    await regRoster('인력', '박목수', '형틀목공', 230000);
    await regRoster('인력', '정목수', '형틀목공', 230000, { bank: '신한', acc: '110-222-333444' });
    await regRoster('장비', '대성중기', '6W', 680000, { bank: '기업', acc: '123-456789-01-011' });
    await regRoster('자재', '가은레미콘', '레미콘', 98000, { spec: '25-21-08', bank: '농협', acc: '301-0000-1111-21', supply: '관급 (우리가 구매)', alloc: '22' });
    await shot('명부 6칸 (레미콘 관급 배정 22㎥)');
    await S.tap('tab', '동기화'); await S.type('주소 (Tailscale)', 'http://127.0.0.1:8766'); await S.tap('button', '지금 맞추기'); await p.waitForTimeout(1500);
    for (const d of days) {
      if (d > 2) await syncNight();   // 전날 밤 집 PC와 맞추기
      today = `11/${d}`;
      await S.day(iso(d)); await S.tap('tab', '일지'); await p.waitForTimeout(400);
      if (d === 2) { await weather('맑음'); await pick(crew); await content(work[2]); say('■ 11/2 일지: 명부에서 5명·대 고르기'); await shot('11/2 일지'); continue; }
      if (d === 9) { say('■ 11/9(월) 비 — 작업 없음'); await weather('비'); await S.tap('button', '작업 없음(비 등)'); await okIfAsked(); await shot('11/9 비'); continue; }
      if (d === 10) {
        say('■ 11/10(화) 07:50 긴급 전화 — 점촌 배수로 막힘. 오전 긴급, 오후 요성리');
        await S.tap('button', '+ 접수'); await S.click('긴급'); await S.type('공사 이름', '점촌 배수로 막힘 긴급');
        await S.type('공사 위치 (주소·마을·도로명 등)', '점촌동 중앙시장 앞'); await S.tap('button', '지금 위치'); await p.waitForTimeout(1500);
        await S.type('연락처 이름', '점촌동 행정복지센터'); await S.type('전화번호', '054-550-8600');
        await S.click('피해 사진(전) 찍기', false); await shot('긴급 접수 (체크 2개)'); await S.tap('button', '접수', true); await p.waitForTimeout(800);
        await S.tap('tab', '일지'); await weather('맑음');
        await pick(['김반장 · 보통인부'], { '인': '0.5' });
        await S.click('장비'); await S.type('장비 (6W, 덤프 25톤 …)', '덤프 25톤'); await S.type('받는 업체', '한빛운수');
        await S.type('수량 (반일 0.5)', '3'); await S.type('단위', '대'); await S.type('단가 (원)', '282000'); await S.tap('button', '저장', true); await okIfAsked();
        await content('시장 앞 배수로 준설 30m, 덤프 3대 반출'); await shot('긴급 일지');
        await pickSite('요성리 용배수로 개체공사'); await S.tap('tab', '일지'); await weather('맑음');
        await pick(crew, { '인#0': '0.5' });   // 김반장은 오후만: 고르는 창에서 0.5
        await content(work[10]); await shot('11/10 요성리 (김반장 0.5)'); continue;
      }
      if (d === 20) { say('■ 11/20(금) 바빠서 일지 못 씀 (23일 밤에 입력)'); continue; }
      await copyYesterday();
      if (d === 11) { await S.click('김반장 · 단가', false); await p.waitForTimeout(500); await S.type('수량', '1'); await S.tap('button', '고친 내용 저장'); await okIfAsked(); say('■ 11/11 어제(0.5) 복사 → 김반장 1로 고침'); }
      if (pour[d]) { await pick(['가은레미콘 · 레미콘'], { '㎥': pour[d] }); say(`■ 11/${d} 타설 레미콘 ${pour[d]}㎥`); }
      await weather('맑음'); await content(work[d]);
      if (d === 12) {
        say('■ 11/12(목) 점심 — 불정동 옹벽 견적 요청 접수');
        await S.tap('button', '+ 접수'); await S.click('견적'); await S.type('공사 이름', '불정동 옹벽 보수 견적'); await S.type('공사 위치 (주소·마을·도로명 등)', '불정동 마을회관 뒤');
        await shot('견적 접수 (체크 2개)'); await S.tap('button', '접수', true); await p.waitForTimeout(800);
        await pickSite('요성리 용배수로 개체공사');
      }
      if (d === 23) {
        say('■ 11/23(월) 저녁 — 밀린 20일 일지 입력, 견적 건 취소');
        await S.day(iso(23, '19:30')); await S.tap('tab', '일지'); await S.top(); await S.tap('button', '2026-11-23'); await p.waitForTimeout(500);
        await shot('날짜 고르기'); say('   달력: ' + (await S.all()).filter(t => /20/.test(t)).slice(0, 4).join(' | ')); await S.click('20일', false).catch(async () => S.click('20')); await p.waitForTimeout(300);
        for (const b of ['확인', 'OK']) if (await p.getByRole('button', { name: b, exact: true }).count()) { await p.getByRole('button', { name: b, exact: true }).click(); break; }
        await p.waitForTimeout(600); say('   날짜 칸: ' + ((await S.has('2026-11-20')) ? '2026-11-20 으로 바뀜' : '안 바뀜!'));
        await copyYesterday(); await pick(['가은레미콘 · 레미콘'], { '㎥': pour[20] }); await weather('맑음'); await content(work[20]); await shot('밀린 11/20 입력');
        await pickSite('불정동 옹벽 보수 견적'); await S.tap('tab', '홈'); await S.tap('button', '취소', true); await p.waitForTimeout(400); await okIfAsked(); await shot('견적 취소 뒤');
        await pickSite('요성리 용배수로 개체공사');
      }
    }
    // ── 12/1 (화) 아침: 지난달 보고
    await S.tap('tab', '명부'); await S.top(); await shot('11/30 명부 (관급 사용·남음)');
    say('■ 12/1(화) 07:40 현장 — 11월 보고 올리기');
    await syncNight(); await S.day('2026-12-01T07:40:00+09:00'); await S.tap('tab', '결제 요청'); await p.waitForTimeout(800); await S.top(); await shot('12/1 결제 요청 탭');
    say('   화면 월: ' + ((await S.has('2026-11')) ? '2026-11 (지난달)' : '이번 달?'));
    if (process.env.STOP_AT_REPORT) throw new Error('보고 전 멈춤(분석용)');
    for (const [bank, acc] of [['농협', '352-0000-1234-53'], ['대구', '505-10-123456-7']]) {   // 박목수, 한빛운수
      await S.tap('button', '계좌 넣기'); await S.type('은행', bank); await S.type('계좌번호', acc); await S.tap('button', '저장', true); await p.waitForTimeout(700);
    }
    say('   계좌 없음 남음: ' + (await S.has('계좌 없음')));
    // 대성중기 줄 바로 아래 「계좌·방식」
    const eq = await S.text('대성중기', false);
    const ys = await p.getByRole('button', { name: '계좌·방식' }).evaluateAll((els) => els.map(e => { const r = e.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; }));
    const tgt = ys.filter(([x, y]) => y > eq[1]).sort((a, b) => a[1] - b[1])[0]; say('   대성중기 계좌·방식 ' + JSON.stringify(tgt));
    await p.mouse.click(tgt[0], tgt[1]); await p.waitForTimeout(600);
    await S.click('부가세 10% 더해서'); await S.tap('button', '저장', true); await p.waitForTimeout(700);
    await S.top(); await shot('보내기 전');
    await syncNight(); await shot('집 PC와 맞춤');
    await S.tap('tab', '결제 요청'); await S.top(); await S.tap('button', '대표님께 보고 메일 보내기'); await p.waitForTimeout(500); await shot('보내기 확인');
    await S.tap('button', '보내기', true); await p.waitForTimeout(3000); await S.top(); await shot('보낸 뒤');
    say('   결과: ' + (await S.all()).filter(t => /보냄|보냈|대기|못 보냄|연결/.test(t)).join(' | '));
  } catch (e) { say('!! 막힘: ' + e.message); await shot('막힌 화면'); }
  say('페이지 오류: ' + JSON.stringify(S.errs));
  require('fs').writeFileSync(OUT + '/log.txt', log.join('\n')); await S.b.close();
})();
