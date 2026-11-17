// 실제 집 PC 서버(파이썬)와 폰 코드가 맞물리는지 확인한다.
// 실행: 서버를 `python -m jinsung.api --demo --port 8765` 로 띄운 뒤
//       flutter test --dart-define=JINSUNG_SERVER=http://127.0.0.1:8765 test/server_link_test.dart
import 'package:flutter_test/flutter_test.dart';
import 'package:jinsung_app/payout.dart';
import 'package:jinsung_app/roster.dart';
import 'package:jinsung_app/row_db.dart';
import 'package:jinsung_app/store.dart';
import 'package:jinsung_app/sync.dart';

const server = String.fromEnvironment('JINSUNG_SERVER');

void main() {
  test('폰이 서버에서 받아 오고, 오프라인 입력을 올리고, 충돌을 남긴다', () async {
    final link = ServerLink(server);
    final phone = Store(MemoryDb(), device: 'phone-test');
    final first = await link.sync(phone);
    expect(first.received, greaterThan(10));
    final site = (await phone.db.all('site')).firstWhere((s) => s['site_type'] == '정식');
    final payee = (await phone.db.all('payee')).first;

    await phone.addInput(site['id'] as String, '2026-11-20', '인력', '보통인부', 3, payee['id'] as String);
    final up = await link.sync(phone);
    expect([up.sent, up.conflicts], [2, 0]);

    // 다른 폰이 같은 줄을 먼저 고친 경우
    final other = Store(MemoryDb(), device: 'phone-other');
    await link.sync(other);
    final line = (await other.db.all('input_line')).firstWhere((l) => l['qty'] == '3' && l['item'] == '보통인부');
    await other.update('input_line', line['id'] as String, line['version'] as int, {'qty': '4'});
    await link.sync(other);
    await phone.update('input_line', line['id'] as String, line['version'] as int, {'qty': '5'});
    final clash = await link.sync(phone);
    expect(clash.conflicts, 1);
    expect((await phone.mustGet('input_line', line['id'] as String))['qty'], '4');
    expect(((await phone.db.openConflicts()).single['incoming'] as Map)['qty'], '5');
  }, skip: server.isEmpty ? '서버 주소 없음 (JINSUNG_SERVER)' : false);

  test('폰에서 「대표님께 보고 메일 보내기」 → 집 PC가 보고서 메일을 만들어 보내고 결과가 폰으로', () async {
    final link = ServerLink(server);
    final phone = Store(MemoryDb(), device: 'phone-mail');
    await link.sync(phone);
    final site = await phone.receive('12월 시험 현장', '공사', '2026-12-01');
    final kim = await phone.saveRoster(kind: '인력', payee: '시험김씨', item: '보통인부', unit: '인', unitPrice: 200000);
    final eq = await phone.saveRoster(kind: '장비', payee: '시험중기', item: '6W', unit: '일', unitPrice: 680000);
    for (final d in ['2026-12-01', '2026-12-02', '2026-12-03']) {
      await phone.addFromRoster(site, d, [(kim, '1'), (eq, '1')]);
    }
    final kimPayee = (await phone.roster()).firstWhere((r) => r.id == kim).row['payee_id'] as String;
    await phone.setPayeeInfo(kimPayee, bank: '농협', account: '351-0000-0000-00');
    final send = (await phone.monthPayouts('2026-12')).fold<int>(0, (a, o) => a + o.transfer);
    final kimOut = (await phone.monthPayouts('2026-12')).firstWhere((o) => o.name == '시험김씨');
    expect([kimOut.p.total, kimOut.incomeTax, kimOut.localTax, kimOut.transfer], [600000, 4050, 400, 595550]);
    expect(send, greaterThan(600000)); // 데모 서버의 11월 미지급 이월 포함
    await phone.markPayRequested('2026-12', status: '보낼 요청');
    await link.sync(phone); // 올림 → 집 PC가 보냄
    await link.sync(phone); // 결과 받아 옴
    final r = (await phone.lastPayRequest('2026-12'))!;
    expect(r.status, '전송됨', reason: r.result);
    expect(r.result, contains('월말보고_2026-12.xlsx'));
  }, skip: server.isEmpty ? '서버 주소 없음 (JINSUNG_SERVER)' : false);

  test('집 PC가 만든 할 일(발주·체크)을 폰에서 체크할 수 있다', () async {
    final phone = Store(MemoryDb(), device: 'phone-task');
    await ServerLink(server).sync(phone);
    final t = (await phone.db.all('site_task')).firstWhere((r) => r['done'] != 1);
    expect(t['version'], isNotNull);
    await phone.checkTask(t['id'] as String, '2026-11-16');
    expect((await phone.mustGet('site_task', t['id'] as String))['done'], 1);
    final up = await ServerLink(server).sync(phone);
    expect(up.conflicts, 0);
  }, skip: server.isEmpty ? '서버 주소 없음 (JINSUNG_SERVER)' : false);
}
