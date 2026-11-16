// 화면 확인용(브라우저): 새 폰처럼 아무 자료도 없는 상태로 같은 앱을 띄운다.
import 'package:material_ui/material_ui.dart';

import 'main.dart';
import 'row_db.dart';
import 'store.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(JinsungApp(store: Store(MemoryDb(), device: 'blank')));
}
