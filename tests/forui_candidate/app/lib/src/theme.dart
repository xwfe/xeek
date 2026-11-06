import 'package:flutter/painting.dart';
import 'package:flutter/services.dart';
import 'package:forui/forui.dart';

/// 原型 `adr/design/zh-CN/styles.css` 的颜色变量，改这里就是改整套界面的颜色。
///
/// 原型另有 --side、--soft、--purple、--warning，forui 没有对应的语义色，真用到时再加主题扩展。
/// 原型没有危险色，[danger] 先取一个在两种底色上都够对比度的值。
final class KeexPalette {
  const KeexPalette({
    required this.bg,
    required this.surface,
    required this.raised,
    required this.text,
    required this.muted,
    required this.line,
    required this.accent,
    required this.accentText,
    required this.danger,
    required this.dangerText,
  });

  final Color bg, surface, raised, text, muted, line, accent, accentText, danger, dangerText;

  static const dark = KeexPalette(
    bg: Color(0xFF0F131C),
    surface: Color(0xFF181E29),
    raised: Color(0xFF202835),
    text: Color(0xFFE6EAF2),
    muted: Color(0xFFA0ACBD),
    line: Color(0xFF2B3544),
    accent: Color(0xFF4EDEA3),
    accentText: Color(0xFF06291B),
    danger: Color(0xFFFF8A80),
    dangerText: Color(0xFF3B0907),
  );

  static const light = KeexPalette(
    bg: Color(0xFFF5F7F9),
    surface: Color(0xFFFFFFFF),
    raised: Color(0xFFEDF1F5),
    text: Color(0xFF1B2838),
    muted: Color(0xFF566577),
    line: Color(0xFFDCE3E9),
    accent: Color(0xFF096B48),
    accentText: Color(0xFFFFFFFF),
    danger: Color(0xFFB3261E),
    dangerText: Color(0xFFFFFFFF),
  );
}

/// 平台默认字体的名字。forui 默认用它自带的 Inter，原型要求中文走系统字体。
///
/// 中文字形由系统回退补上（Android 是 Noto Sans CJK，iOS 是苹方），回退时按应用语言选简体字形。
String systemFontFamily(TargetPlatform platform) => switch (platform) {
  TargetPlatform.iOS || TargetPlatform.macOS => 'CupertinoSystemText',
  _ => 'Roboto',
};

/// forui 触屏主题的页头按钮、侧栏项都是 44 高，达不到 Android 的 48dp（adr/design/README.md §4）。
/// 各补 2 的内边距到 48。图标按钮直接用 forui 的 lg 尺寸，它就是 48×48。
const keexHeaderActionStyle = FHeaderActionStyleDelta.delta(padding: EdgeInsetsGeometryDelta.add(EdgeInsets.all(2)));
const keexSidebarItemStyle = FSidebarItemStyleDelta.delta(
  padding: EdgeInsetsGeometryDelta.add(EdgeInsets.symmetric(vertical: 2)),
);

FThemeData keexTheme(Brightness brightness, TargetPlatform platform) {
  final p = brightness == Brightness.dark ? KeexPalette.dark : KeexPalette.light;
  final colors = FColors(
    brightness: brightness,
    systemOverlayStyle: brightness == Brightness.dark ? SystemUiOverlayStyle.light : SystemUiOverlayStyle.dark,
    barrier: const Color(0x99000000),
    background: p.bg,
    foreground: p.text,
    primary: p.accent,
    primaryForeground: p.accentText,
    secondary: p.raised,
    secondaryForeground: p.text,
    muted: p.raised,
    mutedForeground: p.muted,
    destructive: p.danger,
    destructiveForeground: p.dangerText,
    error: p.danger,
    errorForeground: p.dangerText,
    card: p.surface,
    border: p.line,
  );
  final typeface = FTypeface.inherit(colors: colors, touch: true, fontFamily: systemFontFamily(platform));
  return FThemeData(
    colors: colors,
    touch: true,
    typography: FTypography(display: typeface, body: typeface),
  );
}
