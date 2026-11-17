// 「진행 중」 공사 누르기 → 밀린 날 고르기 → 그 현장·그 날짜 일지가 바로 열린다 (360·412폭, 넘치면 실패)
import 'package:flutter_test/flutter_test.dart';
import 'package:jinsung_app/main.dart';
import 'package:jinsung_app/row_db.dart';
import 'package:jinsung_app/store.dart';
import 'package:material_ui/material_ui.dart';

void main() {
  for (final w in [360.0, 412.0]) {
    testWidgets('진행 중 → 밀린 날 → 일지 (${w.toInt()}폭)', (t) async {
      t.view.physicalSize = Size(w * 3, 800 * 3);
      t.view.devicePixelRatio = 3;
      addTearDown(t.view.reset);
      final s = Store(MemoryDb(), device: 'phone');
      final today = DateTime.now();
      final start = workDateOf(today.subtract(const Duration(days: 10)));
      final a = await s.receive('난간기둥보수', '공사', start);
      await s.proceed(a, plannedStart: start);
      final b = await s.receive('요성리 용배수로', '공사', start);
      await s.proceed(b, plannedStart: start);
      final miss = await s.missingLogDays(a, workDateOf(today));
      expect(miss, isNotEmpty);
      await t.pumpWidget(JinsungApp(store: s));
      await t.pumpAndSettle();
      expect(find.byType(DropdownButtonFormField<String>), findsNothing); // 현장 고르기 칸은 없어짐 (버튼 줄 하나)
      expect(find.byKey(const ValueKey('og_new')), findsOneWidget);
      expect(find.textContaining('난간기둥보수 · 밀린 ${miss.length}일'), findsOneWidget);
      await t.tap(find.byKey(const ValueKey('og_난간기둥보수')));
      await t.pumpAndSettle();
      await t.tap(find.byKey(ValueKey('cl_${miss.last}')));
      await t.pumpAndSettle();
      // 일지 탭, 그 현장, 그 날짜
      expect(find.text('오늘 일지 쓰기'), findsOneWidget);
      expect(find.text(miss.last), findsOneWidget);
      final f = find.widgetWithText(TextField, '오늘 한 일');
      await t.scrollUntilVisible(f, 300, scrollable: find.descendant(of: find.byType(LogPage), matching: find.byType(Scrollable)).first);
      await t.enterText(f, '난간 기둥 페인트 1차');
      await t.ensureVisible(find.text('내용 저장'));
      await t.pumpAndSettle();
      await t.tap(find.text('내용 저장'));
      await t.pumpAndSettle();
      expect(await s.missingLogDays(a, workDateOf(today)), isNot(contains(miss.last)));
      expect(find.textContaining('밀린 ${miss.length - 1}일').evaluate().length + (miss.length == 1 ? 1 : 0), greaterThan(0));
      // 「현장 보기」 → 홈, 홈 「일지」 칸의 날짜를 누르면 그 날 일지로
      await t.tap(find.byKey(const ValueKey('og_요성리 용배수로')));
      await t.pumpAndSettle();
      await t.tap(find.byKey(const ValueKey('cl_view')));
      await t.pumpAndSettle();
      expect(find.text('오늘 현장 보기'), findsOneWidget);
      await t.scrollUntilVisible(find.byKey(const ValueKey('home_today')), 300,
          scrollable: find.byWidgetPredicate((w) => w is Scrollable && w.axisDirection == AxisDirection.down).first);
      await t.tap(find.byKey(const ValueKey('home_today')));
      await t.pumpAndSettle();
      expect(find.text('오늘 일지 쓰기'), findsOneWidget);
      expect(find.text(workDateOf(today)), findsOneWidget);
    });
  }
}
