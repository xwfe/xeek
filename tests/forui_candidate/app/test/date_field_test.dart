// 日期框和读屏：forui 原样的日期框没有读屏能用的点击动作，keex 包一层后补上。
import 'package:flutter/rendering.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:forui/forui.dart';
import 'package:keex_forui_candidate/src/date_field.dart';
import 'package:keex_forui_candidate/src/theme.dart';
import 'package:material_ui/material_ui.dart' show MaterialApp;

import 'helpers.dart';

void main() {
  testWidgets('forui 原样的日期框：读屏只能聚焦，不能点开（变了要重新评估）', (tester) async {
    final handle = tester.ensureSemantics();
    await tester.pumpWidget(
      MaterialApp(
        locale: const Locale('zh', 'CN'),
        supportedLocales: const [Locale('zh', 'CN')],
        localizationsDelegates: FLocalizations.localizationsDelegates,
        home: FTheme(
          data: keexTheme(Brightness.dark, TargetPlatform.android),
          child: FScaffold(child: FDateField.calendar(label: const Text('对照日期'))),
        ),
      ),
    );
    final data = tester.getSemantics(find.byType(EditableText)).getSemanticsData();
    expect(data.label, contains('对照日期'));
    expect(data.hasAction(SemanticsAction.tap), isFalse);
    expect(data.hasAction(SemanticsAction.focus), isTrue);
    handle.dispose();
  });

  testWidgets('keex 日期框：读屏点一下就打开日历，标签还在同一个节点上', (tester) async {
    final handle = tester.ensureSemantics();
    await pumpApp(tester);
    await openFirstEntry(tester);
    await tester.ensureVisible(find.byType(KeexDateField));
    await tester.pumpAndSettle();
    final node = tester.getSemantics(find.byType(KeexDateField));
    final data = node.getSemanticsData();
    expect(data.label, contains('到期日'));
    expect(data.hasAction(SemanticsAction.tap), isTrue);
    expect(find.byType(FCalendar), findsNothing);

    node.owner!.performAction(node.id, SemanticsAction.tap);
    await tester.pumpAndSettle();
    expect(find.byType(FCalendar), findsOneWidget);
    // 日历里的日子要各自是读屏节点，不能被并进日期框那一个节点。
    expect(tester.getSemantics(find.byType(KeexDateField)).getSemanticsData().label, isNot(contains('15')));
    handle.dispose();
  });
}
