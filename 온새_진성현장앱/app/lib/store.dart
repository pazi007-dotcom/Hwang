/// 저장 규칙 (설계안 3장). 서버의 store.py 와 같은 규칙을 폰 안에서 지킨다.
///
/// 1. 작업일은 사용자가 정한 날짜만 쓴다(시각에서 다시 뽑지 않는다).
/// 2. 모든 투입은 반드시 하나의 현장에 속한다.
/// 3. 같은 기록을 두 기기가 동시에 고치면 덮어쓰지 않고 '충돌'로 남긴다.
/// 4. 마감된 달은 사유 없이 고칠 수 없다.
library;

import 'dart:convert';

import 'package:uuid/uuid.dart';

import 'row_db.dart';

const kinds = ['인력', '장비', '자재', '외주'];
const jobTypes = ['긴급', '견적', '수의', '입찰', '민원', '기타'];

/// 접수하자마자 생기는 필수 확인사항 (구분별).
const firstChecks = {
  '긴급': ['현장 위치·진입로 확인', '피해 범위 사진(전) 촬영', '발주처 지시 내용·범위 문서(문자)로 받기', '필요 장비·인력 즉시 수배'],
  '견적': ['현장 답사', '물량 실측(연장·폭·높이)', '견적서 제출 기한 확인'],
  '수의': ['현장 답사', '계약 금액·공기 확인', '도면·내역 수령', '착수 서류 확인'],
  '입찰': ['공고문 자격 조건 확인', '현장 설명회·답사 일정', '투찰 마감 일시', '내역서 수익성 검토'],
  '민원': ['민원인 연락', '현장 확인·사진', '원인 판단(하자/유지관리)', '처리 결과 통보'],
  '기타': ['현장 확인'],
};
const _refs = ['log_id', 'site_id', 'payee_id', 'work_type_id', 'run_id'];
const _uuid = Uuid();

class StoreError implements Exception {
  StoreError(this.message);
  final String message;
  @override
  String toString() => message;
}

class ConflictError extends StoreError {
  ConflictError() : super('다른 기기에서 먼저 고친 기록입니다. 충돌 검토에서 골라 주세요.');
}

class LockedError extends StoreError {
  LockedError(super.message);
}

final _datePattern = RegExp(r'^\d{4}-\d{2}-\d{2}$');

/// 작업일 확인: 'YYYY-MM-DD' 만 받는다. 시각이 붙은 값은 받지 않는다.
String parseWorkDate(String value) {
  final text = value.trim();
  if (!_datePattern.hasMatch(text)) {
    throw StoreError('작업일 형식이 아닙니다: $value (예: 2026-11-12)');
  }
  final parts = text.split('-').map(int.parse).toList();
  final d = DateTime(parts[0], parts[1], parts[2]);
  if (d.year != parts[0] || d.month != parts[1] || d.day != parts[2]) {
    throw StoreError('없는 날짜입니다: $value');
  }
  return text;
}

/// 날짜를 작업일 글자로. 시각·시간대와 무관하게 달력 날짜만 쓴다.
String workDateOf(DateTime d) =>
    '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

String cleanQty(Object qty) {
  final n = num.tryParse(qty.toString().trim());
  if (n == null) throw StoreError('숫자가 아닙니다: $qty');
  if (n <= 0) throw StoreError('수량은 0보다 커야 합니다.');
  return n == n.roundToDouble() ? n.toInt().toString() : n.toString();
}

int won(Object qty, int unitPrice) => (num.parse(qty.toString()) * unitPrice).round();

class Store {
  Store(this.db, {required this.device, DateTime Function()? clock}) : _clock = clock ?? DateTime.now;

  final RowDb db;
  final String device;
  final DateTime Function() _clock;

  /// 한국 시각 ISO (기록 시각). 작업일과는 따로 저장한다.
  String now() {
    final k = _clock().toUtc().add(const Duration(hours: 9));
    String two(int v) => v.toString().padLeft(2, '0');
    return '${k.year.toString().padLeft(4, '0')}-${two(k.month)}-${two(k.day)}'
        'T${two(k.hour)}:${two(k.minute)}:${two(k.second)}+09:00';
  }

