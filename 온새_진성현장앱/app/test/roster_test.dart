// 명부 → 일지(명부에서 고르기) → 사람별 출역표 → 월·연간 집계.
import 'package:flutter_test/flutter_test.dart';
import 'package:jinsung_app/ledger.dart';
import 'package:jinsung_app/roster.dart';
import 'package:jinsung_app/row_db.dart';
import 'package:jinsung_app/store.dart';
import 'package:jinsung_app/works.dart';

void main() {
  test('명부 등록 → 두 달 출역 → 사람별 달력·월·연간', () async {
    final s = Store(MemoryDb(), device: 'phone');
    final ys = await s.receive('요성리', '공사', '2026-10-01');
    final em = await s.receive('점촌 긴급', '긴급', '2026-11-10');
    final kim = await s.saveRoster(kind: '인력', payee: '김반장', item: '보통인부', unit: '인', unitPrice: 187000, phone: '010-1111-2222');
    final park = await s.saveRoster(kind: '인력', payee: '박목수 팀', item: '형틀목공', unit: '인', unitPrice: 230000);
    final w6 = await s.saveRoster(kind: '장비', payee: '대성중기', item: '6W', unit: '일', unitPrice: 680000);
    final w3 = await s.saveRoster(kind: '장비', payee: '대성중기', item: '3W', unit: '일', unitPrice: 560000);
    final dump = await s.saveRoster(kind: '장비', payee: '한빛운수', item: '덤프 25톤', unit: '대', unitPrice: 282000);
    expect((await s.roster()).length, 5);
    // 같은 사람 다시 등록하면 단가만 바뀌고 새로 생기지 않음
    await s.saveRoster(kind: '인력', payee: '김반장', item: '보통인부', unit: '인', unitPrice: 190000);
    expect((await s.roster(kind: '인력')).length, 2);
    await s.saveRoster(kind: '인력', payee: '김반장', item: '보통인부', unit: '인', unitPrice: 187000);

    // 10월 3일, 11월 4일 출역 (명부에서 고르기)
    for (final d in ['2026-10-05', '2026-10-06', '2026-10-07']) {
      await s.addFromRoster(ys, d, [(kim, '1'), (park, '2'), (w6, '1')]);
    }
    for (final d in ['2026-11-09', '2026-11-11', '2026-11-12']) {
      await s.addFromRoster(ys, d, [(kim, '1'), (park, '2'), (w6, '1')]);
    }
    // 11/10: 오전 긴급, 오후 요성리
    await s.addFromRoster(em, '2026-11-10', [(kim, '0.5'), (w3, '0.5'), (dump, '3')]);
    await s.addFromRoster(ys, '2026-11-10', [(kim, '0.5'), (park, '2')]);
    // 일지에 처음 적은 사람은 명부에 자동으로
    await s.addLine(siteId: ys, workDate: '2026-11-12', kind: '인력', item: '철근공', qty: 1, unit: '인', unitPrice: 250000, payee: '최철근');
    expect((await s.roster(kind: '인력')).map((r) => r.label), contains('최철근 · 철근공'));

    final kimId = (await s.roster()).firstWhere((r) => r.id == kim).row['payee_id'] as String;
    final nov = await s.personMonth(kimId, '2026-11');
    expect(nov.keys.toList()..sort(), ['2026-11-09', '2026-11-10', '2026-11-11', '2026-11-12']);
    expect(nov['2026-11-10']!.qty, 1);
    expect(nov['2026-11-10']!.parts.map((p) => '${p.site} ${p.qty}').toSet(), {'점촌 긴급 0.5', '요성리 0.5'});
    expect(nov.values.fold<num>(0, (a, d) => a + d.qty), 4);

    final year = {for (final y in await s.yearByPayee('2026')) '${y.name}/${y.detail}': y};
    final k = year['김반장/인력 보통인부']!;
    expect([k.qty[10], k.qty[11], k.qtyTotal, k.amountTotal], [3, 4, 7, 7 * 187000]);
    final p = year['박목수 팀/인력 형틀목공']!;
    expect([p.qty[10], p.qty[11], p.qtyTotal], [6, 8, 14]);
    expect(year['대성중기/장비 6W']!.qtyTotal, 6);
    expect(year['대성중기/장비 3W']!.qtyTotal, 0.5); // 같은 업체라도 기종별로
    expect(year['한빛운수/장비 덤프 25톤']!.qty[11], 3);

    final sites = {for (final y in await s.yearBySite('2026')) y.name: y};
    expect(sites['요성리']!.amount[10], 3 * (187000 + 460000 + 680000));
    expect(sites['점촌 긴급']!.amountTotal, 93500 + 280000 + 846000);

    final text = await s.personText(kimId, '김반장', '2026-11');
    expect(text, contains('11-10  점촌 긴급 보통인부 0.5인, 요성리 보통인부 0.5인'));
    expect(text, contains('합계 4인 · 748,000원 (4일)'));

    // 명부에서 빼도 지난 집계는 그대로
    await s.retireRoster(kim);
    expect((await s.roster()).any((r) => r.id == kim), isFalse);
    expect((await s.yearByPayee('2026')).firstWhere((y) => y.name == '김반장').qtyTotal, 7);
    // 월말 결제에도 같은 숫자
    expect((await s.monthPayments('2026-11')).firstWhere((x) => x.name == '김반장').total, 4 * 187000);
  });

  test('관급자재 배정 → 사용·남은량 (명부에서 이 현장 배정량 입력)', () async {
    final s = Store(MemoryDb(), device: 'phone');
    final ys = await s.receive('요성리', '공사', '2026-11-02');
    final rmc = await s.saveRoster(kind: '자재', payee: '가은레미콘', item: '레미콘', spec: '25-21-08', unit: '㎥', unitPrice: 98000);
    await s.setAllocation(ys, '레미콘', '25-21-08', '㎥', '180', '도급자관급');
    await s.addFromRoster(ys, '2026-11-06', [(rmc, '5.5')]);
    await s.addFromRoster(ys, '2026-11-13', [(rmc, '6')]);
    var a = (await s.allocations(ys))['레미콘|25-21-08']!;
    expect([a.supply, a.alloc, a.used], ['도급자관급', 180, 11.5]);
    await s.setAllocation(ys, '레미콘', '25-21-08', '㎥', '170', '도급자관급'); // 고치면 덮어씀
    a = (await s.allocations(ys))['레미콘|25-21-08']!;
    expect([(await s.db.all('allocation')).length, a.alloc], [1, 170]);
  });

  test('공종 추가 → 측점으로 시공 연장 → 공정률', () async {
    final s = Store(MemoryDb(), device: 'phone');
    final ys = await s.receive('요성리', '공사', '2026-11-02');
    final wt = await s.addWorkType(ys, 'U형 개거', '250', channel: true);
    await s.addProgressSta(ys, '2026-11-09', wt, 'No.0', 'No.0+12');
    await s.addProgressSta(ys, '2026-11-10', wt, 'No.0+12', 'No.1+4');
    final w = (await s.workProgress(ys, workDate: '2026-11-10')).single;
    expect([w.done, w.design, w.today.length], [24, 250, 1]);
    expect(w.rate, closeTo(0.096, 1e-9));
    expect(() => s.addProgressSta(ys, '2026-11-11', wt, 'No.2', 'No.1'), throwsA(isA<StoreError>()));
  });

  test('진행 중 공사의 밀린 일지: 시작일 이후 평일 중 일지 없는 날', () async {
    final s = Store(MemoryDb(), device: 'phone');
    final a = await s.receive('난간기둥보수', '공사', '2026-11-09');
    await s.proceed(a, plannedStart: '2026-11-11');
    await s.markNoWork(a, '2026-11-12'); // 비 → 일지 있음
    await s.setLogContent(a, '2026-11-16', '페인트');
    // 11/17(화) 기준: 11/11 수, 11/13 금 이 밀림 (11/12 비, 11/14·15 주말, 11/16 씀)
    expect(await s.missingLogDays(a, '2026-11-17'), ['2026-11-11', '2026-11-13']);
  });
}
