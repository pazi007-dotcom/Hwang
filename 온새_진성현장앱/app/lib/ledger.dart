/// 업무일지 장부: 투입 한 줄 넣기·고치기·지우기, 추천값, 월 결제·월 집계 (폰 안에서 완결).
///
/// 원칙
/// - 기준 정보(단가표·업체 목록)가 없어도 바로 입력된다. 처음 쓰는 업체·항목은 저장하는 순간 등록된다.
/// - 단가는 "이 받는 곳에 이 항목을 마지막으로 넣은 값" → "기준 단가" → "이 항목 마지막 값" 순으로 미리 채운다.
/// - 값의 주인은 업무일지 한 줄. 결제·집계는 그 줄을 더할 뿐이다(따로 입력하는 숫자 없음).
library;

import 'roster.dart';
import 'row_db.dart';
import 'store.dart';

const defaultUnit = {'인력': '인', '장비': '일', '자재': '㎥', '외주': '식'};

String _norm(String s) => s.replaceAll(RegExp(r'\s+|\(주\)|주식회사|㈜'), '');

class PayeeTotal {
  PayeeTotal(this.payeeId, this.name);
  final String payeeId;
  final String name;
  final Set<String> kinds = {};
  final Map<String, int> bySite = {};
  int total = 0;
  int carry = 0; // 지난달까지 미지급
  int paid = 0; // 이달 청구분에 대해 지급한 금액
  int lines = 0;
  num manDays = 0; // 인력 공수
  num equipDays = 0; // 장비 일수
  final Map<String, num> equipment = {}; // '덤프 25톤|대' → 수량
  int get balance => total + carry - paid;
}

class SiteTotal {
  SiteTotal(this.siteId, this.name);
  final String siteId;
  final String name;
  final Map<String, int> byKind = {for (final k in kinds) k: 0};
  final Set<String> days = {}; // 일지가 있는 날 (접수만 한 날 포함)
  final Set<String> restDays = {}; // 그중 '작업 없음'(비 등)
  final Set<String> inputDays = {}; // 투입이 있었던 날 = 작업한 날
  num manDays = 0;
  num equipDays = 0;
  final Map<String, num> materials = {}; // '레미콘 25-21-08|㎥' → 수량
  final Map<String, num> equipment = {}; // '덤프 25톤|대' → 수량 (일 단위가 아닌 장비도 보이게)
  int get workDays => inputDays.length;
  int get total => byKind.values.fold(0, (a, b) => a + b);
}

extension Ledger on Store {
  // ---------- 받는 곳 ----------
  Future<String> ensurePayee(String name, {String kind = '인력'}) async {
    final n = name.trim();
    if (n.isEmpty) throw StoreError('받는 곳(사람·업체)을 적어 주세요.');
    for (final p in await db.all('payee')) {
      if (_norm(p['name'] as String) == _norm(n)) return p['id'] as String;
    }
    return insert('payee', {'name': n, 'payee_type': kind == '인력' ? '개인' : '업체'});
  }

  // ---------- 한 줄 넣기 ----------
  /// 기준 정보가 없어도 저장된다. 단가를 처음 쓰는 항목이면 기준 단가로도 남긴다.
  Future<String> addLine({
    required String? siteId,
    required String workDate,
    required String kind,
    required String item,
    required Object qty,
    required String unit,
    required Object unitPrice,
    required String payee,
    String spec = '',
    String? note,
    String? workTypeId,
    String? staFrom,
    String? staTo,
    String? reason,
  }) async {
    if (!kinds.contains(kind)) throw StoreError('종류는 $kinds 중 하나입니다.');
    final it = item.trim();
    if (it.isEmpty) throw StoreError('항목(직종·장비·자재 이름)을 적어 주세요.');
    final u = unit.trim().isEmpty ? defaultUnit[kind]! : unit.trim();
    final price = int.tryParse(unitPrice.toString().replaceAll(',', '').trim());
    if (price == null || price < 0) throw StoreError('단가를 숫자로 적어 주세요. (0원도 됩니다)');
    final q = cleanQty(qty);
    final logId = await logFor(siteId, workDate, reason: reason);
    final wd = (await mustGet('work_log', logId))['work_date'] as String;
    final payeeId = await ensurePayee(payee, kind: kind);
    final site = await mustGet('site', siteId!);
    if (site['status'] == '접수') {
      // 투입이 들어왔다 = 실제로 일을 시작했다 → 진행 (긴급 건은 접수 당일 바로 일한다)
      await update('site', siteId, site['version'] as int, {'status': '진행'});
    }
    final sp = spec.trim();
    if (await findRate(kind, it, sp, null, wd) == null) {
      await insert('rate', {
        'kind': kind, 'item': it, 'spec': sp, 'unit': u, 'unit_price': price, 'payee_id': null,
        'valid_from': wd, 'is_draft': 0,
      });
    }
    await learnRoster(kind, payeeId, it, sp, u, price);
    return insert('input_line', {
      'log_id': logId, 'kind': kind, 'item': it, 'spec': sp, 'qty': q, 'unit': u,
      'unit_price': price, 'amount': won(q, price), 'payee_id': payeeId,
      'work_type_id': workTypeId, 'sta_from': staFrom, 'sta_to': staTo, 'share_group': null,
      'note': (note == null || note.trim().isEmpty) ? null : note.trim(),
    });
  }