  Future<void> _log(String table, String rowId, String op, int? baseVersion, Rec? data,
      {String? reason, String? device, String? at}) async {
    await db.appendChange({
      'table_name': table,
      'row_id': rowId,
      'op': op,
      'base_version': baseVersion,
      'data_json': data == null ? null : jsonEncode(data),
      'reason': reason,
      'device': device ?? this.device,
      'at': at ?? now(),
    });
  }

  Future<String> insert(String table, Rec values) async {
    final t = now();
    final row = <String, dynamic>{
      'id': _uuid.v4(),
      ...values,
      'version': 1,
      'created_at': t,
      'updated_at': t,
    };
    await db.put(table, row);
    await _log(table, row['id'] as String, '추가', null, row);
    return row['id'] as String;
  }

  Future<Rec> mustGet(String table, String id) async {
    final r = await db.get(table, id);
    if (r == null) throw StoreError('$table에 없는 기록입니다.');
    return r;
  }

  // ---------- 현장 ----------
  Future<String> createSite(String name, {String siteType = '정식', double? lat, double? lon,
      String status = '진행', String? jobType, String? receivedDate, String? instructions}) async {
    if (name.trim().isEmpty) throw StoreError('현장 이름을 넣어 주세요.');
    return insert('site', {
      'name': name.trim(), 'site_type': siteType, 'client': null, 'contract_amount': null,
      'start_date': null, 'end_date': null, 'gps_lat': lat, 'gps_lon': lon, 'gps_radius_m': null,
      'sta_interval': '20', 'sta_label_shift': 0,
      'status': status, 'job_type': jobType, 'received_date': receivedDate, 'planned_start': null,
      'instructions': instructions, 'status_reason': null,
    });
  }


  // ---------- 접수 → 보류 / 취소 / 진행 → 완공 (서버 intake.py 와 같은 규칙) ----------
  /// 접수. 이름과 구분만 있으면 된다. 접수하는 순간 그날 일지에 [접수] 한 줄이 남는다.
  Future<String> receive(String name, String jobType, String receivedDate,
      {String? instructions, String? contactName, String? contactPhone}) async {
    if (!jobTypes.contains(jobType)) throw StoreError('접수 구분은 $jobTypes 중 하나입니다.');
    final day = parseWorkDate(receivedDate);
    final siteType = jobType == '입찰' ? '정식' : (jobType == '민원' || jobType == '기타') ? '보수기타' : '긴급수의';
    final note = (instructions == null || instructions.trim().isEmpty) ? null : instructions.trim();
    final site = await createSite(name, siteType: siteType, status: '접수', jobType: jobType,
        receivedDate: day, instructions: note);
    if (contactName != null && contactName.trim().isNotEmpty) {
      await insert('contact', {
        'site_id': site, 'name': contactName.trim(), 'role': null,
        'phone': (contactPhone ?? '').trim().isEmpty ? null : contactPhone!.trim(), 'note': null,
      });
    }
    for (final title in firstChecks[jobType]!) {
      await addTask(site, '확인', title, dueDate: day);
    }
    final logId = await logFor(site, day);
    final row = await mustGet('work_log', logId);
    await update('work_log', logId, row['version'] as int,
        {'content': '[접수·$jobType] ${name.trim()}${note == null ? '' : ' — $note'}'});
    return site;
  }

  Future<String> addTask(String siteId, String kind, String title, {String? dueDate}) => insert('site_task', {
        'site_id': siteId, 'kind': kind, 'title': title,
        'due_date': dueDate == null ? null : parseWorkDate(dueDate), 'qty': null, 'unit': null,
        'work_type_id': null, 'source': '직접', 'done': 0, 'done_date': null, 'note': null,
      });

  Future<void> checkTask(String taskId, String doneDate, {bool done = true}) async {
    final row = await mustGet('site_task', taskId);
    await update('site_task', taskId, row['version'] as int,
        {'done': done ? 1 : 0, 'done_date': done ? parseWorkDate(doneDate) : null});
  }

