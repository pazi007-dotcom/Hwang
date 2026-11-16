// 월말 이체 목록: 작업자는 사람마다 따로(일당 원천세), 장비 업체는 부가세 별도면 더해서. 보낸 뒤 이월이 0이 되는지.
import 'package:flutter_test/flutter_test.dart';
import 'package:jinsung_app/ledger.dart';
import 'package:jinsung_app/payout.dart';
import 'package:jinsung_app/roster.dart';
import 'package:jinsung_app/row_db.dart';
import 'package:jinsung_app/store.dart';

void main() {
  test('일당 소득세 계산', () {
    expect(dailyIncomeTax(150000), 0);
    expect(dailyIncomeTax(187000), 999); // 37,000 × 6% × 45%
    expect(dailyIncomeTax(230000), 2160);
    expect(dailyIncomeTax(93500), 0);
  });

  test('11월 이체 목록 → 보냄 → 12월 이월 0', () async {
    final s = Store(MemoryDb(), device: 'phone');
    final ys = await s.receive('요성리', '공사', '2026-11-01');
    final em = await s.receive('점촌 긴급', '긴급', '2026-11-10');
    final kim = await s.saveRoster(kind: '인력', payee: '김반장', item: '보통인부', unit: '인', unitPrice: 187000);
    final lee = await s.saveRoster(kind: '인력', payee: '이영수', item: '보통인부', unit: '인', unitPrice: 187000);
    final pk1 = await s.saveRoster(kind: '인력', payee: '박목수', item: '형틀목공', unit: '인', unitPrice: 230000);
    final pk2 = await s.saveRoster(kind: '인력', payee: '정목수', item: '형틀목공', unit: '인', unitPrice: 230000);
    final w6 = await s.saveRoster(kind: '장비', payee: '대성중기', item: '6W', unit: '일', unitPrice: 680000);
    final dump = await s.saveRoster(kind: '장비', payee: '한빛운수', item: '덤프 25톤', unit: '대', unitPrice: 282000);

    final days = [for (var d = 2; d <= 30; d++) DateTime(2026, 11, d)]
        .where((d) => d.weekday <= 5 && d.day != 10)
        .map((d) => '2026-11-${d.day.toString().padLeft(2, '0')}')
        .toList(); // 20일
    expect(days.length, 20);
    for (final d in days) {
      await s.addFromRoster(ys, d, [(kim, '1'), (lee, '1'), (pk1, '1'), (pk2, '1'), (w6, '1')]);
    }
    // 11/10: 이영수 오전 긴급 0.5 + 오후 요성리 0.5 → 하루 일당 187,000 (세금은 하루로 한 번)
    await s.addFromRoster(em, '2026-11-10', [(lee, '0.5'), (dump, '3')]);
    await s.addFromRoster(ys, '2026-11-10', [(lee, '0.5'), (kim, '1')]);

    final payeeOf = {for (final r in await s.roster()) r.payeeName: r.row['payee_id'] as String};
    await s.setPayeeInfo(payeeOf['김반장']!, bank: '농협', account: '351-1111-2222-33');
    await s.setPayeeInfo(payeeOf['대성중기']!, bank: '국민', account: '123-45-678', holder: '대성중기(주)', rule: '부가세별도');

    final list = {for (final o in await s.monthPayouts('2026-11')) o.name: o};
    // 사람마다 한 건씩: 작업자 4명 + 장비 2곳
    expect(list.length, 6);
    expect([for (final o in list.values) o.group], ['작업자', '작업자', '작업자', '작업자', '장비', '장비']);

    final k = list['김반장']!; // 21일 × 187,000
    expect([k.p.total, k.workDays, k.incomeTax, k.localTax, k.transfer], [3927000, 21, 20970, 2090, 3927000 - 23060]);
    expect(k.accountText, '농협 351-1111-2222-33');
    final l = list['이영수']!; // 하루 0.5+0.5 = 187,000 → 21일
    expect([l.p.total, l.workDays, l.incomeTax], [3927000, 21, 20970]);
    final p = list['박목수']!; // 20일 × 230,000, 하루 2,160
    expect([p.p.total, p.incomeTax, p.localTax, p.transfer], [4600000, 43200, 4320, 4600000 - 47520]);
    expect(p.hasAccount, isFalse);
    final d = list['대성중기']!; // 20일 × 680,000 + 부가세
    expect([d.p.total, d.vat, d.incomeTax, d.transfer], [13600000, 1360000, 0, 14960000]);
    expect(d.accountText, '국민 123-45-678 (대성중기(주))');
    expect(list['한빛운수']!.transfer, 846000);

    final text = await s.payoutText('2026-11');
    expect(text, contains('── 작업자 4명'));
    expect(text, contains('김반장  농협 351-1111-2222-33  3,903,940원'));
    expect(text, contains('박목수  계좌 없음  4,552,480원'));
    expect(text, contains('대성중기  국민 123-45-678 (대성중기(주))  14,960,000원'));

    // 김반장·대성중기 보냄 → 12월 이월 0. 이영수는 일부만(1,000,000) → 일지 기준 2,927,000 남음
    await s.recordPayout(k, '2026-11', '2026-12-05');
    await s.recordPayout(d, '2026-11', '2026-12-05');
    await s.recordPayment(payeeOf['이영수']!, '2026-11', 1000000, '2026-12-05');
    final dec = {for (final p in await s.monthPayments('2026-12')) p.name: p};
    expect(dec['김반장']?.balance ?? 0, 0);
    expect(dec['대성중기']?.balance ?? 0, 0);
    expect(dec['이영수']!.carry, 2927000);
    final nov = {for (final o in await s.monthPayouts('2026-11')) o.name: o};
    expect([nov['김반장']!.p.balance, nov['김반장']!.transfer], [0, 0]); // 보낸 뒤 11월 목록에서 0
    expect(nov['대성중기']!.transfer, 0);
    expect(nov['이영수']!.transfer, 2927000 - 23060); // 남은 일지 금액 − 아직 안 뗀 세금
  });
}