  /// 한 줄 고치기. 마감된 달이면 사유가 있어야 한다.
  Future<void> editLine(String lineId, {Object? qty, Object? unitPrice, String? payee, String? item,
      String? spec, String? unit, String? note, String? reason}) async {
    final row = await mustGet('input_line', lineId);
    final ch = <String, dynamic>{};
    if (qty != null) ch['qty'] = cleanQty(qty);
    if (unitPrice != null) {
      final p = int.tryParse(unitPrice.toString().replaceAll(',', '').trim());
      if (p == null || p < 0) throw StoreError('단가를 숫자로 적어 주세요.');
      ch['unit_price'] = p;
    }
    if (payee != null) ch['payee_id'] = await ensurePayee(payee, kind: row['kind'] as String);
    if (item != null && item.trim().isNotEmpty) ch['item'] = item.trim();
    if (spec != null) ch['spec'] = spec.trim();
    if (unit != null && unit.trim().isNotEmpty) ch['unit'] = unit.trim();
    if (note != null) ch['note'] = note.trim().isEmpty ? null : note.trim();
    if (ch.containsKey('qty') && !ch.containsKey('unit_price')) ch['unit_price'] = row['unit_price'];
    if (ch.isEmpty) return;
    await update('input_line', lineId, row['version'] as int, ch, reason: reason);
  }

  Future<void> deleteLine(String lineId, {String? reason}) async {
    final row = await mustGet('input_line', lineId);
    await delete('input_line', lineId, row['version'] as int, reason: reason ?? '일지에서 삭제');
  }

  Future<void> setWeather(String siteId, String workDate, String weather) async {
    final logId = await logFor(siteId, workDate);
    final row = await mustGet('work_log', logId);
    await update('work_log', logId, row['version'] as int, {'weather': weather});
  }

  Future<void> setLogContent(String siteId, String workDate, String content) async {
    final logId = await logFor(siteId, workDate);
    final row = await mustGet('work_log', logId);
    await update('work_log', logId, row['version'] as int, {'content': content.trim()});
  }

  // ---------- 추천값 ----------
  /// 이 종류로 자주 쓴 항목 (최근 순).
  Future<List<String>> recentItems(String kind) async {
    final seen = <String, String>{};
    final lines = (await db.all('input_line')).where((l) => l['kind'] == kind).toList()
      ..sort((a, b) => (b['created_at'] as String).compareTo(a['created_at'] as String));
    for (final l in lines) {
      seen.putIfAbsent(l['item'] as String, () => l['created_at'] as String);
    }
    for (final r in await db.all('rate')) {
      if (r['kind'] == kind) seen.putIfAbsent(r['item'] as String, () => '');
    }
    return seen.keys.toList();
  }

