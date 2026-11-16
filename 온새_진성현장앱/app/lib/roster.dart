/// 명부(작업자·장비 미리 등록)와 사람·장비별 출역표, 연간 집계.
///
/// - 명부 한 칸 = 받는 곳(사람·업체) + 항목(직종·기종·자재) + 단위·단가. 같은 업체가 6W·3W를 대면 두 칸.
/// - 일지에 처음 적은 사람·장비는 저장할 때 자동으로 명부에 들어간다(따로 등록 안 해도 됨).
/// - 출역표·연간 집계는 일지 줄을 더할 뿐이다(값의 주인은 업무일지).
library;

import 'ledger.dart';
import 'row_db.dart';
import 'store.dart';

class RosterEntry {
  RosterEntry(this.row, this.payeeName);
  final Rec row;
  final String payeeName;
  String get id => row['id'] as String;
  String get kind => row['kind'] as String;
  String get item => row['item'] as String;
  String get spec => (row['spec'] ?? '') as String;
  String get unit => row['unit'] as String;
  int get price => row['unit_price'] as int;
  String get label => '$payeeName · $item${spec.isEmpty ? '' : ' $spec'}';
}

/// 한 사람(또는 장비)의 하루: 어느 현장에 얼마나.
class DayWork {
  DayWork(this.date);
  final String date;
  final List<({String site, String item, num qty, String unit, int amount})> parts = [];
  num get qty => parts.fold<num>(0, (a, p) => a + p.qty);
  int get amount => parts.fold<int>(0, (a, p) => a + p.amount);
}

class YearRow {
  YearRow(this.key, this.name, this.detail);
  final String key;
  final String name;
  final String detail; // 직종·기종 등
  final Map<int, num> qty = {}; // 월 → 공수·일수·대수
  final Map<int, int> amount = {}; // 월 → 금액
  String unit = '';
  num get qtyTotal => qty.values.fold<num>(0, (a, b) => a + b);
  int get amountTotal => amount.values.fold<int>(0, (a, b) => a + b);
}

extension Roster on Store {
  Future<List<RosterEntry>> roster({String? kind, bool includeInactive = false}) async {
    final names = {for (final p in await db.all('payee')) p['id']: p['name'] as String};
    final out = [
      for (final r in await db.all('roster'))
        if ((kind == null || r['kind'] == kind) && (includeInactive || r['active'] != 0))
          RosterEntry(r, names[r['payee_id']] ?? '(지워진 받는 곳)'),
    ];
    out.sort((a, b) {
      final k = kinds.indexOf(a.kind) - kinds.indexOf(b.kind);
      return k != 0 ? k : a.label.compareTo(b.label);
    });
    return out;
  }

  /// 명부 등록(이미 있으면 단가·단위·연락처만 고친다).
  Future<String> saveRoster({required String kind, required String payee, required String item,
      required String unit, required Object unitPrice, String spec = '', String? phone, String? memo}) async {
    if (!kinds.contains(kind)) throw StoreError('종류는 $kinds 중 하나입니다.');
    if (item.trim().isEmpty) throw StoreError('직종·기종·자재 이름을 적어 주세요.');
    final price = int.tryParse(unitPrice.toString().replaceAll(',', '').trim());
    if (price == null || price < 0) throw StoreError('단가를 숫자로 적어 주세요.');
    final payeeId = await ensurePayee(payee, kind: kind);
    final it = item.trim(), sp = spec.trim();
    final u = unit.trim().isEmpty ? defaultUnit[kind]! : unit.trim();
    for (final r in await db.all('roster')) {
      if (r['payee_id'] == payeeId && r['kind'] == kind && r['item'] == it && (r['spec'] ?? '') == sp) {
        await update('roster', r['id'] as String, r['version'] as int, {
          'unit': u, 'unit_price': price, 'active': 1,
          if (phone != null) 'phone': phone.trim().isEmpty ? null : phone.trim(),
          if (memo != null) 'memo': memo.trim().isEmpty ? null : memo.trim(),
        });
        return r['id'] as String;
      }
    }
    return insert('roster', {
      'payee_id': payeeId, 'kind': kind, 'item': it, 'spec': sp, 'unit': u, 'unit_price': price,
      'phone': (phone ?? '').trim().isEmpty ? null : phone!.trim(),
      'memo': (memo ?? '').trim().isEmpty ? null : memo!.trim(), 'active': 1,
    });
  }

  /// 명부에서 빼기(지난 일지·집계는 그대로).
  Future<void> retireRoster(String id) async {
    final r = await mustGet('roster', id);
    await update('roster', id, r['version'] as int, {'active': 0});
  }

  /// 일지에 처음 적은 사람·장비를 명부에 자동으로 넣는다(addLine 이 부름).
  Future<void> learnRoster(String kind, String payeeId, String item, String spec, String unit, int price) async {
    for (final r in await db.all('roster')) {
      if (r['payee_id'] == payeeId && r['kind'] == kind && r['item'] == item && (r['spec'] ?? '') == spec) return;
    }
    await insert('roster', {
      'payee_id': payeeId, 'kind': kind, 'item': item, 'spec': spec, 'unit': unit, 'unit_price': price,
      'phone': null, 'memo': null, 'active': 1,
    });
  }

