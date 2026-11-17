// 화면 확인용(브라우저): 새 폰처럼 아무 자료도 없는 상태로 같은 앱을 띄운다.
import 'package:material_ui/material_ui.dart';

import 'main.dart';
import 'row_db.dart';
import 'store.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  // 실제 앱처럼 기기마다 다른 이름 (같은 이름이면 집 PC가 '내 기록'으로 보고 내려 주지 않는다)
  runApp(JinsungApp(store: Store(MemoryDb(), device: 'web-${DateTime.now().microsecondsSinceEpoch.toRadixString(36)}')));
}
