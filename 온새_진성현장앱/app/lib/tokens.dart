/// 디자인 토큰 (설계안 10장). 색·글자·간격은 여기 한 곳에서만 정한다.
library;

import 'package:material_ui/material_ui.dart';

class Tokens {
  const Tokens({
    required this.bg, required this.card, required this.line, required this.text,
    required this.sub, required this.blue, required this.ok, required this.warn, required this.bad,
  });
  final Color bg, card, line, text, sub, blue, ok, warn, bad;

  static const navy = Tokens(
    bg: Color(0xFF0B1626), card: Color(0xFF132238), line: Color(0xFF26384F),
    text: Color(0xFFEEF3F9), sub: Color(0xFF9DB0C7), blue: Color(0xFF4C9DFF),
    ok: Color(0xFF3ECF8E), warn: Color(0xFFF5A524), bad: Color(0xFFFF6B6B),
  );

  /// 야외 모드: 밝은 바탕, 대비 7:1 이상.
  static const outdoor = Tokens(
    bg: Color(0xFFFFFFFF), card: Color(0xFFF3F6FA), line: Color(0xFF8A9BB0),
    text: Color(0xFF0B1626), sub: Color(0xFF33475F), blue: Color(0xFF0B4FB3),
    ok: Color(0xFF0A6B3D), warn: Color(0xFF8A5200), bad: Color(0xFFB00020),
  );

  static const double radius = 12, pad = 16, gap = 12, group = 24, touch = 56;
  static const double fTitle = 22, fSub = 18, fBody = 16, fNote = 14;

  ThemeData theme() {
    final dark = bg.computeLuminance() < 0.5;
    final scheme = ColorScheme.fromSeed(
      seedColor: blue, brightness: dark ? Brightness.dark : Brightness.light,
    ).copyWith(primary: blue, surface: bg, onSurface: text, error: bad);
    final border = OutlineInputBorder(
        borderRadius: BorderRadius.circular(radius), borderSide: BorderSide(color: line));
    return ThemeData(
      useMaterial3: true,
      fontFamily: 'Pretendard',
      colorScheme: scheme,
      scaffoldBackgroundColor: bg,
      textTheme: TextTheme(
        titleLarge: TextStyle(fontSize: fTitle, fontWeight: FontWeight.w700, color: text),
        titleMedium: TextStyle(fontSize: fSub, fontWeight: FontWeight.w700, color: text),
        bodyLarge: TextStyle(fontSize: fBody, height: 1.5, color: text),
        bodyMedium: TextStyle(fontSize: fBody, height: 1.5, color: text),
        bodySmall: TextStyle(fontSize: fNote, height: 1.5, color: sub),
        labelLarge: const TextStyle(fontSize: fBody, fontWeight: FontWeight.w700),
      ),
      appBarTheme: AppBarTheme(backgroundColor: bg, foregroundColor: text, elevation: 0,
          titleTextStyle: TextStyle(fontSize: fTitle, fontWeight: FontWeight.w700, color: text)),
      cardTheme: CardThemeData(
        color: card, elevation: 0, margin: EdgeInsets.zero,
        shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(radius), side: BorderSide(color: line)),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true, fillColor: bg, border: border, enabledBorder: border,
        labelStyle: TextStyle(color: sub, fontSize: fNote),
        contentPadding: const EdgeInsets.symmetric(horizontal: pad, vertical: 16),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: blue, foregroundColor: Colors.white,
          minimumSize: const Size.fromHeight(touch),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(radius)),
          textStyle: const TextStyle(fontSize: fBody, fontWeight: FontWeight.w700),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: text, side: BorderSide(color: line),
          minimumSize: const Size.fromHeight(touch),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(radius)),
        ),
      ),
      navigationBarTheme: NavigationBarThemeData(
        backgroundColor: card, indicatorColor: blue.withValues(alpha: 0.2), height: 72,
        labelTextStyle: WidgetStatePropertyAll(TextStyle(fontSize: fNote, color: text)),
      ),
      dividerTheme: DividerThemeData(color: line, thickness: 1),
    );
  }
}

String wonText(num n) {
  final s = n.round().abs().toString();
  final b = StringBuffer(n < 0 ? '-' : '');
  for (var i = 0; i < s.length; i++) {
    if (i > 0 && (s.length - i) % 3 == 0) b.write(',');
    b.write(s[i]);
  }
  return b.toString();
}
