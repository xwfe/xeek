// K057 要求核心路径在 200% 字号下可用。这里看布局有没有溢出；能不能看清另在模拟器截图里看。
import 'package:flutter/rendering.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:forui/forui.dart';

import 'helpers.dart';

bool truncated(WidgetTester tester, String text) =>
    tester.renderObject<RenderParagraph>(find.text(text)).didExceedMaxLines;

void main() {
  testWidgets('200% 字号、320 宽：forui 默认把列表项文字截成一行（变了要重新评估）', (tester) async {
    await pumpApp(tester, size: const Size(320, 800), textScale: 2);
    final navigator = tester.state<NavigatorState>(find.byType(Navigator).first);
    navigator.push(
      PageRouteBuilder<void>(
        pageBuilder: (_, _, _) => FScaffold(
          child: ListView(
            children: [
              FTile(title: const Text('对照：很长的条目标题'), subtitle: const Text('登录 · user00000@example.com')),
            ],
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(truncated(tester, '登录 · user00000@example.com'), isTrue);
  });

  testWidgets('200% 字号、320 宽：keex 的列表行换行，不截断', (tester) async {
    await pumpApp(tester, size: const Size(320, 800), textScale: 2);
    expect(truncated(tester, '登录 · user00000@example.com'), isFalse);
    expect(truncated(tester, '示例银行 00000'), isFalse);
  });

  for (final width in const [320.0, 390.0, 768.0, 1024.0]) {
    testWidgets('200% 字号、$width 宽：列表、详情、设置都不溢出', (tester) async {
      final errors = await collectFlutterErrors(() async {
        await pumpApp(tester, size: Size(width, width < 720 ? 800 : 768), textScale: 2);
        await openFirstEntry(tester);
        // 详情页是懒加载列表，滚到底让每个字段都布局一遍。
        await tester.drag(find.byType(Scrollable).last, const Offset(0, -3000));
        await tester.pumpAndSettle();
        tester.state<NavigatorState>(find.byType(Navigator).first).pop();
        await tester.pumpAndSettle();
        await tester.tap(find.byIcon(FLucideIcons.settings));
        await tester.pumpAndSettle();
      });
      expect(errors, isEmpty, reason: errors.join('\n'));
    });
  }
}
