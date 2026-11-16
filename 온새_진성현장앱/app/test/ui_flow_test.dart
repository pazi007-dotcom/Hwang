// 사람이 누르는 순서 그대로 화면을 조작하는 시험 (기준 정보가 하나도 없는 새 폰에서 시작).
// 화면이 넘치면(RenderFlex overflow) 시험이 실패한다 → 화면 잘림 검사를 겸한다.
import 'package:flutter_test/flutter_test.dart';
import 'package:jinsung_app/device.dart';
import 'package:jinsung_app/ledger.dart';
import 'package:jinsung_app/main.dart';
import 'package:jinsung_app/payout.dart';
import 'package:jinsung_app/row_db.dart';
import 'package:jinsung_app/store.dart';
import 'package:material_ui/material_ui.dart';

Future<void> scrollTo(WidgetTester t, Finder f) async {
  await t.scrollUntilVisible(f, 200, scrollable: find.byType(Scrollable).first, maxScrolls: 80);
  await t.pumpAndSettle();
}

Future<void> tapText(WidgetTester t, String text) async {
  if (find.text(text).evaluate().isEmpty) {
    // 화면 밖이면 아래로, 없으면 위로 찾아 간다
    try {
      await t.scrollUntilVisible(find.text(text), 200, scrollable: find.byType(Scrollable).first, maxScrolls: 40);
    } catch (_) {
      await t.scrollUntilVisible(find.text(text), -200, scrollable: find.byType(Scrollable).first, maxScrolls: 80);
    }
    await t.pumpAndSettle();
  }
  final f = find.text(text).last;
  await t.ensureVisible(f);
  await t.pumpAndSettle();
  await t.tap(f);
  await t.pumpAndSettle();
}

Future<void> field(WidgetTester t, String key, String value) async {
  final f = find.byKey(ValueKey(key));
  await scrollTo(t, f);
  await t.enterText(f, value);
  await t.pumpAndSettle();
}

Future<void> receive(WidgetTester t, String name, {String? type, bool full = false}) async {
  await t.tap(find.text('+ 접수'));
  await t.pumpAndSettle();
  if (type != null) {
    await t.tap(find.byKey(ValueKey('jt_$type')));
    await t.pumpAndSettle();
  }
  await t.enterText(find.byKey(const ValueKey('rc_name')), name);
  if (full) {
    // 위치: 주소 + 지금 위치, 연락처: 폰에서 고르기, 체크리스트 하나 체크
    DeviceKit.here = () async => (lat: 36.72381, lon: 128.11654);
    DeviceKit.pickContact = () async => (name: '문경시 건설과 박주무관', phone: '054-550-6000');
    await t.enterText(find.byKey(const ValueKey('rc_addr')), '점촌동 123-4 앞 도로');
    await t.tap(find.byKey(const ValueKey('rc_here')));
    await t.pumpAndSettle();
    expect(find.textContaining('좌표 저장: 36.72381'), findsOneWidget);
    await t.tap(find.byKey(const ValueKey('rc_contact')));
    await t.pumpAndSettle();
    expect(find.text('054-550-6000'), findsOneWidget);
    final ck = find.byKey(const ValueKey('ck_현장 위치·진입로 확인'));
    await t.ensureVisible(ck);
    await t.pumpAndSettle();
    await t.tap(ck);
    await t.pumpAndSettle();
  }
  final ok = find.byKey(const ValueKey('rc_ok'));
  await t.ensureVisible(ok);
  await t.pumpAndSettle();
  await t.tap(ok);
  await t.pumpAndSettle();
}

Future<void> addLine(WidgetTester t, String item, String payee, String qty, String? price) async {
  await field(t, 'f_item', item);
  await field(t, 'f_payee', payee);
  await t.testTextInput.receiveAction(TextInputAction.done); // 받는 곳 입력 끝 → 단가 추천
  await t.pumpAndSettle();
  await field(t, 'f_qty', qty);
  if (price != null) await field(t, 'f_price', price);
  final save = find.byKey(const ValueKey('f_save'));
  await scrollTo(t, save);
  await t.tap(save);
  await t.pumpAndSettle();
  await t.pump(const Duration(seconds: 5)); // 저장 알림 닫힘
  await t.pumpAndSettle();
}

