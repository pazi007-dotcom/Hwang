// 명부 → 일지(명부에서 고르기) → 사람별 출역표 → 월·연간 집계.
import 'package:flutter_test/flutter_test.dart';
import 'package:jinsung_app/ledger.dart';
import 'package:jinsung_app/roster.dart';
import 'package:jinsung_app/row_db.dart';
import 'package:jinsung_app/store.dart';

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
}