  /// 이 항목에 자주 쓴 받는 곳 (최근 순). 항목이 비면 이 종류 전체.
  Future<List<String>> recentPayees(String kind, {String? item}) async {
    final names = {for (final p in await db.all('payee')) p['id']: p['name'] as String};
    final lines = (await db.all('input_line'))
        .where((l) => l['kind'] == kind && (item == null || item.isEmpty || l['item'] == item))
        .toList()
      ..sort((a, b) => (b['created_at'] as String).compareTo(a['created_at'] as String));
    final out = <String>[];
    for (final l in lines) {
      final n = names[l['payee_id']];
      if (n != null && !out.contains(n)) out.add(n);
    }
    if (out.isEmpty && item != null && item.isNotEmpty) {
      return recentPayees(kind); // 처음 쓰는 항목이면 이 종류에 썼던 받는 곳
    }
    return out;
  }

  /// 단가·단위 추천: 이 받는 곳+항목의 마지막 값 → 기준 단가 → 이 항목의 마지막 값.
  Future<({int? price, String? unit, String? spec})> suggest(String kind, String item, String payee,
      String workDate) async {
    final it = item.trim();
    if (it.isEmpty) return (price: null, unit: null, spec: null);
    String? payeeId;
    for (final p in await db.all('payee')) {
      if (_norm(p['name'] as String) == _norm(payee)) payeeId = p['id'] as String;
    }
    final lines = (await db.all('input_line')).where((l) => l['kind'] == kind && l['item'] == it).toList()
      ..sort((a, b) => (b['created_at'] as String).compareTo(a['created_at'] as String));
    final mine = lines.where((l) => payeeId != null && l['payee_id'] == payeeId);
    if (mine.isNotEmpty) {
      final l = mine.first;
      return (price: l['unit_price'] as int, unit: l['unit'] as String, spec: l['spec'] as String?);
    }
    final rate = await findRate(kind, it, '', payeeId, workDate);
    if (rate != null) return (price: rate['unit_price'] as int, unit: rate['unit'] as String, spec: null);
    if (lines.isNotEmpty) {
      final l = lines.first;
      return (price: l['unit_price'] as int, unit: l['unit'] as String, spec: l['spec'] as String?);
    }
    return (price: null, unit: null, spec: null);
  }

  /// 어제와 같이: 이 현장의 가장 최근 일지(작업일 이전)에서 복사할 후보.
  /// 기본 선택: 인력은 켬, 장비는 그 전날에도 있었던(매일 쓰는) 것만 켬, 자재·외주는 끔.
  /// → 타설한 날의 레미콘·펌프카가 다음 날로 끌려가 쌓이는 일을 막는다.
  Future<({String? from, List<({Rec line, String payee, bool pick})> items})> copyCandidates(
      String siteId, String workDate) async {
    final logs = (await db.all('work_log'))
        .where((l) => l['site_id'] == siteId && (l['work_date'] as String).compareTo(workDate) < 0)
        .toList()
      ..sort((a, b) => (b['work_date'] as String).compareTo(a['work_date'] as String));
    final all = await db.all('input_line');
    final names = {for (final p in await db.all('payee')) p['id']: p['name'] as String};
    List<Rec> linesOf(Rec log) => all.where((l) => l['log_id'] == log['id']).toList()
      ..sort((a, b) => (a['created_at'] as String).compareTo(b['created_at'] as String));
    for (var i = 0; i < logs.length; i++) {
      final lines = linesOf(logs[i]);
      if (lines.isEmpty) continue;
      // 그 전 작업일(투입이 있는 날)
      List<Rec> before = const [];
      for (var j = i + 1; j < logs.length; j++) {
        final b = linesOf(logs[j]);
        if (b.isNotEmpty) {
          before = b;
          break;
        }
      }
      bool recurring(Rec l) => before.isEmpty ||
          before.any((b) => b['kind'] == l['kind'] && b['item'] == l['item'] && b['payee_id'] == l['payee_id']);
      return (
        from: logs[i]['work_date'] as String,
        items: [
          for (final l in lines)
            (
              line: l,
              payee: names[l['payee_id']] ?? '미지정',
              pick: l['kind'] == '인력' || (l['kind'] == '장비' && recurring(l)),
            ),
        ],
      );
    }
    return (from: null, items: <({Rec line, String payee, bool pick})>[]);
  }

