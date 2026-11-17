/// 공종(작업 종류)과 공정(시공 연장). 공정률 = 시공한 연장 ÷ 설계 연장.
/// U형 개거는 집 PC가 물량(철근·거푸집·레미콘)과 발주·체크 일정을 자동으로 계산한다(템플릿 9).
library;

import 'dart:convert';

import 'ledger.dart';
import 'row_db.dart';
import 'stations.dart';
import 'store.dart';

class WorkProgress {
  WorkProgress(this.row, this.done, this.today);
  final Rec row;
  final num done; // 지금까지 시공 m
  final List<Rec> today; // 이 날 기록
  String get id => row['id'] as String;
  String get name => row['name'] as String;
  num get design => num.tryParse((row['design_length'] ?? '') as String) ?? 0;
  double get rate => design > 0 ? (done / design).clamp(0, 1).toDouble() : 0;
}

extension Works on Store {
  /// 공종 추가. channel=true 면 U형 개거(내폭·높이 m) → 집 PC가 물량·발주 일정을 만든다.
  Future<String> addWorkType(String siteId, String name, Object length,
      {bool channel = false, String innerW = '1.0', String wallH = '1.0'}) async {
    if (name.trim().isEmpty) throw StoreError('공종 이름을 적어 주세요.');
    final len = num.tryParse(length.toString().replaceAll(',', '').trim());
    if (len == null || len <= 0) throw StoreError('설계 연장(m)을 숫자로 적어 주세요.');
    return insert('work_type', {
      'site_id': siteId, 'template_code': channel ? '9' : '0', 'name': name.trim(), 'design_length': fmtQty(len),
      'design_params': channel ? jsonEncode({'inner_w': innerW, 'wall_h': wallH, 'part': 'all'}) : null,
      'exec_params': null, 'exec_budget': null,
    });
  }

  /// 오늘 시공: 측점 시작~끝 → 연장(m)을 공정으로 남긴다.
  Future<String> addProgressSta(String siteId, String workDate, String workTypeId, String staFrom, String staTo) async {
    final site = await mustGet('site', siteId);
    final iv = double.tryParse((site['sta_interval'] ?? '20').toString()) ?? 20;
    final a = parseSta(staFrom, interval: iv), b = parseSta(staTo, interval: iv);
    if (b <= a) throw StoreError('측점 끝이 시작보다 커야 합니다 ($staFrom → $staTo).');
    return addProgress(siteId, workDate, workTypeId, staText(b - a), 'm',
        staFrom: staText(a), staTo: staText(b));
  }

  Future<List<WorkProgress>> workProgress(String siteId, {String? workDate}) async {
    final logs = {for (final l in await db.all('work_log')) l['id']: l};
    final out = <WorkProgress>[];
    for (final w in await db.all('work_type')) {
      if (w['site_id'] != siteId) continue;
      num done = 0;
      final today = <Rec>[];
      for (final p in await db.all('progress')) {
        if (p['work_type_id'] != w['id']) continue;
        done += num.tryParse(p['qty'] as String) ?? 0;
        if (workDate != null && logs[p['log_id']]?['work_date'] == workDate) today.add(p);
      }
      out.add(WorkProgress(w, done, today));
    }
    out.sort((a, b) => (a.row['created_at'] as String).compareTo(b.row['created_at'] as String));
    return out;
  }
}
