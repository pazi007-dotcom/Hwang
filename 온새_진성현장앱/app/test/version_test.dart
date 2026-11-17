// 화면에 보이는 앱 버전 = pubspec.yaml 버전 (어긋나면 폰에 뭐가 깔렸는지 헷갈린다)
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:jinsung_app/main.dart';
import 'package:jinsung_app/row_db.dart';
import 'package:jinsung_app/store.dart';

void main() {
  test('pubspec 버전과 화면 버전이 같다', () {
    final v = RegExp(r'^version: ([\d.]+)\+', multiLine: true).firstMatch(File('pubspec.yaml').readAsStringSync())!.group(1);
    expect(appVersion, v);
  });

  testWidgets('동기화 탭에 앱 버전이 보인다', (t) async {
    await t.pumpWidget(JinsungApp(store: Store(MemoryDb(), device: 'phone')));
    await t.pumpAndSettle();
    await t.tap(find.text('동기화'));
    await t.pumpAndSettle();
    await t.scrollUntilVisible(find.byKey(const ValueKey('app_version')), 200, scrollable: find.byType(Scrollable).first);
    expect(find.text('진성현장 앱 $appVersion'), findsOneWidget);
  });
}
