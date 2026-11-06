import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart';
// forui 建在从 SDK 拆出来的 material_ui 上。这里也必须用它：
// 混用 package:flutter/material.dart 会出现两套互不相认的 Theme 和本地化。
import 'package:material_ui/material_ui.dart' show MaterialApp, ThemeMode;

import 'shell.dart';
import 'theme.dart';

class KeexForuiApp extends StatelessWidget {
  const KeexForuiApp({super.key, this.brightness});

  /// 测试用来固定深浅色；为空时跟随系统。
  final Brightness? brightness;

  @override
  Widget build(BuildContext context) {
    final platform = defaultTargetPlatform;
    return MaterialApp(
      title: 'keex forui 预实验',
      debugShowCheckedModeBanner: false,
      locale: const Locale('zh', 'CN'),
      supportedLocales: const [Locale('zh', 'CN')],
      localizationsDelegates: FLocalizations.localizationsDelegates,
      theme: keexTheme(Brightness.light, platform).toApproximateMaterialTheme(),
      darkTheme: keexTheme(Brightness.dark, platform).toApproximateMaterialTheme(),
      themeMode: switch (brightness) {
        null => ThemeMode.system,
        Brightness.dark => ThemeMode.dark,
        Brightness.light => ThemeMode.light,
      },
      builder: (context, child) => FTheme(
        data: keexTheme(brightness ?? MediaQuery.platformBrightnessOf(context), platform),
        child: FToaster(child: child!),
      ),
      home: const KeexShell(),
    );
  }
}