  /// 고른 줄만 작업일로 복사한다.
  Future<int> copyLines(String siteId, String workDate, List<({Rec line, String payee, bool pick})> items,
      {String? reason}) async {
    var n = 0;
    for (final c in items.where((c) => c.pick)) {
      final l = c.line;
      await addLine(siteId: siteId, workDate: workDate, kind: l['kind'] as String,
          item: l['item'] as String, spec: (l['spec'] ?? '') as String, qty: l['qty'] as String,
          unit: l['unit'] as String, unitPrice: l['unit_price'] as int, payee: c.payee,
          workTypeId: l['work_type_id'] as String?, reason: reason);
      n++;
    }
    return n;
  }

  /// 예전 이름 유지(기본 선택만 복사).
  Future<int> copyLastDay(String siteId, String workDate) async {
    final c = await copyCandidates(siteId, workDate);
    return copyLines(siteId, workDate, c.items);
  }

  /// 겹침 확인: 같은 사람이 하루 1공수를 넘거나, 같은 업체 같은 장비가 하루 1일을 넘으면 알린다(막지는 않음).
  /// 하루 두세 현장을 뛰는 날 0.5 + 0.5 로 나눠야 할 것을 1 + 1 로 넣는 실수를 잡는다.
  Future<String?> overbook(String workDate, String kind, String item, String payee, Object qty,
      {String? excludeLineId}) async {
    if (kind != '인력' && kind != '장비') return null;
    final q = num.tryParse(qty.toString().trim());
    if (q == null) return null;
    String? payeeId;
    for (final p in await db.all('payee')) {
      if (_norm(p['name'] as String) == _norm(payee)) payeeId = p['id'] as String;
    }
    if (payeeId == null) return null;
    final logs = {for (final l in await db.all('work_log')) if (l['work_date'] == workDate) l['id']: l['site_id']};
    final sites = {for (final s in await db.all('site')) s['id']: s['name'] as String};
    num used = 0;
    final where = <String, num>{};
    for (final l in await db.all('input_line')) {
      if (!logs.containsKey(l['log_id']) || l['payee_id'] != payeeId || l['id'] == excludeLineId) continue;
      if (l['kind'] != kind) continue;
      if (kind == '장비' && (l['item'] != item || l['unit'] != '일')) continue;
      final v = num.parse(l['qty'] as String);
      used += v;
      final n = sites[logs[l['log_id']]] ?? '';
      where[n] = (where[n] ?? 0) + v;
    }
    final total = used + q;
    if (used == 0 || total <= 1) return null;
    final unitWord = kind == '인력' ? '공수' : '일';
    final w = where.entries.map((e) => '${e.key} ${fmtQty(e.value)}$unitWord').join(', ');
    return '$payee ${kind == '장비' ? '$item ' : ''}$workDate 에 이미 $w → 이번까지 하루 ${fmtQty(total)}$unitWord입니다. '
        '두 현장을 나눠 뛰었으면 0.5씩 넣으세요.${kind == '장비' ? ' (장비 2대면 그대로 저장)' : ''}';
  }

  // ---------- 월 결제·월 집계 ----------
  Future<List<Rec>> _monthLines(String month) async {
    final logs = {for (final l in await db.all('work_log')) l['id']: l};
    final out = <Rec>[];
    for (final l in await db.all('input_line')) {
      final log = logs[l['log_id']];
      if (log == null || !(log['work_date'] as String).startsWith(month)) continue;
      out.add({...l, 'work_date': log['work_date'], 'site_id': log['site_id']});
    }
    out.sort((a, b) {
      final d = (a['work_date'] as String).compareTo(b['work_date'] as String);
      return d != 0 ? d : (a['created_at'] as String).compareTo(b['created_at'] as String);
    });
    return out;
  }

  Future<List<Rec>> monthLinesAll(String month) => _monthLines(month);

  Future<List<Rec>> linesOfPayee(String payeeId, String month) async =>
      (await _monthLines(month)).where((l) => l['payee_id'] == payeeId).toList();

