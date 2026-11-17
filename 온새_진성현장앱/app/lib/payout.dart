/// 이체 목록: 월말에 "누구에게 얼마를 보내나". 받는 사람·업체 1곳 = 이체 1건.
///
/// - 작업자(일용)는 사람마다 따로: 하루 일당에서 15만원 넘는 부분 × 6% × 45%(근로소득세액공제 55% 뺀 값)를
///   소득세로, 그 10%를 지방소득세로 뗀다. 하루씩 계산해서 더하고, 10원 미만 버림, 소득세가 1,000원 미만이면
///   떼지 않는다(소액부징수). 세율·공제는 세무사 확인용 기본값이다.
/// - 장비·자재 업체는 '부가세 별도'로 해 두면 이달 금액의 10%를 더해 보낸다.
/// - 지급을 기록하면 보낸 돈 + 뗀 세금 − 더한 부가세 만큼 일지 금액이 정산된 것으로 본다(다음 달 이월이 맞게).
library;

import 'ledger.dart';
import 'row_db.dart';
import 'store.dart';

const payRules = ['일용', '부가세별도', '그대로'];
const payRuleLabel = {'일용': '일용 (소득세 떼고)', '부가세별도': '부가세 10% 더해서', '그대로': '그대로'};

/// 하루 일당 → 그날 소득세(원 미만 버림).
int dailyIncomeTax(int pay) => pay <= 150000 ? 0 : ((pay - 150000) * 27) ~/ 1000;

class Payout {
  Payout(this.p, this.info);
  final PayeeTotal p;
  final Rec info; // payee 행
  String get name => p.name;
  String get payeeId => p.payeeId;
  String get rule => (info['pay_rule'] as String?) ?? (info['payee_type'] == '개인' ? '일용' : '그대로');
  String get bank => (info['bank'] as String?) ?? '';
  String get account => (info['account_no'] as String?) ?? '';
  String get holder => (info['holder'] as String?) ?? '';
  bool get hasAccount => bank.isNotEmpty && account.isNotEmpty;
  String get group => p.kinds.contains('인력') ? '작업자' : p.kinds.contains('장비') ? '장비' : '자재·외주';
  int incomeTax = 0;
  int localTax = 0;
  int vat = 0;
  int workDays = 0;
  int get deduct => incomeTax + localTax;
  int deductDone = 0; // 이미 지급 기록에서 뗀 세금
  int vatDone = 0; // 이미 지급 기록에서 더한 부가세
  int get deductLeft => deduct - deductDone;
  int get vatLeft => vat - vatDone;

  /// 보낼 돈 = 일지 기준 남은 돈(이월 포함, 정산액 뺀) − 아직 안 뗀 세금 + 아직 안 더한 부가세
  int get transfer => p.balance - deductLeft + vatLeft;
  String get accountText => hasAccount ? '$bank $account${holder.isEmpty || holder == name ? '' : ' ($holder)'}' : '계좌 없음';

  String get breakdown => [
        if (p.manDays > 0) '${fmtQty(p.manDays)}공수 · $workDays일',
        for (final e in p.equipment.entries) '${e.key.split('|')[0]} ${fmtQty(e.value)}${e.key.split('|')[1]}',
        '이달 ${wonFmt(p.total)}',
        if (incomeTax > 0) '소득세 −${wonFmt(incomeTax)}',
        if (localTax > 0) '지방세 −${wonFmt(localTax)}',
        if (vat > 0) '부가세 +${wonFmt(vat)}',
        if (p.carry != 0) '이월 ${wonFmt(p.carry)}',
        if (p.paid != 0) '지급됨 −${wonFmt(p.paid)}',
      ].join(' · ');
}

extension Payouts on Store {
  /// 받는 곳 정보(계좌·지급 방식) 고치기.
  Future<void> setPayeeInfo(String payeeId, {String? bank, String? account, String? holder, String? rule}) async {
    final p = await mustGet('payee', payeeId);
    if (rule != null && !payRules.contains(rule)) throw StoreError('지급 방식은 $payRules 중 하나입니다.');
    final ch = <String, Object?>{};
    if (bank != null) ch['bank'] = bank.trim();
    if (account != null) ch['account_no'] = account.trim();
    if (holder != null) ch['holder'] = holder.trim();
    if (rule != null) ch['pay_rule'] = rule;
    await update('payee', payeeId, p['version'] as int? ?? 1, ch);
  }

