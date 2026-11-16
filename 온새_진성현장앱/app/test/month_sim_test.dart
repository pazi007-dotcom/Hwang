// 한 달 실사용 시뮬레이션 (2026년 11월). 폰 코드 + 실제 집 PC 서버.
// 실행: 서버를 `python -m jinsung.api --db <파일> --port 8765` 로 띄운 뒤
//   flutter test --dart-define=JINSUNG_SERVER=http://127.0.0.1:8765 --dart-define=SIM_OUT=<json> test/month_sim_test.dart
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:jinsung_app/ledger.dart';
import 'package:jinsung_app/row_db.dart';
import 'package:jinsung_app/store.dart';
import 'package:jinsung_app/sync.dart';

const server = String.fromEnvironment('JINSUNG_SERVER');
const outPath = String.fromEnvironment('SIM_OUT');
final log = <String>[];
final problems = <String>[];
void say(String s) => log.add(s);
void problem(String s) {
  problems.add(s);
  log.add('  ⚠ $s');
}

Future<T?> tryDo<T>(String what, Future<T> Function() f) async {
  try {
    return await f();
  } on StoreError catch (e) {
    say('  → 거부: $what — ${e.message}');
    return null;
  }
}

void main() {
  test('2026년 11월 한 달', () async {
    // 시계: 입력하는 '순간'(기록 시각)을 시나리오에 맞춰 바꾼다. 작업일은 따로 고른다.
    var clock = DateTime.utc(2026, 11, 2, 0);
    final db = MemoryDb();
    final phone = Store(db, device: 'phone', clock: () => clock);
    final link = ServerLink(server);
    Future<void> at(int day, int hour) async => clock = DateTime.utc(2026, 11, day, hour - 9);
    Future<SyncResult> sync(String when) async {
      final r = await link.sync(phone);
      say('  [맞추기 $when] $r');
      return r;
    }

    // ── 11/2 큰 공사 낙찰 → 접수 → 진행(시작 예정 11/3)
    await at(2, 9);
    say('11/2 요성리 낙찰 접수, 시작 예정 11/3');
    final ys = await phone.receive('요성리 용배수로 개체공사', '입찰', '2026-11-02',
        instructions: 'U형 개거 1.0×1.0 L=250m', contactName: '문경시 담당', contactPhone: '054-550-0000');
    await phone.proceed(ys, plannedStart: '2026-11-03');
    await sync('11/2 저녁');
    final tasks = (await phone.db.all('site_task')).where((t) => t['site_id'] == ys).toList();
    say('  발주·체크: ${tasks.length}건 (서버에서 내려옴: ${tasks.where((t) => t['source'] == '온새 제안').length}건)');
    if (tasks.where((t) => t['source'] == '온새 제안').isEmpty) problem('시작 예정일을 넣었는데 발주·체크 일정이 안 생김');

    // ── 평일 작업 (비 오는 날 제외)
    final rain = {9, 19};
    final pours = {6: 5.5, 13: 6.0, 20: 6.5, 27: 5.0};
    for (var d = 3; d <= 28; d++) {
      final wd = DateTime(2026, 11, d).weekday;
      if (wd == DateTime.sunday) continue;
      await at(d, 18);
      final date = '2026-11-${d.toString().padLeft(2, '0')}';
      if (rain.contains(d)) {
        await phone.markNoWork(ys, date);
        say('$date 비 → 작업 없음');
        continue;
      }
      if (d == 3) {
        // 첫날은 하나씩 입력
        await phone.addLine(siteId: ys, workDate: date, kind: '인력', item: '형틀목공', qty: 2, unit: '인', unitPrice: 230000, payee: '박목수 팀');
        await phone.addLine(siteId: ys, workDate: date, kind: '인력', item: '보통인부', qty: 1, unit: '인', unitPrice: 187000, payee: '김반장');
        await phone.addLine(siteId: ys, workDate: date, kind: '인력', item: '보통인부', qty: 1, unit: '인', unitPrice: 187000, payee: '이영수');
        await phone.addLine(siteId: ys, workDate: date, kind: '장비', item: '6W', qty: 1, unit: '일', unitPrice: 680000, payee: '대성중기');
        say('$date 첫날 4줄 직접 입력');
      } else if (d == 21) {
        continue; // 21일은 깜빡 → 23일 밤에 밀린 일지로 입력
      } else {
        final n = await phone.copyLastDay(ys, date);
        if (n == 0) problem('$date 어제와 같이 복사 안 됨');
      }
      if (pours.containsKey(d)) {
        await phone.addLine(siteId: ys, workDate: date, kind: '자재', item: '레미콘', spec: '25-21-08', qty: pours[d]!, unit: '㎥', unitPrice: 98000, payee: '가은레미콘');
        await phone.addLine(siteId: ys, workDate: date, kind: '장비', item: '펌프카', qty: 1, unit: '일', unitPrice: 750000, payee: '문경펌프');
      }
    }
    // 어제와 같이 복사가 레미콘·펌프카까지 끌고 왔는지 확인 (타설 다음 날)
    final cand = await phone.copyCandidates(ys, '2026-11-07');
    say('  11/7 어제와 같이 후보: ${cand.items.map((c) => '${c.line['item']}${c.pick ? '(켬)' : '(끔)'}').join(', ')}');
    final lines7 = await phone.linesOf(ys, '2026-11-07');
    final carried = lines7.where((l) => l['item'] == '레미콘' || l['item'] == '펌프카').length;
    if (carried > 0) problem('타설 다음 날(11/7) "어제와 같이"가 레미콘·펌프카 $carried줄까지 복사함 → 사람이 지워야 함');

    // ── 11/10 오전 긴급 A, 오후 요성리 (같은 사람·장비 반나절씩)
    await at(10, 8);
    say('11/10 08시 긴급 A 접수 → 오전 작업');
    final a = await phone.receive('점촌 배수로 긴급복구', '긴급', '2026-11-10', instructions: '토사 준설 30m');
    final w10 = await phone.overbook('2026-11-10', '인력', '보통인부', '김반장', '0.5');
    say('  저장 전 겹침 경고: ${w10 ?? '없음'}');
    await phone.addLine(siteId: a, workDate: '2026-11-10', kind: '인력', item: '보통인부', qty: '0.5', unit: '인', unitPrice: 187000, payee: '김반장');
    await phone.addLine(siteId: a, workDate: '2026-11-10', kind: '장비', item: '6W', qty: '0.5', unit: '일', unitPrice: 680000, payee: '대성중기');
    await phone.addLine(siteId: a, workDate: '2026-11-10', kind: '장비', item: '덤프 25톤', qty: 3, unit: '대', unitPrice: 282000, payee: '한빛운수');
    // 요성리 11/10 은 어제와 같이로 김반장 1, 6W 1 이 이미 들어가 있음 → 반나절로 고쳐야 함
    final ys10 = await phone.linesOf(ys, '2026-11-10');
    var dupKim = 0.0, dupW6 = 0.0;
    final kim = await phone.ensurePayee('김반장');
    for (final l in ys10) {
      if (l['item'] == '보통인부' && l['payee_id'] == kim) dupKim += num.parse(l['qty'] as String);
      if (l['item'] == '6W') dupW6 += num.parse(l['qty'] as String);
    }
    say('  요성리 11/10 에 이미 김반장 $dupKim공수, 6W $dupW6일 (어제와 같이)');
    for (final l in ys10) {
      if ((l['item'] == '보통인부' && l['payee_id'] == kim) || l['item'] == '6W') {
        await phone.editLine(l['id'] as String, qty: '0.5');
      }
    }
    say('  → 요성리 쪽 김반장·6W 를 0.5 로 고침');

    // ── 11/12 견적 B 접수 → 보류 → 11/20 취소(투입 없음 → 파기)
    await at(12, 10);
    final b = await phone.receive('모전 농로 포장 견적', '견적', '2026-11-12');
    await phone.hold(b, '발주처 예산 미확정');
    await at(20, 10);
    final rb = await phone.cancel(b, '발주 취소');
    say('11/12 견적 B 접수 → 보류 → 11/20 취소: $rb');
    if (rb != '파기') problem('투입 없는 견적 취소가 파기되지 않음');

    // ── 11/14 수의 C: 답사에 인부 1명 → 11/15 취소(투입 있음 → 보관)
    await at(14, 17);
    final c = await phone.receive('산양 소하천 수의 견적', '수의', '2026-11-14');
    final w14 = await phone.overbook('2026-11-14', '인력', '보통인부', '이영수', 1);
    say('  저장 전 겹침 경고: ${w14 ?? '없음'}');
    if (w14 == null) problem('11/14 이영수 하루 2공수인데 경고 없음');
    await phone.addLine(siteId: c, workDate: '2026-11-14', kind: '인력', item: '보통인부', qty: 1, unit: '인', unitPrice: 187000, payee: '이영수', note: '답사 동행');
    await at(15, 9);
    final rc = await phone.cancel(c, '계약 무산');
    say('11/14 수의 C 답사(인부 1) → 11/15 취소: $rc');
    if (rc != '보관') problem('투입 있는 수의 취소가 보관되지 않음');
    // 이영수는 11/14 에 요성리에도 1공수 → 하루 2공수
    final lee = await phone.ensurePayee('이영수');
    final ys14 = (await phone.linesOf(ys, '2026-11-14')).where((l) => l['payee_id'] == lee).length;
    expect(ys14, greaterThan(0));

    // ── 11/17 긴급 D(오전)·E(오후)
    await at(17, 8);
    final dd = await phone.receive('불암리 도로 유실 긴급', '긴급', '2026-11-17');
    final ee = await phone.receive('가은 배수관 막힘 긴급', '긴급', '2026-11-17');
    await phone.addLine(siteId: dd, workDate: '2026-11-17', kind: '장비', item: '3W', qty: '0.5', unit: '일', unitPrice: 560000, payee: '대성중기');
    await phone.addLine(siteId: ee, workDate: '2026-11-17', kind: '장비', item: '3W', qty: '0.5', unit: '일', unitPrice: 560000, payee: '대성중기');
    await phone.addLine(siteId: ee, workDate: '2026-11-17', kind: '자재', item: 'PE관', spec: 'D300', qty: 6, unit: 'm', unitPrice: 45000, payee: '문경관재');
    say('11/17 긴급 D 오전 3W 0.5, 긴급 E 오후 3W 0.5 + PE관 6m');
    final stE = (await phone.mustGet('site', ee))['status'];
    say('  긴급 E 상태: $stE');
    if (stE != '진행') problem('투입이 들어간 긴급 건이 접수 상태로 남음');

    // ── 11/23 밤: 21일 일지를 밀려서 입력
    await at(23, 22);
    final n21 = await phone.copyLastDay(ys, '2026-11-21');
    say('11/23 22시 밀린 11/21 일지 입력(어제와 같이 $n21줄)');
    final l21 = (await phone.db.all('work_log')).where((l) => l['site_id'] == ys && l['work_date'] == '2026-11-21');
    if (l21.isEmpty || !(l21.first['created_at'] as String).startsWith('2026-11-23')) problem('밀린 일지의 작업일/기록 시각이 섞임');

    // ── 중간 맞추기 + PC에서 같은 줄을 고침 → 충돌
    await sync('11/23 밤');
    final pc = Store(MemoryDb(), device: 'pc-web');
    await link.sync(pc);
    final target = (await pc.linesOf(ys, '2026-11-24')).isEmpty ? null : null;
    expect(target, isNull);
    await at(24, 18);
    // 11/24 일지는 아직 없음 → 11/20 장비 줄을 두 기기가 동시에 고침
    final l20 = (await phone.linesOf(ys, '2026-11-20')).firstWhere((l) => l['item'] == '펌프카');
    final pcRow = await pc.mustGet('input_line', l20['id'] as String);
    await pc.update('input_line', l20['id'] as String, pcRow['version'] as int, {'qty': '1', 'unit_price': 800000});
    await link.sync(pc);
    await phone.editLine(l20['id'] as String, unitPrice: 780000);
    final rs = await sync('11/24 (PC에서 펌프카 단가 800,000, 폰에서 780,000 으로 동시 수정)');
    final conflicts = await phone.db.openConflicts();
    say('  충돌 검토 ${conflicts.length}건 → 폰 값(780,000) 선택');
    if (rs.conflicts != 1) problem('동시 수정이 충돌로 잡히지 않음');
    if (conflicts.isNotEmpty) await phone.resolveConflict(conflicts.first, 'incoming');

    // ── 잘못 넣은 줄 지우기
    final l25 = await phone.linesOf(ys, '2026-11-25');
    await phone.deleteLine(l25.last['id'] as String);
    say('11/25 마지막 줄(${l25.last['item']}) 잘못 넣어 지움');

    // ── 지급
    await at(15, 12);
    await phone.recordPayment(await phone.ensurePayee('대성중기'), '2026-11', 5000000, '2026-11-15');
    say('11/15 대성중기 중간 지급 5,000,000');

    await at(30, 20);
    await sync('11/30 월말');

    // ── 월말 결과
    final pay = await phone.monthPayments('2026-11');
    final sites = await phone.monthSites('2026-11');
    say('');
    say('== 11월 결제 (폰) ==');
    for (final p in pay) {
      say('${p.name.padRight(8)} 이달 ${wonFmt(p.total).padLeft(11)}  지급 ${wonFmt(p.paid).padLeft(10)}  잔액 ${wonFmt(p.balance).padLeft(11)}  '
          '${p.manDays > 0 ? '${fmtQty(p.manDays)}공수 ' : ''}${p.equipDays > 0 ? '${fmtQty(p.equipDays)}일 ' : ''}${p.bySite.length}개 현장');
    }
    say('== 11월 현장별 (폰) ==');
    for (final s in sites) {
      say('${s.name}  ${wonFmt(s.total)}  작업 ${s.workDays}일 쉼 ${s.restDays.length}일  인력 ${fmtQty(s.manDays)}공수  장비 ${fmtQty(s.equipDays)}일  자재 ${s.materials}');
    }
    final ysT = sites.firstWhere((x) => x.name.startsWith('요성리'));
    final remi = ysT.materials['레미콘 25-21-08|㎥'] ?? 0;
    final pump = pay.firstWhere((p) => p.name == '문경펌프').equipDays;
    say('검산: 레미콘 ${fmtQty(remi)}㎥ (타설 4회 합 23㎥), 펌프카 ${fmtQty(pump)}일 (타설 4회 → 4일)');
    if (remi != 23) problem('레미콘 합계가 실제 타설량과 다름: $remi');
    if (pump != 4) problem('펌프카 일수가 실제와 다름: $pump');
    if (ysT.workDays != 21 || ysT.restDays.length != 2) problem('요성리 작업일 ${ysT.workDays}일·쉼 ${ysT.restDays.length}일 (실제 21일·2일)');
    // 손 계산 대조
    final hand = {'박목수 팀': 42 * 230000, '김반장': 21 * 187000, '이영수': 22 * 187000,
      '대성중기': (19.5 * 680000 + 0.5 * 680000 + 1 * 560000).round(), '문경펌프': 3 * 750000 + 780000,
      '가은레미콘': 23 * 98000, '한빛운수': 3 * 282000, '문경관재': 6 * 45000};
    for (final p in pay) {
      if (hand[p.name] != p.total) problem('${p.name} 앱 ${p.total} ≠ 손 계산 ${hand[p.name]}');
    }
    say('손 계산 대조: 받는 곳 ${hand.length}곳 모두 ${problems.isEmpty ? '일치' : '확인 필요'}');
    final text = await phone.paymentText('2026-11');
    say('');
    say('== 카톡 복사 문안 ==');
    say(text);

    if (outPath.isNotEmpty) {
      File(outPath).writeAsStringSync(jsonEncode({
        'log': log,
        'problems': problems,
        'pay': [for (final p in pay) {'name': p.name, 'total': p.total, 'paid': p.paid, 'balance': p.balance, 'bySite': p.bySite}],
        'sites': [for (final s in sites) {'name': s.name, 'total': s.total, 'byKind': s.byKind, 'days': s.days.length}],
        'grand': pay.fold<int>(0, (a, p) => a + p.total),
      }));
    }
  }, skip: server.isEmpty ? '서버 주소 없음' : false, timeout: const Timeout(Duration(minutes: 5)));
}