  /// 받는 곳 1곳 = 한 줄. 현장별 금액, 이월 미지급, 이달 지급, 잔액. 금액 큰 순.
  Future<List<PayeeTotal>> monthPayments(String month) async {
    final sites = {for (final s in await db.all('site')) s['id']: s['name'] as String};
    final payees = {for (final p in await db.all('payee')) p['id']: p['name'] as String};
    final out = <String, PayeeTotal>{};
    for (final l in await _monthLines(month)) {
      final id = l['payee_id'] as String;
      final p = out.putIfAbsent(id, () => PayeeTotal(id, payees[id] ?? '(지워진 받는 곳)'));
      final amt = l['amount'] as int;
      p.kinds.add(l['kind'] as String);
      p.bySite.update(sites[l['site_id']] ?? '(지워진 현장)', (v) => v + amt, ifAbsent: () => amt);
      p.total += amt;
      p.lines++;
      if (l['kind'] == '인력') p.manDays += num.parse(l['qty'] as String);
      if (l['kind'] == '장비' && l['unit'] == '일') p.equipDays += num.parse(l['qty'] as String);
      if (l['kind'] == '장비') {
        p.equipment.update('${l['item']}|${l['unit']}', (v) => v + num.parse(l['qty'] as String),
            ifAbsent: () => num.parse(l['qty'] as String));
      }
    }
    // 이월: 이전 달까지 투입 − 이전 달 청구분 지급
    final logs = {for (final l in await db.all('work_log')) l['id']: l['work_date'] as String};
    final billed = <String, int>{};
    for (final l in await db.all('input_line')) {
      final d = logs[l['log_id']];
      if (d != null && d.compareTo('$month-01') < 0) {
        billed.update(l['payee_id'] as String, (v) => v + (l['amount'] as int), ifAbsent: () => l['amount'] as int);
      }
    }
    final paidBefore = <String, int>{};
    final paidNow = <String, int>{};
    for (final p in await db.all('payment')) {
      final m = p['month'] as String;
      final target = m.compareTo(month) < 0 ? paidBefore : (m == month ? paidNow : null);
      // 정산액 = 보낸 돈 + 뗀 세금 − 더한 부가세 (일지 금액 기준)
      final settled = (p['amount'] as int) + ((p['deduct'] ?? 0) as int) - ((p['vat'] ?? 0) as int);
      target?.update(p['payee_id'] as String, (v) => v + settled, ifAbsent: () => settled);
    }
    for (final id in {...billed.keys}) {
      final carry = (billed[id] ?? 0) - (paidBefore[id] ?? 0);
      if (carry != 0) out.putIfAbsent(id, () => PayeeTotal(id, payees[id] ?? '(지워진 받는 곳)')).carry = carry;
    }
    for (final e in paidNow.entries) {
      out.putIfAbsent(e.key, () => PayeeTotal(e.key, payees[e.key] ?? '(지워진 받는 곳)')).paid = e.value;
    }
    for (final e in out.entries) {
      e.value.carry = (billed[e.key] ?? 0) - (paidBefore[e.key] ?? 0);
    }
    return out.values.toList()
      ..sort((a, b) {
        final d = b.balance.compareTo(a.balance);
        return d != 0 ? d : a.name.compareTo(b.name);
      });
  }

  /// 현장 1곳 = 한 줄. 인력 공수·장비 일수·자재 수량, 종류별 금액, 일지 쓴 날.
  Future<List<SiteTotal>> monthSites(String month) async {
    final sites = {for (final s in await db.all('site')) s['id']: s['name'] as String};
    final out = <String, SiteTotal>{};
    for (final log in await db.all('work_log')) {
      if (!(log['work_date'] as String).startsWith(month)) continue;
      final id = log['site_id'] as String;
      final st = out.putIfAbsent(id, () => SiteTotal(id, sites[id] ?? '(지워진 현장)'));
      st.days.add(log['work_date'] as String);
      if (log['no_work'] == 1) st.restDays.add(log['work_date'] as String);
    }
    for (final l in await _monthLines(month)) {
      final s = out[l['site_id']]!;
      s.inputDays.add(l['work_date'] as String);
      final q = num.parse(l['qty'] as String);
      s.byKind[l['kind'] as String] = s.byKind[l['kind']]! + (l['amount'] as int);
      if (l['kind'] == '인력') s.manDays += q;
      if (l['kind'] == '장비' && l['unit'] == '일') s.equipDays += q;
      if (l['kind'] == '장비') {
        s.equipment.update('${l['item']}|${l['unit']}', (v) => v + q, ifAbsent: () => q);
      }
      if (l['kind'] == '자재') {
        final key = '${l['item']} ${l['spec'] ?? ''}'.trim();
        s.materials.update('$key|${l['unit']}', (v) => v + q, ifAbsent: () => q);
      }
    }
    return out.values.toList()..sort((a, b) => b.total.compareTo(a.total));
  }