  Future<void> _setStatus(String siteId, String status, Rec more) async {
    final row = await mustGet('site', siteId);
    await update('site', siteId, row['version'] as int, {'status': status, ...more});
  }

  Future<void> hold(String siteId, String reason) async {
    if (reason.trim().isEmpty) throw StoreError('보류 사유를 적어 주세요.');
    await _setStatus(siteId, '보류', {'status_reason': reason.trim()});
  }

  /// 진행. 시작 예정일을 넣으면 집 PC와 맞출 때 발주·체크 일정이 만들어진다.
  Future<void> proceed(String siteId, {String? plannedStart}) => _setStatus(siteId, '진행', {
        'status_reason': null,
        'planned_start': (plannedStart == null || plannedStart.isEmpty) ? null : parseWorkDate(plannedStart),
      });

  Future<void> complete(String siteId, String endDate) =>
      _setStatus(siteId, '완공', {'end_date': parseWorkDate(endDate)});

  /// 취소. 투입(돈)이 없으면 파기('파기'), 있으면 '취소'로 남긴다('보관').
  Future<String> cancel(String siteId, String reason) async {
    if (reason.trim().isEmpty) throw StoreError('취소 사유를 적어 주세요.');
    final logs = (await db.all('work_log')).where((l) => l['site_id'] == siteId).toList();
    final logIds = logs.map((l) => l['id']).toSet();
    final spent = (await db.all('input_line')).any((l) => logIds.contains(l['log_id']));
    var locked = false;
    for (final l in logs) {
      if (await isLocked((l['work_date'] as String).substring(0, 7))) locked = true;
    }
    if (spent || locked) {
      await _setStatus(siteId, '취소', {'status_reason': reason.trim()});
      return '보관';
    }
    final why = '취소 파기: ${reason.trim()}';
    for (final p in await db.all('progress')) {
      if (logIds.contains(p['log_id'])) await delete('progress', p['id'] as String, p['version'] as int, reason: why);
    }
    for (final table in ['site_task', 'contact', 'attachment', 'photo', 'work_log', 'work_type', 'station', 'allocation']) {
      for (final r in await db.all(table)) {
        if (r['site_id'] == siteId) await delete(table, r['id'] as String, r['version'] as int, reason: why);
      }
    }
    await delete('site', siteId, (await mustGet('site', siteId))['version'] as int, reason: why);
    return '파기';
  }

  /// 기한이 지났거나 [daysAhead]일 안에 오는 할 일 (보류·취소 건 제외).
  Future<List<Rec>> dueTasks(String today, {int daysAhead = 2, String? siteId}) async {
    final t = DateTime.parse(today);
    final limit = workDateOf(t.add(Duration(days: daysAhead)));
    final sites = {for (final s in await db.all('site')) s['id']: s};
    final out = <Rec>[];
    for (final r in await db.all('site_task')) {
      final site = sites[r['site_id']];
      if (r['done'] == 1 || r['due_date'] == null || site == null) continue;
      if (siteId != null && r['site_id'] != siteId) continue;
      if (!const ['접수', '진행', '완공'].contains(site['status'])) continue;
      if ((r['due_date'] as String).compareTo(limit) > 0) continue;
      final gap = DateTime.parse(r['due_date'] as String).difference(t).inDays;
      out.add({
        ...r, 'site_name': site['name'], 'late': gap < 0,
        'when': gap == 0 ? '오늘' : (gap > 0 ? 'D-$gap' : '${-gap}일 지남'),
      });
    }
    out.sort((a, b) => (a['due_date'] as String).compareTo(b['due_date'] as String));
    return out;
  }

  // ---------- 마감 ----------
  Future<bool> isLocked(String month) async => await db.get('month_lock', month) != null;

  Future<void> _checkUnlocked(String workDate, String? reason, {bool creating = false}) async {
    final month = workDate.substring(0, 7);
    if (await isLocked(month) && (reason == null || reason.isEmpty)) {
      throw LockedError('$month은 월말 보고를 보내 마감된 달입니다. '
          '${creating ? '추가' : '수정'}하려면 사유를 넣어 주세요(정정 보고서 대상).');
    }
  }