  Future<List<Payout>> monthPayouts(String month) async {
    final rows = await monthPayments(month);
    final info = {for (final p in await db.all('payee')) p['id'] as String: p};
    // 사람별·날짜별 일당 (현장 여러 곳이면 더해서 하루 일당)
    final daily = <String, Map<String, int>>{};
    final totals = <String, int>{};
    for (final l in await monthLinesAll(month)) {
      totals.update(l['payee_id'] as String, (v) => v + (l['amount'] as int), ifAbsent: () => l['amount'] as int);
      if (l['kind'] != '인력') continue;
      daily.putIfAbsent(l['payee_id'] as String, () => {}).update(
          l['work_date'] as String, (v) => v + (l['amount'] as int),
          ifAbsent: () => l['amount'] as int);
    }
    final done = <String, (int, int)>{};
    for (final pm in await db.all('payment')) {
      if (pm['month'] != month) continue;
      final o = done[pm['payee_id'] as String] ?? (0, 0);
      done[pm['payee_id'] as String] = (o.$1 + ((pm['deduct'] ?? 0) as int), o.$2 + ((pm['vat'] ?? 0) as int));
    }
    final out = <Payout>[];
    for (final p in rows) {
      final o = Payout(p, info[p.payeeId] ?? {'payee_type': '업체'});
      final days = daily[p.payeeId] ?? const {};
      o.workDays = days.length;
      if (o.rule == '일용') {
        var tax = days.values.fold<int>(0, (a, d) => a + dailyIncomeTax(d));
        tax = tax ~/ 10 * 10;
        if (tax < 1000) tax = 0;
        o.incomeTax = tax;
        o.localTax = tax ~/ 10 ~/ 10 * 10;
      } else if (o.rule == '부가세별도') {
        o.vat = (totals[p.payeeId] ?? 0) ~/ 10;
      }
      final dn = done[p.payeeId] ?? (0, 0);
      o.deductDone = dn.$1;
      o.vatDone = dn.$2;
      out.add(o);
    }
    const order = ['작업자', '장비', '자재·외주'];
    out.sort((a, b) {
      final g = order.indexOf(a.group) - order.indexOf(b.group);
      return g != 0 ? g : b.transfer.compareTo(a.transfer);
    });
    return out;
  }

  /// 이체 목록대로 보냈다고 기록: 보낸 돈 + 뗀 세금 − 더한 부가세 = 정산된 일지 금액.
  Future<String> recordPayout(Payout o, String month, String paidDate) async {
    if (o.transfer <= 0) throw StoreError('${o.name}: 보낼 돈이 없습니다.');
    return insert('payment', {
      'payee_id': o.payeeId, 'month': month, 'amount': o.transfer, 'deduct': o.deductLeft, 'vat': o.vatLeft,
      'paid_date': parseWorkDate(paidDate),
    });
  }

  /// 은행 이체·카톡용 목록.
  Future<String> payoutText(String month) async {
    final list = (await monthPayouts(month)).where((o) => o.transfer > 0).toList();
    final b = StringBuffer('[결제 요청] 진성건설 ${month.substring(0, 4)}년 ${int.parse(month.substring(5))}월 · 현장소장 → 사장님\n');
    final sum = list.fold<int>(0, (a, o) => a + o.transfer);
    b.writeln('${list.length}건 · 결제하실 돈 ${wonFmt(sum)}원');
    final noAcc = list.where((o) => !o.hasAccount).map((o) => o.name).toList();
    if (noAcc.isNotEmpty) b.writeln('※ 계좌 확인 필요: ${noAcc.join(', ')}');
    for (final g in ['작업자', '장비', '자재·외주']) {
      final gl = list.where((o) => o.group == g).toList();
      if (gl.isEmpty) continue;
      b.writeln();
      b.writeln('── $g ${gl.length}${g == '작업자' ? '명' : '곳'} · ${wonFmt(gl.fold<int>(0, (a, o) => a + o.transfer))}원 ──');
      for (final o in gl) {
        b.writeln('${o.name}  ${o.accountText}  ${wonFmt(o.transfer)}원');
        b.writeln('  ${o.breakdown}');
      }
    }
    final tax = list.fold<int>(0, (a, o) => a + o.deduct);
    if (tax > 0) {
      b.writeln();
      b.writeln('뗀 세금 ${wonFmt(tax)}원 (소득세 ${wonFmt(list.fold<int>(0, (a, o) => a + o.incomeTax))} · '
          '지방소득세 ${wonFmt(list.fold<int>(0, (a, o) => a + o.localTax))}) → 다음 달 10일까지 신고·납부');
    }
    b.writeln();
    b.writeln('근거: 사람별 출역표·일지 (월말보고 Excel 「이체목록」「출역표」 시트)');
    return b.toString().trimRight();
  }
}

/// 결제 요청(현장소장 → 사장님). 결제는 사장님이 하고, 앱은 올린 날·금액만 남긴다.
class PayRequest {
  PayRequest(this.row);
  final Rec row;
  String get date => (row['requested_at'] as String).substring(0, 10);
  int get amount => row['amount'] as int;
  int get count => row['payee_count'] as int;
  String get status => (row['status'] as String?) ?? '복사';
  String get result => (row['result'] as String?) ?? '';
}

extension PayRequests on Store {
  Future<PayRequest?> lastPayRequest(String month) async {
    final rows = (await db.all('pay_request')).where((r) => r['month'] == month).toList()
      ..sort((a, b) => (a['requested_at'] as String).compareTo(b['requested_at'] as String));
    return rows.isEmpty ? null : PayRequest(rows.last);
  }

  /// 결제 요청을 올렸다고 남긴다(금액·건수는 그때 값).
  Future<String> markPayRequested(String month, {String status = '복사'}) async {
    final list = (await monthPayouts(month)).where((o) => o.transfer > 0).toList();
    if (list.isEmpty) throw StoreError('결제할 돈이 없습니다.');
    return insert('pay_request', {
      'month': month, 'amount': list.fold<int>(0, (a, o) => a + o.transfer), 'payee_count': list.length,
      'requested_at': now(), 'status': status,
    });
  }

  /// 사장님이 결제를 마쳤다고 알려 오면: 남은 건 전부 지급으로 기록(세금·부가세 포함). 몇 건 기록했는지 돌려줌.
  Future<int> markAllPaid(String month, String paidDate) async {
    var n = 0;
    for (final o in await monthPayouts(month)) {
      if (o.transfer <= 0) continue;
      await recordPayout(o, month, paidDate);
      n++;
    }
    return n;
  }
}
