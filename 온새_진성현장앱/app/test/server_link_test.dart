// 실제 집 PC 서버(파이썬)와 폰 코드가 맞물리는지 확인한다.
// 실행: 서버를 `python -m jinsung.api --demo --port 8765` 로 띄운 뒤
//       flutter test --dart-define=JINSUNG_SERVER=http://127.0.0.1:8765 test/server_link_test.dart
import 'package:flutter_test/flutter_test.dart';
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
}