  // ---------- 일지·투입 ----------
  Future<String> logFor(String? siteId, String workDate, {String? reason}) async {
    if (siteId == null || siteId.isEmpty) {
      throw StoreError("현장을 골라 주세요. 어디에도 속하지 않으면 '본사·공통'을 고릅니다.");
    }
    final site = await mustGet('site', siteId);
    if (site['status'] == '취소') {
      throw StoreError("'${site['name']}'은(는) 취소된 건입니다. 일지를 쓸 수 없습니다.");
    }
    final wd = parseWorkDate(workDate);
    await _checkUnlocked(wd, reason, creating: true);
    for (final l in await db.all('work_log')) {
      if (l['site_id'] == siteId && l['work_date'] == wd) return l['id'] as String;
    }
    return insert('work_log', {
      'site_id': siteId, 'work_date': wd, 'weather': null, 'content': null, 'note': null,
      'no_work': 0, 'tbm': 0,
    });
  }

  /// 업체 전용 단가 → 공통 단가 순, 작업일 기준 가장 최근 적용분.
  Future<Rec?> findRate(String kind, String item, String spec, String? payeeId, String workDate) async {
    final rows = (await db.all('rate'))
        .where((r) =>
            r['kind'] == kind && r['item'] == item && (r['spec'] ?? '') == spec &&
            (r['valid_from'] as String).compareTo(workDate) <= 0 &&
            (r['payee_id'] == null || r['payee_id'] == payeeId))
        .toList();
    if (rows.isEmpty) return null;
    rows.sort((a, b) {
      final own = (a['payee_id'] == null ? 1 : 0) - (b['payee_id'] == null ? 1 : 0);
      return own != 0 ? own : (b['valid_from'] as String).compareTo(a['valid_from'] as String);
    });
    return rows.first;
  }

  Future<String> addInput(String? siteId, String workDate, String kind, String item, Object qty,
      String payeeId, {String spec = '', String? unit, int? unitPrice, String? workTypeId,
      String? staFrom, String? staTo, String? reason}) async {
    if (!kinds.contains(kind)) throw StoreError('종류는 $kinds 중 하나입니다.');
    final q = cleanQty(qty);
    final logId = await logFor(siteId, workDate, reason: reason);
    final wd = (await mustGet('work_log', logId))['work_date'] as String;
    if (unitPrice == null || unit == null) {
      final rate = await findRate(kind, item, spec, payeeId, wd);
      if (rate == null) throw StoreError('기준 단가가 없습니다: $kind $item $spec'.trim());
      unitPrice ??= rate['unit_price'] as int;
      unit ??= rate['unit'] as String;
    }
    return insert('input_line', {
      'log_id': logId, 'kind': kind, 'item': item, 'spec': spec, 'qty': q, 'unit': unit,
      'unit_price': unitPrice, 'amount': won(q, unitPrice), 'payee_id': payeeId,
      'work_type_id': workTypeId, 'sta_from': staFrom, 'sta_to': staTo, 'share_group': null,
    });
  }

  Future<String> addProgress(String siteId, String workDate, String workTypeId, Object qty,
      String unit, {String? staFrom, String? staTo}) async {
    final logId = await logFor(siteId, workDate);
    return insert('progress', {
      'log_id': logId, 'work_type_id': workTypeId, 'sta_from': staFrom, 'sta_to': staTo,
      'qty': cleanQty(qty), 'unit': unit,
    });
  }

  Future<String> markNoWork(String siteId, String workDate, {String weather = '비'}) async {
    final logId = await logFor(siteId, workDate);
    final row = await mustGet('work_log', logId);
    await update('work_log', logId, row['version'] as int, {'no_work': 1, 'weather': weather});
    return logId;
  }