void main() {
  for (final size in const [Size(360, 740), Size(412, 915), Size(840, 900)]) {
    testWidgets('빈 폰에서 접수 → 일지 → 고치기 → 결제 집계 (${size.width.toInt()}폭)', (t) async {
      t.view.physicalSize = size * 2.625;
      t.view.devicePixelRatio = 2.625;
      addTearDown(t.view.reset);
      final store = Store(MemoryDb(), device: 'phone');
      await t.pumpWidget(JinsungApp(store: store));
      await t.pumpAndSettle();
      expect(find.textContaining('「+ 접수」'), findsWidgets);

      // 1) 공사 건 두 개 접수 (큰 공사 + 긴급)
      await receive(t, '요성리 용배수로');
      await receive(t, '점촌 긴급복구', type: '긴급', full: true);
      final sites = await store.db.all('site');
      expect(sites.length, 2);
      final em = sites.firstWhere((x) => x['name'] == '점촌 긴급복구');
      expect([em['job_type'], em['address'], em['gps_lat']], ['긴급', '점촌동 123-4 앞 도로', 36.72381]);
      expect((await store.db.all('contact')).single['phone'], '054-550-6000');
      final tasks = (await store.db.all('site_task')).where((x) => x['site_id'] == em['id']).toList();
      expect(tasks.length, 4);
      expect([for (final x in tasks) if (x['done'] == 1) x['title']], ['현장 위치·진입로 확인']);

      // 2) 일지 탭: 현재 현장은 방금 접수한 '점촌 긴급복구'
      await t.tap(find.text('일지'));
      await t.pumpAndSettle();
      await addLine(t, '보통인부', '김반장', '0.5', '187000');
      // 같은 직종으로 다른 사람: 항목·단가가 남아 있으므로 이름과 수량만
      await addLine(t, '보통인부', '이씨', '1', null);
      await tapText(t, '장비');
      await addLine(t, '6W', '대성중기', '0.5', '680000');
      expect((await store.db.all('input_line')).length, 3);
      await scrollTo(t, find.textContaining('투입 3줄'));

      // 3) 현장을 요성리로 바꿔 같은 날 오후 작업 입력 — 단가는 추천으로 채워진다
      await t.tap(find.byType(DropdownButtonFormField<String>).first);
      await t.pumpAndSettle();
      await t.tap(find.textContaining('요성리 용배수로').last);
      await t.pumpAndSettle();
      await t.tap(find.text('일지'));
      await t.pumpAndSettle();
      await addLine(t, '보통인부', '김반장', '0.5', null);
      await tapText(t, '장비');
      await addLine(t, '6W', '대성중기', '0.5', null);
      await tapText(t, '자재');
      await field(t, 'f_item', '레미콘');
      await scrollTo(t, find.widgetWithText(TextField, '규격 (25-21-08 등, 선택)'));
      await t.enterText(find.widgetWithText(TextField, '규격 (25-21-08 등, 선택)'), '25-21-08');
      await addLine(t, '레미콘', '가은레미콘', '6', '98000');

      final lines = await store.db.all('input_line');
      expect(lines.length, 6);
      final amounts = {for (final l in lines) '${l['item']}/${l['qty']}/${l['amount']}'};
      expect(amounts, containsAll(['보통인부/0.5/93500', '보통인부/1/187000', '6W/0.5/340000', '레미콘/6/588000']));

      // 4) 줄을 눌러 고치기: 레미콘 6 → 6.5
      final remicon = find.textContaining('레미콘 25-21-08 6㎥');
      await scrollTo(t, remicon);
      await t.tap(remicon);
      await t.pumpAndSettle();
      await t.enterText(find.byKey(const ValueKey('e_qty')), '6.5');
      await t.tap(find.byKey(const ValueKey('e_save')));
      await t.pumpAndSettle();
      expect((await store.db.all('input_line')).any((l) => l['qty'] == '6.5' && l['amount'] == 637000), isTrue);

      // 5) 결제 탭: 누구에게 얼마
      await t.tap(find.text('결제 요청'));
      await t.pumpAndSettle();
      final month = workDateOf(DateTime.now()).substring(0, 7);
      final pay = {for (final p in await store.monthPayments(month)) p.name: p};
      expect(pay['대성중기']!.total, 680000);
      expect(pay['대성중기']!.bySite, {'점촌 긴급복구': 340000, '요성리 용배수로': 340000});
      expect(pay['김반장']!.total, 187000);
      expect(pay['김반장']!.manDays, 1);
      await scrollTo(t, find.text('작업자 2명 · 374,000원')); // 김반장·이씨 따로. 하루 소득세 999원 → 1,000원 미만이라 안 뗌
      expect(find.text('김반장'), findsOneWidget);
      await scrollTo(t, find.byKey(const ValueKey('po_대성중기')));
      expect(find.text('대성중기'), findsOneWidget);
      expect(find.text('680,000원'), findsWidgets);
      final sitesTotal = {for (final s in await store.monthSites(month)) s.name: s};
      expect(sitesTotal['요성리 용배수로']!.total, 93500 + 340000 + 637000);
      expect(sitesTotal['요성리 용배수로']!.materials, {'레미콘 25-21-08|㎥': 6.5});

      // 6) 대표님께 보고 메일 보내기 (집 PC 주소가 없으면 요청만 남고, 맞추면 집 PC가 보낸다)
      await t.pump(const Duration(seconds: 3)); // 앞 알림이 사라질 때까지
      await t.drag(find.byType(Scrollable).first, const Offset(0, 5000)); // 맨 위로
      await t.pumpAndSettle();
      await t.tap(find.byKey(const ValueKey('send_mail')));
      await t.pumpAndSettle();
      expect(find.textContaining('결제 요청 1,691,000원'), findsOneWidget);
      await t.tap(find.widgetWithText(FilledButton, '보내기'));
      await t.pumpAndSettle();
      final req = (await store.lastPayRequest(month))!;
      expect([req.amount, req.status], [1691000, '보낼 요청']);
      expect(find.textContaining('보낼 준비'), findsOneWidget);
      await t.pump(const Duration(seconds: 3)); // 복사 알림이 사라질 때까지
      await t.ensureVisible(find.byKey(const ValueKey('all_paid')));
      await t.pumpAndSettle();
      await t.tap(find.byKey(const ValueKey('all_paid')));
      await t.pumpAndSettle();
      await t.tap(find.widgetWithText(FilledButton, '결제 끝남'));
      await t.pumpAndSettle();
      final after = {for (final p in await store.monthPayments(month)) p.name: p};
      expect(after['대성중기']!.paid, 680000);
      expect([for (final p in after.values) p.balance].every((b) => b == 0), isTrue); // 전부 지급 완료
      expect((await store.monthPayouts(month)).every((o) => o.transfer == 0), isTrue);
    });
  }
}
