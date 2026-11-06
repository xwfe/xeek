// Flutter 自带的四条无障碍准则：Android 48dp、iOS 44pt 点击区域，可点的东西都有标签，文字对比度。
// 测试字体把每个字画成 1em 宽的方块，中文本来就接近 1em，所以中文排版的宽度和真机差不多，英文会偏宽。
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:forui/forui.dart';

import 'helpers.dart';

final guidelines = <String, AccessibilityGuideline>{
  'Android 点击区域': androidTapTargetGuideline,
  'iOS 点击区域': iOSTapTargetGuideline,
  '可点元素有标签': labeledTapTargetGuideline,
  '文字对比度': textContrastGuideline,
};

/// 四条全跑完再报，一次看全哪条不过、卡在哪个元素上。
Future<List<String>> evaluateAll(WidgetTester tester) async {
  final failures = <String>[];
  for (final MapEntry(key: name, value: guideline) in guidelines.entries) {
    final result = await guideline.evaluate(tester);
    if (!result.passed) failures.add('$name：${result.reason}');
  }
  return failures;
}

void main() {
  final screens = <String, Future<void> Function(WidgetTester)>{
    '列表页': (_) async {},
    '详情页': openFirstEntry,
    '设置页': (tester) async {
      await tester.tap(find.byIcon(FLucideIcons.settings));
      await tester.pumpAndSettle();
    },
  };

  // Android 把输入框标签放在提示文字里，Android 11 的 uiautomator 导出看不到，所以在这一层核对。
  testWidgets('列表页和详情页的每个输入框都有读屏标签', (tester) async {
    final handle = tester.ensureSemantics();
    await pumpApp(tester);
    final listLabels = textFieldLabels(tester);
    await openFirstEntry(tester);
    await tester.drag(find.byType(Scrollable).last, const Offset(0, -3000));
    await tester.pumpAndSettle();
    final detailLabels = [...textFieldLabels(tester)];
    handle.dispose();
    expect(listLabels, ['搜索\n标题或账号']);
    expect(detailLabels.where((l) => l.trim().isEmpty), isEmpty, reason: detailLabels.join(' | '));
  });

  for (final brightness in Brightness.values) {
    for (final size in const [Size(390, 844), Size(1024, 768)]) {
      for (final MapEntry(key: name, value: open) in screens.entries) {
        testWidgets('$name ${brightness.name} ${size.width.toInt()} 宽：点击区域、标签、对比度', (tester) async {
          final handle = tester.ensureSemantics();
          await pumpApp(tester, size: size, brightness: brightness);
          await open(tester);
          final failures = await evaluateAll(tester);
          handle.dispose();
          expect(failures, isEmpty, reason: failures.join('\n'));
        });
      }
    }
  }
}