  Future<String?> _monthOf(String table, Rec row) async {
    if (table == 'work_log' || table == 'invoice' || table == 'photo' || table == 'level_run') {
      return (row['work_date'] as String).substring(0, 7);
    }
    if (table == 'input_line' || table == 'progress') {
      final log = await db.get('work_log', row['log_id'] as String);
      return log == null ? null : (log['work_date'] as String).substring(0, 7);
    }
    return null;
  }

  Future<int> update(String table, String id, int baseVersion, Rec changes, {String? reason}) async {
    final current = await mustGet(table, id);
    if (current['version'] != baseVersion) {
      await db.addConflict({
        'id': _uuid.v4(), 'table_name': table, 'row_id': id, 'base_version': baseVersion,
        'current': current, 'incoming': changes, 'created_at': now(),
      });
      throw ConflictError();
    }
    final month = await _monthOf(table, current);
    if (month != null) await _checkUnlocked('$month-01', reason);
    final ch = Map<String, dynamic>.from(changes);
    if (ch.containsKey('work_date')) {
      ch['work_date'] = parseWorkDate(ch['work_date'] as String);
      await _checkUnlocked(ch['work_date'] as String, reason);
    }
    if (table == 'input_line' && (ch.containsKey('qty') || ch.containsKey('unit_price'))) {
      final q = cleanQty(ch['qty'] ?? current['qty']);
      final price = (ch['unit_price'] ?? current['unit_price']) as int;
      ch['qty'] = q;
      ch['amount'] = won(q, price);
    }
    for (final k in ['id', 'version', 'created_at', 'updated_at']) {
      ch.remove(k);
    }
    await db.put(table, {...current, ...ch, 'version': baseVersion + 1, 'updated_at': now()});
    await _log(table, id, '수정', baseVersion, ch, reason: reason);
    return baseVersion + 1;
  }

  Future<void> delete(String table, String id, int baseVersion, {String? reason}) async {
    final current = await mustGet(table, id);
    if (current['version'] != baseVersion) {
      await db.addConflict({
        'id': _uuid.v4(), 'table_name': table, 'row_id': id, 'base_version': baseVersion,
        'current': current, 'incoming': {'삭제': true}, 'created_at': now(),
      });
      throw ConflictError();
    }
    final month = await _monthOf(table, current);
    if (month != null) await _checkUnlocked('$month-01', reason);
    await db.remove(table, id);
    await _log(table, id, '삭제', baseVersion, null, reason: reason);
  }

  /// 충돌 검토에서 고르기. keep: 'current'(먼저 저장된 값) 또는 'incoming'(이 기기 값).
  Future<void> resolveConflict(Rec conflict, String keep) async {
    if (keep == 'incoming') {
      final table = conflict['table_name'] as String;
      final id = conflict['row_id'] as String;
      final incoming = Map<String, dynamic>.from(conflict['incoming'] as Map);
      final row = await db.get(table, id);
      if (row != null) {
        if (incoming['삭제'] == true) {
          await delete(table, id, row['version'] as int, reason: '충돌 검토에서 선택');
        } else {
          await update(table, id, row['version'] as int, incoming, reason: '충돌 검토에서 선택');
        }
      }
    } else if (keep != 'current') {
      throw StoreError("keep은 'current' 또는 'incoming'입니다.");
    }
    await db.closeConflict(conflict['id'] as String);
  }

  // ---------- 집계 (화면용) ----------
  Future<List<Rec>> linesOf(String siteId, String workDate) async {
    final logs = (await db.all('work_log'))
        .where((l) => l['site_id'] == siteId && l['work_date'] == workDate)
        .map((l) => l['id'])
        .toSet();
    final rows = (await db.all('input_line')).where((l) => logs.contains(l['log_id'])).toList();
    rows.sort((a, b) => (a['created_at'] as String).compareTo(b['created_at'] as String));
    return rows;
  }

  Future<int> monthCost(String siteId, String month) async {
    final logs = {
      for (final l in await db.all('work_log'))
        if (l['site_id'] == siteId && (l['work_date'] as String).startsWith(month)) l['id'],
    };
    var sum = 0;
    for (final l in await db.all('input_line')) {
      if (logs.contains(l['log_id'])) sum += l['amount'] as int;
    }
    return sum;
  }