  /// 명부에서 고른 사람·장비를 한 번에 일지에 넣는다. picks: (명부 id, 수량)
  Future<int> addFromRoster(String siteId, String workDate, List<(String, String)> picks, {String? reason}) async {
    final all = {for (final r in await roster(includeInactive: true)) r.id: r};
    var n = 0;
    for (final (id, qty) in picks) {
      final r = all[id];
      if (r == null) continue;
      await addLine(siteId: siteId, workDate: workDate, kind: r.kind, item: r.item, spec: r.spec, qty: qty,
          unit: r.unit, unitPrice: r.price, payee: r.payeeName, reason: reason);
      n++;
    }
    return n;
  }

  Future<List<Rec>> _lines(bool Function(String date) inRange) async {
    final logs = {for (final l in await db.all('work_log')) l['id']: l};
    return [
      for (final l in await db.all('input_line'))
        if (logs[l['log_id']] != null && inRange(logs[l['log_id']]!['work_date'] as String))
          {...l, 'work_date': logs[l['log_id']]!['work_date'], 'site_id': logs[l['log_id']]!['site_id']},
    ];
  }

  /// 출역표: 한 받는 곳의 한 달, 날짜별로 어느 현장에 얼마나. item 을 주면 그 직종·기종만.
  Future<Map<String, DayWork>> personMonth(String payeeId, String month, {String? item}) async {
    final sites = {for (final s in await db.all('site')) s['id']: s['name'] as String};
    final out = <String, DayWork>{};
    for (final l in await _lines((d) => d.startsWith(month))) {
      if (l['payee_id'] != payeeId || (item != null && l['item'] != item)) continue;
      out.putIfAbsent(l['work_date'] as String, () => DayWork(l['work_date'] as String)).parts.add((
        site: sites[l['site_id']] ?? '(지워진 현장)',
        item: l['item'] as String,
        qty: num.parse(l['qty'] as String),
        unit: l['unit'] as String,
        amount: l['amount'] as int,
      ));
    }
    return out;
  }

  /// 연간 집계: 받는 곳·항목별(사람·장비) 월별 수량과 금액.
  Future<List<YearRow>> yearByPayee(String year) async {
    final names = {for (final p in await db.all('payee')) p['id']: p['name'] as String};
    final out = <String, YearRow>{};
    for (final l in await _lines((d) => d.startsWith(year))) {
      final key = '${l['payee_id']}|${l['kind']}|${l['item']}|${l['unit']}';
      final r = out.putIfAbsent(key, () => YearRow(key, names[l['payee_id']] ?? '(지워진 받는 곳)', '${l['kind']} ${l['item']}'));
      final m = int.parse((l['work_date'] as String).substring(5, 7));
      r.unit = l['unit'] as String;
      r.qty[m] = (r.qty[m] ?? 0) + num.parse(l['qty'] as String);
      r.amount[m] = (r.amount[m] ?? 0) + (l['amount'] as int);
    }
    return out.values.toList()..sort((a, b) => b.amountTotal.compareTo(a.amountTotal));
  }

  /// 연간 집계: 현장별 월별 금액.
  Future<List<YearRow>> yearBySite(String year) async {
    final sites = {for (final s in await db.all('site')) s['id']: s['name'] as String};
    final out = <String, YearRow>{};
    for (final l in await _lines((d) => d.startsWith(year))) {
      final id = l['site_id'] as String;
      final r = out.putIfAbsent(id, () => YearRow(id, sites[id] ?? '(지워진 현장)', ''));
      final m = int.parse((l['work_date'] as String).substring(5, 7));
      r.amount[m] = (r.amount[m] ?? 0) + (l['amount'] as int);
    }
    return out.values.toList()..sort((a, b) => b.amountTotal.compareTo(a.amountTotal));
  }

  /// 카톡·문자용 출역 확인서 (사람에게 보내 날짜·공수를 맞춰 볼 때).
  Future<String> personText(String payeeId, String payeeName, String month) async {
    final days = (await personMonth(payeeId, month)).values.toList()..sort((a, b) => a.date.compareTo(b.date));
    final b = StringBuffer('[진성건설] $payeeName ${month.substring(0, 4)}년 ${int.parse(month.substring(5))}월 출역\n');
    for (final d in days) {
      b.writeln('${d.date.substring(5)}  ${d.parts.map((p) => '${p.site} ${p.item} ${fmtQty(p.qty)}${p.unit}').join(', ')}');
    }
    final units = <String, num>{};
    for (final d in days) {
      for (final p in d.parts) {
        units[p.unit] = (units[p.unit] ?? 0) + p.qty;
      }
    }
    b.writeln('합계 ${units.entries.map((e) => '${fmtQty(e.value)}${e.key}').join(' · ')} · ${wonFmt(days.fold<int>(0, (a, d) => a + d.amount))}원 (${days.length}일)');
    return b.toString().trimRight();
  }
}
