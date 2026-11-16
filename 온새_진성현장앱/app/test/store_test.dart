// 폰 저장 규칙·동기화 (설계안 3장, 12장 검증 계획). 서버 tests/ 와 같은 사례를 폰 코드로 확인한다.
import 'package:flutter_test/flutter_test.dart';
import 'package:jinsung_app/ledger.dart';
import 'package:jinsung_app/row_db.dart';
import 'package:jinsung_app/stations.dart';
import 'package:jinsung_app/store.dart';
import 'package:jinsung_app/sync.dart';

Future<({Store pc, Store phone, String site, String payee})> pair() async {
  final pc = Store(MemoryDb(), device: 'pc');
  final phone = Store(MemoryDb(), device: 'phone');
  final site = await pc.createSite('요성리 용배수로');
  final payee = await pc.insert('payee', {'name': '대성중기', 'payee_type': '업체'});
  await pc.insert('rate', {
    'kind': '장비', 'item': '덤프 25톤', 'spec': '', 'unit': '대', 'unit_price': 282000,
    'payee_id': null, 'valid_from': '2026-01-01', 'is_draft': 0,
  });
  await sync(phone, pc);
  return (pc: pc, phone: phone, site: site, payee: payee);
}

/// 폰 ↔ PC (둘 다 같은 규칙 코드). 실제 서버와의 연결은 server_link_test.dart 에서 확인한다.
Future<SyncResult> sync(Store client, Store server) => syncWith(
    client,
    (changes) async => [for (final c in changes) await server.applyChange(c)],
    (since) async => (await server.db.changesSince(since)).where((c) => c['device'] != client.device).toList());

Future<Map<String, Rec>> rows(Store s, String table) async =>
    {for (final r in await s.db.all(table)) r['id'] as String: r};