  /// 지급 기록. 다음 달에는 남은 잔액만 이월된다.
  Future<String> recordPayment(String payeeId, String month, Object amount, String paidDate) async {
    final a = int.tryParse(amount.toString().replaceAll(',', '').trim());
    if (a == null || a <= 0) throw StoreError('지급 금액을 숫자로 적어 주세요.');
    return insert('payment', {'payee_id': payeeId, 'month': month, 'amount': a, 'paid_date': parseWorkDate(paidDate)});
  }

  /// 카톡·문자로 보낼 결제 요약 (받는 곳별 금액, 계좌로 보낼 때 바로 쓰는 형식).
  Future<String> paymentText(String month) async {
    final rows = await monthPayments(month);
    final sites = await monthSites(month);
    String w(int n) => wonFmt(n);
    final b = StringBuffer('[진성건설] ${month.substring(0, 4)}년 ${int.parse(month.substring(5))}월 결제 요약\n');
    final total = rows.fold<int>(0, (s, p) => s + p.total);
    final due = rows.fold<int>(0, (s, p) => s + p.balance);
    b.writeln('이달 투입 ${w(total)}원 · 지급할 잔액 ${w(due)}원 · 받는 곳 ${rows.length}곳');
    b.writeln();
    for (final p in rows) {
      b.writeln('■ ${p.name}  ${w(p.balance)}원');
      final parts = <String>[
        if (p.manDays > 0) '${fmtQty(p.manDays)}공수',
        for (final e in p.equipment.entries) '${e.key.split('|')[0]} ${fmtQty(e.value)}${e.key.split('|')[1]}',
        for (final e in p.bySite.entries) '${e.key} ${w(e.value)}',
        if (p.carry != 0) '이월 ${w(p.carry)}',
        if (p.paid != 0) '지급 ${w(p.paid)}',
      ];
      b.writeln('  ${parts.join(' / ')}');
    }
    b.writeln();
    b.writeln('[현장별]');
    for (final s in sites) {
      b.writeln('■ ${s.name}  ${w(s.total)}원 (작업 ${s.workDays}일${s.restDays.isEmpty ? '' : ' · 쉼 ${s.restDays.length}일'})');
      final eq = s.equipment.entries.map((e) => '${e.key.split('|')[0]} ${fmtQty(e.value)}${e.key.split('|')[1]}').join(', ');
      b.writeln('  인력 ${fmtQty(s.manDays)}공수 ${w(s.byKind['인력']!)} / 장비${eq.isEmpty ? '' : '($eq)'} ${w(s.byKind['장비']!)}'
          ' / 자재 ${w(s.byKind['자재']!)} / 외주 ${w(s.byKind['외주']!)}');
    }
    return b.toString().trimRight();
  }
}

String wonFmt(num n) {
  final s = n.round().abs().toString();
  final b = StringBuffer(n < 0 ? '-' : '');
  for (var i = 0; i < s.length; i++) {
    if (i > 0 && (s.length - i) % 3 == 0) b.write(',');
    b.write(s[i]);
  }
  return b.toString();
}

String fmtQty(num q) {
  if (q == q.roundToDouble()) return q.toInt().toString();
  var t = q.toStringAsFixed(2);
  while (t.endsWith('0')) {
    t = t.substring(0, t.length - 1);
  }
  return t.endsWith('.') ? t.substring(0, t.length - 1) : t;
}

String monthShift(String month, int delta) {
  final y = int.parse(month.substring(0, 4));
  final m = int.parse(month.substring(5)) - 1 + delta;
  final yy = y + (m >= 0 ? m ~/ 12 : -((-m + 11) ~/ 12));
  final mm = ((m % 12) + 12) % 12 + 1;
  return '${yy.toString().padLeft(4, '0')}-${mm.toString().padLeft(2, '0')}';
}
