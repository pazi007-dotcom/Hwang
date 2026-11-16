// 「어제와 같이」 고르는 화면과 하루 겹침 경고를 화면에서 직접 누른다 (접은 폴드 폭 360).
import 'package:flutter_test/flutter_test.dart';
import 'package:jinsung_app/ledger.dart';
import 'package:jinsung_app/main.dart';
import 'package:jinsung_app/row_db.dart';
import 'package:jinsung_app/store.dart';
import 'package:material_ui/material_ui.dart';

void main() {
  testWidgets('어제와 같이: 자재·가끔 쓴 장비는 꺼져 있고, 고른 것만 복사 / 하루 겹침 경고', (t) async {
    t.view.physicalSize = const Size(360, 740) * 2.625;
    t.view.devicePixelRatio = 2.625;
    addTearDown(t.view.reset);
    final store = Store(MemoryDb(), device: 'phone');
    final today = workDateOf(DateTime.now());
    final d1 = workDateOf(DateTime.now().subtract(const Duration(days: 2)));
    final d2 = workDateOf(DateTime.now().subtract(const Duration(days: 1)));
    final ys = await store.receive('요성리', '입찰', d1);
    final em = await store.receive('긴급 A', '긴급', d1);
    for (final d in [d1, d2]) {
      await store.addLine(siteId: ys, workDate: d, kind: '인력', item: '보통인부', qty: 1, unit: '인', unitPrice: 187000, payee: '김반장');
      await store.addLine(siteId: ys, workDate: d, kind: '장비', item: '6W', qty: 1, unit: '일', unitPrice: 680000, payee: '대성중기');
    }
    await store.addLine(siteId: ys, workDate: d2, kind: '장비', item: '펌프카', qty: 1, unit: '일', unitPrice: 750000, payee: '문경펌프');
    await store.addLine(siteId: ys, workDate: d2, kind: '자재', item: '레미콘', qty: 6, unit: '㎥', unitPrice: 98000, payee: '가은레미콘');
    expect((await store.mustGet('site', em))['status'], '접수'); // 긴급 A는 아직 투입 없음

    await t.pumpWidget(JinsungApp(store: store));
    await t.pumpAndSettle();
    // 현장: 요성리로
    await t.tap(find.byType(DropdownButtonFormField<String>).first);
    await t.pumpAndSettle();
    await t.tap(find.textContaining('요성리').last);
    await t.pumpAndSettle();
    await t.tap(find.text('일지'));
    await t.pumpAndSettle();
    await t.tap(find.text('어제와 같이'));
    await t.pumpAndSettle();
    expect(find.text('$d2 → $today 복사'), findsOneWidget);
    bool checked(int i) => (t.widget(find.byKey(ValueKey('copy_$i'))) as CheckboxListTile).value!;
    expect([checked(0), checked(1), checked(2), checked(3)], [true, true, false, false]); // 인부·6W 켬, 펌프카·레미콘 끔
    await t.tap(find.text('고른 줄 복사'));
    await t.pumpAndSettle();
    expect((await store.linesOf(ys, today)).map((l) => l['item']), ['보통인부', '6W']);

    // 같은 날 긴급 A로 옮겨 김반장 1공수 → 겹침 경고가 떠야 한다
    await t.tap(find.byType(DropdownButtonFormField<String>).first);
    await t.pumpAndSettle();
    await t.tap(find.textContaining('긴급 A').last);
    await t.pumpAndSettle();
    await t.pump(const Duration(seconds: 3)); // 복사 알림이 사라질 때까지
    await t.pumpAndSettle();
    await t.enterText(find.byKey(const ValueKey('f_item')), '보통인부');
    await t.enterText(find.byKey(const ValueKey('f_payee')), '김반장');
    await t.enterText(find.byKey(const ValueKey('f_price')), '187000');
    await t.pumpAndSettle();
    await t.scrollUntilVisible(find.byKey(const ValueKey('f_save')), 200, scrollable: find.byType(Scrollable).first);
    await t.ensureVisible(find.byKey(const ValueKey('f_save')));
    await t.pumpAndSettle();
    await t.tap(find.byKey(const ValueKey('f_save')));
    await t.pumpAndSettle();
    expect(find.text('하루 겹침 확인'), findsOneWidget);
    expect(find.textContaining('하루 2공수'), findsOneWidget);
    await t.tap(find.text('고치기')); // 저장하지 않고 돌아감
    await t.pumpAndSettle();
    expect(await store.linesOf(em, today), isEmpty);
    await t.enterText(find.byKey(const ValueKey('f_qty')), '0.5');
    await t.pumpAndSettle();
    await t.ensureVisible(find.byKey(const ValueKey('f_save')));
    await t.pumpAndSettle();
    await t.tap(find.byKey(const ValueKey('f_save')));
    await t.pumpAndSettle();
    expect(find.text('하루 겹침 확인'), findsOneWidget); // 1 + 0.5 도 경고
    await t.tap(find.text('그대로 저장'));
    await t.pumpAndSettle();
    expect((await store.linesOf(em, today)).single['qty'], '0.5');
    expect((await store.mustGet('site', em))['status'], '진행'); // 투입이 들어가면 진행으로
  });
}
