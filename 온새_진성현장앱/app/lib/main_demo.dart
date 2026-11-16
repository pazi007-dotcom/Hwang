// 화면 확인용(브라우저): 폰 저장소 대신 메모리에 예시 자료를 넣고 같은 화면을 띄운다.
// 업체·단가는 모두 예시다.
import 'package:material_ui/material_ui.dart';

import 'ledger.dart';
import 'main.dart';
import 'row_db.dart';
import 'store.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final store = Store(MemoryDb(), device: 'demo');
  final big = await store.receive('요성리 용배수로 개체공사', '입찰', '2026-11-01', instructions: '개거 1.0×1.0 L=250m');
  await store.proceed(big, plannedStart: '2026-11-10');
  final e = await store.receive('점촌 배수로 긴급복구', '긴급', '2026-11-16', instructions: '토사 유입 구간 약 30m 준설',
      contactName: '담당 주무관', contactPhone: '054-000-0000');
  for (final d in ['2026-11-10', '2026-11-11', '2026-11-12', '2026-11-13', '2026-11-14']) {
    await store.addLine(siteId: big, workDate: d, kind: '인력', item: '형틀목공', qty: 2, unit: '인', unitPrice: 230000, payee: '박목수 팀');
    await store.addLine(siteId: big, workDate: d, kind: '인력', item: '보통인부', qty: 3, unit: '인', unitPrice: 187000, payee: '김반장');
    await store.addLine(siteId: big, workDate: d, kind: '장비', item: '6W', qty: 1, unit: '일', unitPrice: 680000, payee: '대성중기');
  }
  await store.addLine(siteId: big, workDate: '2026-11-12', kind: '자재', item: '레미콘', spec: '25-21-08', qty: '5.5', unit: '㎥', unitPrice: 98000, payee: '가은레미콘');
  await store.addLine(siteId: big, workDate: '2026-11-14', kind: '자재', item: '레미콘', spec: '25-21-08', qty: '6.5', unit: '㎥', unitPrice: 98000, payee: '가은레미콘');
  await store.addLine(siteId: big, workDate: '2026-11-16', kind: '인력', item: '보통인부', qty: '0.5', unit: '인', unitPrice: 187000, payee: '김반장');
  await store.addLine(siteId: e, workDate: '2026-11-16', kind: '인력', item: '보통인부', qty: '0.5', unit: '인', unitPrice: 187000, payee: '김반장');
  await store.addLine(siteId: e, workDate: '2026-11-16', kind: '장비', item: '6W', qty: '0.5', unit: '일', unitPrice: 680000, payee: '대성중기');
  await store.addLine(siteId: e, workDate: '2026-11-16', kind: '장비', item: '덤프 25톤', qty: 3, unit: '대', unitPrice: 282000, payee: '한빛운수(주) 문경영업소', note: '토사 반출');
  await store.recordPayment((await store.db.all('payee')).firstWhere((p) => p['name'] == '대성중기')['id'] as String, '2026-11', 2000000, '2026-11-15');
  runApp(JinsungApp(store: store));
}
