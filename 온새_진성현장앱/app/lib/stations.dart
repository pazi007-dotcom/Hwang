/// 측점 = 모든 기록의 주소. 누가거리(m)로 저장하고 'No.2+10' 으로 보여 준다.
library;

import 'store.dart';

final _sta = RegExp(r'^\s*(?:no|넘버|측점)?\s*\.?\s*(\d+)\s*(?:\+\s*(\d+(?:\.\d+)?))?\s*$', caseSensitive: false);

double parseSta(String text, {double interval = 20, int labelShift = 0}) {
  final s = text.trim();
  if (s.toLowerCase().endsWith('m')) return double.parse(s.substring(0, s.length - 1));
  final m = _sta.firstMatch(s);
  if (m == null) throw StoreError('측점 형식이 아닙니다: $text (예: No.2+10)');
  final no = int.parse(m.group(1)!) + labelShift;
  final plus = double.parse(m.group(2) ?? '0');
  if (no < 0) throw StoreError('측점 치환 후 음수가 됩니다: $text');
  if (plus >= interval) throw StoreError('+값이 측점 간격(${interval.toStringAsFixed(0)}m) 이상입니다: $text');
  return no * interval + plus;
}

String formatSta(num meters, {double interval = 20}) {
  final no = (meters / interval).floor();
  final plus = meters - no * interval;
  if (plus.abs() < 1e-9) return 'No.$no';
  var t = plus.toStringAsFixed(1);
  if (t.endsWith('.0')) t = t.substring(0, t.length - 2);
  return 'No.$no+$t';
}

String staText(num m) => m == m.roundToDouble() ? m.toInt().toString() : m.toString();