void main() {
  group('날짜', () {
    test('작업일은 날짜만 받는다', () {
      expect(parseWorkDate('2026-11-12'), '2026-11-12');
      expect(() => parseWorkDate('2026-11-12T21:10'), throwsA(isA<StoreError>()));
      expect(() => parseWorkDate('2026-02-30'), throwsA(isA<StoreError>()));
      expect(parseWorkDate('2028-02-29'), '2028-02-29');
    });

    test('12·13일 일지를 14일 밤에 몰아 입력해도 각자의 날짜에 들어간다', () async {
      final p = await pair();
      final late = Store(p.phone.db, device: 'phone', clock: () => DateTime.utc(2026, 11, 14, 12, 10));
      await late.addInput(p.site, '2026-11-12', '장비', '덤프 25톤', 3, p.payee);
      await late.addInput(p.site, '2026-11-13', '장비', '덤프 25톤', 2, p.payee);
      final logs = await p.phone.db.all('work_log');
      expect(logs.map((l) => l['work_date']).toSet(), {'2026-11-12', '2026-11-13'});
      expect(logs.first['created_at'], '2026-11-14T21:10:00+09:00'); // 기록 시각은 따로
    });

    test('월말 자정 직후(한국 12월 1일 0시 10분)에 입력해도 고른 작업일 그대로', () async {
      final p = await pair();
      final s = Store(p.phone.db, device: 'phone', clock: () => DateTime.utc(2026, 11, 30, 15, 10));
      await s.addInput(p.site, '2026-11-30', '장비', '덤프 25톤', 1, p.payee);
      expect(await s.monthCost(p.site, '2026-11'), 282000);
      expect(await s.monthCost(p.site, '2026-12'), 0);
      expect(workDateOf(DateTime(2026, 11, 30, 23, 59)), '2026-11-30');
    });
  });

  group('저장 규칙', () {
    test('현장 없이는 저장하지 않는다 · 단가는 기준 정보에서', () async {
      final p = await pair();
      expect(() => p.phone.addInput(null, '2026-11-12', '장비', '덤프 25톤', 1, p.payee),
          throwsA(isA<StoreError>()));
      final id = await p.phone.addInput(p.site, '2026-11-12', '장비', '덤프 25톤', '0.5', p.payee);
      final line = await p.phone.mustGet('input_line', id);
      expect([line['qty'], line['unit'], line['amount']], ['0.5', '대', 141000]);
      expect(() => p.phone.addInput(p.site, '2026-11-12', '장비', '펌프카', 1, p.payee),
          throwsA(isA<StoreError>()));
    });

    test('마감된 달은 사유가 있어야 고친다', () async {
      final p = await pair();
      await p.phone.db.put('month_lock', {'id': '2026-11', 'month': '2026-11'});
      expect(() => p.phone.addInput(p.site, '2026-11-12', '장비', '덤프 25톤', 1, p.payee),
          throwsA(isA<LockedError>()));
      await p.phone.addInput(p.site, '2026-11-12', '장비', '덤프 25톤', 1, p.payee, reason: '누락분');
    });

    test('작업 없음 일지 · 긴급 현장', () async {
      final p = await pair();
      final log = await p.phone.markNoWork(p.site, '2026-11-15');
      expect((await p.phone.mustGet('work_log', log))['no_work'], 1);
    });
  });

  group('접수', () {
    test('접수하면 그날 일지와 확인사항이 함께 생긴다', () async {
      final p = await pair();
      final e = await p.phone.receive('점촌 긴급복구', '긴급', '2026-11-16',
          instructions: '준설 30m', contactName: '김주무관', contactPhone: '054-000-0000');
      final site = await p.phone.mustGet('site', e);
      expect([site['status'], site['job_type'], site['site_type']], ['접수', '긴급', '긴급수의']);
      final log = (await p.phone.db.all('work_log')).single;
      expect(log['note'], '[접수·긴급] 점촌 긴급복구 — 준설 30m');
      expect(log['content'], isNull); // 작업 내용 칸은 소장 몫
      expect((await p.phone.db.all('site_task')).length, 4);
      expect((await p.phone.dueTasks('2026-11-17', siteId: e)).first['when'], '1일 지남');
      await sync(p.phone, p.pc);
      expect((await p.pc.db.all('contact')).single['name'], '김주무관');
    });

    test('보류는 보관, 투입 없는 취소는 파기, 투입 있는 취소는 보관', () async {
      final p = await pair();
      final a = await p.phone.receive('견적 A', '견적', '2026-11-16');
      await p.phone.hold(a, '예산 미확정');
      expect(await p.phone.dueTasks('2026-11-20'), isEmpty); // 보류 건은 알리지 않는다
      await p.phone.proceed(a, plannedStart: '2026-12-01');
      expect((await p.phone.mustGet('site', a))['planned_start'], '2026-12-01');
      expect(await p.phone.cancel(a, '발주 취소'), '파기');
      expect(await p.phone.db.all('work_log'), isEmpty);
      expect((await p.phone.db.all('site')).length, 1);

      final b = await p.phone.receive('답사만 한 건', '수의', '2026-11-16');
      await p.phone.addInput(b, '2026-11-16', '장비', '덤프 25톤', 1, p.payee);
      expect(await p.phone.cancel(b, '계약 무산'), '보관');
      expect(() => p.phone.addInput(b, '2026-11-17', '장비', '덤프 25톤', 1, p.payee),
          throwsA(isA<StoreError>()));
      expect(await p.phone.monthCost(b, '2026-11'), 282000); // 돈은 집계에 남는다
    });

    test('체크하면 할 일에서 빠진다', () async {
      final p = await pair();
      final e = await p.phone.receive('긴급 B', '긴급', '2026-11-16');
      final first = (await p.phone.dueTasks('2026-11-16', siteId: e)).first;
      await p.phone.checkTask(first['id'] as String, '2026-11-16');
      expect((await p.phone.dueTasks('2026-11-16', siteId: e)).length, 3);
    });
  });

  group('동기화', () {
    test('오프라인 입력이 PC로 올라가고, 두 번 해도 그대로', () async {
      final p = await pair();
      await p.phone.addInput(p.site, '2026-11-12', '장비', '덤프 25톤', 3, p.payee);
      final r = await sync(p.phone, p.pc);
      expect([r.sent, r.conflicts], [2, 0]);
      expect(await rows(p.pc, 'input_line'), await rows(p.phone, 'input_line'));
      final again = await sync(p.phone, p.pc);
      expect([again.sent, again.received, again.conflicts], [0, 0, 0]);
    });

    test('두 기기가 같은 줄을 고치면 두 값이 모두 남는다', () async {
      final p = await pair();
      final line = await p.phone.addInput(p.site, '2026-11-12', '장비', '덤프 25톤', 3, p.payee);
      await sync(p.phone, p.pc);
      await p.pc.update('input_line', line, 1, {'qty': '4'});
      await p.phone.update('input_line', line, 1, {'qty': '5'});
      expect((await sync(p.phone, p.pc)).conflicts, 1);
      expect((await p.pc.mustGet('input_line', line))['qty'], '4');
      expect((await p.phone.mustGet('input_line', line))['qty'], '4');
      final c = await p.phone.db.openConflicts();
      expect((c.single['incoming'] as Map)['qty'], '5');
      await p.phone.resolveConflict(c.single, 'incoming');
      await sync(p.phone, p.pc);
      final pcLine = await p.pc.mustGet('input_line', line);
      expect([pcLine['qty'], pcLine['amount']], ['5', 5 * 282000]);
      expect(await p.phone.db.openConflicts(), isEmpty);
    });

    test('같은 날 일지를 따로 만들어도 하나로 이어진다', () async {
      final p = await pair();
      await p.pc.addInput(p.site, '2026-11-13', '장비', '덤프 25톤', 1, p.payee);
      await p.phone.addInput(p.site, '2026-11-13', '장비', '덤프 25톤', 2, p.payee);
      await sync(p.phone, p.pc);
      for (final s in [p.pc, p.phone]) {
        final logs = await s.db.all('work_log');
        final lines = await s.db.all('input_line');
        expect(logs.length, 1);
        expect(lines.map((l) => l['qty']).toList()..sort(), ['1', '2']);
        expect(lines.every((l) => l['log_id'] == logs.single['id']), isTrue);
      }
    });

    test('삭제와 수정이 겹치면 잃지 않고 충돌로 남는다', () async {
      final p = await pair();
      final line = await p.phone.addInput(p.site, '2026-11-12', '장비', '덤프 25톤', 3, p.payee);
      await sync(p.phone, p.pc);
      await p.pc.update('input_line', line, 1, {'qty': '4'});
      await p.phone.delete('input_line', line, 1, reason: '잘못 입력');
      expect((await sync(p.phone, p.pc)).conflicts, 1);
      expect((await p.phone.mustGet('input_line', line))['qty'], '4');
    });
  });

  test('측점', () {
    expect(parseSta('No.2+10'), 50);
    expect(parseSta('no 12'), 240);
    expect(parseSta('NO.0+5.8'), 5.8);
    expect(formatSta(50), 'No.2+10');
    expect(formatSta(240), 'No.12');
    expect(() => parseSta('No.2+25'), throwsA(isA<StoreError>()));
  });

  test('자재는 단가 없이 수량만 넣을 수 있다 (금액 0 → 보고서 공란)', () async {
    final s = Store(MemoryDb(), device: 'phone');
    final site = await s.receive('요성리', '공사', '2026-11-01');
    await s.addLine(siteId: site, workDate: '2026-11-14', kind: '자재', item: '모래', qty: 5, unit: '㎥', unitPrice: '', payee: '문경골재');
    expect((await s.db.all('input_line')).single['amount'], 0);
    expect(() => s.addLine(siteId: site, workDate: '2026-11-14', kind: '인력', item: '보통인부', qty: 1, unit: '인', unitPrice: '', payee: '김반장'),
        throwsA(isA<StoreError>()));
  });
}