  // ---------- 동기화: 상대 기기의 변경 한 건 적용 (서버 sync.py 와 같은 규칙) ----------
  Future<String> _real(String id) async => await db.alias(id) ?? id;

  Future<Rec> _remap(Rec data) async {
    final out = Map<String, dynamic>.from(data);
    for (final k in _refs) {
      if (out[k] is String) out[k] = await _real(out[k] as String);
    }
    return out;
  }

  Future<Rec?> _twin(String table, Rec data) async {
    if (table == 'work_log') {
      for (final l in await db.all('work_log')) {
        if (l['site_id'] == data['site_id'] && l['work_date'] == data['work_date']) return l;
      }
    }
    return null;
  }

  Future<Rec> applyChange(Rec ch) async {
    final table = ch['table_name'] as String;
    final op = ch['op'] as String;
    final seq = ch['seq'];
    final data = ch['data_json'] == null ? null : jsonDecode(ch['data_json'] as String) as Rec;
    final origin = ch['device'] as String;
    final at = ch['at'] as String;
    if (op == '마감') {
      final month = data!['month'] as String;
      if (await db.get('month_lock', month) == null) {
        await db.put('month_lock', {'id': month, 'month': month, 'locked_at': at});
        await _log('month_lock', month, '마감', null, data, device: origin, at: at);
      }
      return {'seq': seq, 'status': '적용'};
    }
    final rowId = await _real(ch['row_id'] as String);
    final cur = await db.get(table, rowId);
    if (op == '추가') {
      if (cur != null) return {'seq': seq, 'status': '건너뜀'};
      final row = await _remap(data!);
      final twin = await _twin(table, row);
      if (twin != null) {
        await db.setAlias(ch['row_id'] as String, twin['id'] as String);
        return {'seq': seq, 'status': '이어 붙임', 'real_id': twin['id']};
      }
      await db.put(table, row);
      await _log(table, row['id'] as String, '추가', null, row, device: origin, at: at);
      return {'seq': seq, 'status': '적용'};
    }
    if (cur == null) return {'seq': seq, 'status': '건너뜀'};
    final base = ch['base_version'] as int;
    if (op == '수정') {
      final changes = await _remap(data!);
      final same = changes.entries.every((e) => cur[e.key] == e.value);
      if (cur['version'] == base + 1 && same) return {'seq': seq, 'status': '건너뜀'};
      if (cur['version'] != base) {
        return {
          'seq': seq, 'status': '충돌', 'current': cur, 'incoming': changes,
          'table': table, 'row_id': rowId, 'base_version': base,
        };
      }
      await db.put(table, {...cur, ...changes, 'version': base + 1, 'updated_at': at});
      await _log(table, rowId, '수정', base, changes,
          reason: ch['reason'] as String?, device: origin, at: at);
      return {'seq': seq, 'status': '적용'};
    }
    if (op == '삭제') {
      if (cur['version'] != base) {
        return {
          'seq': seq, 'status': '충돌', 'current': cur, 'incoming': {'삭제': true},
          'table': table, 'row_id': rowId, 'base_version': base,
        };
      }
      await db.remove(table, rowId);
      await _log(table, rowId, '삭제', base, null,
          reason: ch['reason'] as String?, device: origin, at: at);
      return {'seq': seq, 'status': '적용'};
    }
    return {'seq': seq, 'status': '건너뜀'};
  }

  /// 내 변경이 늦었다 → 먼저 저장된 값으로 맞추고 내 값은 '충돌 검토'에 남긴다.
  Future<void> adopt(Rec res) async {
    final table = res['table'] as String;
    final cur = Map<String, dynamic>.from(res['current'] as Map);
    await db.put(table, cur);
    await db.addConflict({
      'id': _uuid.v4(), 'table_name': table, 'row_id': res['row_id'],
      'base_version': res['base_version'], 'current': cur,
      'incoming': Map<String, dynamic>.from(res['incoming'] as Map), 'created_at': now(),
    });
  }
}
